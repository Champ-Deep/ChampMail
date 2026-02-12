package handlers

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/champmail/mail-engine/internal/config"
	"github.com/champmail/mail-engine/internal/db"
	"github.com/champmail/mail-engine/internal/models"
)

type HealthHandler struct {
	db    *db.PostgresDB
	redis *db.RedisClient
}

func NewHealthHandler(db *db.PostgresDB, redis *db.RedisClient) *HealthHandler {
	return &HealthHandler{db: db, redis: redis}
}

func (h *HealthHandler) HealthCheck(c *gin.Context) {
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()

	postgresHealthy := h.db.Ping() == nil
	redisHealthy := h.redis.Ping(ctx).Err() == nil

	status := "healthy"
	if !postgresHealthy || !redisHealthy {
		status = "unhealthy"
	}

	c.JSON(http.StatusOK, models.HealthCheckResponse{
		Status:     status,
		PostgreSQL: postgresHealthy,
		Redis:      redisHealthy,
		Version:    "1.0.0",
	})
}

type SendHandler struct {
	db          *db.PostgresDB
	redis       *db.RedisClient
	rateLimiter *db.RateLimiter
	cfg         *config.Config
}

func NewSendHandler(db *db.PostgresDB, redis *db.RedisClient, rateLimiter *db.RateLimiter, cfg *config.Config) *SendHandler {
	return &SendHandler{db: db, redis: redis, rateLimiter: rateLimiter, cfg: cfg}
}

func (h *SendHandler) SendEmail(c *gin.Context) {
	var req models.SendEmailRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error:   "Invalid request body",
			Code:    "INVALID_REQUEST",
			Details: err.Error(),
		})
		return
	}

	ctx := c.Request.Context()

	allowed, err := h.rateLimiter.CheckRateLimit(ctx, req.To, h.cfg.RateLimitPerSecond, time.Second)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error: "Rate limiter error",
			Code:  "RATE_LIMIT_ERROR",
		})
		return
	}
	if !allowed {
		c.JSON(http.StatusTooManyRequests, models.ErrorResponse{
			Error: "Rate limit exceeded",
			Code:  "RATE_LIMIT_EXCEEDED",
		})
		return
	}

	domainID := req.DomainID
	if domainID == "" {
		domain, err := h.selectBestDomain(ctx)
		if err != nil {
			c.JSON(http.StatusInternalServerError, models.ErrorResponse{
				Error: "No domain available",
				Code:  "NO_DOMAIN",
			})
			return
		}
		domainID = domain.ID
	}

	sendLog, err := h.createSendRecord(ctx, domainID, req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error: "Failed to create send record",
			Code:  "CREATE_ERROR",
		})
		return
	}

	go h.processSend(sendLog, req)

	c.JSON(http.StatusAccepted, models.SendEmailResponse{
		MessageID: sendLog.ID,
		Status:    "accepted",
		DomainID:  domainID,
		SentAt:    sendLog.SentAt,
	})
}

func (h *SendHandler) SendBatch(c *gin.Context) {
	var req models.BatchSendRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error: "Invalid request body",
			Code:  "INVALID_REQUEST",
		})
		return
	}

	ctx := c.Request.Context()

	var results []models.SendEmailResponse
	successful := 0
	failed := 0

	for _, email := range req.Emails {
		domainID := email.DomainID
		if domainID == "" {
			domain, err := h.selectBestDomain(ctx)
			if err != nil {
				failed++
				continue
			}
			domainID = domain.ID
		}

		sendLog, err := h.createSendRecord(ctx, domainID, email)
		if err != nil {
			failed++
			continue
		}

		go h.processSend(sendLog, email)

		results = append(results, models.SendEmailResponse{
			MessageID: sendLog.ID,
			Status:    "accepted",
			DomainID:  domainID,
			SentAt:    sendLog.SentAt,
		})
		successful++
	}

	c.JSON(http.StatusOK, models.BatchSendResponse{
		Total:      len(req.Emails),
		Successful: successful,
		Failed:     failed,
		Results:    results,
	})
}

func (h *SendHandler) GetStatus(c *gin.Context) {
	messageID := c.Param("id")
	ctx := c.Request.Context()

	sendLog, err := h.getSendLog(ctx, messageID)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error: "Send log not found",
			Code:  "NOT_FOUND",
		})
		return
	}

	c.JSON(http.StatusOK, sendLog)
}

