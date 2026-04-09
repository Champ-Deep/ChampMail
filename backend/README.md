# Champion's Email Engine - Backend

FastAPI backend for the Champion's Email Automation Engine.

## Quick Start

### Prerequisites

- Python 3.11+
- ChampGraph running (see `/infrastructure`)
- Redis running (see `/infrastructure`)

### Installation

```bash
cd /Users/champion/ChampMail/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload --port 8000
```

### Access

- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

### Authentication

Development credentials:
- Admin: `admin@champions.dev` / `admin123`
- User: `user@champions.dev` / `user123`

Get a token:
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@champions.dev", "password": "admin123"}'
```

Use the token:
```bash
curl http://localhost:8000/api/v1/prospects \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Get JWT token
- `POST /api/v1/auth/register` - Register new user
- `GET /api/v1/auth/me` - Get current user info

### Prospects
- `GET /api/v1/prospects` - List prospects
- `POST /api/v1/prospects` - Create prospect
- `GET /api/v1/prospects/{email}` - Get prospect
- `PUT /api/v1/prospects/{email}` - Update prospect
- `DELETE /api/v1/prospects/{email}` - Delete prospect
- `POST /api/v1/prospects/bulk` - Bulk import

### Sequences
- `GET /api/v1/sequences` - List sequences
- `POST /api/v1/sequences` - Create sequence
- `GET /api/v1/sequences/{id}` - Get sequence
- `PUT /api/v1/sequences/{id}` - Update sequence
- `POST /api/v1/sequences/{id}/enroll` - Enroll prospects
- `POST /api/v1/sequences/{id}/pause` - Pause sequence
- `POST /api/v1/sequences/{id}/resume` - Resume sequence

### Webhooks
- `POST /api/v1/webhooks/email-events` - Email tracking events
- `POST /api/v1/webhooks/leads` - New lead submissions
- `POST /api/v1/webhooks/n8n` - n8n workflow events
- `POST /api/v1/webhooks/trigger/{name}` - Trigger n8n workflow

### Knowledge Graph
- `POST /api/v1/graph/query` - Execute Cypher query
- `POST /api/v1/graph/search` - Semantic search
- `POST /api/v1/graph/chat` - Conversational interface
- `GET /api/v1/graph/entities/{id}` - Get entity with relations
- `GET /api/v1/graph/stats` - Graph statistics

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py        # Authentication endpoints
│   │       ├── prospects.py   # Prospect CRUD
│   │       ├── sequences.py   # Sequence management
│   │       ├── webhooks.py    # Webhook handlers
│   │       └── graph.py       # Graph query endpoints
│   ├── core/
│   │   ├── config.py          # Settings
│   │   └── security.py        # JWT auth
│   ├── db/
│   │   └── champgraph.py      # ChampGraph client
│   ├── schemas/
│   │   ├── prospect.py        # Prospect schemas
│   │   └── sequence.py        # Sequence schemas
│   └── main.py                # FastAPI app
├── tests/
├── .env
├── requirements.txt
└── pyproject.toml
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
ruff check .
ruff format .
```

## Next Steps

After the backend is running:

1. **Cycle 3**: Build multi-step sequence engine in n8n
2. **Cycle 4**: Add reply detection service
3. **Cycle 5**: Build Next.js frontend
