package mailer

import (
	"fmt"
	"net/mail"
	"strings"
	"time"
)

// Message is the input to BuildAndSign.
type Message struct {
	From        string // "Name <addr@domain>" or "addr@domain"
	To          string
	Subject     string
	HTMLBody    string
	TextBody    string
	ReplyTo     string
	MessageID   string // without angle brackets; built if empty
	Domain      string // sending domain (for Message-ID + DKIM d=)
	ExtraHeaders map[string]string // e.g. List-Unsubscribe, List-Unsubscribe-Post
}

// orderedHeaders builds the header list in the order they appear in the message,
// which is also (for the signable subset) the DKIM h= order.
func (m *Message) orderedHeaders() []header {
	hs := []header{
		{"From", m.From},
		{"To", m.To},
		{"Subject", m.Subject},
		{"Date", time.Now().UTC().Format(time.RFC1123Z)},
		{"Message-ID", "<" + m.MessageID + ">"},
		{"MIME-Version", "1.0"},
	}
	if m.ReplyTo != "" {
		hs = append(hs, header{"Reply-To", m.ReplyTo})
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

	body, contentType := buildBody(m)
	hs := m.orderedHeaders()
	hs = append(hs, header{"Content-Type", contentType})

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

func buildBody(m *Message) (body, contentType string) {
	if m.HTMLBody != "" && m.TextBody != "" {
		boundary := "champmail-" + randToken(16)
		var b strings.Builder
		b.WriteString("--" + boundary + "\r\n")
		b.WriteString("Content-Type: text/plain; charset=UTF-8\r\n\r\n")
		b.WriteString(m.TextBody + "\r\n\r\n")
		b.WriteString("--" + boundary + "\r\n")
		b.WriteString("Content-Type: text/html; charset=UTF-8\r\n\r\n")
		b.WriteString(m.HTMLBody + "\r\n\r\n")
		b.WriteString("--" + boundary + "--\r\n")
		return b.String(), `multipart/alternative; boundary="` + boundary + `"`
	}
	if m.HTMLBody != "" {
		return m.HTMLBody, "text/html; charset=UTF-8"
	}
	return m.TextBody, "text/plain; charset=UTF-8"
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
