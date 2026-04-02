#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ChampMail — One-shot installer
#
# Works on: Ubuntu 20.04+, Debian 11+, macOS 13+
# Run as a regular user (NOT root). sudo is invoked automatically where needed.
#
# Usage:
#   bash install.sh                         # interactive (prompts for API key)
#   OPENROUTER_API_KEY=sk-or-v1-... bash install.sh   # fully non-interactive
#   bash install.sh --skip-graphiti         # skip ChampGraph / Neo4j setup
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── colours ──────────────────────────────────────────────────────────────────
CYAN='\033[1;36m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'
RED='\033[1;31m'; RESET='\033[0m'; DIM='\033[2m'

log()  { echo -e "${CYAN}  →${RESET} $*"; }
ok()   { echo -e "${GREEN}  ✓${RESET} $*"; }
warn() { echo -e "${YELLOW}  ⚠${RESET} $*"; }
die()  { echo -e "${RED}  ✗ ERROR:${RESET} $*" >&2; exit 1; }
hr()   { echo -e "${DIM}  $(printf '─%.0s' {1..60})${RESET}"; }

# ── flags ─────────────────────────────────────────────────────────────────────
SKIP_GRAPHITI=false
for arg in "$@"; do [[ "$arg" == "--skip-graphiti" ]] && SKIP_GRAPHITI=true; done

# ── detect OS ─────────────────────────────────────────────────────────────────
OS="linux"
if [[ "$(uname)" == "Darwin" ]]; then OS="mac"; fi

# ── banner ────────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "${CYAN}"
cat << 'BANNER'
  ██████╗██╗  ██╗ █████╗ ███╗   ███╗██████╗ ███╗   ███╗ █████╗ ██╗██╗
 ██╔════╝██║  ██║██╔══██╗████╗ ████║██╔══██╗████╗ ████║██╔══██╗██║██║
 ██║     ███████║███████║██╔████╔██║██████╔╝██╔████╔██║███████║██║██║
 ██║     ██╔══██║██╔══██║██║╚██╔╝██║██╔═══╝ ██║╚██╔╝██║██╔══██║██║██║
 ╚██████╗██║  ██║██║  ██║██║ ╚═╝ ██║██║     ██║ ╚═╝ ██║██║  ██║██║███████╗
  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝╚══════╝
BANNER
echo -e "${RESET}"
echo -e "  ${DIM}AI-Powered Cold-Email Outreach Platform — Installer v1.0${RESET}"
echo ""
hr

# ── resolve install directory ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
CHAMPMAIL_DIR="$SCRIPT_DIR"
GRAPHITI_DIR="$(dirname "$CHAMPMAIL_DIR")/Graphiti-knowledge-graph"

log "ChampMail directory : $CHAMPMAIL_DIR"
log "ChampGraph directory: $GRAPHITI_DIR"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — System dependencies
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [1/8] System dependencies${RESET}"
hr

if [[ "$OS" == "mac" ]]; then
  if ! command -v brew &>/dev/null; then
    log "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  fi
  for pkg in git python3 docker; do
    if ! command -v "$pkg" &>/dev/null; then
      log "Installing $pkg via brew..."
      brew install "$pkg" || true
    fi
  done
else
  # Linux (Debian/Ubuntu)
  if command -v apt-get &>/dev/null; then
    log "Updating apt packages..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
      git curl wget ca-certificates gnupg lsb-release \
      python3 python3-pip python3-venv python3-dev \
      build-essential libpq-dev 2>/dev/null || true
  fi
fi
ok "System packages ready"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Docker
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [2/8] Docker & Docker Compose${RESET}"
hr

if ! command -v docker &>/dev/null; then
  if [[ "$OS" == "linux" ]]; then
    log "Installing Docker Engine..."
    curl -fsSL https://get.docker.com | sudo bash
    sudo usermod -aG docker "$USER"
    warn "Docker installed. You may need to log out and back in for group changes."
    warn "If docker commands fail, run:  newgrp docker"
  else
    die "Docker not found. Install Docker Desktop from https://www.docker.com/products/docker-desktop"
  fi
else
  ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
fi

if ! docker compose version &>/dev/null && ! docker-compose version &>/dev/null; then
  if [[ "$OS" == "linux" ]]; then
    log "Installing Docker Compose plugin..."
    sudo apt-get install -y docker-compose-plugin 2>/dev/null || \
      sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose
  fi
fi
ok "Docker Compose ready"

# Compose command (v2 plugin vs legacy)
if docker compose version &>/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Clone / verify repos
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [3/8] Repositories${RESET}"
hr

