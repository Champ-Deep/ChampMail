<div align="center">

# 📧 ChampMail

**Self-hosted, AI-powered cold email outreach platform**

Own your deliverability. Own your data. Own your pipeline.

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway&logoColor=white)](https://railway.app)
[![License](https://img.shields.io/badge/License-AGPL--3.0-blue)](LICENSE)

</div>

---

## ✨ What is ChampMail?

ChampMail is a **full-stack email outreach platform** that replaces tools like Instantly, Smartlead, and Woodpecker — without monthly per-seat fees or third-party SMTP dependencies.

**Key difference:** ChampMail includes its own **mail engine**, so you send email directly from your infrastructure. No Mailgun. No SendGrid. Full control over deliverability and reputation.

### 🎯 Core Features

| Feature | Description |
|---------|-------------|
| 📬 **Built-in Mail Engine** | Send & receive directly — SMTP out, IMAP in |
| 🤖 **AI Personalization** | Claude-powered email generation via OpenRouter |
| 📊 **Open & Click Tracking** | Real-time analytics with pixel tracking + link wrapping |
| 🔄 **Multi-domain Rotation** | Rotate sender domains to protect deliverability |
| 👥 **Prospect Management** | CSV import, dedup, segmentation |
| 📝 **Template Builder** | Drag-and-drop MJML email editor |
| 🔐 **Team Management** | Multi-user with JWT auth and role-based access |
| 🌐 **DNS Management** | Cloudflare integration for SPF/DKIM/DMARC setup |
| 📈 **Campaign Analytics** | Sends, opens, clicks, bounces, replies |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)           │
│                    Tailwind CSS · Nginx              │
└──────────────────────┬──────────────────────────────┘
                       │ REST API
┌──────────────────────▼──────────────────────────────┐
│                 Backend (FastAPI)                     │
│  Auth · Campaigns · Templates · Tracking · Analytics │
├──────────┬───────────┬───────────┬──────────────────┤
│ PostgreSQL│   Redis   │ FalkorDB  │   Mail Engine    │
│  (Users,  │  (Cache,  │  (Graph,  │   (Go · SMTP     │
│  Campaigns│  Sessions)│  optional)│    outbound)     │
│  Domains) │           │           │                  │
└──────────┴───────────┴───────────┴──────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- [OpenRouter](https://openrouter.ai/) API key (for AI features)

### 1. Clone & configure

```bash
git clone https://github.com/Champ-Deep/ChampMail.git
cd ChampMail
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start everything

```bash
docker compose up -d
```

### 3. Open the app

| Service | URL |
|---------|-----|
| 🖥️ Frontend | [localhost:3000](http://localhost:3000) |
| 📡 API Docs | [localhost:8000/docs](http://localhost:8000/docs) |
| ❤️ Health Check | [localhost:8000/health](http://localhost:8000/health) |

**Default login:** `admin@champions.dev` / `admin123`

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, Vite, Tailwind CSS, Zustand |
| **Backend** | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| **Database** | PostgreSQL 16 (asyncpg) |
| **Cache** | Redis 7 |
| **Graph DB** | FalkorDB (optional — knowledge graph features) |
| **Mail Engine** | Go (custom SMTP sender with tracking injection) |
| **AI** | OpenRouter (Claude, GPT-4, Gemini, Perplexity) |
| **Auth** | JWT with bcrypt password hashing |
| **DNS** | Cloudflare API for domain verification |
| **Deployment** | Docker, Railway |

---

## 📂 Project Structure

```
ChampMail/
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── api/v1/          # REST endpoints
│   │   ├── core/            # Config, security
│   │   ├── db/              # PostgreSQL, Redis, FalkorDB
│   │   ├── models/          # SQLAlchemy models
│   │   ├── services/        # Business logic
│   │   └── middleware/       # Rate limiting
│   ├── alembic/             # Database migrations
│   ├── scripts/             # Startup scripts
│   ├── Dockerfile
│   └── railway.toml
├── frontend/                # React SPA
│   ├── src/
│   │   ├── components/      # UI components
│   │   ├── pages/           # Route pages
│   │   ├── stores/          # Zustand state
│   │   └── api/             # API client
│   ├── Dockerfile
│   └── railway.toml
├── mail-engine/             # Go SMTP service
├── infrastructure/          # Docker configs for data layer
├── docs/                    # Deployment & testing guides
├── docker-compose.yml       # Local dev environment
└── .env.example             # Environment template
```

---

## ⚙️ Environment Variables

Copy `.env.example` and configure:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Production | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Production | 32+ char secret for token signing |
| `OPENROUTER_API_KEY` | For AI | Enables AI email personalization |
| `FRONTEND_URL` | Production | Frontend origin for CORS |
| `REDIS_URL_OVERRIDE` | Production | Redis connection URL |
| `WEBHOOK_SECRET` | Production | HMAC secret for webhook verification |
| `SMTP_HOST` / `SMTP_PORT` | For email | Mail server configuration |

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full production deployment guide.

---

## 🧪 Development

```bash
# Backend (with hot reload)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (with HMR)
cd frontend
npm install
npm run dev
```

### API Documentation

FastAPI auto-generates interactive docs:
- **Swagger UI**: [localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🚢 Deployment

ChampMail is designed for [Railway](https://railway.app):

- **Backend** — Dockerfile builder with health checks at `/health/live`
- **Frontend** — Nginx serving the React build with API proxy
- **Database** — Railway PostgreSQL + Redis plugins

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for step-by-step instructions.

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

Please follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.

---

## 📄 License

AGPL-3.0 — See [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ for email marketers who want full control.**

[Report Bug](https://github.com/Champ-Deep/ChampMail/issues) · [Request Feature](https://github.com/Champ-Deep/ChampMail/issues)

</div>
