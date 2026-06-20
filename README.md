# Asynchronous Transaction Risk & AML Triaging Engine

A production-grade, FCA-compliant Anti-Money Laundering triaging system built for UK FinTech/RegTech contexts. Validates ISO 20022 (pacs.008) financial transactions, runs a simulated multi-agent compliance pipeline powered by **Claude AI**, and broadcasts live decisions via WebSockets.

---

## Architecture Overview

```
POST /api/v1/transaction
        │
        ▼
┌─────────────────────┐      202 Accepted (immediate)
│  ISO 20022 Parser   │ ─────────────────────────────▶ Client
│  Pydantic Validator │
└────────┬────────────┘
         │ BackgroundTask
         ▼
┌─────────────────────────────────────────────────────────┐
│               Multi-Agent Triage Pipeline               │
│                                                         │
│  [Agent 1: Sifter]                                      │
│   Parses payload, checks £10,000 structuring threshold  │
│          │                                              │
│  [Agent 2: OSINT Investigator]                          │
│   Simulates UK Companies House API lookup for UBO data  │
│          │                                              │
│  [Agent 3: Risk Scorer → Claude Opus]                   │
│   Evaluates MLR-2017 red flags, returns structured JSON │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
  WebSocket Broadcast ──▶ Live Dashboard (ws://localhost:8000/ws/compliance)
         │
         ▼
  In-Memory Ledger (GET /api/v1/ledger)
```

---

## Key Features

- **ISO 20022 (pacs.008) Ingestion** — Validates nested debtor/creditor payloads including UK sort codes and account numbers in any format (dashes, spaces, raw)
- **Non-blocking async pipeline** — Returns `202 Accepted` immediately; triage runs as a background task
- **3-Agent compliance loop** — Sifter → OSINT → Risk Scorer, each broadcasting real-time step updates
- **Claude AI structured output** — Uses `claude-opus-4-8` with `RiskAssessment` Pydantic schema enforcement; falls back to deterministic rule engine if no API key is set
- **FCA MLR-2017 red flag detection** — Structuring/smurfing detection, offshore UBO checks (Seychelles, BVI, Cayman Islands), dormant shell company identification
- **Live WebSocket dashboard** — Agent steps and triage outcomes pushed to connected clients in real time
- **Synthetic transaction simulator** — Generates weighted test payloads across three AML typologies

---

## Risk Typologies Detected

| Typology | Trigger | Risk | Action |
|---|---|---|---|
| Structuring / Smurfing | Amount £9,000–£9,999 | MEDIUM | ESCALATE_TO_MLRO |
| Offshore Shell Company | Dormant status or Seychelles/BVI UBO | HIGH | FREEZE_ACCOUNT |
| High-Value Corporate | Amount ≥ £100,000 | HIGH | FREEZE_ACCOUNT |
| Standard Retail | Amount £150–£4,500, clean entity | LOW | ALLOW |

---

## Regulatory Alignment

| Framework | How It Is Addressed |
|---|---|
| **MLR 2017** | UBO identification via Companies House OSINT agent on every corporate transfer |
| **FCA SYSC** | Every triage decision produces a natural-language audit rationale |
| **Explainable AI (XAI)** | `reasoning` field on every ledger entry justifies account freeze decisions to the Financial Ombudsman |

---

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI |
| Data Validation | Pydantic v2 (ISO 20022 schemas) |
| AI Evaluation | Anthropic Claude Opus (`claude-opus-4-8`) |
| Real-Time Updates | FastAPI WebSockets |
| Test Data | Faker (`en_GB` locale) |
| HTTP Client | httpx |
| Runtime | Python 3.13, uv |

---

## Quickstart

```bash
# 1. Clone and enter the project
git clone https://github.com/nvs998/aml-triaging-engine.git
cd aml-triaging-engine

# 2. Create virtual environment and install dependencies
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 3. (Optional) Set Claude API key for AI-powered risk scoring
export ANTHROPIC_API_KEY=sk-ant-...

# 4. Start the server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the live dashboard at `http://127.0.0.1:8000`

Swagger API docs at `http://127.0.0.1:8000/docs`

---

## Submitting Test Transactions

```bash
# Submit 1 transaction
python scripts/submit_transactions.py

# Submit 10 and print triage results
python scripts/submit_transactions.py -n 10 --poll

# Continuous simulation (one transaction every 5 seconds)
python scripts/submit_transactions.py --loop

# Custom interval
python scripts/submit_transactions.py --loop --interval 10 --poll
```

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/transaction` | Ingest and queue an ISO 20022 transaction |
| `GET` | `/api/v1/transaction/{tx_id}` | Poll triage status for a specific transaction |
| `GET` | `/api/v1/ledger` | Retrieve full in-memory audit log |
| `WS` | `/ws/compliance` | WebSocket stream for live agent events |

### Example Request

```bash
curl -X POST http://127.0.0.1:8000/api/v1/transaction \
  -H "Content-Type: application/json" \
  -d '{
    "message_identifier": "pacs.008.abc123",
    "debtor": {
      "name": "John Smith",
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

### Example Response

```json
{
  "message": "ISO 20022 schema validated. Dropping into asynchronous triaging queue.",
  "transaction_id": "TX-A3F1C2D4-LON",
  "status_query_url": "/api/v1/transaction/TX-A3F1C2D4-LON"
}
```

---

## Mock Companies House Registry

Three companies are pre-loaded to exercise all risk paths:

| Registration | Company | Status | UBO | Expected Risk |
|---|---|---|---|---|
| `UK12984401` | Apex Apex Ltd | Active | Dimitri Volkov (Seychelles) | HIGH |
| `UK99882211` | Vanguard Global Holdings Ltd | Dormant | Hidden Beneficiary Corp (BVI) | HIGH |
| `UK00110022` | National Grid UK Utility Ltd | Active | HM Treasury Nominees (UK) | LOW |

---

## Project Structure

```
aml-triaging-engine/
├── app/
│   ├── main.py                    # FastAPI routes and WebSocket endpoint
│   ├── ledger.py                  # In-memory transaction store
│   ├── config.py                  # Environment configuration
│   ├── parser/
│   │   └── models.py              # ISO 20022 Pydantic schemas + validators
│   ├── agents/
│   │   ├── crew.py                # 3-agent triage pipeline
│   │   └── tools.py               # Mock Companies House API client
│   ├── services/
│   │   ├── claude_client.py       # Claude AI structured risk evaluator
│   │   └── websocket_manager.py   # WebSocket connection pool + broadcaster
│   └── graphql/
│       ├── schema.py              # Strawberry GraphQL schema
│       └── resolvers.py           # Audit trail resolvers
└── scripts/
    ├── generate_transactions.py   # Synthetic ISO 20022 payload generator
    └── submit_transactions.py     # CLI tool to submit transactions to the API
```
