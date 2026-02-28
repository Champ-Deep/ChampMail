package smtp

import (
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"fmt"
	"strings"
)

type DKIM struct {
	privateKey *rsa.PrivateKey
	selector   string
	domain     string
}

func NewDKIM(selector, domain string) *DKIM {
	return &DKIM{
		selector: selector,
		domain:   domain,
	}
}

func (d *DKIM) GenerateKeyPair(bits int) error {
	if bits == 0 {
		bits = 2048
	}

	privateKey, err := rsa.GenerateKey(rand.Reader, bits)
	if err != nil {
		return fmt.Errorf("failed to generate RSA key pair: %w", err)
	}

	d.privateKey = privateKey
	return nil
}

func (d *DKIM) LoadPrivateKey(pemData []byte) error {
	block, _ := pem.Decode(pemData)
	if block == nil {
		if len(pemData) > 0 && !strings.Contains(string(pemData), "BEGIN") {
			decoded, err := base64.StdEncoding.DecodeString(string(pemData))
			if err != nil {
				return fmt.Errorf("failed to decode base64 key: %w", err)
			}
			return d.LoadPrivateKey(decoded)
		}
		return fmt.Errorf("invalid PEM format")
	}

	var err error
	pkcs8Key, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		d.privateKey, err = x509.ParsePKCS1PrivateKey(block.Bytes)
		if err != nil {
			return fmt.Errorf("failed to parse private key: %w", err)
		}
		return nil
	}

	var ok bool
	d.privateKey, ok = pkcs8Key.(*rsa.PrivateKey)
	if !ok {
		return fmt.Errorf("not an RSA private key")
	}
	return nil
}

func (d *DKIM) GetPublicKey() string {
	if d.privateKey == nil {
		return ""
	}
	return base64.StdEncoding.EncodeToString(d.privateKey.PublicKey.N.Bytes())
}

func (d *DKIM) GetDNSRecord() string {
	pubKey := d.GetPublicKey()
	return fmt.Sprintf("v=DKIM1; k=rsa; p=%s", pubKey)
}

func (d *DKIM) SignMessage(msg []byte, from, to, selector, domain string) ([]byte, error) {
	if d.privateKey == nil {
		return msg, fmt.Errorf("no private key loaded")
	}

	dkimHeader := d.buildDKIMHeader(msg, from, to, selector, domain)

	parts := bytes.SplitN(msg, []byte("\r\n\r\n"), 2)
	if len(parts) < 2 {
		return msg, fmt.Errorf("invalid message format")
	}

	headers := string(parts[0])
	body := string(parts[1])

	newHeaders := headers + dkimHeader
	return []byte(newHeaders + "\r\n" + body), nil
}

func (d *DKIM) buildDKIMHeader(msg []byte, from, to, selector, domain string) string {
	headerHash := d.hashHeaders(msg)

	sig := d.signData([]byte(headerHash))

	return fmt.Sprintf("DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=%s; s=%s; h=from:to:subject:date:message-id; b=%s\r\n",
		domain, selector, sig)
}

func (d *DKIM) hashHeaders(msg []byte) string {
	parts := bytes.SplitN(msg, []byte("\r\n\r\n"), 2)
	if len(parts) < 2 {
		return ""
	}

	headers := string(parts[0])

	var fromLine, toLine, subjectLine, dateLine, messageIDLine string

	for _, line := range strings.Split(headers, "\r\n") {
		lower := strings.ToLower(line)
		if strings.HasPrefix(lower, "from:") {
			fromLine = strings.TrimSpace(strings.TrimPrefix(line, "From:"))
		} else if strings.HasPrefix(lower, "to:") {
			toLine = strings.TrimSpace(strings.TrimPrefix(line, "To:"))
		} else if strings.HasPrefix(lower, "subject:") {
			subjectLine = strings.TrimSpace(strings.TrimPrefix(line, "Subject:"))
		} else if strings.HasPrefix(lower, "date:") {
			dateLine = strings.TrimSpace(strings.TrimPrefix(line, "Date:"))
		} else if strings.HasPrefix(lower, "message-id:") {
			messageIDLine = strings.TrimSpace(strings.TrimPrefix(line, "Message-ID:"))
		}
	}

	headerStr := fmt.Sprintf("From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\nMessage-ID: %s",
		strings.Join(strings.Fields(fromLine), " "),
		strings.Join(strings.Fields(toLine), " "),
		strings.Join(strings.Fields(subjectLine), " "),
		strings.Join(strings.Fields(dateLine), " "),
		strings.Join(strings.Fields(messageIDLine), " "))

	return headerStr
}

func (d *DKIM) signData(data []byte) string {
	hash := sha256.Sum256(data)
	sig, err := rsa.SignPKCS1v15(rand.Reader, d.privateKey, 0, hash[:])
	if err != nil {
		return ""
	}
	return base64.StdEncoding.EncodeToString(sig)
}

type DKIMSigner struct {
	dkim   *DKIM
	domain string
}

func NewDKIMSigner(privateKeyPEM string, domain, selector string) (*DKIMSigner, error) {
	dkim := NewDKIM(selector, domain)

	if err := dkim.LoadPrivateKey([]byte(privateKeyPEM)); err != nil {
		return nil, err
	}

	return &DKIMSigner{
		dkim:   dkim,
		domain: domain,
	}, nil
}

func (s *DKIMSigner) SignMessage(msg []byte, from, to, selector, domain string) ([]byte, error) {
	return s.dkim.SignMessage(msg, from, to, selector, domain)
}

type DKIMSignerInterface interface {
	SignMessage(msg []byte, from, to, selector, domain string) ([]byte, error)
}

func GenerateKeyPair(selector, domain string) (privateKeyPEM, publicKeyDNS string, err error) {
	dkim := NewDKIM(selector, domain)
	if err := dkim.GenerateKeyPair(2048); err != nil {
		return "", "", err
	}

	privateKeyBytes, err := x509.MarshalPKCS8PrivateKey(dkim.privateKey)
	if err != nil {
		return "", "", err
	}
	privateKeyPEM = string(pem.EncodeToMemory(&pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: privateKeyBytes,
	}))

	publicKeyDNS = dkim.GetDNSRecord()

	return privateKeyPEM, publicKeyDNS, nil
}
