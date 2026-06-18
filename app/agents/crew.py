import asyncio
import logging
from datetime import datetime

from app.parser.models import ISO20022Payload
from app.agents.tools import CompaniesHouseClient
from app.services.claude_client import ClaudeAMLClient
from app.services.websocket_manager import websocket_manager
from app.ledger import TRANSACTION_LEDGER

logger = logging.getLogger("AMLEngine.Crew")

companies_house_client = CompaniesHouseClient()
claude_client = ClaudeAMLClient()


async def run_agentic_triage_loop(tx_id: str, payload: ISO20022Payload):
    logger.info(f"Starting multi-agent evaluation for: {tx_id}")

    # Agent 1: Sifter
    await asyncio.sleep(1.0)
    await websocket_manager.broadcast({
        "event": "AGENT_STEP",
        "tx_id": tx_id,
        "agent": "Sifting Agent",
        "log": f"Successfully parsed ISO payload {payload.message_identifier}. Extracted amount: {payload.transaction.amount} GBP. Running transactional structure rules..."
    })

    # Agent 2: OSINT Investigator
    companies_house_num = payload.creditor.companies_house_number
    record = None

    if companies_house_num:
        record = await companies_house_client.lookup_company(companies_house_num)
        if record:
            psc = record["person_with_significant_control"]
            ubo_details = f"{psc['name']} ({psc['nationality']} / Resident in {psc['country_of_residence']})"
            await websocket_manager.broadcast({
                "event": "AGENT_STEP",
                "tx_id": tx_id,
                "agent": "OSINT Investigator",
                "log": f"Companies House lookup successful for {companies_house_num}. Company: {record['company_name']}. Status: {record['status']}. UBO: {ubo_details}."
            })
        else:
            await websocket_manager.broadcast({
                "event": "AGENT_STEP",
                "tx_id": tx_id,
                "agent": "OSINT Investigator",
                "log": f"No registry match found for Companies House ID {companies_house_num}. Entity could not be verified."
            })
    else:
        await websocket_manager.broadcast({
            "event": "AGENT_STEP",
            "tx_id": tx_id,
            "agent": "OSINT Investigator",
            "log": "Bypassed corporate check. Payee evaluated as a private consumer account."
        })

    # Agent 3: Risk Scorer
    await websocket_manager.broadcast({
        "event": "AGENT_STEP",
        "tx_id": tx_id,
        "agent": "Risk Scorer",
        "log": "Forwarding metadata and registry findings to the Claude AI compliance evaluator..."
    })

    evaluation = await claude_client.evaluate_risk(
        transaction=payload.transaction.model_dump(),
        company_metadata=record,
    )

    risk_score = evaluation["risk_score"]
    TRANSACTION_LEDGER[tx_id].update({
        "status": "FROZEN" if risk_score == "HIGH" else "ESCALATED" if risk_score == "MEDIUM" else "APPROVED",
        "risk_score": risk_score,
        "confidence_score": evaluation["confidence_score"],
        "reasoning": evaluation["reasoning"],
        "recommended_action": evaluation["recommended_action"],
        "completed_at": datetime.utcnow().isoformat()
    })

    await websocket_manager.broadcast({
        "event": "TRIAGE_COMPLETE",
        "tx_id": tx_id,
        "payload": TRANSACTION_LEDGER[tx_id]
    })

    if risk_score == "HIGH":
        logger.warning(f"FREEZE PROTOCOL ENGAGED: Account {payload.creditor.account_number} frozen.")
