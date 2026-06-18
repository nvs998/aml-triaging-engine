# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

An Asynchronous Transaction Risk & AML (Anti-Money Laundering) Triaging Engine built for UK FinTech/RegTech contexts. It validates ISO 20022 (pacs.008) financial transactions, runs a simulated multi-agent compliance pipeline, and broadcasts live updates via WebSockets. Designed to demonstrate FCA-compliance patterns, explainable AI scoring, and async microservice architecture.

## Setup & Running

The project uses `uv` (v0.11.1) with Python 3.13. The virtual environment is at `./aml_triaging/`.

```bash
# Activate venv
source aml_triaging/bin/activate

# Install dependencies — always use uv, never pip
uv pip install fastapi uvicorn pydantic
uv pip install 'uvicorn[standard]'  # required for WebSocket support

# Run the development server
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Or via the entrypoint directly
python main.py
```

The interactive API docs are available at `http://127.0.0.1:8000/docs` when the server is running.

## Architecture

Currently a **single-file prototype** (`main.py`). The `blueprint.md` describes the target modular structure to grow toward.

### Core Components in `main.py`

**Pydantic Schemas (ISO 20022 / pacs.008)**
- `PartyDetails` — debtor/creditor with UK sort code and account number
- `TransactionDetails` — amount, currency, reference, optional Companies House number
- `ISO20022Payload` — top-level message wrapping debtor, creditor, and transaction

**In-Memory Ledger**
- `TRANSACTION_LEDGER: Dict[str, dict]` — the sole state store; no database yet. Transaction IDs follow the pattern `TX-{8hex}-LON`.

**3-Agent Simulation Pipeline** (`run_agentic_triage_loop`)
Runs as a `BackgroundTask` so the HTTP response returns `202 Accepted` immediately:
1. **Sifter Agent** — parses ISO payload, inspects amount against the £10,000 structuring threshold
2. **OSINT Investigator** — simulates a UK Companies House lookup for UBO (Ultimate Beneficial Owner) data
3. **Risk Scorer** — applies FCA MLR-2017 rules to produce `LOW/MEDIUM/HIGH` risk with a confidence score and `recommended_action` (`ALLOW` / `ESCALATE_TO_MLRO` / `FREEZE_ACCOUNT`)

Risk scoring logic:
- `£9,000–£9,999` → MEDIUM / ESCALATE (smurfing detection)
- Dormant company, Seychelles UBO, or amount ≥ £100,000 → HIGH / FREEZE

**WebSocket Manager** (`ConnectionManager`)
- Endpoint: `ws://localhost:8000/ws/compliance`
- Broadcasts `AGENT_STEP` events per agent and a final `TRIAGE_COMPLETE` event with the full ledger entry

**REST Endpoints**
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/transaction` | Ingest and queue a new transaction |
| `GET`  | `/api/v1/transaction/{tx_id}` | Poll status for a specific transaction |
| `GET`  | `/api/v1/ledger` | Retrieve full in-memory audit log |

### Planned Architecture (from `blueprint.md`)

The target structure splits `main.py` into:
- `app/parser/` — Pydantic models + inbound validator
- `app/agents/` — Real CrewAI agent definitions + Companies House tool
- `app/graphql/` — Strawberry GraphQL schema + resolvers for the audit trail
- `app/services/` — Gemini API client (structured JSON output) + WebSocket manager
- Docker Compose orchestration with Redis for a real async queue (Celery)

When expanding the codebase, follow this module split rather than growing `main.py` further.
