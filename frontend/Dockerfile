# ChampMail Frontend Dockerfile
# Multi-stage build with nginx for production

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Build arguments for environment variables
# Use relative path so nginx can proxy to backend
ARG VITE_API_URL=/api/v1
ARG VITE_N8N_WEBHOOK_URL=https://championtest.up.railway.app/webhook/email_agent

# Set environment variables for build
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_N8N_WEBHOOK_URL=$VITE_N8N_WEBHOOK_URL

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy nginx config template (envsubst replaces $PORT and $BACKEND_URL at runtime)
COPY nginx.conf.template /etc/nginx/conf.d/default.conf.template

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Railway assigns PORT dynamically; default to 80 for local Docker
ENV PORT=80
ENV BACKEND_URL=http://backend:8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:${PORT}/ || exit 1

# Use envsubst to inject PORT and BACKEND_URL into nginx config, then start nginx
CMD sh -c "envsubst '\$PORT \$BACKEND_URL' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"
