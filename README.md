# AML Sentinel — Asynchronous Transaction Risk & AML Triaging Engine

> A production-grade, FCA-compliant Anti-Money Laundering system built for UK FinTech/RegTech.
> Validates ISO 20022 (pacs.008) transactions, runs a real multi-agent AI compliance pipeline,
> and broadcasts live decisions via WebSocket.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.137-009688?logo=fastapi&logoColor=white)
![CrewAI](https://img.shields.io/badge/CrewAI-1.14-FF6B35)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4?logo=google&logoColor=white)
![Claude](https://img.shields.io/badge/Claude-Opus_4-CC785C)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Just here to see the flow?

> **No setup needed.** Two options depending on how much time you have:

| | Link | What you get |
|---|---|---|
| **Static Demo** | [Open Demo →](https://aml-triaging-engine.bravegrass-ea4501f1.uksouth.azurecontainerapps.io/demo) | Pre-loaded portfolio showcase — all three risk typologies, live-looking telemetry, no backend required |
| **Live Engine** | [Open Live App →](https://aml-triaging-engine.bravegrass-ea4501f1.uksouth.azurecontainerapps.io/) | The real thing — submit transactions, watch agents fire in real time, see the ledger fill up |

The static demo is the fastest way to understand the interface and the three detection typologies. The live engine lets you POST actual payloads and observe the WebSocket event stream.

---

## What This Is

A UK-context AML compliance backend that screens financial transactions the moment they arrive. When a payment is posted:

1. The ISO 20022 payload is validated against UK banking rules (sort codes, account numbers, amounts)
2. A `202 Accepted` is returned immediately — the gateway never blocks
3. A three-stage AI agent pipeline runs in the background:
   - **Sifter** — queries the debtor's transaction history and checks for structuring patterns
   - **OSINT Investigator** — looks up the creditor on the UK Companies House registry and traces the Ultimate Beneficial Owner (UBO)
   - **Risk Scorer** — synthesises both sets of findings using Gemini 2.5 Flash and applies FCA MLR-2017 rules
4. Every agent step is broadcast live over WebSocket to the dashboard
5. The final verdict — risk score, recommended action, and a natural-language regulatory rationale — is written to a persistent SQLite audit ledger

The system degrades gracefully: full CrewAI + Gemini pipeline when keys are set, Claude Opus fallback if only Anthropic is configured, and a pure deterministic rule engine with zero LLM dependency if no keys are present at all.

---

## Architecture

```
Client (Browser / cURL / Script)
        │
        │  POST /api/v1/transaction  (ISO 20022 JSON)
        ▼
┌──────────────────────────────────────┐
│  FastAPI  ·  Pydantic v2 Validation  │──── 202 Accepted (immediate)
│  Sort codes · Amounts · Account nums │
└───────────────┬──────────────────────┘
                │ BackgroundTask (non-blocking)
                ▼
┌──────────────────────────────────────────────────────────────┐
│                  run_agentic_triage_loop()                   │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Pipeline selector (env-key driven)                  │     │
│  │  GEMINI_API_KEY  →  CrewAI + Gemini 2.5 Flash       │     │
│  │  ANTHROPIC_KEY   →  Rules + Claude Opus scoring     │     │
│  │  Neither         →  Pure deterministic rule engine  │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                              │
│  Agent 1 · Sifter          ← LedgerQueryTool (SQLite)       │
│      ↓                                                       │
│  Agent 2 · OSINT           ← CompaniesHouseTool (CH API)    │
│      ↓                                                       │
│  Agent 3 · Risk Scorer     ← Structured JSON (schema-pinned)│
└───────────────┬──────────────────────────────────────────────┘
                │
                ├──▶  WebSocket broadcast  →  Live Dashboard
                │
                ▼
        SQLite  aml_ledger.db
                │
                ▼
        GET /api/v1/ledger   ·   GET /api/v1/transaction/{tx_id}
```

---

## Key Features

- **ISO 20022 (pacs.008) ingestion** — Accepts sort codes in any UK format (`20-45-12`, `204512`, `20 45 12`) and normalises automatically
- **Non-blocking async gateway** — Returns `202 Accepted` in milliseconds; the entire agent pipeline runs as a background task
- **Real CrewAI pipeline** — Three actual agents with memory, tool use, and sequential task dependencies (not a mock)
- **Structured LLM output** — Gemini uses `responseSchema`, Claude uses Pydantic `parse()` — schema is enforced at the SDK level, not just prompt-engineered
- **FCA MLR-2017 red flag detection** — Structuring / smurfing, offshore UBO (Seychelles, BVI, Cayman), dormant shell companies, high-value EDD threshold
- **Transaction history analysis** — Sifter Agent queries the debtor's full ledger history to detect velocity abuse, escalation patterns, and round-number avoidance
- **Live WebSocket dashboard** — Every agent step and the final verdict are pushed to connected clients as they happen
- **Three-tier graceful fallback** — Gemini → Claude → deterministic rules → error state; the system always produces a verdict
- **Persistent SQLite audit trail** — Every decision is written with reasoning, confidence score, and recommended action
- **Synthetic load generator** — Weighted Faker-based script produces realistic UK payloads across all three AML typologies

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI 0.137 |
| Runtime | Python 3.13 · uv 0.11 |
| Data Validation | Pydantic v2 (ISO 20022 schemas + field validators) |
| Agent Orchestration | CrewAI 1.14 (Agent · Task · Crew · Process.sequential) |
| Primary LLM | Google Gemini 2.5 Flash (schema-constrained JSON output) |
| Fallback LLM | Anthropic Claude Opus `claude-opus-4-8` (Pydantic structured output + adaptive thinking) |
| Database | SQLite via `aiosqlite` (async, persistent) |
| Real-Time | FastAPI WebSockets |
| HTTP Client | httpx (async + sync, exponential backoff on Gemini) |
| Test Data | Faker `en_GB` locale |
| Deployment | Docker multi-stage · Azure Container Apps (UK South) |

---

## Regulatory Alignment

| Framework | Requirement | Implementation |
|---|---|---|
| **MLR 2017 · Reg 27** | Detect structuring (splitting payments to avoid £10k threshold) | Sifter Agent + history analysis via LedgerQueryTool |
| **MLR 2017 · Reg 28** | Identify shell companies used for layering | OSINT Agent queries Companies House status + UBO |
| **MLR 2017 · Reg 33** | Enhanced due diligence on large transfers | ≥ £100,000 auto-escalates regardless of entity status |
| **FCA SYSC** | Robust systems for identifying fraud and AML risk | Full audit record per transaction with pipeline provenance |
| **Explainable AI (XAI)** | Account-freeze decisions must be justifiable to the Financial Ombudsman | `reasoning` field written in plain English on every ledger entry |

---

## Risk Typologies

| Typology | Trigger Condition | Risk Score | Recommended Action |
|---|---|---|---|
| Structuring / Smurfing | Amount £9,000 – £9,999 | `MEDIUM` | `ESCALATE_TO_MLRO` |
| Dormant Shell Company | Companies House status = Dormant | `HIGH` | `FREEZE_ACCOUNT` |
| Offshore Beneficial Owner | UBO country = Seychelles · BVI · Cayman · Bahamas · Panama | `HIGH` | `FREEZE_ACCOUNT` |
| High-Value Transfer | Amount ≥ £100,000 | `HIGH` | `FREEZE_ACCOUNT` |
| Standard Retail | None of the above | `LOW` | `ALLOW` |

Higher-severity findings override lower ones. A dormant company receiving £9,500 is scored HIGH, not MEDIUM.

---

## Mock Companies House Registry

Three companies are pre-loaded to exercise every risk path without needing a real API key:

| Registration No. | Company | CH Status | UBO / Jurisdiction | Expected Verdict |
|---|---|---|---|---|
| `UK12984401` | Apex Apex Ltd | Active | Dimitri Volkov · **Seychelles** | `HIGH` · `FREEZE_ACCOUNT` |
| `UK99882211` | Vanguard Global Holdings Ltd | **Dormant** | Hidden Beneficiary Corp · **BVI** | `HIGH` · `FREEZE_ACCOUNT` |
| `UK00110022` | National Grid UK Utility Ltd | Active | HM Treasury Nominees · United Kingdom | `LOW` · `ALLOW` |

When `COMPANY_HOUSE_KEY` is set, any real Companies House number is looked up live via the official API.

---

## Quickstart

### Prerequisites

- Python 3.13
- [`uv`](https://github.com/astral-sh/uv) (`pip install uv`)
- A Gemini or Anthropic API key *(optional — the rule engine works without either)*

### 1. Clone and install

```bash
git clone https://github.com/nvs998/aml-triaging-engine.git
cd aml-triaging-engine

uv venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

uv pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in what you have:

```env
GEMINI_API_KEY=your-gemini-key          # primary LLM (CrewAI pipeline)
ANTHROPIC_API_KEY=your-claude-key       # fallback LLM (deterministic + Claude scoring)
COMPANY_HOUSE_KEY=your-ch-api-key       # optional — enables live Companies House lookups
HOST=127.0.0.1
PORT=8000
```

**No API keys?** The rule-based engine handles everything — you still get valid risk scores and WebSocket events.

### 3. Start the server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

| URL | What's there |
|---|---|
| `http://127.0.0.1:8000` | Live compliance dashboard |
| `http://127.0.0.1:8000/demo` | Static portfolio showcase |
| `http://127.0.0.1:8000/docs` | Swagger / OpenAPI explorer |

---

## Submitting Test Transactions

The `submit_transactions.py` script generates realistic UK payloads and posts them to the running backend.

```bash
# Submit one transaction
python scripts/submit_transactions.py

# Submit 10 and print each triage result
python scripts/submit_transactions.py -n 10 --poll

# Continuous load — one transaction every 5 seconds (Ctrl+C to stop)
python scripts/submit_transactions.py --loop

# Faster load with results
python scripts/submit_transactions.py --loop --interval 2 --poll
```

Each payload is randomly weighted across three typologies:
- **15%** — Structuring / smurfing (£9,800–£9,995)
- **15%** — High-value corporate (£110,000–£500,000, always with a Companies House number)
- **70%** — Standard retail (£150–£4,500)

To preview payloads without submitting:

```bash
python scripts/generate_transactions.py
```

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/transaction` | Ingest and queue an ISO 20022 transaction |
| `GET` | `/api/v1/transaction/{tx_id}` | Poll triage status for a specific transaction |
| `GET` | `/api/v1/ledger` | Full audit ledger (all transactions, newest first) |
| `WS` | `/ws/compliance` | WebSocket stream — `AGENT_STEP` and `TRIAGE_COMPLETE` events |

### Example: submit a high-risk transaction

```bash
curl -X POST http://127.0.0.1:8000/api/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "message_identifier": "pacs.008.abc123",
    "debtor": {
      "name": "Stellar Logistics Co",
      "sort_code": "20-45-12",
      "account_number": "44891023"
    },
    "creditor": {
      "name": "Apex Apex Ltd",
      "sort_code": "60-83-01",
      "account_number": "99201145",
      "companies_house_number": "UK12984401"
    },
    "transaction": {
      "amount": 250000.00,
      "currency": "GBP",
      "reference": "IP Portfolio Acquisition"
    }
  }'
```

**Accepted response (immediate):**
```json
{
  "message": "ISO 20022 schema validated. Dropping into asynchronous triaging queue.",
  "transaction_id": "TX-A3F1C2D4-LON",
  "status_query_url": "/api/v1/transaction/TX-A3F1C2D4-LON"
}
```

**Poll for the verdict:**
```bash
curl http://127.0.0.1:8000/api/v1/transaction/TX-A3F1C2D4-LON
```

```json
{
  "id": "TX-A3F1C2D4-LON",
  "debtor_name": "Stellar Logistics Co",
  "creditor_name": "Apex Apex Ltd",
  "amount": 250000.0,
  "currency": "GBP",
  "status": "FROZEN",
  "risk_score": "HIGH",
  "confidence_score": 0.96,
  "reasoning": "Creditor entity registered to an active company with an offshore UBO (Dimitri Volkov, Seychelles). Transfer of £250,000 exceeds the enhanced due diligence threshold. Shell company layering risk detected under MLR-2017 reg. 28 and 33.",
  "recommended_action": "FREEZE_ACCOUNT",
  "completed_at": "2026-06-24T11:45:05"
}
```

### WebSocket events

Connect to `ws://localhost:8000/ws/compliance` to receive a stream of:

```json
{ "event": "AGENT_STEP",      "tx_id": "TX-...", "agent": "Sifting Agent",    "log": "..." }
{ "event": "AGENT_STEP",      "tx_id": "TX-...", "agent": "OSINT Investigator","log": "..." }
{ "event": "AGENT_STEP",      "tx_id": "TX-...", "agent": "Risk Scorer",       "log": "..." }
{ "event": "TRIAGE_COMPLETE", "tx_id": "TX-...", "payload": { ...full ledger row... } }
```

---

## Project Structure

```
aml-triaging-engine/
│
├── main.py                        # Entrypoint — starts uvicorn on app.main:app
├── requirements.txt               # Full pinned dependency list
├── Dockerfile                     # Multi-stage build (builder + lean runtime)
├── containerapp.yaml              # Azure Container Apps deployment manifest
├── .env.example                   # Template — copy to .env and fill in keys
├── aml_ledger.db                  # SQLite audit ledger (auto-created on first run)
├── index.html                     # Live compliance dashboard (served at /)
├── demo.html                      # Static portfolio showcase (served at /demo)
│
├── app/
│   ├── main.py                    # FastAPI routes, lifespan, WebSocket endpoint
│   ├── config.py                  # Reads .env — exposes API keys and host/port
│   ├── ledger.py                  # Async SQLite CRUD via aiosqlite
│   │
│   ├── parser/
│   │   └── models.py              # Pydantic v2 ISO 20022 schemas + field validators
│   │
│   ├── agents/
│   │   ├── crew.py                # All three pipeline variants + public entry point
│   │   └── tools.py               # CompaniesHouseTool · LedgerQueryTool · mock registry
│   │
│   ├── services/
│   │   ├── claude_client.py       # Anthropic async client · RiskAssessment structured output
│   │   ├── gemini_client.py       # Gemini REST client · schema-constrained JSON · backoff
│   │   └── websocket_manager.py   # Connection pool · broadcast helper
│   │
│   └── graphql/                   # Placeholder — Strawberry GraphQL audit trail (roadmap)
│
└── scripts/
    ├── generate_transactions.py   # Faker-based ISO 20022 payload generator
    └── submit_transactions.py     # CLI: submit 1, N, or loop continuously
```

---

## Upcoming enhancements

- **RAG over FCA regulation** — load the actual MLR-2017 PDF and JMLSG guidance into a vector store so the Risk Scorer can cite specific clauses, not just apply hardcoded rule labels
- **LangGraph conditional routing** — skip the OSINT agent for low-suspicion transactions, cutting cost and latency by ~40% on clean retail payments
- **Human-in-the-loop MLRO review** — pause HIGH-risk verdicts for a Money Laundering Reporting Officer to approve before any account freeze executes, as required by FCA SYSC

---

## 👤 Author

Naveen Soni
