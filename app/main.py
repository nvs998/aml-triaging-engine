import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.responses import FileResponse, Response

from app.parser.models import ISO20022Payload
from app.agents.crew import run_agentic_triage_loop
from app.services.websocket_manager import websocket_manager
from app.ledger import init_db, create_transaction, get_transaction, get_all_transactions

logger = logging.getLogger("AMLEngine")

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("SQLite ledger initialised at aml_ledger.db")
    yield


app = FastAPI(
    title="Asynchronous Transaction Risk & AML Triaging Engine",
    description="FCA-compliant ISO 20022 transactional triaging engine using multi-agent simulators.",
    version="1.0.0",
    lifespan=lifespan,
)

# ----------------------------------------------------------------------
# Static & UI Routes
# ----------------------------------------------------------------------

@app.get("/")
async def serve_dashboard():
    return FileResponse(BASE_DIR / "index.html")

@app.get("/demo")
async def serve_demo():
    return FileResponse(BASE_DIR / "demo.html")

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def devtools():
    return Response(status_code=204)

# ----------------------------------------------------------------------
# REST Endpoints
# ----------------------------------------------------------------------

@app.post("/api/v1/transaction", status_code=status.HTTP_202_ACCEPTED)
async def ingest_transaction(payload: ISO20022Payload, background_tasks: BackgroundTasks):
    tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}-LON"
    await create_transaction({
        "id": tx_id,
        "timestamp": datetime.utcnow().isoformat(),
        "debtor_name": payload.debtor.name,
        "debtor_sort_code": payload.debtor.sort_code,
        "debtor_account": payload.debtor.account_number,
        "creditor_name": payload.creditor.name,
        "creditor_sort_code": payload.creditor.sort_code,
        "creditor_account": payload.creditor.account_number,
        "amount": payload.transaction.amount,
        "currency": payload.transaction.currency,
        "status": "PROCESSING",
        "companies_house_number": payload.creditor.companies_house_number,
    })
    background_tasks.add_task(run_agentic_triage_loop, tx_id, payload)
    return {
        "message": "ISO 20022 schema validated. Dropping into asynchronous triaging queue.",
        "transaction_id": tx_id,
        "status_query_url": f"/api/v1/transaction/{tx_id}",
    }

@app.get("/api/v1/transaction/{tx_id}")
async def get_transaction_by_id(tx_id: str):
    tx = await get_transaction(tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not located in the ledger.")
    return tx

@app.get("/api/v1/ledger")
async def get_entire_ledger():
    return await get_all_transactions()

# ----------------------------------------------------------------------
# WebSocket
# ----------------------------------------------------------------------

@app.websocket("/ws/compliance")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"ping": "pong"})
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
