package mailer

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/pem"
	"strings"
	"testing"
)

func pemKey(t *testing.T, bits int) string {
	t.Helper()
	k, err := rsa.GenerateKey(rand.Reader, bits)
	if err != nil {
		t.Fatal(err)
	}
	der := x509.MarshalPKCS1PrivateKey(k)
	return string(pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: der}))
}

// B: bodies are quoted-printable-encoded (non-ASCII → =XX), with the CTE header.
func TestQPEncodesBody(t *testing.T) {
	m := &Message{From: "a@d.com", To: "b@e.com", Subject: "hi",
		HTMLBody: "<p>café</p>", MessageID: "m@d.com", Domain: "d.com"}
	raw, err := BuildAndSign(m, "sel", pemKey(t, 2048))
	if err != nil {
		t.Fatal(err)
	}
	s := string(raw)
	if !strings.Contains(s, "Content-Transfer-Encoding: quoted-printable") {
		t.Fatalf("missing quoted-printable CTE:\n%s", s)
	}
	if !strings.Contains(s, "=C3=A9") { // é in UTF-8, QP-encoded
		t.Fatalf("body not QP-encoded:\n%s", s)
	}
}

// C: a non-ASCII Subject is RFC-2047 encoded-word.
func TestSubjectRFC2047(t *testing.T) {
	m := &Message{From: "a@d.com", To: "b@e.com", Subject: "café meeting",
		TextBody: "x", MessageID: "m@d.com", Domain: "d.com"}
	raw, err := BuildAndSign(m, "sel", pemKey(t, 2048))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.ToLower(string(raw)), "=?utf-8?q?") {
		t.Fatalf("subject not RFC-2047 encoded:\n%s", raw)
	}
}

// D: a CRLF-injected Subject must NOT create a new header line.
func TestHeaderInjectionStripped(t *testing.T) {
	m := &Message{From: "a@d.com", To: "b@e.com", Subject: "hi\r\nBcc: evil@x.com",
		TextBody: "x", MessageID: "m@d.com", Domain: "d.com"}
	raw, err := BuildAndSign(m, "sel", pemKey(t, 2048))
	if err != nil {
		t.Fatal(err)
	}
	for _, ln := range strings.Split(string(raw), "\r\n") {
		if strings.HasPrefix(strings.ToLower(strings.TrimSpace(ln)), "bcc:") {
			t.Fatalf("CRLF injection created a Bcc header:\n%s", raw)
		}
	}
}

// E: a sub-2048 key is rejected at sign time.
func TestKeyFloor2048(t *testing.T) {
	m := &Message{From: "a@d.com", To: "b@e.com", Subject: "hi",
		TextBody: "x", MessageID: "m@d.com", Domain: "d.com"}
	if _, err := BuildAndSign(m, "sel", pemKey(t, 1024)); err == nil {
		t.Fatal("expected sub-2048 key to be rejected")
	}
}
