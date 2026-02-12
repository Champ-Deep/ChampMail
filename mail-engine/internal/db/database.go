package db

import (
	"database/sql"
	"fmt"
	"time"

	_ "github.com/lib/pq"

	"github.com/champmail/mail-engine/internal/config"
)

type PostgresDB struct {
	*sql.DB
}

func NewPostgresDB(cfg *config.Config) (*PostgresDB, error) {
	connStr := fmt.Sprintf(
		"host=%s port=%d user=%s password=%s dbname=%s sslmode=disable",
		cfg.PostgresHost, cfg.PostgresPort, cfg.PostgresUser, cfg.PostgresPassword, cfg.PostgresDB,
	)

	db, err := sql.Open("postgres", connStr)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	db.SetMaxOpenConns(cfg.PostgresMaxOpenConns)
	db.SetMaxIdleConns(cfg.PostgresMaxIdleConns)
	db.SetConnMaxLifetime(cfg.PostgresConnMaxLifetime)

	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	postgresDB := &PostgresDB{db}

	if err := postgresDB.createTables(); err != nil {
		return nil, fmt.Errorf("failed to create tables: %w", err)
	}

	return postgresDB, nil
}

func (db *PostgresDB) createTables() error {
	queries := []string{
		`CREATE TABLE IF NOT EXISTS domains (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			domain_name VARCHAR(255) UNIQUE NOT NULL,
			status VARCHAR(50) DEFAULT 'pending',
			mx_verified BOOLEAN DEFAULT FALSE,
			spf_verified BOOLEAN DEFAULT FALSE,
			dkim_verified BOOLEAN DEFAULT FALSE,
			dmarc_verified BOOLEAN DEFAULT FALSE,
			dkim_selector VARCHAR(100),
			dkim_private_key TEXT,
			dkim_public_key TEXT,
			daily_send_limit INTEGER DEFAULT 50,
			sent_today INTEGER DEFAULT 0,
			warmup_enabled BOOLEAN DEFAULT TRUE,
			warmup_day INTEGER DEFAULT 0,
			health_score DECIMAL(5,2) DEFAULT 100.00,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS send_logs (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			domain_id UUID REFERENCES domains(id),
			recipient VARCHAR(255) NOT NULL,
			from_address VARCHAR(255) NOT NULL,
			subject TEXT,
			message_id VARCHAR(255) UNIQUE,
			status VARCHAR(50) DEFAULT 'pending',
			error_message TEXT,
			sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			opened_at TIMESTAMP,
			clicked_at TIMESTAMP,
			bounced_at TIMESTAMP,
			bounce_type VARCHAR(50),
			team_id UUID
		)`,
		`CREATE TABLE IF NOT EXISTS bounces (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			send_log_id UUID REFERENCES send_logs(id),
			email VARCHAR(255) NOT NULL,
			bounce_type VARCHAR(50) NOT NULL,
			smtp_response TEXT,
			processed BOOLEAN DEFAULT FALSE,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS api_keys (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			key_hash VARCHAR(255) UNIQUE NOT NULL,
			name VARCHAR(100) NOT NULL,
			team_id UUID,
			permissions TEXT[],
			last_used_at TIMESTAMP,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			expires_at TIMESTAMP
		)`,
		`CREATE TABLE IF NOT EXISTS daily_stats (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			domain_id UUID REFERENCES domains(id),
			date DATE NOT NULL,
			total_sent INTEGER DEFAULT 0,
			total_opened INTEGER DEFAULT 0,
			total_clicked INTEGER DEFAULT 0,
			total_bounced INTEGER DEFAULT 0,
			unique_opens INTEGER DEFAULT 0,
			unique_clicks INTEGER DEFAULT 0,
			created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
			UNIQUE(domain_id, date)
		)`,
		`CREATE INDEX IF NOT EXISTS idx_send_logs_domain_id ON send_logs(domain_id)`,
		`CREATE INDEX IF NOT EXISTS idx_send_logs_status ON send_logs(status)`,
		`CREATE INDEX IF NOT EXISTS idx_send_logs_sent_at ON send_logs(sent_at DESC)`,
		`CREATE INDEX IF NOT EXISTS idx_bounces_email ON bounces(email)`,
	}

	for _, query := range queries {
		if _, err := db.Exec(query); err != nil {
			return fmt.Errorf("failed to execute query: %w", err)
		}
	}

	return nil
}

type Domain struct {
	ID             string    `json:"id"`
	DomainName     string    `json:"domain_name"`
	Status         string    `json:"status"`
	MXVerified     bool      `json:"mx_verified"`
	SPFVerified    bool      `json:"spf_verified"`
	DKIMVerified   bool      `json:"dkim_verified"`
	DMARCVerified  bool      `json:"dmarc_verified"`
	DKIMSelector   string    `json:"dkim_selector,omitempty"`
	DKIMPrivateKey string    `json:"-"`
	DKIMPublicKey  string    `json:"dkim_public_key,omitempty"`
	DailySendLimit int       `json:"daily_send_limit"`
	SentToday      int       `json:"sent_today"`
	WarmupEnabled  bool      `json:"warmup_enabled"`
	WarmupDay      int       `json:"warmup_day"`
	HealthScore    float64   `json:"health_score"`
	CreatedAt      time.Time `json:"created_at"`
}

type SendLog struct {
	ID           string     `json:"id"`
	DomainID     string     `json:"domain_id"`
	Recipient    string     `json:"recipient"`
	FromAddress  string     `json:"from_address"`
	Subject      string     `json:"subject"`
	MessageID    string     `json:"message_id"`
	Status       string     `json:"status"`
	ErrorMessage string     `json:"error_message,omitempty"`
	SentAt       time.Time  `json:"sent_at"`
	OpenedAt     *time.Time `json:"opened_at,omitempty"`
	ClickedAt    *time.Time `json:"clicked_at,omitempty"`
	BouncedAt    *time.Time `json:"bounced_at,omitempty"`
	BounceType   string     `json:"bounce_type,omitempty"`
	TeamID       string     `json:"team_id,omitempty"`
}

type Bounce struct {
	ID           string    `json:"id"`
	SendLogID    string    `json:"send_log_id"`
	Email        string    `json:"email"`
	BounceType   string    `json:"bounce_type"`
	SMTPResponse string    `json:"smtp_response"`
	Processed    bool      `json:"processed"`
	CreatedAt    time.Time `json:"created_at"`
}

type APIKey struct {
	ID          string     `json:"id"`
	KeyHash     string     `json:"-"`
	Name        string     `json:"name"`
	TeamID      string     `json:"team_id,omitempty"`
	Permissions []string   `json:"permissions"`
	LastUsedAt  *time.Time `json:"last_used_at,omitempty"`
	CreatedAt   time.Time  `json:"created_at"`
	ExpiresAt   *time.Time `json:"expires_at,omitempty"`
}

type DailyStats struct {
	ID           string    `json:"id"`
	DomainID     string    `json:"domain_id"`
	Date         time.Time `json:"date"`
	TotalSent    int       `json:"total_sent"`
	TotalOpened  int       `json:"total_opened"`
	TotalClicked int       `json:"total_clicked"`
	TotalBounced int       `json:"total_bounced"`
	UniqueOpens  int       `json:"unique_opens"`
	UniqueClicks int       `json:"unique_clicks"`
	CreatedAt    time.Time `json:"created_at"`
}
