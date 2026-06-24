# AML Triaging Engine — Complete Project Guide

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Why It Exists](#2-why-it-exists)
3. [Regulatory Context](#3-regulatory-context)
4. [Architecture Overview](#4-architecture-overview)
5. [Project File Structure](#5-project-file-structure)
6. [Configuration & Environment](#6-configuration--environment)
7. [Data Models — ISO 20022 Schemas](#7-data-models--iso-20022-schemas)
8. [The Database — SQLite Ledger](#8-the-database--sqlite-ledger)
9. [The Three-Agent Pipeline](#9-the-three-agent-pipeline)
10. [Agent Tools](#10-agent-tools)
11. [LLM Clients](#11-llm-clients)
12. [Pipeline Selection Logic](#12-pipeline-selection-logic)
13. [REST API Endpoints](#13-rest-api-endpoints)
14. [WebSocket Real-Time Layer](#14-websocket-real-time-layer)
15. [The Frontend Dashboard](#15-the-frontend-dashboard)
16. [Risk Typologies & Scoring Rules](#16-risk-typologies--scoring-rules)
17. [Mock Companies House Registry](#17-mock-companies-house-registry)
18. [Test Data Scripts](#18-test-data-scripts)
19. [Docker & Azure Deployment](#19-docker--azure-deployment)
20. [Planned Future Work](#20-planned-future-work)
21. [End-to-End Request Flow](#21-end-to-end-request-flow)

---

## 1. What This Project Is

The **AML Triaging Engine** is a UK FinTech/RegTech backend system that automatically screens financial transactions for money-laundering risk. When a transaction arrives in ISO 20022 (pacs.008) format, the system:

1. Validates the message against UK banking rules (sort codes, account numbers).
2. Immediately returns a `202 Accepted` acknowledgement so the calling bank is not kept waiting.
3. In the background, runs a three-stage AI agent pipeline — structuring analysis, corporate identity lookup, and risk scoring.
4. Writes the final verdict (LOW / MEDIUM / HIGH, with a natural-language rationale) into a persistent SQLite ledger.
5. Broadcasts every step of that pipeline in real time over WebSocket so a live dashboard can animate the process.

---

## 2. Why It Exists

This project was built to demonstrate mastery of the skills most sought by UK FinTech and RegTech employers:

- **ISO 20022** — the modern interbank message format replacing SWIFT MT
- **Asynchronous microservice design** — non-blocking API + background worker
- **Multi-agent AI orchestration** with CrewAI
- **Structured LLM output** — using Gemini and Claude to return validated JSON, not free text
- **FCA regulatory knowledge** — explainable AI decisions that can withstand Ombudsman scrutiny
- **Real-time UX** — WebSocket event streaming to a live compliance terminal

---

## 3. Regulatory Context

Three UK regulatory frameworks shape every design decision:

| Framework | What It Requires | How This System Addresses It |
|-----------|-----------------|------------------------------|
| **Money Laundering Regulations 2017 (MLR 2017)** | Identify the Ultimate Beneficial Owner (UBO) of every corporate counterparty | OSINT Agent queries Companies House on every transfer with a company number |
| **FCA SYSC (Senior Management Arrangements, Systems and Controls)** | Firms must have robust systems for identifying fraud and AML risk | Every triage produces a structured audit record with reasoning |
| **Explainable AI (XAI)** | Account-freeze decisions must be justifiable to the Financial Ombudsman Service | Every ledger entry includes a `reasoning` field written in plain English by the LLM |

**Key thresholds implemented:**
- **£10,000 structuring threshold** — payments of £9,000–£9,999 trigger smurfing detection (MLR 2017, reg. 27)
- **£100,000 enhanced due diligence** — large-value transactions auto-escalate (MLR 2017, reg. 33)
- **Offshore UBO jurisdictions** — Seychelles, BVI, Cayman Islands, Bahamas, Panama

---

## 4. Architecture Overview

```
Client (Browser / cURL / Script)
        │
        │ POST /api/v1/transaction  (ISO 20022 JSON)
        ▼
┌──────────────────────────┐
│  FastAPI — app/main.py   │  ←── Pydantic validation (sorts codes, amounts)
│  202 Accepted instantly  │  ←── Writes PROCESSING record to SQLite
└──────────┬───────────────┘
           │
           │ BackgroundTask (non-blocking)
           ▼
┌────────────────────────────────────────────────────────────┐
│                 run_agentic_triage_loop()                  │
│                   app/agents/crew.py                       │
│                                                            │
│  Selects pipeline based on available API keys:             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  GEMINI_API_KEY set?                                 │  │
│  │    YES → Full CrewAI pipeline (Gemini 2.5 Flash)    │  │
│  │    NO, ANTHROPIC_API_KEY set?                        │  │
│  │      YES → Deterministic + Claude Opus fallback      │  │
│  │      NO → Pure rule-based engine (no LLM)            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                            │
│  Agent 1: Sifter          (LedgerQueryTool)               │
│  Agent 2: OSINT           (CompaniesHouseTool)            │
│  Agent 3: Risk Scorer     (Claude/Gemini structured JSON) │
└──────────┬─────────────────────────────────────────────────┘
           │
           ├──▶ WebSocket broadcast (per agent step + final verdict)
           │
           ▼
   SQLite — aml_ledger.db (update risk_score, reasoning, status)
           │
           ▼
   GET /api/v1/transaction/{tx_id}  ← Client polls for result
   GET /api/v1/ledger               ← Full audit log
```

---

## 5. Project File Structure

```
aml-triaging-engine/
│
├── main.py                      # Entrypoint — starts uvicorn, proxies to app/main.py
├── requirements.txt             # Full pinned dependency list
├── Dockerfile                   # Multi-stage Docker build
├── containerapp.yaml            # Azure Container Apps deployment manifest
├── .env.example                 # Template for environment variables
├── .env                         # Actual secrets (gitignored)
├── aml_ledger.db                # SQLite database (auto-created on first run)
├── index.html                   # Main live dashboard (served at /)
├── demo.html                    # Secondary demo page (served at /demo)
├── blueprint.md                 # Architectural roadmap and design notes
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, all routes, WebSocket endpoint
│   ├── config.py                # Reads .env — exposes API keys and host/port
│   ├── ledger.py                # All SQLite CRUD operations (async with aiosqlite)
│   │
│   ├── parser/
│   │   ├── __init__.py
│   │   └── models.py            # Pydantic schemas: Debtor, Creditor, ISO20022Payload
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── crew.py              # Three pipeline variants + public entry point
│   │   └── tools.py             # CompaniesHouseTool, LedgerQueryTool, mock registry
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── claude_client.py     # Anthropic Claude async client + local fallback
│   │   ├── gemini_client.py     # Google Gemini HTTP client with exponential backoff
│   │   └── websocket_manager.py # Connection pool + broadcast helper
│   │
│   └── graphql/
│       ├── __init__.py
│       ├── schema.py            # Placeholder (Strawberry GraphQL — not yet implemented)
│       └── resolvers.py         # Placeholder
│
└── scripts/
    ├── generate_transactions.py # Faker-based ISO 20022 payload generator
    └── submit_transactions.py   # CLI tool: submit 1, N, or loop continuously
```

---

## 6. Configuration & Environment

**File: `app/config.py`**

Reads a `.env` file via `python-dotenv` and exposes five variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Enables Claude Opus fallback pipeline | (empty) |
| `GEMINI_API_KEY` | Enables full CrewAI + Gemini pipeline | (empty) |
| `COMPANY_HOUSE_KEY` | Enables live Companies House API calls | (empty) |
| `HOST` | Bind address for uvicorn | `127.0.0.1` |
| `PORT` | Port for uvicorn | `8000` |

**Pipeline selection is driven entirely by which keys are populated** (see section 12).

When no keys are set, the system falls back to a deterministic rule engine with no LLM dependency — the server is always fully functional.

---

## 7. Data Models — ISO 20022 Schemas

**File: `app/parser/models.py`**

The ISO 20022 pacs.008 "Customer Credit Transfer" message is modelled with four Pydantic v2 classes.

### `Debtor`
| Field | Type | Validation |
|-------|------|-----------|
| `name` | str | 2–70 characters |
| `sort_code` | str | Strips non-digits, enforces exactly 6 digits, normalises to `XX-XX-XX` |
| `account_number` | str | Strips spaces, enforces exactly 8 digits |

### `Creditor`
Same fields as `Debtor`, plus:
| Field | Type | Validation |
|-------|------|-----------|
| `companies_house_number` | Optional[str] | No format enforcement — passed as-is to the OSINT agent |

### `TransactionDetails`
| Field | Type | Validation |
|-------|------|-----------|
| `amount` | float | Must be > 0 |
| `currency` | str | Defaults to `"GBP"` |
| `reference` | str | 1–140 characters |

### `ISO20022Payload`
The top-level wrapper:
| Field | Type |
|-------|------|
| `message_identifier` | str — e.g. `pacs.008.001.08.77192` |
| `debtor` | `Debtor` |
| `creditor` | `Creditor` |
| `transaction` | `TransactionDetails` |

**Sort code validator detail:** The validator uses `re.sub(r"\D", "", v)` to strip any dashes or spaces before checking length, so inputs like `20-45-12`, `20 45 12`, and `204512` are all accepted and normalised to `20-45-12`.

---

## 8. The Database — SQLite Ledger

**File: `app/ledger.py`**

Uses `aiosqlite` for fully asynchronous SQLite access. The database file is `aml_ledger.db` in the project root (configurable via `DB_PATH` env var).

### Schema

```sql
CREATE TABLE IF NOT EXISTS transactions (
    id                     TEXT PRIMARY KEY,     -- e.g. TX-A3F1C2D4-LON
    timestamp              TEXT NOT NULL,         -- UTC ISO 8601
    debtor_name            TEXT,
    debtor_sort_code       TEXT,
    debtor_account         TEXT,
    creditor_name          TEXT,
    creditor_sort_code     TEXT,
    creditor_account       TEXT,
    companies_house_number TEXT,
    amount                 REAL,
    currency               TEXT DEFAULT 'GBP',
    status                 TEXT DEFAULT 'PROCESSING',
    risk_score             TEXT,                  -- LOW / MEDIUM / HIGH
    confidence_score       REAL,                  -- 0.0 – 1.0
    reasoning              TEXT,                  -- natural-language rationale
    recommended_action     TEXT,                  -- ALLOW / ESCALATE_TO_MLRO / FREEZE_ACCOUNT
    completed_at           TEXT                   -- UTC ISO 8601
)
```

### Status lifecycle

```
PROCESSING  →  APPROVED   (risk_score = LOW)
            →  ESCALATED  (risk_score = MEDIUM)
            →  FROZEN     (risk_score = HIGH)
            →  ERROR      (all pipelines failed)
```

### Functions

| Function | What It Does |
|----------|-------------|
| `init_db()` | Creates the table if it doesn't exist. Called on application startup via FastAPI lifespan. |
| `create_transaction(data)` | Inserts a new row with `status = PROCESSING`. |
| `update_transaction(tx_id, updates)` | Dynamic UPDATE — builds SET clause from a dict. Used by agents after triage completes. |
| `get_transaction(tx_id)` | Returns a single row as a dict, or `None`. |
| `get_all_transactions()` | Returns all rows as `{tx_id: row_dict}`, newest first. |

---

## 9. The Three-Agent Pipeline

**File: `app/agents/crew.py`**

All three pipeline variants share the same three-stage conceptual flow. In the full CrewAI pipeline, these are real AI agents with LLM reasoning and tool calls.

### Agent 1 — Transaction Sifting Agent

**Role:** Financial intelligence analyst.

**Tool:** `LedgerQueryTool` — queries the SQLite database for the debtor's full transaction history.

**What it does:**
1. Retrieves the debtor's prior payment history from the ledger.
2. Checks each of these patterns explicitly:
   - **Structuring** — multiple payments just below £10,000
   - **Round-number avoidance** — amounts like £9,999 or £4,999
   - **Velocity** — abnormally high frequency vs. historical baseline
   - **Escalation** — amounts incrementally growing
   - **New payee** — first-time payment to this creditor
   - **Reference quality** — vague or inconsistent descriptions
   - **Clean baseline** — regular consistent payments suggesting legitimate activity

**Output:** A structured behavioural analysis with specific cited evidence and a confidence level (HIGH / MEDIUM / LOW).

### Agent 2 — OSINT Corporate Investigator

**Role:** Corporate intelligence analyst with Companies House access.

**Tool:** `CompaniesHouseTool` — looks up company status, incorporation date, and UBO.

**What it does:**
- If the creditor has a `companies_house_number`: calls the tool to retrieve the registry record.
- If no number is present: reports the payee as a private individual and skips lookup.
- Flags: dormant shell companies, offshore PSC ownership (Seychelles, BVI), newly incorporated entities.

**Output:** Company status, incorporation date, UBO name, nationality, country of residence, and share percentage.

### Agent 3 — Senior AML Compliance Officer (Risk Scorer)

**Role:** Senior Compliance Officer applying FCA MLR-2017 rules.

**What it does:**
Synthesises findings from Agents 1 and 2 and applies these explicit rules:

| Condition | Risk | Action |
|-----------|------|--------|
| Amount £9,000–£9,999 | MEDIUM | ESCALATE_TO_MLRO |
| Dormant company | HIGH | FREEZE_ACCOUNT |
| Offshore UBO (Seychelles/BVI/Cayman) | HIGH | FREEZE_ACCOUNT |
| Amount ≥ £100,000 with unverified entity | HIGH | FREEZE_ACCOUNT |
| None of the above | LOW | ALLOW |

**Output:** A structured JSON object enforced by the `RiskAssessment` Pydantic model:
```json
{
  "risk_score": "HIGH",
  "confidence_score": 0.96,
  "reasoning": "Creditor is a dormant shell company with offshore UBO in Seychelles...",
  "recommended_action": "FREEZE_ACCOUNT"
}
```

### CrewAI Orchestration

```python
crew = Crew(
    agents=[sifter, osint, risk_scorer],
    tasks=[task1, task2, task3],
    process=Process.sequential,  # Tasks run in order, output feeds forward
    verbose=True,
    tracing=True,
)
await crew.kickoff_async(inputs={})
```

Each task has a **WebSocket callback** (`_ws_callback`) that fires when the task completes, broadcasting an `AGENT_STEP` event to all connected dashboard clients. This is a sync-to-async bridge using `asyncio.run_coroutine_threadsafe` because CrewAI callbacks are synchronous while FastAPI runs an async event loop.

---

## 10. Agent Tools

**File: `app/agents/tools.py`**

### `CompaniesHouseTool` (CrewAI `BaseTool`)

- **Tool name registered with LLM:** `companies_house_lookup`
- **Input:** Company registration number string (e.g. `UK12984401` or `12984401`)
- **Logic:**
  1. Checks the in-memory mock registry first (always wins for test numbers like `UK12984401`).
  2. If `COMPANY_HOUSE_KEY` is set, strips the `UK` prefix and makes a live HTTP call to `api.company-information.service.gov.uk`.
  3. Fetches both the company profile and the PSC (Persons with Significant Control) list.
  4. Maps the real API response to the internal record format.
- **Returns:** JSON string of the company record, or a "no match found" message.

### `LedgerQueryTool` (CrewAI `BaseTool`)

- **Tool name registered with LLM:** `ledger_query`
- **Input:** Debtor account number string (e.g. `44891023`)
- **Logic:** Opens the SQLite DB with `sqlite3` (sync, since CrewAI tools are sync), fetches up to 50 prior transactions for that account ordered by timestamp descending.
- **Returns:** Formatted plain-text report including:
  - All historical transactions with date, amount, creditor, risk score
  - Amount range and average
  - Warning if any amounts fall in the £9,000–£9,999 structuring band

### `CompaniesHouseClient` (async wrapper)

An async class wrapping `lookup_company_sync` in `asyncio.run_in_executor` so the deterministic fallback pipeline doesn't block the event loop while making HTTP calls.

### Mock Companies House Registry

Three companies are hardcoded to cover all risk scenarios without requiring a real API key:

| Number | Company | Status | UBO Location | Expected Risk |
|--------|---------|--------|--------------|---------------|
| `UK12984401` | Apex Apex Ltd | Active | Seychelles | HIGH |
| `UK99882211` | Vanguard Global Holdings Ltd | Dormant | BVI | HIGH |
| `UK00110022` | National Grid UK Utility Ltd | Active | United Kingdom | LOW |

---

## 11. LLM Clients

### `ClaudeAMLClient` — `app/services/claude_client.py`

Uses **Anthropic's `AsyncAnthropic` SDK** with the `claude-opus-4-8` model.

**Key feature:** Uses `client.messages.parse()` with `output_format=RiskAssessment` — this is the Anthropic SDK's structured output mode, which enforces the Pydantic schema at the SDK level (not just prompt engineering).

**System prompt:** Instructs the model to act as a Senior Compliance Officer, evaluate MLR-2017 red flags, and identify structuring, smurfing, and offshore shell transfers.

**Adaptive thinking:** The call uses `thinking={"type": "adaptive"}` — Claude will apply extended reasoning automatically when the transaction is complex.

**Fallback (`_compute_local_fallback`):** If the API key is missing or the API call fails, falls back to a deterministic rule engine:
- Dormant company → HIGH / FREEZE_ACCOUNT
- Seychelles/BVI UBO → HIGH / FREEZE_ACCOUNT
- Amount £9,000–£9,999 → MEDIUM / ESCALATE_TO_MLRO
- Otherwise → LOW / ALLOW

### `GeminiAMLClient` — `app/services/gemini_client.py`

Makes a raw **HTTPS POST** to the Gemini REST API (not via a Google SDK) using `httpx`.

**Model:** `gemini-2.5-flash-preview-09-2025`

**Structured output:** Uses `responseMimeType: "application/json"` and `responseSchema` to enforce the same four-field JSON schema — this is Gemini's native schema-constrained generation, eliminating hallucination of field names.

**Retry logic:** Exponential backoff with delays `[1, 2, 4, 8, 16]` seconds across 5 attempts. Falls back to the same deterministic rules if all retries fail.

**Temperature:** Set to `0.1` — very low, to maximise determinism in compliance decisions.

---

## 12. Pipeline Selection Logic

**Entry point: `run_agentic_triage_loop()` in `app/agents/crew.py`**

```
GEMINI_API_KEY set?
    YES  →  _run_crew_pipeline()         (CrewAI + Gemini 2.5 Flash as primary LLM)
    NO
    ANTHROPIC_API_KEY set?
        YES  →  _run_deterministic_pipeline()  (rule-based flow + Claude Opus scoring)
        NO   →  _run_rules_pipeline()          (pure deterministic rules, no LLM)

On any exception in primary:
    →  _run_rules_pipeline()  (safety fallback)

On exception in rules pipeline:
    →  Write status=ERROR, risk=HIGH, action=ESCALATE_TO_MLRO
```

**Why this matters:** The system degrades gracefully at every level. In production, it will use the full AI pipeline. In development with no keys, it still produces valid compliance verdicts. In a catastrophic failure, it defaults to `ESCALATE_TO_MLRO` to ensure no high-risk transaction slips through unreviewed.

### Full CrewAI Pipeline (`_run_crew_pipeline`)

Uses `Process.sequential` — tasks execute in order. Sifter output is available in the context when OSINT runs; both are available when the Risk Scorer runs. The LLM for all three agents is Gemini 2.5 Flash. A local Ollama Llama 3.1 8B is also defined in the code (for future local-model experiments) but not actively wired to any agent.

### Deterministic Fallback Pipeline (`_run_deterministic_pipeline`)

Simulates the Sifter and OSINT steps with direct function calls (no LLM), then calls the Claude client for risk scoring. The Claude client itself has its own local fallback if it can't reach the API.

### Pure Rules Pipeline (`_run_rules_pipeline`)

No network calls to any LLM. Applies the MLR-2017 thresholds directly:
1. Check amount against £9,000–£9,999 band
2. Check company status (dormant) and UBO country (offshore jurisdictions)
3. Check amount ≥ £100,000
4. Higher-severity findings override lower-severity ones

---

## 13. REST API Endpoints

**File: `app/main.py`**

### `POST /api/v1/transaction`

**Request body:** `ISO20022Payload` JSON

**What happens:**
1. Pydantic validates the entire payload (sort codes, amounts, etc.)
2. Generates a unique transaction ID: `TX-{8 random hex digits uppercase}-LON`
3. Writes a `PROCESSING` record to SQLite
4. Adds `run_agentic_triage_loop` to FastAPI `BackgroundTasks`
5. Returns `202 Accepted` immediately

**Response:**
```json
{
  "message": "ISO 20022 schema validated. Dropping into asynchronous triaging queue.",
  "transaction_id": "TX-A3F1C2D4-LON",
  "status_query_url": "/api/v1/transaction/TX-A3F1C2D4-LON"
}
```

### `GET /api/v1/transaction/{tx_id}`

Returns the full ledger row for a specific transaction. Returns 404 if not found.

Example completed response:
```json
{
  "id": "TX-A3F1C2D4-LON",
  "timestamp": "2026-06-23T10:45:00",
  "debtor_name": "Alex Mercer",
  "debtor_sort_code": "20-45-12",
  "debtor_account": "44891023",
  "creditor_name": "Apex Apex Ltd",
  "creditor_sort_code": "60-83-01",
  "creditor_account": "99201145",
  "companies_house_number": "UK12984401",
  "amount": 250000.00,
  "currency": "GBP",
  "status": "FROZEN",
  "risk_score": "HIGH",
  "confidence_score": 0.96,
  "reasoning": "Creditor is an active company with offshore UBO in Seychelles...",
  "recommended_action": "FREEZE_ACCOUNT",
  "completed_at": "2026-06-23T10:45:05"
}
```

### `GET /api/v1/ledger`

Returns all transactions as a dict keyed by transaction ID, ordered newest first.

### `GET /`

Serves `index.html` — the main live dashboard.

### `GET /demo`

Serves `demo.html` — a secondary demo page.

### `WS /ws/compliance`

WebSocket endpoint. After connecting, clients receive JSON events (see section 14). The server responds to any client text message with `{"ping": "pong"}` as a heartbeat.

---

## 14. WebSocket Real-Time Layer

**File: `app/services/websocket_manager.py`**

### `ConnectionManager`

A singleton (`websocket_manager`) that maintains a list of all active WebSocket connections.

| Method | What It Does |
|--------|-------------|
| `connect(ws)` | Accepts the WebSocket handshake, appends to active list |
| `disconnect(ws)` | Removes from active list on client disconnect |
| `broadcast(message)` | Sends JSON to every active connection; logs errors but doesn't crash if one client is gone |

### Event Schema

**`AGENT_STEP` event** — emitted after each agent completes its task:
```json
{
  "event": "AGENT_STEP",
  "tx_id": "TX-A3F1C2D4-LON",
  "agent": "Sifting Agent",
  "log": "[Sifter output, truncated to 600 chars]"
}
```

**`TRIAGE_COMPLETE` event** — emitted after the full pipeline finishes:
```json
{
  "event": "TRIAGE_COMPLETE",
  "tx_id": "TX-A3F1C2D4-LON",
  "payload": { ...full ledger row... }
}
```

### Sync-to-Async Bridge

CrewAI task callbacks are synchronous, but the WebSocket manager's `broadcast()` is a coroutine. The bridge uses:
```python
asyncio.run_coroutine_threadsafe(websocket_manager.broadcast(...), loop)
```
where `loop` is the event loop captured at the start of `_run_crew_pipeline`. This is necessary because CrewAI executes its agent loop in a thread pool.

---

## 15. The Frontend Dashboard

**File: `index.html`** (served at `/`)

A single-page application built with Tailwind CSS (CDN), Font Awesome icons, and vanilla JavaScript. No build step required.

### Layout

The dashboard has a three-column layout on large screens:

**Left column — Ingestion Gateway:**
- Three preset scenario buttons (Structuring, Dormant Shell, Clean Payroll)
- Raw ISO 20022 payload viewer (shows the JSON sent to the backend)

**Middle column — Agent Pipeline:**
- Visual timeline of the three agents with animated step indicators
- Live event terminal showing WebSocket messages in real time

**Right column — Decision Panel:**
- Risk card that changes colour on outcome (red = HIGH, amber = MEDIUM, green = LOW)
- Shows risk score, AI reasoning, and recommended action
- Mini audit ledger showing the 10 most recent transactions

**Full Ledger tab:**
- A full sortable table of all transactions fetched from `GET /api/v1/ledger`

### WebSocket Client Logic

```javascript
function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    socket = new WebSocket(`${wsProtocol}//${window.location.host}/ws/compliance`);
    // On disconnect: auto-retry after 3 seconds
}
```

Events are filtered by `tx_id` — when tracking a specific transaction, events from other concurrent transactions are ignored.

### Three Pre-Built Scenarios

| Scenario | Amount | Creditor | Expected Outcome |
|----------|--------|----------|-----------------|
| Smurfing & Structuring | £9,850 | Apex Holdings Ltd (UK12984401, Seychelles UBO) | HIGH / FREEZE |
| Dormant Shell Transfer | £145,000 | VANGUARD HOLDINGS GROUP LIMITED | HIGH / FREEZE |
| High-Street Payroll | £3,250 | Jonathan Doe (private individual) | LOW / ALLOW |

### Light / Dark Mode

Theme is toggled via a sun/moon button and persisted in `localStorage`. The light mode is implemented via CSS class overrides on `html.light` — approximately 20 Tailwind utility class overrides covering backgrounds, borders, and text colours.

---

## 16. Risk Typologies & Scoring Rules

The system detects four AML typologies, applied in priority order (high overrides medium, etc.):

### Typology 1 — Structuring / Smurfing
- **Trigger:** Amount between £9,000 and £9,999 (inclusive)
- **Legal basis:** MLR 2017, regulation 27 — designed to evade the £10,000 reporting threshold
- **Risk:** MEDIUM
- **Action:** ESCALATE_TO_MLRO

### Typology 2 — Dormant Shell Company
- **Trigger:** Companies House status is `"Dormant"`
- **Legal basis:** MLR 2017, regulation 28 — shell companies used for layering
- **Risk:** HIGH
- **Action:** FREEZE_ACCOUNT

### Typology 3 — Offshore UBO
- **Trigger:** PSC (Person with Significant Control) country of residence is Seychelles, BVI, British Virgin Islands, or Cayman Islands
- **Legal basis:** MLR 2017 — offshore structures used to conceal beneficial ownership
- **Risk:** HIGH
- **Action:** FREEZE_ACCOUNT

### Typology 4 — High-Value Corporate Transfer
- **Trigger:** Amount ≥ £100,000
- **Legal basis:** MLR 2017, regulation 33 — enhanced due diligence mandatory
- **Risk:** HIGH
- **Action:** FREEZE_ACCOUNT

### Standard Clearance
- **Trigger:** None of the above
- **Risk:** LOW
- **Action:** ALLOW
- **Confidence:** 0.85–0.99 (deterministic) or LLM-generated (AI pipelines)

---

## 17. Mock Companies House Registry

Three companies are hardcoded in `app/agents/tools.py` to allow full pipeline testing without a Companies House API key:

### `UK12984401` — Apex Apex Ltd
- **Status:** Active
- **Incorporated:** 2026-04-10 (very recently — red flag)
- **Business:** Financial holding companies (SIC 64209)
- **Address:** 85 Great Portland Street, London W1W 7LT
- **UBO:** Dimitri Volkov, Cypriot national, resident in **Seychelles**, 75% ownership
- **Expected risk:** HIGH — offshore UBO

### `UK99882211` — Vanguard Global Holdings Ltd
- **Status:** Dormant
- **Incorporated:** 2019-11-23
- **Business:** Management consultancy
- **Address:** 12 Laleham Road, London SE13 5EH
- **UBO:** Hidden Beneficiary Corporation, **BVI**, 100% ownership
- **Expected risk:** HIGH — both dormant and offshore UBO

### `UK00110022` — National Grid UK Utility Ltd
- **Status:** Active
- **Incorporated:** 1999-04-10 (long-established)
- **Business:** Electricity production (SIC 35110)
- **Address:** 1-3 Strand, London WC2N 5EH
- **UBO:** HM Treasury Nominees, British, **United Kingdom**, 51% ownership
- **Expected risk:** LOW — legitimate established utility

---

## 18. Test Data Scripts

### `scripts/generate_transactions.py`

Generates synthetic ISO 20022 payloads using the `Faker` library with the `en_GB` locale.

**Transaction typology distribution (randomised):**
| Probability | Typology | Amount Range |
|-------------|----------|-------------|
| 15% | Structuring / Smurfing | £9,800–£9,995 |
| 15% | High-value corporate | £110,000–£500,000 |
| 70% | Standard retail | £150–£4,500 |

**Sort code generation:** Randomly picks from common UK bank prefixes (20=Barclays, 40=HSBC, 60=NatWest etc.) then generates the remaining digits. 20% of the time produces a space-separated format, 20% unformatted, 60% hyphenated — to exercise the validator.

**Account number generation:** 8 random digits. 25% of the time adds a space in the middle (e.g. `1234 5678`) to test whitespace stripping.

Can be run standalone to preview payloads:
```bash
python scripts/generate_transactions.py
```

### `scripts/submit_transactions.py`

A CLI tool that generates and submits transactions to the running backend.

**Options:**
```
-n N         Submit N transactions (default: 1)
--poll       After submitting, poll each transaction until triage completes and print the result
--loop       Submit continuously until Ctrl+C
--interval S Seconds between submissions in loop mode (default: 5)
--base-url   Backend URL (default: http://127.0.0.1:8000)
```

**Examples:**
```bash
# Submit 1 transaction and see it accepted
python scripts/submit_transactions.py

# Submit 10 and wait for triage results
python scripts/submit_transactions.py -n 10 --poll

# Stress test: continuous submission every 2 seconds
python scripts/submit_transactions.py --loop --interval 2 --poll
```

**Polling logic:** Checks `GET /api/v1/transaction/{tx_id}` every second, times out after 30 seconds if status remains `PROCESSING`.

---

## 19. Docker & Azure Deployment

### `Dockerfile`

A two-stage build:
1. **Builder stage** (`python:3.13-slim`): Installs `uv` from its GitHub Container Registry image, then uses it to install all dependencies from `requirements.txt` into the system Python.
2. **Runtime stage** (`python:3.13-slim`): Copies installed site-packages from builder, copies only the `app/` directory and HTML files, exposes port 8000.

```bash
# Build
docker build -t aml-engine .

# Run (all pipelines active)
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=your-key \
  -e ANTHROPIC_API_KEY=your-key \
  aml-engine
```

The `CMD` uses `--host 0.0.0.0` (not `127.0.0.1`) so the port is reachable from outside the container.

### `containerapp.yaml` — Azure Container Apps

Configures deployment to Azure UK South:
- **Container registry:** `amlenginecr.azurecr.io`
- **Secrets:** ACR password, Gemini key, and Anthropic key stored as Container App secrets (not plaintext env vars)
- **Persistent storage:** Azure Files mounted at `/mnt/data/` for the SQLite database (so data survives container restarts)
- **Scaling:** Fixed at 1 replica (min=max=1) — appropriate for a demo; set `maxReplicas > 1` for production
- **Ingress:** External (publicly reachable), target port 8000

---

## 20. Planned Future Work

The `blueprint.md` describes three future phases, none yet implemented:

### Phase A — RAG over FCA Regulations
Load the actual FCA MLR-2017 PDF and JMLSG guidance documents into a **ChromaDB** vector store using LangChain document loaders. Wrap the vector store as a `FCARegulationTool` accessible by the Risk Scorer. The agent can then cite specific regulation clauses in its reasoning, not just apply hardcoded rules.

Files to create: `app/rag/loader.py`, `app/rag/vector_store.py`

### Phase B — LangGraph Conditional Routing
Add a LangGraph state machine that routes transactions based on Sifter confidence:
- High suspicion → full pipeline (all three agents)
- Low suspicion → fast path (Sifter → Risk Scorer only, skip OSINT)
- Medium + no Companies House number → fast path

Estimated 40% latency and cost reduction on clean transactions.

Files to create: `app/graph/state.py`, `app/graph/router.py`

### Phase C — Human-in-the-Loop MLRO Review
For `HIGH` risk transactions, pause the LangGraph pipeline and hold the transaction in `PENDING_MLRO_REVIEW` state. A Money Laundering Reporting Officer reviews the case via a new `POST /api/v1/transaction/{tx_id}/review` endpoint. The graph resumes with the officer's decision recorded in the audit trail. This implements FCA SYSC compliance — automated account freezes without human sign-off would fail a regulatory audit.

The `graphql/` directory (currently placeholder files) is intended to provide an audit trail query interface using Strawberry GraphQL once the above phases are implemented.

---

## 21. End-to-End Request Flow

Here is the complete journey of one transaction, step by step:

```
1. Client POSTs ISO 20022 JSON to /api/v1/transaction

2. FastAPI receives it → Pydantic validates:
   - Sort code format (normalised to XX-XX-XX)
   - Account number (exactly 8 digits)
   - Amount (must be > 0)
   - Message identifier and reference (length bounds)
   If validation fails → 422 Unprocessable Entity returned immediately

3. Transaction ID generated: "TX-{8 hex chars uppercase}-LON"
   e.g. TX-A3F1C2D4-LON

4. SQLite row inserted with status=PROCESSING

5. FastAPI returns 202 Accepted:
   { "transaction_id": "TX-A3F1C2D4-LON", "status_query_url": "..." }

6. Background task starts: run_agentic_triage_loop(tx_id, payload)

7. Pipeline selector checks env vars:
   → With GEMINI_API_KEY: kicks off CrewAI crew

8. Agent 1 (Sifter) runs:
   - LedgerQueryTool queries SQLite for debtor's history
   - Gemini 2.5 Flash analyses output for structuring patterns
   - Task callback fires → WebSocket broadcast:
     { "event": "AGENT_STEP", "agent": "Sifting Agent", "log": "..." }

9. Agent 2 (OSINT) runs:
   - CompaniesHouseTool looks up companies_house_number
   - Checks mock registry (or live API if key set)
   - Returns company status + UBO details
   - Task callback fires → WebSocket broadcast

10. Agent 3 (Risk Scorer) runs:
    - Receives context from both prior agents
    - Gemini applies MLR-2017 rules
    - Returns RiskAssessment JSON (schema-enforced)
    - Task callback fires → WebSocket broadcast

11. crew.kickoff_async() returns
    Final RiskAssessment extracted from task3.output.pydantic

12. SQLite updated:
    status = FROZEN / ESCALATED / APPROVED
    risk_score, confidence_score, reasoning, recommended_action, completed_at

13. Final WebSocket broadcast:
    { "event": "TRIAGE_COMPLETE", "tx_id": "...", "payload": {...full row...} }

14. If risk_score == HIGH:
    Logger warning: "FREEZE PROTOCOL ENGAGED: Account {account} frozen."
    (In a real system, this would POST to the core banking freeze API)

15. Dashboard receives TRIAGE_COMPLETE:
    - Decision card changes colour (red)
    - Reasoning text populated
    - Ledger list updated
    - Stats counters incremented

16. Client can also poll at any time:
    GET /api/v1/transaction/TX-A3F1C2D4-LON
    → Returns the full ledger row with final verdict
```

---

*This document covers every file, function, data flow, regulatory rule, and design decision in the project as of June 2026.*
