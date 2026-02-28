package smtp

import (
	"bytes"
	"context"
	"crypto/tls"
	"fmt"
	"net"
	"net/smtp"
	"strings"
	"time"

	"github.com/champmail/mail-engine/internal/db"
)

type Sender struct {
	cfg *SMTPConfig
}

type SMTPConfig struct {
	Host           string
	Port           int
	Username       string
	Password       string
	UseTLS         bool
	PostfixEnabled bool
	DialTimeout    time.Duration
	WriteTimeout   time.Duration
	ReadTimeout    time.Duration
}

func NewSender(cfg *SMTPConfig) *Sender {
	return &Sender{cfg: cfg}
}

type SendOptions struct {
	To          string
	From        string
	FromName    string
	Subject     string
	HTMLBody    string
	TextBody    string
	ReplyTo     string
	MessageID   string
	Domain      *db.Domain
	DKIMSigner  DKIMSignerInterface
	TrackOpens  bool
	TrackClicks bool
	TrackingURL string

	SMTPHost   string
	SMTPPort   int
	SMTPUser   string
	SMTPPass   string
	SMTPUseTLS bool
}

func (s *Sender) Send(ctx context.Context, opts SendOptions) error {
	var host string
	var port int
	var user, pass string
	var useTLS bool

	if opts.SMTPHost != "" {
		host = opts.SMTPHost
		port = opts.SMTPPort
		user = opts.SMTPUser
		pass = opts.SMTPPass
		useTLS = opts.SMTPUseTLS
	} else if s.cfg != nil && s.cfg.PostfixEnabled {
		host = "localhost"
		port = 25
		user = ""
		pass = ""
		useTLS = false
	} else if s.cfg != nil {
		host = s.cfg.Host
		port = s.cfg.Port
		user = s.cfg.Username
		pass = s.cfg.Password
		useTLS = s.cfg.UseTLS
	} else {
		return fmt.Errorf("no SMTP configuration available")
	}

	from := opts.From
	if from == "" && opts.Domain != nil {
		from = fmt.Sprintf("noreply@%s", opts.Domain.DomainName)
	}

	htmlBody := opts.HTMLBody
	textBody := opts.TextBody

	if htmlBody == "" && textBody != "" {
		htmlBody = fmt.Sprintf("<html><body><pre>%s</pre></body></html>", textBody)
	} else if htmlBody != "" && textBody == "" {
		textBody = stripHTML(htmlBody)
	}

	msg := s.buildMessage(from, opts.To, opts.FromName, opts.Subject, htmlBody, textBody, opts.ReplyTo, opts.MessageID, opts.Domain)

	if opts.DKIMSigner != nil {
		signedMsg, err := opts.DKIMSigner.SignMessage(msg, from, opts.To, opts.Domain.DKIMSelector, opts.Domain.DomainName)
		if err != nil {
			return fmt.Errorf("failed to sign message: %w", err)
		}
		msg = signedMsg
	}

	return s.sendViaSMTP(ctx, host, port, user, pass, useTLS, from, opts.To, msg)
}

func (s *Sender) buildMessage(from, to, fromName, subject, htmlBody, textBody, replyTo, messageID string, domain *db.Domain) []byte {
	var msg bytes.Buffer

	msg.WriteString(fmt.Sprintf("From: %s\r\n", formatAddress(from, fromName)))
	msg.WriteString(fmt.Sprintf("To: %s\r\n", to))
	msg.WriteString(fmt.Sprintf("Subject: %s\r\n", subject))
	msg.WriteString(fmt.Sprintf("Message-ID: <%s@%s>\r\n", messageID, getDomainFromEmail(from)))
	msg.WriteString(fmt.Sprintf("Date: %s\r\n", time.Now().UTC().Format(time.RFC1123Z)))

	if replyTo != "" {
		msg.WriteString(fmt.Sprintf("Reply-To: %s\r\n", replyTo))
	}

	if domain != nil {
		msg.WriteString(fmt.Sprintf("List-Unsubscribe: <mailto:unsubscribe@%s?subject=unsubscribe>\r\n", domain.DomainName))
	}

	msg.WriteString("MIME-Version: 1.0\r\n")
	msg.WriteString("Content-Type: multipart/alternative; boundary=\"boundary\"\r\n")
	msg.WriteString("\r\n")

	msg.WriteString("--boundary\r\n")
	msg.WriteString("Content-Type: text/plain; charset=\"UTF-8\"\r\n")
	msg.WriteString("Content-Transfer-Encoding: quoted-printable\r\n")
	msg.WriteString("\r\n")
	msg.WriteString(quotePrintable(textBody))
	msg.WriteString("\r\n")

	msg.WriteString("--boundary\r\n")
	msg.WriteString("Content-Type: text/html; charset=\"UTF-8\"\r\n")
	msg.WriteString("Content-Transfer-Encoding: quoted-printable\r\n")
	msg.WriteString("\r\n")
	msg.WriteString(quotePrintable(htmlBody))
	msg.WriteString("\r\n")

	msg.WriteString("--boundary--\r\n")

	return msg.Bytes()
}