# ChampMail repo
if [[ ! -f "$CHAMPMAIL_DIR/docker-compose.yml" ]]; then
  log "Cloning ChampMail..."
  git clone https://github.com/developer00777/Champ_mail.git "$CHAMPMAIL_DIR"
else
  ok "ChampMail repo found at $CHAMPMAIL_DIR"
fi

# Graphiti / ChampGraph repo
if [[ "$SKIP_GRAPHITI" == "false" ]]; then
  if [[ ! -f "$GRAPHITI_DIR/docker-compose.yml" ]]; then
    log "Cloning ChampGraph (Graphiti knowledge graph)..."
    git clone https://github.com/developer00777/Graphiti-knowledge-graph.git "$GRAPHITI_DIR" 2>/dev/null || \
    git clone https://github.com/getzep/graphiti.git "$GRAPHITI_DIR" 2>/dev/null || \
    warn "Could not clone ChampGraph repo — skipping. You can add it manually later."
  else
    ok "ChampGraph repo found at $GRAPHITI_DIR"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Collect required secrets
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [4/8] Configuration${RESET}"
hr

# OpenRouter API key
if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo ""
  echo -e "  You need an OpenRouter API key for all AI features."
  echo -e "  ${DIM}Get one free at: https://openrouter.ai/keys${RESET}"
  echo ""
  read -rp "  Enter your OpenRouter API key (sk-or-v1-...): " OPENROUTER_API_KEY
  echo ""
fi
[[ -z "$OPENROUTER_API_KEY" ]] && die "OpenRouter API key is required."

# Generate secrets
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
EMAIL_ENC_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
NEO4J_PASS=$(python3 -c "import secrets; print(secrets.token_hex(12))")
PG_PASS=$(python3 -c "import secrets; print(secrets.token_hex(12))")

ok "Secrets generated"

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Write .env files
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [5/8] Writing environment files${RESET}"
hr

# ── ChampMail .env ────────────────────────────────────────────────────────────
cat > "$CHAMPMAIL_DIR/.env" << EOF
# ChampMail — generated by install.sh
# ────────────────────────────────────

# Application
DEBUG=false
ENVIRONMENT=production

# PostgreSQL
POSTGRES_HOST=postgres
POSTGRES_USER=champmail
POSTGRES_PASSWORD=$PG_PASS
POSTGRES_DB=champmail
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6380

# ChampGraph (Knowledge Graph)
CHAMPGRAPH_URL=http://champ-graph:8080
CHAMPGRAPH_API_KEY=

# Security
JWT_SECRET_KEY=$JWT_SECRET
EMAIL_ENCRYPTION_KEY=$EMAIL_ENC_KEY

# AI — OpenRouter (one key for all AI features)
OPENROUTER_API_KEY=$OPENROUTER_API_KEY
GENERAL_MODEL=openai/gpt-4.1-mini

# SMTP — update after running: champmail setup smtp
SMTP_HOST=smtp.ethereal.email
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
MAIL_FROM_EMAIL=
MAIL_FROM_NAME=ChampMail

# IMAP — update after running: champmail setup imap
IMAP_HOST=imap.ethereal.email
IMAP_PORT=993
IMAP_USERNAME=
IMAP_PASSWORD=
IMAP_USE_SSL=true
IMAP_MAILBOX=INBOX

# Public URLs
PUBLIC_API_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000

# DNS (optional — for domain management)
CLOUDFLARE_API_TOKEN=
NAMECHEAP_API_KEY=
EOF

ok "ChampMail .env written"

# ── ChampGraph .env ───────────────────────────────────────────────────────────
if [[ "$SKIP_GRAPHITI" == "false" && -d "$GRAPHITI_DIR" ]]; then
  cat > "$GRAPHITI_DIR/.env" << EOF
# ChampGraph — generated by install.sh

CHAMP_GRAPH_API_KEY=
OPENAI_API_KEY=$OPENROUTER_API_KEY
OPENAI_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=openai/gpt-4.1-mini
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=$NEO4J_PASS
EMBEDDING_MODEL=openai/text-embedding-3-small
TEAM_DOMAINS=champmail.dev
API_HOST=0.0.0.0
API_PORT=8080
CORS_ORIGINS=
EOF
  ok "ChampGraph .env written"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — Start ChampGraph (Neo4j + knowledge graph)
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [6/8] Starting ChampGraph (Neo4j + knowledge graph API)${RESET}"
hr

