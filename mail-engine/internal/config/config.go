package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	ServerPort  string
	Environment string
	Debug       bool

	PostgresHost            string
	PostgresPort            int
	PostgresUser            string
	PostgresPassword        string
	PostgresDB              string
	PostgresMaxOpenConns    int
	PostgresMaxIdleConns    int
	PostgresConnMaxLifetime time.Duration

	RedisHost     string
	RedisPort     int
	RedisPassword string
	RedisDB       int

	DKIMSelector       string
	DKIMDomain         string
	DKIMPrivateKeyPath string

	DailySendLimit      int
	RateLimitPerSecond  int
	BounceCheckInterval time.Duration

	APIKeys map[string]string
}

func Load() (*Config, error) {
	cfg := &Config{
		ServerPort:  getEnv("SERVER_PORT", "8025"),
		Environment: getEnv("ENVIRONMENT", "development"),
		Debug:       getEnvAsBool("DEBUG", false),

		PostgresHost:            getEnv("POSTGRES_HOST", "postgres"),
		PostgresPort:            getEnvAsInt("POSTGRES_PORT", 5432),
		PostgresUser:            getEnv("POSTGRES_USER", "champmail"),
		PostgresPassword:        getEnv("POSTGRES_PASSWORD", "champmail_dev"),
		PostgresDB:              getEnv("POSTGRES_DB", "champmail"),
		PostgresMaxOpenConns:    getEnvAsInt("POSTGRES_MAX_OPEN_CONNS", 25),
		PostgresMaxIdleConns:    getEnvAsInt("POSTGRES_MAX_IDLE_CONNS", 5),
		PostgresConnMaxLifetime: getEnvAsDuration("POSTGRES_CONN_MAX_LIFETIME", time.Hour),

		RedisHost:     getEnv("REDIS_HOST", "redis"),
		RedisPort:     getEnvAsInt("REDIS_PORT", 6379),
		RedisPassword: getEnv("REDIS_PASSWORD", ""),
		RedisDB:       getEnvAsInt("REDIS_DB", 0),

		DKIMSelector:       getEnv("DKIM_SELECTOR", "champmail"),
		DKIMDomain:         getEnv("DKIM_DOMAIN", "champmail.com"),
		DKIMPrivateKeyPath: getEnv("DKIM_PRIVATE_KEY_PATH", "/etc/champmail/dkim/private.pem"),

		DailySendLimit:      getEnvAsInt("DAILY_SEND_LIMIT", 1000),
		RateLimitPerSecond:  getEnvAsInt("RATE_LIMIT_PER_SECOND", 10),
		BounceCheckInterval: getEnvAsDuration("BOUNCE_CHECK_INTERVAL", time.Minute*5),

		APIKeys: make(map[string]string),
	}

	if apiKey := os.Getenv("MASTER_API_KEY"); apiKey != "" {
		cfg.APIKeys["master"] = apiKey
	}

	return cfg, nil
}

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func getEnvAsInt(key string, defaultValue int) int {
	if value := os.Getenv(key); value != "" {
		if parsed, err := strconv.Atoi(value); err == nil {
			return parsed
		}
	}
	return defaultValue
}

func getEnvAsBool(key string, defaultValue bool) bool {
	if value := os.Getenv(key); value != "" {
		return value == "true" || value == "1"
	}
	return defaultValue
}

func getEnvAsDuration(key string, defaultValue time.Duration) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue.String()
}
