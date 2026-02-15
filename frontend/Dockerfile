# ChampMail Frontend Dockerfile
# Multi-stage build with nginx for production

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Build arguments for environment variables
# VITE_API_URL is hardcoded to /api/v1 so nginx proxies API calls to the backend.
# Do NOT set VITE_API_URL as a Railway service variable — it would override this at build time.
ARG VITE_N8N_WEBHOOK_URL=https://championtest.up.railway.app/webhook/email_agent

# Set environment variables for build
ENV VITE_API_URL=/api/v1
ENV VITE_N8N_WEBHOOK_URL=$VITE_N8N_WEBHOOK_URL

# Copy package files and npm config
COPY package*.json .npmrc ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Remove default nginx config to avoid conflicts
RUN rm -f /etc/nginx/conf.d/default.conf

# Copy nginx config template (envsubst replaces $PORT and $BACKEND_URL at runtime)
COPY nginx.conf.template /etc/nginx/conf.d/default.conf.template

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Railway assigns PORT dynamically; default to 80 for local Docker
ENV PORT=80
ENV BACKEND_URL=http://backend:8000

EXPOSE ${PORT}

# Use entrypoint script to substitute env vars and start nginx
CMD ["/docker-entrypoint.sh"]