if [[ "$SKIP_GRAPHITI" == "false" && -d "$GRAPHITI_DIR" ]]; then
  cd "$GRAPHITI_DIR"
  log "Pulling ChampGraph images..."
  $DC pull --quiet 2>/dev/null || true
  log "Starting Neo4j and ChampGraph..."
  $DC up -d
  log "Waiting for Neo4j to become healthy (up to 90s)..."
  for i in $(seq 1 18); do
    sleep 5
    if docker inspect graphiti-knowledge-graph-neo4j-1 &>/dev/null && \
       [[ "$(docker inspect --format='{{.State.Health.Status}}' graphiti-knowledge-graph-neo4j-1 2>/dev/null)" == "healthy" ]]; then
      ok "Neo4j is healthy"
      break
    fi
    echo -ne "  ${DIM}waiting... ${i}/18${RESET}\r"
  done
  cd "$CHAMPMAIL_DIR"
else
  warn "Skipping ChampGraph setup (--skip-graphiti)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — Connect networks + Start ChampMail stack
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [7/8] Starting ChampMail stack${RESET}"
hr

cd "$CHAMPMAIL_DIR"
log "Pulling ChampMail images..."
$DC pull --quiet 2>/dev/null || true
log "Building and starting all services..."
$DC up -d --build

log "Waiting for backend to become healthy (up to 120s)..."
for i in $(seq 1 24); do
  sleep 5
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' champmail-backend 2>/dev/null || echo "starting")
  if [[ "$STATUS" == "healthy" ]]; then
    ok "Backend is healthy"
    break
  fi
  echo -ne "  ${DIM}waiting... ${i}/24 (${STATUS})${RESET}\r"
done

# Connect ChampGraph to ChampMail network (so they can talk)
if [[ "$SKIP_GRAPHITI" == "false" ]]; then
  log "Connecting ChampGraph to ChampMail network..."
  docker network connect champmail-main-1_champmail-network \
    graphiti-knowledge-graph-champ-graph-1 2>/dev/null && ok "Networks connected" || \
    warn "Network connect skipped (may already be connected)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — Install CLI globally
# ─────────────────────────────────────────────────────────────────────────────
hr
echo -e "${CYAN}  [8/8] Installing champmail CLI${RESET}"
hr

# Install Python deps for CLI (direct service-layer invocation)
log "Installing Python dependencies..."
cd "$CHAMPMAIL_DIR/backend"
python3 -m pip install --quiet --user -r requirements.txt 2>/dev/null || \
  pip3 install --quiet --user -r requirements.txt 2>/dev/null || \
  warn "pip install failed — CLI may not work. Run: pip3 install -r backend/requirements.txt"

# Make CLI script executable
chmod +x "$CHAMPMAIL_DIR/champmail"

# Symlink to ~/.local/bin
mkdir -p "$HOME/.local/bin"
ln -sf "$CHAMPMAIL_DIR/champmail" "$HOME/.local/bin/champmail"

# Ensure ~/.local/bin is in PATH
SHELL_RC="$HOME/.bashrc"
[[ -n "${ZSH_VERSION:-}" || "$SHELL" == *zsh* ]] && SHELL_RC="$HOME/.zshrc"
if ! grep -q '\.local/bin' "$SHELL_RC" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
  log "Added ~/.local/bin to PATH in $SHELL_RC"
fi
export PATH="$HOME/.local/bin:$PATH"

ok "champmail CLI installed"

# ─────────────────────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────────────────────
cd "$CHAMPMAIL_DIR"
echo ""
hr
echo ""
echo -e "  ${GREEN}Installation complete!${RESET}"
echo ""
echo -e "  ${CYAN}Services running:${RESET}"
echo -e "  ${DIM}  Frontend     →  http://localhost:3000${RESET}"
echo -e "  ${DIM}  Backend API  →  http://localhost:8000${RESET}"
echo -e "  ${DIM}  Flower       →  http://localhost:5555${RESET}"
echo -e "  ${DIM}  ChampGraph   →  http://localhost:8080${RESET}"
echo -e "  ${DIM}  Neo4j        →  http://localhost:7474${RESET}"
echo ""
echo -e "  ${CYAN}Get started:${RESET}"
echo -e "  ${DIM}  source ~/.bashrc            # reload PATH (or open a new terminal)${RESET}"
echo -e "  ${DIM}  champmail health check      # verify all systems green${RESET}"
echo -e "  ${DIM}  champmail auth login \\${RESET}"
echo -e "  ${DIM}    --email admin@champions.dev --password admin123${RESET}"
echo -e "  ${DIM}  champmail chat              # start the AI assistant${RESET}"
echo ""
echo -e "  ${CYAN}First-time setup (inside chat or CLI):${RESET}"
echo -e "  ${DIM}  champmail setup smtp        # configure your email provider${RESET}"
echo -e "  ${DIM}  champmail setup imap        # configure reply detection${RESET}"
echo -e "  ${DIM}  champmail setup ai          # confirm your OpenRouter key${RESET}"
echo ""
hr
echo ""
