# ChampMail

## 🚀 Overview
**ChampMail** is a high-performance, self-hosted email marketing and cold outreach platform. Unlike traditional tools that rely on 3rd party SMTP providers, ChampMail is built with a **fully integrated mail engine (Stalwart-based)**, meaning it acts as its own SMTP and IMAP server.

This project combines a **FastAPI backend**, a **Vite/React frontend**, and a **Knowledge Graph (FalkorDB)** to create deeply personalized, AI-driven outreach sequences.

---

## 🛠 Project Architecture

### 1. The Core Infrastructure (Docker)
The system runs on a multi-container architecture:
- **FastAPI (Backend)**: The brains of the operation, handling business logic and API requests.
- **Vite/React (Frontend)**: A premium UI for managing prospects, templates, and sequences.
- **PostgreSQL**: Stores relational data like Users, Teams, and Settings.
- **FalkorDB (Graph)**: Stores the **Knowledge Graph** (Prospects, Companies, and their relationships).
- **Redis**: Handles application caching and session management.

### 2. The Built-in Mail Engine
ChampMail is its own email provider. 
- **Outbound (SMTP)**: It sends emails directly from the server.
- **Inbound (IMAP)**: It monitors its own mailboxes to auto-detect replies and pause sequences.
- **Total Ownership**: You own the data, the metadata, and the delivery reputation.

### 3. Mixed AI Strategy
We use a "Best of Breed" AI approach:
- **Generation (Brain)**: We use **Anthropic (Claude 3.5 Sonnet)** for the highest quality personalization and reasoning.
- **Embeddings (Memory)**: We use **OpenAI (or Gemini)** to create the vector embeddings for our Knowledge Graph search.

---

## 📂 Directory Structure

- `/backend`: FastAPI application, database schemas, and core services.
- `/frontend`: React SPA with TailwindCSS and Easy Email editor.
- `/infrastructure`: Docker configurations for the data layer (PostgreSQL, FalkorDB, Redis).
- `/CloudMeet`: Integrated open-source calendar (like Calendly).
- `/Email Automation`: n8n workflows for complex AI processing.
- `docker-compose.yml`: Single-command local deployment.

---

## 🚀 Getting Started

### 1. Prerequisites
- Docker & Docker Compose
- API Keys for Anthropic (Chat) and OpenAI (Embeddings)

### 2. Setup
1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in your API keys.
3. Run the engine:
   ```bash
   docker compose up -d
   ```
4. Access the UI at `http://localhost:3000`.

### 3. Default Credentials
- **Admin**: `admin@champions.dev` / `admin123`

---

## 📝 Roadmap & Next Steps (For Junior Developers)

### 🧩 Understanding the Stack
1. **FalkorDB**: This is a graph database. You query it using **Cypher** (like SQL but for relationships). It's what allows us to know that "Prospect A works at Company B which was founded by Person C".
2. **Easy Email**: The template editor in the frontend is a drag-and-drop MJML-based editor. It's powerful but requires strict MJML/JSON structures.
3. **n8n**: Some of the heavy lifting for sequences and AI enrichment happens in n8n workflows.

### 🎯 Current Priorities
- **Campaigns UI**: Currently a scaffold. Needs to be built to allow users to launch and pause outreach.
- **Reply Detection Logic**: Finish the IMAP polling service in the backend to match incoming emails to active prospects.
- **CloudMeet Integration**: Ensure booking a meeting automatically updates the prospect status in the graph.

---

## ⚖️ License
AGPL-3.0 - See LICENSE for details.
