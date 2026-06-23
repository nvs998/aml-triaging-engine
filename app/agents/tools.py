import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from crewai.tools import BaseTool

from app.config import COMPANY_HOUSE_KEY

_DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent.parent.parent / "aml_ledger.db")))

logger = logging.getLogger("AMLEngine.OSINT")

COMPANIES_HOUSE_BASE_URL = "https://api.company-information.service.gov.uk"

# ---------------------------------------------------------------------------
# Mock registry — used when COMPANY_HOUSE_KEY is not set or for unknown numbers
# ---------------------------------------------------------------------------

MOCK_COMPANIES_HOUSE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "UK12984401": {
        "company_name": "Apex Apex Ltd",
        "status": "Active",
        "incorporation_date": "2026-04-10",
        "company_type": "ltd",
        "nature_of_business": "64209 - Activities of financial holding companies",
        "registered_address": "85 Great Portland Street, London, W1W 7LT",
        "person_with_significant_control": {
            "name": "Dimitri Volkov",
            "nationality": "Cypriot",
            "country_of_residence": "Seychelles",
            "share_percentage": 75.0
        }
    },
    "UK99882211": {
        "company_name": "Vanguard Global Holdings Ltd",
        "status": "Dormant",
        "incorporation_date": "2019-11-23",
        "company_type": "ltd",
        "nature_of_business": "70229 - Management consultancy activities",
        "registered_address": "12 Laleham Road, London, SE13 5EH",
        "person_with_significant_control": {
            "name": "Hidden Beneficiary Corporation",
            "nationality": "British Virgin Islands",
            "country_of_residence": "BVI",
            "share_percentage": 100.0
        }
    },
    "UK00110022": {
        "company_name": "National Grid UK Utility Ltd",
        "status": "Active",
        "incorporation_date": "1999-04-10",
        "company_type": "plc",
        "nature_of_business": "35110 - Production of electricity",
        "registered_address": "1-3 Strand, London, WC2N 5EH",
        "person_with_significant_control": {
            "name": "HM Treasury Nominees",
            "nationality": "British",
            "country_of_residence": "United Kingdom",
            "share_percentage": 51.0
        }
    }
}


# ---------------------------------------------------------------------------
# Real API helpers
# ---------------------------------------------------------------------------

def _strip_prefix(company_number: str) -> str:
    """Real Companies House numbers have no 'UK' prefix (e.g. '12984401')."""
    clean = company_number.strip().upper()
    if clean.startswith("UK"):
        clean = clean[2:]
    return clean


