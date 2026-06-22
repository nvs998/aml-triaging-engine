import asyncio
import json
import logging
from datetime import datetime

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tasks.task_output import TaskOutput

from app.parser.models import ISO20022Payload
from app.agents.tools import CompaniesHouseTool, CompaniesHouseClient, LedgerQueryTool
from app.services.claude_client import ClaudeAMLClient, RiskAssessment
from app.services.websocket_manager import websocket_manager
from app.ledger import update_transaction, get_transaction
from app.config import ANTHROPIC_API_KEY, GEMINI_API_KEY

logger = logging.getLogger("AMLEngine.Crew")


# ---------------------------------------------------------------------------
# WebSocket callback factory — bridges sync CrewAI callbacks → async FastAPI
# ---------------------------------------------------------------------------

def _ws_callback(tx_id: str, agent_name: str, loop: asyncio.AbstractEventLoop):
    def callback(output: TaskOutput):
        asyncio.run_coroutine_threadsafe(
            websocket_manager.broadcast({
                "event": "AGENT_STEP",
                "tx_id": tx_id,
                "agent": agent_name,
                "log": output.raw[:600],
            }),
            loop,
        )
    return callback


# ---------------------------------------------------------------------------
# Real CrewAI pipeline (requires LLM_API_KEY)
# ---------------------------------------------------------------------------

