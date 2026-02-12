package api

import (
	"time"

	"github.com/champmail/mail-engine/internal/config"
	"github.com/champmail/mail-engine/internal/db"
	"github.com/champmail/mail-engine/internal/handlers"
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func NewRouter(cfg *config.Config, postgresDB *db.PostgresDB, redisClient *db.RedisClient) *gin.Engine {
	router := gin.Default()

	router.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
		AllowMethods:     []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Authorization", "X-API-Key"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))

	rateLimiter := db.NewRateLimiter(redisClient)

	healthHandler := handlers.NewHealthHandler(postgresDB, redisClient)
	sendHandler := handlers.NewSendHandler(postgresDB, redisClient, rateLimiter, cfg)
	domainHandler := handlers.NewDomainHandler(postgresDB)
	statsHandler := handlers.NewStatsHandler(postgresDB, redisClient)
	trackHandler := handlers.NewTrackHandler(redisClient)

	api := router.Group("/api/v1")
	{
		api.GET("/health", healthHandler.HealthCheck)

		send := api.Group("/send")
		send.Use(handlers.APIKeyAuthMiddleware(redisClient))
		{
			send.POST("", sendHandler.SendEmail)
			send.POST("/batch", sendHandler.SendBatch)
			send.GET("/status/:id", sendHandler.GetStatus)
			send.GET("/stats", statsHandler.GetSendStats)
		}

		domains := api.Group("/domains")
		domains.Use(handlers.APIKeyAuthMiddleware(redisClient))
		{
			domains.GET("", domainHandler.ListDomains)
			domains.POST("", domainHandler.CreateDomain)
			domains.GET("/:id", domainHandler.GetDomain)
			domains.DELETE("/:id", domainHandler.DeleteDomain)
			domains.POST("/:id/verify", domainHandler.VerifyDomain)
			domains.GET("/:id/dns-records", domainHandler.GetDNSRecords)
			domains.GET("/:id/health", domainHandler.GetHealth)
		}

		tracking := router.Group("/track")
		{
			tracking.GET("/open/:message_id", trackHandler.TrackOpen)
			tracking.GET("/click/:message_id", trackHandler.TrackClick)
			tracking.POST("/open", trackHandler.TrackOpenJSON)
			tracking.POST("/click", trackHandler.TrackClickJSON)
		}
	}

	router.GET("/health", healthHandler.HealthCheck)
	router.GET("/", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"name":    "ChampMail Mail Engine",
			"version": "1.0.0",
			"docs":    "/docs",
		})
	})

	return router
}
