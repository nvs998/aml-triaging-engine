"""
Submit synthetic ISO 20022 transactions to the AML triaging backend.

Usage:
    python scripts/submit_transactions.py              # submit 1 transaction
    python scripts/submit_transactions.py -n 5         # submit 5 transactions
    python scripts/submit_transactions.py -n 3 --poll  # submit and poll for results
    python scripts/submit_transactions.py --loop       # continuously post every 5s (Ctrl+C to stop)
    python scripts/submit_transactions.py --loop --interval 10  # post every 10s
"""
import argparse
import time
import logging
import sys
from pathlib import Path

import httpx

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.generate_transactions import generate_synthetic_transaction

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AML.Submitter")

BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL = 1.0   # seconds between status checks
POLL_TIMEOUT  = 30.0  # max seconds to wait per transaction


def submit(client: httpx.Client, payload: dict) -> str | None:
    try:
        r = client.post(f"{BASE_URL}/api/v1/transaction", json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        tx_id = data["transaction_id"]
        logger.info("Accepted  → %s  (%s)", tx_id, data["status_query_url"])
        return tx_id
    except httpx.HTTPStatusError as e:
        logger.error("Rejected (HTTP %s): %s", e.response.status_code, e.response.text)
    except httpx.RequestError as e:
        logger.error("Connection failed — is the server running? (%s)", e)
    return None


def poll(client: httpx.Client, tx_id: str) -> dict | None:
    deadline = time.monotonic() + POLL_TIMEOUT
    while time.monotonic() < deadline:
        try:
            r = client.get(f"{BASE_URL}/api/v1/transaction/{tx_id}", timeout=5)
            r.raise_for_status()
            entry = r.json()
            if entry.get("status") != "PROCESSING":
                return entry
        except httpx.RequestError as e:
            logger.warning("Poll error for %s: %s", tx_id, e)
        time.sleep(POLL_INTERVAL)
    logger.warning("Timed out waiting for %s", tx_id)
    return None


def print_result(entry: dict) -> None:
    risk    = entry.get("risk_score", "—")
    action  = entry.get("recommended_action", "—")
    conf    = entry.get("confidence_score")
    conf_s  = f"{conf:.0%}" if conf is not None else "—"
    print(
        f"  [{entry['id']}]  {risk:<7}  {action:<25}  confidence={conf_s}\n"
        f"  Reasoning : {entry.get('reasoning', '—')}\n"
    )


def submit_one(client: httpx.Client, index: int, total: int) -> str | None:
    payload = generate_synthetic_transaction()
    logger.info(
        "Submitting [%d/%s]  £%s  creditor=%s",
        index,
        str(total) if total else "∞",
        f"{payload['transaction']['amount']:,.2f}",
        payload["creditor"]["name"],
    )
    return submit(client, payload)


def main() -> None:
    global BASE_URL
    parser = argparse.ArgumentParser(description="Submit synthetic transactions to the AML engine")
    parser.add_argument("-n", "--count", type=int, default=1, help="Number of transactions to submit (ignored in --loop mode)")
    parser.add_argument("--poll", action="store_true", help="Poll each transaction until triage completes")
    parser.add_argument("--loop", action="store_true", help="Continuously post transactions until Ctrl+C")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between submissions in --loop mode (default: 5)")
    parser.add_argument("--base-url", default=BASE_URL, help="Backend base URL")
    args = parser.parse_args()

    BASE_URL = args.base_url.rstrip("/")

    with httpx.Client() as client:
        if args.loop:
            logger.info("Loop mode active — posting every %ss. Press Ctrl+C to stop.", args.interval)
            i = 1
            try:
                while True:
                    tx_id = submit_one(client, i, 0)
                    if args.poll and tx_id:
                        result = poll(client, tx_id)
                        if result:
                            print_result(result)
                    i += 1
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                logger.info("Stopped after %d transaction(s).", i - 1)
        else:
            tx_ids = []
            for i in range(1, args.count + 1):
                tx_id = submit_one(client, i, args.count)
                if tx_id:
                    tx_ids.append(tx_id)

            if args.poll and tx_ids:
                print(f"\nPolling {len(tx_ids)} transaction(s) for triage results...\n")
                for tx_id in tx_ids:
                    result = poll(client, tx_id)
                    if result:
                        print_result(result)
                    else:
                        print(f"  [{tx_id}]  No result within {POLL_TIMEOUT}s\n")


if __name__ == "__main__":
    main()
