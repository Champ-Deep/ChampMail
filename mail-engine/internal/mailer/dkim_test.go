package mailer

import (
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"strings"
	"testing"
)

func genKey(t *testing.T) (priv string, pub *rsa.PublicKey) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	der := x509.MarshalPKCS1PrivateKey(key)
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: der})
	return string(pemBytes), &key.PublicKey
}

// verifies a DKIM-Signature the way a receiver would: recompute the signed
// header block (with b= emptied) and check the RSA signature + body hash.
func verifyDKIM(t *testing.T, raw []byte, pub *rsa.PublicKey) {
	t.Helper()
	parts := strings.SplitN(string(raw), "\r\n\r\n", 2)
	if len(parts) != 2 {
		t.Fatal("message has no header/body split")
	}
	headerText, body := parts[0], parts[1]

	// Pull out the DKIM-Signature line.
	var dkimVal string
	headerLines := strings.Split(headerText, "\r\n")
	for _, ln := range headerLines {
		if strings.HasPrefix(strings.ToLower(ln), "dkim-signature:") {
			dkimVal = strings.TrimSpace(ln[len("dkim-signature:"):])
		}
	}
	if dkimVal == "" {
		t.Fatal("no DKIM-Signature header")
	}

	tags := map[string]string{}
	for _, seg := range strings.Split(dkimVal, ";") {
		seg = strings.TrimSpace(seg)
		if i := strings.Index(seg, "="); i > 0 {
			tags[seg[:i]] = strings.TrimSpace(seg[i+1:])
		}
	}

	// Body hash check (relaxed).
	cbody := canonicalizeBodyRelaxed(body)
	bh := sha256.Sum256([]byte(cbody))
	if base64.StdEncoding.EncodeToString(bh[:]) != tags["bh"] {
		t.Fatalf("bh mismatch")
	}

	// Rebuild the signed header block in h= order from the actual headers.
	hmap := map[string]string{}
	for _, ln := range headerLines {
		if i := strings.Index(ln, ":"); i > 0 {
			hmap[strings.ToLower(strings.TrimSpace(ln[:i]))] = strings.TrimSpace(ln[i+1:])
		}
	}
	var block strings.Builder
	for _, k := range strings.Split(tags["h"], ":") {
		k = strings.ToLower(strings.TrimSpace(k))
		if v, ok := hmap[k]; ok {
			block.WriteString(canonicalizeHeaderRelaxed(k, v))
		}
	}
	// Append the DKIM-Signature with empty b=.
	emptied := dkimVal
	if i := strings.Index(emptied, "b="); i >= 0 {
		emptied = emptied[:i+2]
	}
	block.WriteString(canonicalizeHeaderRelaxed("DKIM-Signature", emptied))
	toVerify := strings.TrimSuffix(block.String(), "\r\n")

	sig, err := base64.StdEncoding.DecodeString(tags["b"])
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256([]byte(toVerify))
	if err := rsa.VerifyPKCS1v15(pub, crypto.SHA256, digest[:], sig); err != nil {
		t.Fatalf("DKIM signature does not verify: %v", err)
	}
}

func TestBuildAndSignVerifies(t *testing.T) {
	priv, pub := genKey(t)
	msg := &Message{
		From:      "Deep <deep@championsmail.com>",
		To:        "prospect@example.com",
		Subject:   "a quick idea for Acme",
		HTMLBody:  "<p>Hi — worth a 15 min look?</p>",
		TextBody:  "Hi — worth a 15 min look?",
		MessageID: "abc123.tok@championsmail.com",
		Domain:    "championsmail.com",
		ExtraHeaders: map[string]string{
			"List-Unsubscribe":      "<https://championsmail.com/u/opaque-token>",
			"List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
		},
	}
	raw, err := BuildAndSign(msg, "champmail", priv)
	if err != nil {
		t.Fatal(err)
	}
	s := string(raw)
	if !strings.Contains(s, "DKIM-Signature: ") {
		t.Fatal("no DKIM-Signature header emitted")
	}
	// The one-click headers MUST be in the signed h= set, else Gmail/Yahoo ignore them.
	if !strings.Contains(s, "list-unsubscribe:list-unsubscribe-post") &&
		!strings.Contains(strings.ToLower(s), "h=") {
		t.Fatal("expected h= tag")
	}
	hLine := ""
	for _, ln := range strings.Split(s, "\r\n") {
		if strings.HasPrefix(ln, "DKIM-Signature:") {
			hLine = ln
		}
	}
	if !strings.Contains(strings.ToLower(hLine), "list-unsubscribe") ||
		!strings.Contains(strings.ToLower(hLine), "list-unsubscribe-post") {
		t.Fatalf("List-Unsubscribe headers not in DKIM h= tag: %s", hLine)
	}
	verifyDKIM(t, raw, pub)
}

func TestTamperBreaksSignature(t *testing.T) {
	priv, pub := genKey(t)
	msg := &Message{
		From: "a@d.com", To: "b@e.com", Subject: "x", TextBody: "the original body",
		MessageID: "m@d.com", Domain: "d.com",
	}
	raw, err := BuildAndSign(msg, "sel", priv)
	if err != nil {
		t.Fatal(err)
	}
	// Tampering with the signed body must invalidate the body hash.
	tampered := []byte(strings.Replace(string(raw), "the original body", "a forged body", 1))
	parts := strings.SplitN(string(tampered), "\r\n\r\n", 2)
	cbody := canonicalizeBodyRelaxed(parts[1])
	bh := sha256.Sum256([]byte(cbody))
	// Recover bh from the header.
	var origBh string
	for _, ln := range strings.Split(parts[0], "\r\n") {
		if strings.HasPrefix(strings.ToLower(ln), "dkim-signature:") {
			for _, seg := range strings.Split(ln, ";") {
				seg = strings.TrimSpace(seg)
				if strings.HasPrefix(seg, "bh=") {
					origBh = strings.TrimSpace(seg[3:])
				}
			}
		}
	}
	if base64.StdEncoding.EncodeToString(bh[:]) == origBh {
		t.Fatal("body hash unchanged after tampering — signature would still pass")
	}
	_ = pub
}