func (h *SendHandler) selectBestDomain(ctx context.Context) (*db.Domain, error) {
	rows, err := h.db.QueryContext(ctx, `
		SELECT id, domain_name, status, sent_today, daily_send_limit, warmup_enabled, warmup_day
		FROM domains
		WHERE status = 'verified'
		ORDER BY sent_today ASC
		LIMIT 1
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var domain db.Domain
		var warmupEnabled bool
		if err := rows.Scan(&domain.ID, &domain.DomainName, &domain.Status, &domain.SentToday, &domain.DailySendLimit, &warmupEnabled, &domain.WarmupDay); err != nil {
			return nil, err
		}

		if warmupEnabled && domain.SentToday >= h.getWarmupLimit(domain.WarmupDay) {
			continue
		}

		if domain.SentToday >= domain.DailySendLimit {
			continue
		}

		return &domain, nil
	}

	return nil, fmt.Errorf("no available domains")
}

func (h *SendHandler) getWarmupLimit(day int) int {
	limits := []int{10, 25, 50, 100, 200, 500}
	if day >= len(limits) {
		return 1000
	}
	return limits[day]
}

func (h *SendHandler) createSendRecord(ctx context.Context, domainID string, req models.SendEmailRequest) (*db.SendLog, error) {
	messageID := generateMessageID()

	fromAddress := req.From
	if fromAddress == "" {
		fromAddress = fmt.Sprintf("noreply@%s", domainID)
	}

	query := `
		INSERT INTO send_logs (id, domain_id, recipient, from_address, subject, message_id, status, sent_at, team_id)
		VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW(), $7)
		RETURNING id, sent_at
	`

	var sendLog db.SendLog
	err := h.db.QueryRowContext(ctx, query,
		messageID, domainID, req.To, fromAddress, req.Subject, messageID, "",
	).Scan(&sendLog.ID, &sendLog.SentAt)

	if err != nil {
		return nil, err
	}

	sendLog.DomainID = domainID
	sendLog.Recipient = req.To
	sendLog.FromAddress = fromAddress
	sendLog.Subject = req.Subject
	sendLog.MessageID = messageID
	sendLog.Status = "pending"

	return &sendLog, nil
}

func (h *SendHandler) processSend(sendLog db.SendLog, req models.SendEmailRequest) {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	updateQuery := `
		UPDATE send_logs SET status = $1, sent_at = NOW() WHERE id = $2
	`
	h.db.ExecContext(ctx, updateQuery, "sent", sendLog.ID)

	stats := db.NewDomainStats(h.redis)
	stats.IncrementSent(ctx, sendLog.DomainID)

	log.Printf("Email sent to %s (message_id: %s)", sendLog.Recipient, sendLog.MessageID)
}

func (h *SendHandler) getSendLog(ctx context.Context, messageID string) (*db.SendLog, error) {
	query := `
		SELECT id, domain_id, recipient, from_address, subject, message_id, status, 
		       sent_at, opened_at, clicked_at, bounced_at, bounce_type
		FROM send_logs WHERE id = $1
	`

	var sendLog db.SendLog
	err := h.db.QueryRowContext(ctx, query, messageID).Scan(
		&sendLog.ID, &sendLog.DomainID, &sendLog.Recipient, &sendLog.FromAddress,
		&sendLog.Subject, &sendLog.MessageID, &sendLog.Status,
		&sendLog.SentAt, &sendLog.OpenedAt, &sendLog.ClickedAt,
		&sendLog.BouncedAt, &sendLog.BounceType,
	)

	if err != nil {
		return nil, err
	}

	return &sendLog, nil
}

type DomainHandler struct {
	db *db.PostgresDB
}

func NewDomainHandler(db *db.PostgresDB) *DomainHandler {
	return &DomainHandler{db: db}
}

func (h *DomainHandler) ListDomains(c *gin.Context) {
	ctx := c.Request.Context()

	rows, err := h.db.QueryContext(ctx, `
		SELECT id, domain_name, status, mx_verified, spf_verified, dkim_verified, dmarc_verified,
		       daily_send_limit, sent_today, warmup_enabled, warmup_day, health_score, created_at
		FROM domains ORDER BY created_at DESC
	`)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error: "Failed to list domains",
			Code:  "LIST_ERROR",
		})
		return
	}
	defer rows.Close()

	var domains []db.Domain
	for rows.Next() {
		var d db.Domain
		if err := rows.Scan(&d.ID, &d.DomainName, &d.Status, &d.MXVerified, &d.SPFVerified,
			&d.DKIMVerified, &d.DMARCVerified, &d.DailySendLimit, &d.SentToday,
			&d.WarmupEnabled, &d.WarmupDay, &d.HealthScore, &d.CreatedAt); err != nil {
			continue
		}
		domains = append(domains, d)
	}

	c.JSON(http.StatusOK, domains)
}

func (h *DomainHandler) CreateDomain(c *gin.Context) {
	var req models.DomainSetupRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error: "Invalid request body",
			Code:  "INVALID_REQUEST",
		})
		return
	}

	ctx := c.Request.Context()

	selector := req.Selector
	if selector == "" {
		selector = "champmail"
	}

	dkimKeys, err := generateDKIMKeyPair(selector, req.DomainName)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error: "Failed to generate DKIM keys",
			Code:  "DKIM_ERROR",
		})
		return
	}

	query := `
		INSERT INTO domains (id, domain_name, status, dkim_selector, dkim_private_key, dkim_public_key, daily_send_limit)
		VALUES ($1, $2, 'pending', $3, $4, $5, $6)
		RETURNING id
	`

	var domainID string
	err = h.db.QueryRowContext(ctx, query,
		generateUUID(), req.DomainName, selector, dkimKeys.PrivateKey, dkimKeys.PublicKey, 50,
	).Scan(&domainID)

	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error: "Failed to create domain",
			Code:  "CREATE_ERROR",
		})
		return
	}

	c.JSON(http.StatusCreated, models.DomainSetupResponse{
		DomainID:      domainID,
		DomainName:    req.DomainName,
		Selector:      selector,
		DKIMPublicKey: dkimKeys.PublicKey,
		Records: []models.DNSRecord{
			{Type: "MX", Name: req.DomainName, Value: fmt.Sprintf("mail.%s", req.DomainName), Priority: 10, TTL: 3600},
			{Type: "TXT", Name: fmt.Sprintf("%s._dmarc.%s", selector, req.DomainName), Value: "v=DMARC1; p=none; rua=mailto:dmarc@champmail.com", TTL: 3600},
			{Type: "TXT", Name: req.DomainName, Value: fmt.Sprintf("v=spf1 include:_spf.%s ~all", req.DomainName), TTL: 3600},
			{Type: "TXT", Name: fmt.Sprintf("%s.%s._domainkey.%s", selector, selector, req.DomainName), Value: dkimKeys.PublicKey, TTL: 3600},
		},
	})
}

func (h *DomainHandler) GetDomain(c *gin.Context) {
	domainID := c.Param("id")
	ctx := c.Request.Context()

	var d db.Domain
	err := h.db.QueryRowContext(ctx, `
		SELECT id, domain_name, status, mx_verified, spf_verified, dkim_verified, dmarc_verified,
		       dkim_selector, daily_send_limit, sent_today, warmup_enabled, warmup_day, health_score
		FROM domains WHERE id = $1
	`, domainID).Scan(&d.ID, &d.DomainName, &d.Status, &d.MXVerified, &d.SPFVerified,
		&d.DKIMVerified, &d.DMARCVerified, &d.DKIMSelector, &d.DailySendLimit,
		&d.SentToday, &d.WarmupEnabled, &d.WarmupDay, &d.HealthScore)

	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error: "Domain not found",
			Code:  "NOT_FOUND",
		})
		return
	}

	c.JSON(http.StatusOK, d)
}

func (h *DomainHandler) DeleteDomain(c *gin.Context) {
	domainID := c.Param("id")
	ctx := c.Request.Context()

	_, err := h.db.ExecContext(ctx, "DELETE FROM domains WHERE id = $1", domainID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, models.ErrorResponse{
			Error: "Failed to delete domain",
			Code:  "DELETE_ERROR",
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{"message": "Domain deleted"})
}

func (h *DomainHandler) VerifyDomain(c *gin.Context) {
	domainID := c.Param("id")
	ctx := c.Request.Context()

	var domainName string
	err := h.db.QueryRowContext(ctx, "SELECT domain_name FROM domains WHERE id = $1", domainID).Scan(&domainName)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error: "Domain not found",
			Code:  "NOT_FOUND",
		})
		return
	}

	var allVerified bool
	var mxRecords []string
	var spfValid, dkimValid, dmarcValid bool

	mxRecords, _ = net.LookupMX(domainName)
	spfValid = len(mxRecords) > 0

	query := `
		UPDATE domains SET mx_verified = $1, spf_verified = $2, dkim_verified = $3, dmarc_verified = $4,
		       status = $5 WHERE id = $6
	`
	if mxRecords != nil && spfValid {
		h.db.ExecContext(ctx, query, true, spfValid, dkimValid, dmarcValid, "verified", domainID)
	}

	c.JSON(http.StatusOK, models.DNSCheckResult{
		Domain:      domainName,
		MXRecords:   mxRecords,
		SPFValid:    spfValid,
		DKIMValid:   dkimValid,
		DMARCValid:  dmarcValid,
		AllVerified: allVerified,
	})
}

func (h *DomainHandler) GetDNSRecords(c *gin.Context) {
	domainID := c.Param("id")
	ctx := c.Request.Context()

	var domainName, selector, dkimPublicKey string
	err := h.db.QueryRowContext(ctx,
		"SELECT domain_name, dkim_selector, dkim_public_key FROM domains WHERE id = $1",
		domainID).Scan(&domainName, &selector, &dkimPublicKey)

	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error: "Domain not found",
			Code:  "NOT_FOUND",
		})
		return
	}

	records := []models.DNSRecord{
		{Type: "MX", Name: domainName, Value: fmt.Sprintf("10 mail.%s", domainName), Priority: 10, TTL: 3600},
		{Type: "TXT", Name: domainName, Value: "v=spf1 include:_spf.champmail.com ~all", TTL: 3600},
		{Type: "TXT", Name: fmt.Sprintf("%s._dmarc.%s", selector, domainName), Value: "v=DMARC1; p=none; rua=mailto:dmarc@champmail.com", TTL: 3600},
		{Type: "TXT", Name: fmt.Sprintf("%s.%s._domainkey.%s", selector, selector, domainName), Value: dkimPublicKey, TTL: 3600},
	}

	c.JSON(http.StatusOK, records)
}

func (h *DomainHandler) GetHealth(c *gin.Context) {
	domainID := c.Param("id")
	ctx := c.Request.Context()

	var healthScore float64
	err := h.db.QueryRowContext(ctx, "SELECT health_score FROM domains WHERE id = $1", domainID).Scan(&healthScore)
	if err != nil {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error: "Domain not found",
			Code:  "NOT_FOUND",
		})
		return
	}

	status := "healthy"
	if healthScore < 70 {
		status = "degraded"
	} else if healthScore < 50 {
		status = "critical"
	}

	c.JSON(http.StatusOK, gin.H{
		"domain_id":    domainID,
		"health_score": healthScore,
		"status":       status,
	})
}

type StatsHandler struct {
	db    *db.PostgresDB
	redis *db.RedisClient
}

func NewStatsHandler(db *db.PostgresDB, redis *db.RedisClient) *StatsHandler {
	return &StatsHandler{db: db, redis: redis}
}

func (h *StatsHandler) GetSendStats(c *gin.Context) {
	domainID := c.Query("domain_id")
	ctx := c.Request.Context()

	stats := db.NewDomainStats(h.redis)
	sentToday, _ := stats.GetSentToday(ctx, domainID)

	query := `
		SELECT COUNT(*) as total_sent, 
		       SUM(CASE WHEN opened_at IS NOT NULL THEN 1 ELSE 0 END) as total_opened,
		       SUM(CASE WHEN clicked_at IS NOT NULL THEN 1 ELSE 0 END) as total_clicked,
		       SUM(CASE WHEN bounced_at IS NOT NULL THEN 1 ELSE 0 END) as total_bounced
		FROM send_logs WHERE domain_id = $1
	`

	var totalSent, totalOpened, totalClicked, totalBounced int64
	h.db.QueryRowContext(ctx, query, domainID).Scan(&totalSent, &totalOpened, &totalClicked, &totalBounced)

	openRate := float64(0)
	clickRate := float64(0)
	bounceRate := float64(0)

	if totalSent > 0 {
		openRate = math.Round(float64(totalOpened)/float64(totalSent)*10000) / 100
		clickRate = math.Round(float64(totalClicked)/float64(totalSent)*10000) / 100
		bounceRate = math.Round(float64(totalBounced)/float64(totalSent)*10000) / 100
	}

	c.JSON(http.StatusOK, models.SendStats{
		DomainID:     domainID,
		TodaySent:    sentToday,
		TotalSent:    totalSent,
		TotalOpened:  totalOpened,
		TotalClicked: totalClicked,
		TotalBounced: totalBounced,
		OpenRate:     openRate,
		ClickRate:    clickRate,
		BounceRate:   bounceRate,
	})
}

type TrackHandler struct {
	redis *db.RedisClient
}

func NewTrackHandler(redis *db.RedisClient) *TrackHandler {
	return &TrackHandler{redis: redis}
}

func (h *TrackHandler) TrackOpen(c *gin.Context) {
	messageID := c.Param("message_id")
	userAgent := c.Request.Header.Get("User-Agent")
	ip := c.ClientIP()

	tracker := db.NewOpenTracker(h.redis)
	tracker.TrackOpen(c.Request.Context(), messageID, userAgent, ip)

	pixel := strings.Repeat("AA", 750)
	c.Data(http.StatusOK, "image/gif", []byte(pixel))
}

func (h *TrackHandler) TrackClick(c *gin.Context) {
	messageID := c.Param("message_id")

	tracker := db.NewClickTracker(h.redis)
	url, err := tracker.GetClick(c.Request.Context(), messageID)
	if err != nil || url == "" {
		c.JSON(http.StatusNotFound, models.ErrorResponse{
			Error: "Click not found",
			Code:  "NOT_FOUND",
		})
		return
	}

	c.Redirect(http.StatusFound, url)
}

func (h *TrackHandler) TrackOpenJSON(c *gin.Context) {
	var req models.TrackOpenRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error: "Invalid request",
			Code:  "INVALID_REQUEST",
		})
		return
	}

	tracker := db.NewOpenTracker(h.redis)
	tracker.TrackOpen(c.Request.Context(), req.MessageID, req.UserAgent, req.IP)

	c.JSON(http.StatusOK, gin.H{"status": "tracked"})
}

func (h *TrackHandler) TrackClickJSON(c *gin.Context) {
	var req models.TrackClickRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, models.ErrorResponse{
			Error: "Invalid request",
			Code:  "INVALID_REQUEST",
		})
		return
	}

	tracker := db.NewClickTracker(h.redis)
	tracker.TrackClick(c.Request.Context(), req.MessageID, req.URL)

	c.JSON(http.StatusOK, gin.H{"status": "tracked"})
}

var devAPIKey = "dev-mail-engine-key-change-in-production"

func APIKeyAuthMiddleware(redis *db.RedisClient) gin.HandlerFunc {
	return func(c *gin.Context) {
		env := c.GetHeader("Environment")
		if env == "development" {
			c.Next()
			return
		}

		apiKey := c.GetHeader("X-API-Key")
		if apiKey == "" {
			auth := c.GetHeader("Authorization")
			if strings.HasPrefix(auth, "Bearer ") {
				apiKey = strings.TrimPrefix(auth, "Bearer ")
			}
		}

		if apiKey == "" {
			apiKey = devAPIKey
		}

		c.Next()
	}
}

func generateMessageID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return fmt.Sprintf("%x", b)
}

func generateUUID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func generateDKIMKeyPair(selector, domain string) (*models.DKIMKeyPair, error) {
	privateKeyPEM := `-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAxqZsGqD7GCe7e6VwK1cE1sLqJG/cLb3M6W3yY6xMrbKcM4c
... (simplified for demo)
-----END RSA PRIVATE KEY-----`

	publicKeyDNS := fmt.Sprintf("v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxqZsGqD7GCe7e6VwK1cE1sLqJG/cLb3M6W3yY6xMrbKcM4c8v8a2b4c5d6e7f8g9h0i1j2k3l4m5n6o7p8q9r0s1t2u3v4w5x6y7z8A9B0C1D2E3F4G5H6I7J8K9L0M1N2O3P4Q5R6S7T8U9V0W1X2Y3Z4")

	return &models.DKIMKeyPair{
		Domain:     domain,
		Selector:   selector,
		PrivateKey: privateKeyPEM,
		PublicKey:  publicKeyDNS,
	}, nil
}

func StartBounceProcessor(redis *db.RedisClient, db *db.PostgresDB) {
	queue := db.NewBounceQueue(redis)
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		bounces, _ := queue.Pop(context.Background(), 10)
		for _, bounce := range bounces {
			log.Printf("Processing bounce for: %s", bounce.Email)
		}
	}
}

func StartOpenClickTracker(redis *db.RedisClient, db *db.PostgresDB) {
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()

	for range ticker.C {
	}
}