def _fetch_company_profile(company_number: str, api_key: str) -> Optional[Dict[str, Any]]:
    url = f"{COMPANIES_HOUSE_BASE_URL}/company/{company_number}"
    try:
        r = httpx.get(
           url, auth=(api_key, ""), timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        logger.error("[CompaniesHouseAPI] HTTP error fetching profile for %s: %s", company_number, e)
        return None
    except httpx.RequestError as e:
        logger.error("[CompaniesHouseAPI] Network error fetching profile for %s: %s", company_number, e)
        return None


def _fetch_pscs(company_number: str, api_key: str) -> list:
    url = f"{COMPANIES_HOUSE_BASE_URL}/company/{company_number}/persons-with-significant-control"
    try:
        r = httpx.get(url, auth=(api_key, ""), timeout=10)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json().get("items", [])
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("[CompaniesHouseAPI] Error fetching PSCs for %s: %s", company_number, e)
        return []


def _map_to_internal(profile: Dict[str, Any], pscs: list) -> Dict[str, Any]:
    """Map real Companies House API response to our internal record format."""
    address_parts = profile.get("registered_office_address", {})
    address = ", ".join(filter(None, [
        address_parts.get("address_line_1"),
        address_parts.get("address_line_2"),
        address_parts.get("locality"),
        address_parts.get("postal_code"),
    ]))

    sic_codes = profile.get("sic_codes", [])
    nature_of_business = sic_codes[0] if sic_codes else "Unknown"

    psc_data = None
    if pscs:
        psc = pscs[0]
        natures = psc.get("natures_of_control", [])
        share_pct = 0.0
        for nature in natures:
            if "75-to-100-percent" in nature:
                share_pct = 87.5
            elif "50-to-75-percent" in nature:
                share_pct = 62.5
            elif "25-to-50-percent" in nature:
                share_pct = 37.5

        psc_data = {
            "name": psc.get("name", "Unknown"),
            "nationality": psc.get("nationality", "Unknown"),
            "country_of_residence": psc.get("country_of_residence", "Unknown"),
            "share_percentage": share_pct,
        }

    return {
        "company_name": profile.get("company_name", "Unknown"),
        "status": profile.get("company_status", "Unknown").capitalize(),
        "incorporation_date": profile.get("date_of_creation", "Unknown"),
        "company_type": profile.get("type", "Unknown"),
        "nature_of_business": nature_of_business,
        "registered_address": address,
        "person_with_significant_control": psc_data,
    }


def lookup_company_sync(company_number: str) -> Optional[Dict[str, Any]]:
    """
    Core lookup used by both CompaniesHouseTool and CompaniesHouseClient.
    Uses real API when COMPANY_HOUSE_KEY is set, falls back to mock otherwise.
    """
    clean = company_number.strip().upper()

    # Always check mock registry first for known test numbers (UK-prefixed)
    if clean in MOCK_COMPANIES_HOUSE_REGISTRY:
        logger.info("[CompaniesHouseAPI] Using mock registry for test number: %s", clean)
        return MOCK_COMPANIES_HOUSE_REGISTRY[clean]

    if not COMPANY_HOUSE_KEY:
        logger.info("[CompaniesHouseAPI] No API key — no match for %s", clean)
        return None

    # Real Companies House numbers have no 'UK' prefix
    api_number = _strip_prefix(clean)
    logger.info("[CompaniesHouseAPI] Live query for company number: %s", api_number)

    profile = _fetch_company_profile(api_number, COMPANY_HOUSE_KEY)
    if not profile:
        logger.warning("[CompaniesHouseAPI] No profile found for %s", api_number)
        return None

    pscs = _fetch_pscs(api_number, COMPANY_HOUSE_KEY)
    record = _map_to_internal(profile, pscs)
    logger.info("[CompaniesHouseAPI] Live record retrieved: %s (%s)", record["company_name"], record["status"])
    return record


# ---------------------------------------------------------------------------
# CrewAI tool (sync)
# ---------------------------------------------------------------------------

class CompaniesHouseTool(BaseTool):
    name: str = "companies_house_lookup"
    description: str = (
        "Look up a UK company by its Companies House registration number. "
        "Returns company status, incorporation date, nature of business, "
        "registered address, and Ultimate Beneficial Owner (PSC) details. "
        "Input must be the raw registration number string, e.g. UK12984401 or 12984401."
    )

    def _run(self, company_number: str) -> str:
        record = lookup_company_sync(company_number)
        print(f"[CompaniesHouseTool] Lookup result for {company_number}: {record}")
        if record:
            return json.dumps(record, indent=2)
        return f"No registry match found for Companies House ID: {company_number}"


# ---------------------------------------------------------------------------
# Async client for the deterministic fallback pipeline
# ---------------------------------------------------------------------------

class CompaniesHouseClient:
    async def lookup_company(self, company_number: str) -> Optional[Dict[str, Any]]:
        import asyncio
        # Run the sync HTTP calls in a thread so we don't block the event loop
        return await asyncio.get_event_loop().run_in_executor(
            None, lookup_company_sync, company_number
        )


# ---------------------------------------------------------------------------
# Ledger history tool — gives the Sifter Agent access to prior transactions
# ---------------------------------------------------------------------------

class LedgerQueryTool(BaseTool):
    name: str = "ledger_query"
    description: str = (
        "Query the AML transaction ledger for all historical payments made by a specific "
        "debtor account number. Use this to detect structuring patterns (multiple payments "
        "just under £10,000), velocity abuse (many transactions in a short window), or to "
        "confirm a debtor has a clean consistent history. "
        "Input: the debtor account number string (e.g. '44891023')."
    )

    def _run(self, account_number: str) -> str:
        account_number = account_number.strip()

        if not _DB_PATH.exists():
            return "Ledger database not initialised yet. No historical data available."

        try:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT timestamp, creditor_name, amount, status, risk_score
                FROM transactions
                WHERE debtor_account = ?
                ORDER BY timestamp DESC
                LIMIT 50
                """,
                (account_number,),
            )
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
        except Exception as e:
            return f"Ledger query error: {e}"

        if not rows:
            return (
                f"No prior transactions found for account {account_number}. "
                "This is either a first-time sender or a new account."
            )

        amounts = [r["amount"] for r in rows]
        near_threshold = [a for a in amounts if 9_000 <= a <= 9_999]

        lines = [f"Found {len(rows)} prior transaction(s) for account {account_number}:\n"]
        for r in rows:
            lines.append(
                f"  {r['timestamp'][:10]}  £{r['amount']:>10,.2f}  "
                f"→ {r['creditor_name']}  [{r['risk_score'] or 'PENDING'}]"
            )

        lines.append(f"\nAmount range : £{min(amounts):,.2f} – £{max(amounts):,.2f}")
        lines.append(f"Average      : £{sum(amounts)/len(amounts):,.2f}")
        if near_threshold:
            lines.append(
                f"⚠ Near-threshold (£9,000–£9,999): {len(near_threshold)} transaction(s) — structuring indicator"
            )

        return "\n".join(lines)