async def _run_crew_pipeline(tx_id: str, payload: ISO20022Payload) -> None:
    loop = asyncio.get_event_loop()

    llm = LLM(
        model="gemini/gemini-2.5-flash",
        api_key=GEMINI_API_KEY,
        max_tokens=2048,
    )

    local_llama = LLM(
      model="ollama/llama3.1:8b",
      base_url="http://localhost:11434",
  )

    transaction_json = json.dumps({
        "message_identifier": payload.message_identifier,
        "debtor": payload.debtor.model_dump(),
        "creditor": payload.creditor.model_dump(),
        "transaction": payload.transaction.model_dump(),
    }, indent=2)

    companies_house_num = payload.creditor.companies_house_number

    # --- Agents ---
    sifter = Agent(
        role="Transaction Sifting Agent",
        goal=(
            "Detect behavioural and structural AML red flags by analysing the current "
            "transaction against the debtor's full payment history, producing evidence-backed "
            "findings that the Senior Compliance Officer can act on."
        ),
        backstory=(
            "You are a financial intelligence analyst at a UK Tier-1 bank with eight years "
            "of experience in transaction monitoring under FCA supervision. You are trained "
            "in JMLSG guidance (Joint Money Laundering Steering Group) and work closely with "
            "the National Crime Agency's Financial Intelligence Unit when filing Suspicious "
            "Activity Reports (SARs). "
            "You know that money laundering happens in three stages — placement (getting dirty "
            "money into the system), layering (moving it around to obscure the trail), and "
            "integration (making it appear legitimate). Your job is to catch the earliest "
            "signals of placement and layering before they reach the integration stage. "
            "You have seen every structuring pattern: smurfing (splitting large sums into "
            "sub-threshold payments), round-number avoidance (£9,999 instead of £10,000), "
            "velocity abuse (many small payments in a short window), and escalation "
            "(gradually increasing amounts testing the system). "
            "You understand that context matters — a £9,850 payment from a business with "
            "three years of clean payroll history is very different from the same amount sent "
            "by a dormant account to a newly registered company. "
            "Your analysis is the first thing the Senior Compliance Officer reads, so your "
            "findings must be specific, evidence-based, and clearly state your confidence level."
        ),
        tools=[LedgerQueryTool()],
        llm=local_llama,
        allow_delegation=False,
        verbose=True,
    )

    osint = Agent(
        role="OSINT Corporate Investigator",
        goal="Verify the creditor's corporate identity and Ultimate Beneficial Owner via Companies House",
        backstory=(
            "You are a corporate intelligence analyst with access to the UK Companies House registry. "
            "You flag dormant shell companies, offshore PSC ownership structures, and newly "
            "incorporated entities used as money laundering vehicles."
        ),
        tools=[CompaniesHouseTool()],
        llm=local_llama,
        allow_delegation=False,
        verbose=True,
    )

    risk_scorer = Agent(
        role="Senior AML Compliance Officer",
        goal="Synthesize all findings and produce a final structured risk assessment",
        backstory=(
            "You are the Senior Compliance Officer at a UK financial institution, responsible for "
            "applying FCA MLR-2017 rules to produce legally defensible, explainable decisions. "
            "Your assessments must withstand scrutiny from the Financial Ombudsman Service."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=True,
    )

    # --- Tasks ---
    task1 = Task(
        description=(
            f"Perform a full behavioural sift on this ISO 20022 transaction:\n\n{transaction_json}\n\n"
            f"Debtor account number: {payload.debtor.account_number}\n\n"
            "Step 1 — Retrieve history: Call the ledger_query tool with the debtor account "
            "number to pull their full transaction history from the compliance ledger.\n\n"
            "Step 2 — Analyse for these patterns (check each one explicitly):\n"
            "  - Structuring: multiple payments just below £10,000 in a short window\n"
            "  - Round-number avoidance: amounts like £9,999 or £4,999 that suggest deliberate threshold dodging\n"
            "  - Velocity: abnormally high frequency of payments recently vs historical baseline\n"
            "  - Escalation: amounts incrementally increasing across transactions\n"
            "  - New payee: is this the first payment to this creditor, or a known recipient?\n"
            "  - Payment reference: is the reference vague, generic, or inconsistent with the amount?\n"
            "  - Clean baseline: regular, consistent payments that suggest legitimate business activity\n\n"
            "Step 3 — Write your findings with specific evidence: cite exact dates, amounts, "
            "and frequencies. Explain what the pattern means — not just what it is. "
            "State your confidence level (HIGH / MEDIUM / LOW) and the single most "
            "important signal the Senior Compliance Officer should weigh."
        ),
        expected_output=(
            "A structured behavioural analysis with: (1) a summary of the debtor's transaction "
            "history, (2) explicit findings on each pattern checked, (3) the key risk signal "
            "with supporting evidence, and (4) a stated confidence level. "
            "Written so the Senior Compliance Officer can act on it without re-reading the raw data."
        ),
        agent=sifter,
        callback=_ws_callback(tx_id, "Sifting Agent", loop),
    )

    task2 = Task(
        description=(
            f"Investigate the creditor entity in this transaction:\n\n{transaction_json}\n\n"
            + (
                f"The creditor has Companies House number: {companies_house_num}. "
                "Use the companies_house_lookup tool with that number to retrieve their registry record. "
                "Report the company status, incorporation date, and full UBO/PSC details."
                if companies_house_num
                else
                "The creditor has no Companies House number — treat as a private individual. "
                "No registry lookup is needed. State that the payee is an unregistered private consumer."
            )
        ),
        expected_output="A summary of the corporate entity's registry status and UBO details, or confirmation that the payee is a private individual.",
        agent=osint,
        callback=_ws_callback(tx_id, "OSINT Investigator", loop),
    )

    task3 = Task(
        description=(
            "Using the Sifting Agent's structural analysis and the OSINT Investigator's registry findings, "
            "produce a final AML risk assessment applying UK MLR-2017 rules.\n\n"
            "Rules to apply:\n"
            "- Amount £9,000–£9,999 → MEDIUM / ESCALATE_TO_MLRO (structuring)\n"
            "- Dormant company or offshore UBO (Seychelles/BVI/Cayman) → HIGH / FREEZE_ACCOUNT\n"
            "- Amount ≥ £100,000 with unverified entity → HIGH / FREEZE_ACCOUNT\n"
            "- Clean retail transaction → LOW / ALLOW\n\n"
            "Return ONLY a JSON object with these exact keys: "
            "risk_score (LOW/MEDIUM/HIGH), confidence_score (0.0–1.0), "
            "reasoning (string, max 80 words), recommended_action (ALLOW/ESCALATE_TO_MLRO/FREEZE_ACCOUNT)."
        ),
        expected_output='{"risk_score": "...", "confidence_score": 0.0, "reasoning": "...", "recommended_action": "..."}',
        output_pydantic=RiskAssessment,
        agent=risk_scorer,
        callback=_ws_callback(tx_id, "Risk Scorer", loop),
    )

    crew = Crew(
        agents=[sifter, osint, risk_scorer],
        tasks=[task1, task2, task3],
        process=Process.sequential,
        verbose=True,
        tracing=True,
    )

    await crew.kickoff_async(inputs={})

    # Extract structured output from final task
    if task3.output and task3.output.pydantic:
        assessment: RiskAssessment = task3.output.pydantic
    else:
        raw = task3.output.raw if task3.output else "{}"
        assessment = RiskAssessment.model_validate_json(raw)

    risk_score = assessment.risk_score
    await update_transaction(tx_id, {
        "status": "FROZEN" if risk_score == "HIGH" else "ESCALATED" if risk_score == "MEDIUM" else "APPROVED",
        "risk_score": risk_score,
        "confidence_score": assessment.confidence_score,
        "reasoning": assessment.reasoning,
        "recommended_action": assessment.recommended_action,
        "completed_at": datetime.utcnow().isoformat(),
    })


# ---------------------------------------------------------------------------
# Deterministic fallback pipeline (no API key required)
# ---------------------------------------------------------------------------

async def _run_deterministic_pipeline(tx_id: str, payload: ISO20022Payload) -> None:
    await asyncio.sleep(1.0)
    await websocket_manager.broadcast({
        "event": "AGENT_STEP",
        "tx_id": tx_id,
        "agent": "Sifting Agent",
        "log": (
            f"[Fallback] Parsed ISO payload {payload.message_identifier}. "
            f"Amount: £{payload.transaction.amount:,.2f}. Running structure rules..."
        ),
    })

    companies_house_num = payload.creditor.companies_house_number
    record = None
    client = CompaniesHouseClient()

    if companies_house_num:
        record = await client.lookup_company(companies_house_num)
        if record:
            psc = record["person_with_significant_control"]
            await websocket_manager.broadcast({
                "event": "AGENT_STEP",
                "tx_id": tx_id,
                "agent": "OSINT Investigator",
                "log": (
                    f"[Fallback] Companies House lookup: {record['company_name']} "
                    f"({record['status']}). UBO: {psc['name']} — {psc['country_of_residence']}."
                ),
            })
        else:
            await websocket_manager.broadcast({
                "event": "AGENT_STEP",
                "tx_id": tx_id,
                "agent": "OSINT Investigator",
                "log": f"[Fallback] No registry match for {companies_house_num}.",
            })
    else:
        await websocket_manager.broadcast({
            "event": "AGENT_STEP",
            "tx_id": tx_id,
            "agent": "OSINT Investigator",
            "log": "[Fallback] No Companies House number — private consumer account.",
        })

    await websocket_manager.broadcast({
        "event": "AGENT_STEP",
        "tx_id": tx_id,
        "agent": "Risk Scorer",
        "log": "[Fallback] Applying deterministic MLR-2017 rule engine...",
    })

    claude_client = ClaudeAMLClient()
    evaluation = await claude_client.evaluate_risk(
        transaction=payload.transaction.model_dump(),
        company_metadata=record,
    )

    risk_score = evaluation["risk_score"]
    await update_transaction(tx_id, {
        "status": "FROZEN" if risk_score == "HIGH" else "ESCALATED" if risk_score == "MEDIUM" else "APPROVED",
        "risk_score": risk_score,
        "confidence_score": evaluation["confidence_score"],
        "reasoning": evaluation["reasoning"],
        "recommended_action": evaluation["recommended_action"],
        "completed_at": datetime.utcnow().isoformat(),
    })


# ---------------------------------------------------------------------------
# Public entry point called by FastAPI background task
# ---------------------------------------------------------------------------

async def run_agentic_triage_loop(tx_id: str, payload: ISO20022Payload) -> None:
    logger.info("Starting triage for %s (CrewAI=%s)", tx_id, bool(GEMINI_API_KEY))
    try:
        if GEMINI_API_KEY:
            await _run_crew_pipeline(tx_id, payload)
        else:
            await _run_deterministic_pipeline(tx_id, payload)
    except Exception as e:
        logger.error("Pipeline failed for %s: %s", tx_id, e)
        await update_transaction(tx_id, {
            "status": "ERROR",
            "risk_score": "HIGH",
            "confidence_score": 0.0,
            "reasoning": f"Pipeline error — manual review required. ({str(e)[:200]})",
            "recommended_action": "ESCALATE_TO_MLRO",
            "completed_at": datetime.utcnow().isoformat(),
        })

    tx = await get_transaction(tx_id)
    await websocket_manager.broadcast({
        "event": "TRIAGE_COMPLETE",
        "tx_id": tx_id,
        "payload": tx,
    })

    if tx and tx.get("risk_score") == "HIGH":
        logger.warning("FREEZE PROTOCOL ENGAGED: Account %s frozen.", payload.creditor.account_number)
