package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/champmail/mail-engine/internal/api"
	"github.com/champmail/mail-engine/internal/config"
	"github.com/champmail/mail-engine/internal/db"
	"github.com/champmail/mail-engine/internal/handlers"
)

func main() {
	log.Println("Starting ChampMail Mail Engine...")

	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	postgresDB, err := db.NewPostgresDB(cfg)
	if err != nil {
		log.Fatalf("Failed to connect to PostgreSQL: %v", err)
	}
	defer postgresDB.Close()

	redisClient, err := db.NewRedisClient(cfg)
	if err != nil {
		log.Fatalf("Failed to connect to Redis: %v", err)
	}
	defer redisClient.Close()

	router := api.NewRouter(cfg, postgresDB, redisClient)

	go func() {
		handlers.StartBounceProcessor(redisClient, postgresDB)
	}()

	go func() {
		handlers.StartOpenClickTracker(redisClient, postgresDB)
	}()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	serverAddr := ":" + cfg.ServerPort
	log.Printf("ChampMail Mail Engine listening on %s", serverAddr)
	log.Printf("Health check: http://localhost:%s/health", cfg.ServerPort)
	log.Printf("API docs: http://localhost:%s/docs", cfg.ServerPort)

	if err := router.Run(serverAddr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
