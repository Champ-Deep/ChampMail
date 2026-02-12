# Champion's Email Engine - Infrastructure Setup

## Quick Start

### Prerequisites
- Docker Desktop installed and running
- OpenAI API key (for Graphiti embeddings)

### 1. Start Core Services (FalkorDB + Redis)

```bash
cd /Users/champion/ChampMail/infrastructure

# Copy environment file
cp .env.example .env

# Edit .env and add your OPENAI_API_KEY
# nano .env  or  code .env

# Start services
docker compose up -d

# Check status
docker compose ps
```

### 2. Verify FalkorDB is Running

**Option A: Browser UI**
Open http://localhost:3000 in your browser

**Option B: Command Line**
```bash
# Connect via redis-cli
redis-cli -p 6379

# Test a graph query
GRAPH.QUERY default_db "CREATE (n:Test {name: 'hello'}) RETURN n"
GRAPH.QUERY default_db "MATCH (n:Test) RETURN n"

# Clean up test
GRAPH.QUERY default_db "MATCH (n:Test) DELETE n"
```

### 3. Test with Python

```python
# Install FalkorDB Python client
pip install falkordb

# Test connection
from falkordb import FalkorDB

db = FalkorDB(host='localhost', port=6379)
graph = db.select_graph('champions_email_engine')

# Create a test node
graph.query("CREATE (p:Prospect {email: 'test@example.com', name: 'Test User'})")

# Query it back
result = graph.query("MATCH (p:Prospect) RETURN p.email, p.name")
for record in result.result_set:
    print(record)
```

---

## BillionMail Setup

BillionMail requires its own deployment due to complexity (mail server, DNS, certificates).

### Option A: Local Development (No actual sending)

For development, you can use the existing Gmail integration in n8n while building out the system. Switch to BillionMail when ready for production.

### Option B: Full BillionMail Deployment

```bash
# Clone BillionMail repo
cd /opt
git clone https://github.com/aaPanel/BillionMail
cd BillionMail

# Configure
cp env_init .env
# Edit .env - set BILLIONMAIL_HOSTNAME to your domain

# Deploy
docker compose up -d

# Get admin credentials
bash bm.sh default
```

**Requirements for BillionMail:**
- A domain with DNS control
- Clean IP address (not blacklisted)
- Ports 25, 465, 587, 80, 443 available
- SPF, DKIM, DMARC records configured

### Option C: Railway Deployment

See: https://www.billionmail.com/start/docker.html

---

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| FalkorDB | 6379 | Graph database (Redis protocol) |
| FalkorDB Browser | 3000 | Visual graph explorer |
| Redis Cache | 6380 | Application caching |
| Graphiti MCP | 8765 | Claude Desktop integration (optional) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Champion's Email Engine                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  FalkorDB   │    │    Redis    │    │  BillionMail │     │
│  │  (Graph)    │    │   (Cache)   │    │   (Email)    │     │
│  │  :6379      │    │   :6380     │    │   :25/587    │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                │
│                    ┌───────┴───────┐                        │
│                    │   FastAPI     │  (Future - Cycle 2)    │
│                    │   Backend     │                        │
│                    └───────┬───────┘                        │
│                            │                                │
│         ┌──────────────────┼──────────────────┐             │
│         │                  │                  │             │
│  ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐     │
│  │    n8n      │    │   Next.js   │    │  Graphiti   │     │
│  │ (Workflows) │    │ (Frontend)  │    │   (SDK)     │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### FalkorDB won't start
```bash
# Check logs
docker compose logs falkordb

# Common fix: remove old data
docker compose down -v
docker compose up -d
```

### Port conflicts
```bash
# Check what's using a port
lsof -i :6379
lsof -i :3000

# Change ports in .env if needed
```

### Connection refused
```bash
# Ensure Docker is running
docker info

# Check container health
docker compose ps
```

---

## Next Steps

After infrastructure is running:

1. **Cycle 2:** Build FastAPI backend with Graphiti integration
2. **Cycle 3:** Create multi-step sequence engine in n8n
3. **Cycle 4:** Add reply detection service
4. **Cycle 5:** Build Next.js frontend

See `/Users/champion/ChampMail/RALPH-LOOP.md` for full execution plan.
