// Package mailer builds RFC 5322 messages and DKIM-signs them (RFC 6376).
//
// This is a self-contained signer (stdlib crypto only — no external DKIM
// dependency) implementing rsa-sha256 with relaxed/relaxed canonicalization,
// which is what Gmail/Yahoo expect. Critically, the List-Unsubscribe and
// List-Unsubscribe-Post headers are included in the signed header set (the h=
// tag) — Gmail/Yahoo IGNORE one-click unsubscribe headers that aren't covered by
// the DKIM signature, so this is the piece that makes the compliance work real.
package mailer

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"errors"
	"fmt"
	"strings"
	"time"
)

// SignOptions configures a DKIM signature.
type SignOptions struct {
	Domain     string // d=
	Selector   string // s=
	PrivateKey string // PEM-encoded RSA private key (PKCS#1 or PKCS#8)
	// HeaderKeys lists, in order, which headers to sign (h=). List-Unsubscribe
	// and List-Unsubscribe-Post are appended automatically if present.
	HeaderKeys []string
}

// header is a single message header as written.
type header struct {
	Key   string
	Value string
}

// DKIMMinKeyBits is the RSA key-size floor (plan Q3). Sub-2048 DKIM is treated as
// insecure / ignored by major receivers, so a weak key silently kills auth.
const DKIMMinKeyBits = 2048

func parsePrivateKey(pemStr string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(strings.TrimSpace(pemStr)))
	if block == nil {
		return nil, errors.New("dkim: no PEM block in private key")
	}
	var key *rsa.PrivateKey
	if k, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		key = k
	} else {
		keyAny, err := x509.ParsePKCS8PrivateKey(block.Bytes)
		if err != nil {
			return nil, fmt.Errorf("dkim: parse private key: %w", err)
		}
		rsaKey, ok := keyAny.(*rsa.PrivateKey)
		if !ok {
			return nil, errors.New("dkim: not an RSA private key")
		}
		key = rsaKey
	}
	// Key-size floor — enforced on every sign, so per-domain keys loaded from the
	// DB are guarded too, not just the startup key.
	if key.N.BitLen() < DKIMMinKeyBits {
		return nil, fmt.Errorf("dkim: RSA key is %d bits; minimum %d required", key.N.BitLen(), DKIMMinKeyBits)
	}
	return key, nil
}

// canonicalizeHeaderRelaxed applies relaxed header canonicalization (RFC 6376
// §3.4.2): lowercase the name, unfold, compress internal whitespace to one
// space, strip leading/trailing whitespace around the value, single space after
// the colon, terminate with CRLF.
func canonicalizeHeaderRelaxed(key, value string) string {
	k := strings.ToLower(strings.TrimSpace(key))
	v := unfoldAndCompress(value)
	return k + ":" + v + "\r\n"
}

func unfoldAndCompress(s string) string {
	// Unfold (remove CRLF) then collapse runs of whitespace to a single space.
	s = strings.ReplaceAll(s, "\r\n", "")
	s = strings.ReplaceAll(s, "\n", "")
	var b strings.Builder
	prevSpace := false
	for _, r := range s {
		if r == ' ' || r == '\t' {
			prevSpace = true
			continue
		}
		if prevSpace && b.Len() > 0 {
			b.WriteByte(' ')
		}
		prevSpace = false
		b.WriteRune(r)
	}
	return strings.TrimSpace(b.String())
}

// canonicalizeBodyRelaxed applies relaxed body canonicalization: strip trailing
// whitespace on each line, compress internal whitespace runs, remove trailing
// empty lines, and ensure the body ends with a single CRLF (RFC 6376 §3.4.4).
func canonicalizeBodyRelaxed(body string) string {
	body = strings.ReplaceAll(body, "\r\n", "\n")
	lines := strings.Split(body, "\n")
	out := make([]string, 0, len(lines))
	for _, ln := range lines {
		// compress WSP runs then trim trailing WSP
		compressed := unfoldAndCompressKeepLeading(ln)
		out = append(out, strings.TrimRight(compressed, " \t"))
	}
	// remove trailing empty lines
	for len(out) > 0 && out[len(out)-1] == "" {
		out = out[:len(out)-1]
	}
	if len(out) == 0 {
		return "\r\n"
	}
	return strings.Join(out, "\r\n") + "\r\n"
}

func unfoldAndCompressKeepLeading(s string) string {
	var b strings.Builder
	prevSpace := false
	for _, r := range s {
		if r == ' ' || r == '\t' {
			prevSpace = true
			continue
		}
		if prevSpace {
			b.WriteByte(' ')
		}
		prevSpace = false
		b.WriteRune(r)
	}
	if prevSpace {
		b.WriteByte(' ')
	}
	return b.String()
}

// Sign returns the value of the DKIM-Signature header (without the "DKIM-Signature:"
// prefix) for the given headers and body. `headers` must include every key named
// in opts.HeaderKeys. The returned header should be prepended to the message.
func Sign(headers []header, body string, opts SignOptions) (string, error) {
	key, err := parsePrivateKey(opts.PrivateKey)
	if err != nil {
		return "", err
	}

	// Body hash.
	cbody := canonicalizeBodyRelaxed(body)
	bh := sha256.Sum256([]byte(cbody))
	bhB64 := base64.StdEncoding.EncodeToString(bh[:])

	// Resolve which headers to sign (only those actually present), preserving
	// order and ensuring the one-click unsubscribe headers are covered.
	want := append([]string{}, opts.HeaderKeys...)
	for _, extra := range []string{"List-Unsubscribe", "List-Unsubscribe-Post"} {
		if hasHeader(headers, extra) && !containsFold(want, extra) {
			want = append(want, extra)
		}
	}
	var signedKeys []string
	var signedHeaderBlock strings.Builder
	for _, k := range want {
		v, ok := lookupHeader(headers, k)
		if !ok {
			continue
		}
		signedKeys = append(signedKeys, strings.ToLower(k))
		signedHeaderBlock.WriteString(canonicalizeHeaderRelaxed(k, v))
	}

	// Build the DKIM-Signature header value with an empty b=.
	dkimVal := fmt.Sprintf(
		"v=1; a=rsa-sha256; c=relaxed/relaxed; d=%s; s=%s; t=%d; "+
			"h=%s; bh=%s; b=",
		opts.Domain, opts.Selector, time.Now().Unix(),
		strings.Join(signedKeys, ":"), bhB64,
	)

	// The DKIM-Signature header itself is included in the hash, canonicalized,
	// with an empty b= and NO trailing CRLF.
	signedHeaderBlock.WriteString(canonicalizeHeaderRelaxed("DKIM-Signature", dkimVal))
	toSign := strings.TrimSuffix(signedHeaderBlock.String(), "\r\n")

	digest := sha256.Sum256([]byte(toSign))
	sig, err := rsa.SignPKCS1v15(rand.Reader, key, crypto.SHA256, digest[:])
	if err != nil {
		return "", fmt.Errorf("dkim: sign: %w", err)
	}
	bB64 := base64.StdEncoding.EncodeToString(sig)
	return dkimVal + bB64, nil
}

func hasHeader(hs []header, key string) bool {
	_, ok := lookupHeader(hs, key)
	return ok
}

func lookupHeader(hs []header, key string) (string, bool) {
	for _, h := range hs {
		if strings.EqualFold(h.Key, key) {
			return h.Value, true
		}
	}
	return "", false
}

func containsFold(xs []string, target string) bool {
	for _, x := range xs {
		if strings.EqualFold(x, target) {
			return true
		}
	}
	return false
}