func (s *Sender) sendViaSMTP(ctx context.Context, host string, port int, user, pass string, useTLS bool, from, to string, msg []byte) error {
	addr := fmt.Sprintf("%s:%d", host, port)

	var auth smtp.Auth
	if user != "" {
		auth = smtp.PlainAuth("", user, pass, host)
	}

	dialTimeout := 10 * time.Second
	if s.cfg != nil && s.cfg.DialTimeout > 0 {
		dialTimeout = s.cfg.DialTimeout
	}

	dialer := &net.Dialer{Timeout: dialTimeout}

	conn, err := dialer.DialContext(ctx, "tcp", addr)
	if err != nil {
		return fmt.Errorf("failed to connect to SMTP server %s: %w", addr, err)
	}

	if useTLS {
		tlsConn := tls.Client(conn, &tls.Config{
			ServerName: host,
		})
		if err := tlsConn.Handshake(); err != nil {
			conn.Close()
			return fmt.Errorf("TLS handshake failed: %w", err)
		}
		conn = tlsConn
	}

	client, err := smtp.NewClient(conn, host)
	if err != nil {
		conn.Close()
		return fmt.Errorf("failed to create SMTP client: %w", err)
	}
	defer client.Quit()

	if auth != nil {
		if err := client.Auth(auth); err != nil {
			return fmt.Errorf("SMTP auth failed: %w", err)
		}
	}

	if err := client.Mail(from); err != nil {
		return fmt.Errorf("SMTP MAIL command failed: %w", err)
	}

	if err := client.Rcpt(to); err != nil {
		return fmt.Errorf("SMTP RCPT command failed: %w", err)
	}

	w, err := client.Data()
	if err != nil {
		return fmt.Errorf("SMTP DATA command failed: %w", err)
	}

	_, err = w.Write(msg)
	if err != nil {
		return fmt.Errorf("failed to write message: %w", err)
	}

	err = w.Close()
	if err != nil {
		return fmt.Errorf("failed to close message writer: %w", err)
	}

	return nil
}

func formatAddress(email, name string) string {
	if name == "" {
		return email
	}
	return fmt.Sprintf("%s <%s>", name, email)
}

func getDomainFromEmail(email string) string {
	parts := strings.Split(email, "@")
	if len(parts) > 1 {
		return parts[1]
	}
	return "localhost"
}

func quotePrintable(s string) string {
	var buf bytes.Buffer
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c == '\n' {
			buf.WriteString("\r\n")
			if i+1 < len(s) && s[i+1] != '\n' && s[i+1] != '\r' {
				continue
			}
		} else if c == '\r' {
			buf.WriteString("\r")
		} else if c == '=' || c < 32 || c > 126 {
			fmt.Fprintf(&buf, "=%02X", c)
		} else {
			buf.WriteByte(c)
		}
	}
	return buf.String()
}

func stripHTML(html string) string {
	var result strings.Builder
	inTag := false
	for _, c := range html {
		switch {
		case c == '<':
			inTag = true
		case c == '>':
			inTag = false
			result.WriteByte(' ')
		case !inTag:
			result.WriteRune(c)
		}
	}
	return strings.Join(strings.Fields(result.String()), " ")
}

type SMTPError struct {
	Code    int
	Message string
}

func (e *SMTPError) Error() string {
	return fmt.Sprintf("SMTP error %d: %s", e.Code, e.Message)
}
