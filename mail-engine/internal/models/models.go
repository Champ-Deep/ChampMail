package models

import "time"

type SendEmailRequest struct {
	To          string            `json:"to" binding:"required,email"`
	From        string            `json:"from"`
	FromName    string            `json:"from_name"`
	Subject     string            `json:"subject" binding:"required"`
	HTMLBody    string            `json:"html_body"`
	TextBody    string            `json:"text_body"`
	ReplyTo     string            `json:"reply_to"`
	Attachments []Attachment      `json:"attachments"`
	Headers     map[string]string `json:"headers"`
	DomainID    string            `json:"domain_id"`
	TrackOpens  bool              `json:"track_opens"`
	TrackClicks bool              `json:"track_clicks"`
	ScheduledAt *time.Time        `json:"scheduled_at"`
}

type Attachment struct {
	Filename    string `json:"filename"`
	ContentType string `json:"content_type"`
	Content     string `json:"content"`
}

type SendEmailResponse struct {
	MessageID string    `json:"message_id"`
	Status    string    `json:"status"`
	DomainID  string    `json:"domain_id"`
	SentAt    time.Time `json:"sent_at"`
}

type BatchSendRequest struct {
	Emails   []SendEmailRequest `json:"emails" binding:"required,min=1,max=100"`
	DomainID string             `json:"domain_id"`
}

type BatchSendResponse struct {
	Total      int                 `json:"total"`
	Successful int                 `json:"successful"`
	Failed     int                 `json:"failed"`
	Results    []SendEmailResponse `json:"results"`
}

type DNSCheckResult struct {
	Domain       string   `json:"domain"`
	MXRecords    []string `json:"mx_records"`
	SPFRecord    string   `json:"spf_record"`
	SPFValid     bool     `json:"spf_valid"`
	DKIMSelector string   `json:"dkim_selector"`
	DKIMRecord   string   `json:"dkim_record"`
	DKIMValid    bool     `json:"dkim_valid"`
	DMARCRecord  string   `json:"dmarc_record"`
	DMARCValid   bool     `json:"dmarc_valid"`
	AllVerified  bool     `json:"all_verified"`
}

type DKIMKeyPair struct {
	Domain     string `json:"domain"`
	Selector   string `json:"selector"`
	PrivateKey string `json:"private_key"`
	PublicKey  string `json:"public_key"`
}

type DomainSetupRequest struct {
	DomainName string `json:"domain_name" binding:"required"`
	Selector   string `json:"selector"`
}

type DomainSetupResponse struct {
	DomainID      string      `json:"domain_id"`
	DomainName    string      `json:"domain_name"`
	Selector      string      `json:"selector"`
	DKIMPublicKey string      `json:"dkim_public_key"`
	Records       []DNSRecord `json:"records"`
}

type DNSRecord struct {
	Type     string `json:"type"`
	Name     string `json:"name"`
	Value    string `json:"value"`
	Priority int    `json:"priority,omitempty"`
	TTL      int    `json:"ttl"`
}

type SendStats struct {
	DomainID     string  `json:"domain_id"`
	TodaySent    int     `json:"today_sent"`
	TodayLimit   int     `json:"today_limit"`
	TotalSent    int64   `json:"total_sent"`
	TotalOpened  int64   `json:"total_opened"`
	TotalClicked int64   `json:"total_clicked"`
	TotalBounced int64   `json:"total_bounced"`
	OpenRate     float64 `json:"open_rate"`
	ClickRate    float64 `json:"click_rate"`
	BounceRate   float64 `json:"bounce_rate"`
}

type HealthCheckResponse struct {
	Status     string `json:"status"`
	PostgreSQL bool   `json:"postgresql"`
	Redis      bool   `json:"redis"`
	Version    string `json:"version"`
}

type ErrorResponse struct {
	Error   string `json:"error"`
	Code    string `json:"code"`
	Details string `json:"details,omitempty"`
}

type TrackOpenRequest struct {
	MessageID string `json:"message_id" binding:"required"`
	UserAgent string `json:"user_agent"`
	IP        string `json:"ip"`
}

type TrackClickRequest struct {
	MessageID string `json:"message_id" binding:"required"`
	URL       string `json:"url" binding:"required"`
}
