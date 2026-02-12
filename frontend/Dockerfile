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

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Run nginx
CMD ["nginx", "-g", "daemon off;"]
