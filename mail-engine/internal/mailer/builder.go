package mailer

import (
	"fmt"
	"mime"
	"mime/quotedprintable"
	"net/mail"
	"strings"
	"time"
)

// Message is the input to BuildAndSign.
type Message struct {
	From         string // "Name <addr@domain>" or "addr@domain"
	To           string
	Subject      string
	HTMLBody     string
	TextBody     string
	ReplyTo      string
	MessageID    string // without angle brackets; built if empty
	Domain       string // sending domain (for Message-ID + DKIM d=)
	ExtraHeaders map[string]string // e.g. List-Unsubscribe, List-Unsubscribe-Post
}

// sanitizeHeaderValue strips CR/LF so a hostile field value (a Subject or display
// name carrying "\r\nBcc: ...") cannot inject extra headers (RFC 5322 header-
// injection guard, plan §1). Applied to every header value before sign+write, so
// the signed value equals the written value.
func sanitizeHeaderValue(s string) string {
	return strings.NewReplacer("\r", "", "\n", "").Replace(s)
}

// encodeAddress RFC-2047-encodes a non-ASCII display name while leaving the addr
// spec untouched. ASCII names pass through unchanged (QEncoding is a no-op on them).
func encodeAddress(s string) string {
	addr, err := mail.ParseAddress(s)
	if err != nil {
		return s // unparseable → leave as-is; sanitize still runs on it
	}
	if addr.Name == "" {
		return addr.Address
	}
	return mime.QEncoding.Encode("utf-8", addr.Name) + " <" + addr.Address + ">"
}

// orderedHeaders builds the header list in the order they appear in the message,
// which is also (for the signable subset) the DKIM h= order. Non-ASCII Subject /
// display names are RFC-2047-encoded; every value is CR/LF-sanitized.
func (m *Message) orderedHeaders() []header {
	hs := []header{
		{"From", encodeAddress(m.From)},
		{"To", encodeAddress(m.To)},
		{"Subject", mime.QEncoding.Encode("utf-8", m.Subject)},
		{"Date", time.Now().UTC().Format(time.RFC1123Z)},
		{"Message-ID", "<" + m.MessageID + ">"},
		{"MIME-Version", "1.0"},
	}
	if m.ReplyTo != "" {
		hs = append(hs, header{"Reply-To", encodeAddress(m.ReplyTo)})
	}
	// Custom headers (List-Unsubscribe etc.) — deterministic order.
	for _, k := range []string{"List-Unsubscribe", "List-Unsubscribe-Post"} {
		if v, ok := m.ExtraHeaders[k]; ok && v != "" {
			hs = append(hs, header{k, v})
		}
	}
	for k, v := range m.ExtraHeaders {
		if k == "List-Unsubscribe" || k == "List-Unsubscribe-Post" {
			continue
		}
		hs = append(hs, header{k, v})
	}
	for i := range hs {
		hs[i].Value = sanitizeHeaderValue(hs[i].Value)
	}
	return hs
}

// SignableHeaderKeys are the headers we put in the DKIM h= tag (when present).
var SignableHeaderKeys = []string{
	"From", "To", "Subject", "Date", "Message-ID", "Reply-To",
	"MIME-Version", "List-Unsubscribe", "List-Unsubscribe-Post",
}

// BuildAndSign constructs the full RFC 5322 message bytes with a DKIM-Signature
// header prepended. selector/privateKey are the sending domain's DKIM material.
func BuildAndSign(m *Message, selector, privateKey string) ([]byte, error) {
	if m.MessageID == "" {
		m.MessageID = fmt.Sprintf("%d.%s@%s", time.Now().UnixNano(), randToken(8), domainOf(m.From, m.Domain))
	}

	body, contentType, cte := buildBody(m)
	hs := m.orderedHeaders()
	hs = append(hs, header{"Content-Type", contentType})
	if cte != "" {
		hs = append(hs, header{"Content-Transfer-Encoding", cte})
	}

	var msg strings.Builder

	// DKIM-sign (if material provided) and prepend the signature header.
	if selector != "" && privateKey != "" {
		sig, err := Sign(hs, body, SignOptions{
			Domain:     domainOf(m.From, m.Domain),
			Selector:   selector,
			PrivateKey: privateKey,
			HeaderKeys: SignableHeaderKeys,
		})
		if err != nil {
			return nil, err
		}
		msg.WriteString("DKIM-Signature: " + sig + "\r\n")
	}

	for _, h := range hs {
		msg.WriteString(h.Key + ": " + h.Value + "\r\n")
	}
	msg.WriteString("\r\n")
	msg.WriteString(body)
	return []byte(msg.String()), nil
}

// qpEncode quoted-printable-encodes a body part: 7-bit-safe, soft-wrapped at 76
// octets (RFC 2045). MUST run before DKIM signing so the signed body hash (bh=)
// matches what the receiver canonicalizes — a raw 8-bit body gets mutated in
// transit, which breaks bh and fails DKIM (plan §1, builder.go fix).
func qpEncode(s string) string {
	var b strings.Builder
	w := quotedprintable.NewWriter(&b)
	_, _ = w.Write([]byte(s))
	_ = w.Close()
	return b.String()
}

// buildBody returns (body, Content-Type, Content-Transfer-Encoding). Multipart
// carries a per-part CTE inline, so the top-level CTE is empty.
func buildBody(m *Message) (body, contentType, cte string) {
	if m.HTMLBody != "" && m.TextBody != "" {
		boundary := "champmail-" + randToken(16)
		var b strings.Builder
		b.WriteString("--" + boundary + "\r\n")
		b.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
		b.WriteString("Content-Transfer-Encoding: quoted-printable\r\n\r\n")
		b.WriteString(qpEncode(m.TextBody) + "\r\n\r\n")
		b.WriteString("--" + boundary + "\r\n")
		b.WriteString("Content-Type: text/html; charset=UTF-8\r\n")
		b.WriteString("Content-Transfer-Encoding: quoted-printable\r\n\r\n")
		b.WriteString(qpEncode(m.HTMLBody) + "\r\n\r\n")
		b.WriteString("--" + boundary + "--\r\n")
		return b.String(), `multipart/alternative; boundary="` + boundary + `"`, ""
	}
	if m.HTMLBody != "" {
		return qpEncode(m.HTMLBody), "text/html; charset=UTF-8", "quoted-printable"
	}
	return qpEncode(m.TextBody), "text/plain; charset=UTF-8", "quoted-printable"
}

func domainOf(from, fallback string) string {
	if addr, err := mail.ParseAddress(from); err == nil {
		if at := strings.LastIndex(addr.Address, "@"); at >= 0 {
			return addr.Address[at+1:]
		}
	}
	if at := strings.LastIndex(from, "@"); at >= 0 {
		return from[at+1:]
	}
	return fallback
}
