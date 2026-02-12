package db

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/champmail/mail-engine/internal/config"
	"github.com/redis/go-redis/v9"
)

type RedisClient struct {
	*redis.Client
}

func NewRedisClient(cfg *config.Config) (*RedisClient, error) {
	client := redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", cfg.RedisHost, cfg.RedisPort),
		Password: cfg.RedisPassword,
		DB:       cfg.RedisDB,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to ping Redis: %w", err)
	}

	return &RedisClient{client}, nil
}

type RateLimiter struct {
	client *RedisClient
}

func NewRateLimiter(client *RedisClient) *RateLimiter {
	return &RateLimiter{client: client}
}

func (r *RateLimiter) CheckRateLimit(ctx context.Context, key string, limit int, window time.Duration) (bool, error) {
	count, err := r.client.incrBy(ctx, fmt.Sprintf("ratelimit:%s", key), 1)
	if err != nil {
		return false, err
	}

	if count == 1 {
		r.client.Expire(ctx, fmt.Sprintf("ratelimit:%s", key), window)
	}

	return count <= int64(limit), nil
}

func (r *RedisClient) incrBy(ctx context.Context, key string, delta int64) (int64, error) {
	return r.IncrBy(ctx, key, delta).Result()
}

type ClickTracker struct {
	client *RedisClient
}

func NewClickTracker(client *RedisClient) *ClickTracker {
	return &ClickTracker{client: client}
}

func (t *ClickTracker) TrackClick(ctx context.Context, messageID string, url string) error {
	key := fmt.Sprintf("clicks:%s", messageID)
	t.client.HSet(ctx, key, "url", url, "timestamp", time.Now().Unix())
	t.client.Expire(ctx, key, 24*time.Hour)
	return nil
}

func (t *ClickTracker) GetClick(ctx context.Context, messageID string) (string, error) {
	return t.client.HGet(ctx, fmt.Sprintf("clicks:%s", messageID), "url").Result()
}

type OpenTracker struct {
	client *RedisClient
}

func NewOpenTracker(client *RedisClient) *OpenTracker {
	return &OpenTracker{client: client}
}

func (t *OpenTracker) TrackOpen(ctx context.Context, messageID string, userAgent string, ip string) error {
	key := fmt.Sprintf("opens:%s", messageID)
	t.client.HSet(ctx, key,
		"timestamp", time.Now().Unix(),
		"user_agent", userAgent,
		"ip", ip,
	)
	t.client.Expire(ctx, key, 24*time.Hour)
	return nil
}

func (t *OpenTracker) IsTracked(ctx context.Context, messageID string) (bool, error) {
	return t.client.Exists(ctx, fmt.Sprintf("opens:%s", messageID)).Result()
}

type BounceQueue struct {
	client *RedisClient
}

func NewBounceQueue(client *RedisClient) *BounceQueue {
	return &BounceQueue{client: client}
}

func (q *BounceQueue) Push(ctx context.Context, bounce Bounce) error {
	score := float64(time.Now().Unix())
	member := fmt.Sprintf("%s:%s:%s", bounce.Email, bounce.BounceType, bounce.SMTPResponse)
	return q.client.ZAdd(ctx, "bounce_queue", redis.Z{
		Score:  score,
		Member: member,
	}).Err()
}

func (q *BounceQueue) Pop(ctx context.Context, count int64) ([]Bounce, error) {
	result, err := q.client.ZPopMin(ctx, "bounce_queue", count).Result()
	if err != nil {
		return nil, err
	}

	bounces := make([]Bounce, 0, len(result))
	for _, z := range result {
		bounce := Bounce{
			Email:      z.Member.(string),
			BounceType: "unknown",
		}
		bounces = append(bounces, bounce)
	}

	return bounces, nil
}

type DomainStats struct {
	client *RedisClient
}

func NewDomainStats(client *RedisClient) *DomainStats {
	return &DomainStats{client: client}
}

func (s *DomainStats) IncrementSent(ctx context.Context, domainID string) error {
	key := fmt.Sprintf("stats:%s:sent", domainID)
	now := time.Now()
	dayKey := fmt.Sprintf("%s:%s", key, now.Format("2006-01-02"))

	s.client.Incr(ctx, dayKey)
	s.client.Expire(ctx, dayKey, 48*time.Hour)
	return nil
}

func (s *DomainStats) GetSentToday(ctx context.Context, domainID string) (int, error) {
	key := fmt.Sprintf("stats:%s:sent:%s", domainID, time.Now().Format("2006-01-02"))
	result, err := s.client.Get(ctx, key).Result()
	if err == redis.Nil {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	return strconv.Atoi(result)
}
