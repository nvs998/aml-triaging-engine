import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("AMLEngine.OSINT")

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


class CompaniesHouseClient:
    """
    Simulates a secure client connection to the UK Companies House API.
    In production: https://api.company-information.service.gov.uk/company/{company_number}
    """

    async def lookup_company(self, company_number: str) -> Optional[Dict[str, Any]]:
        logger.info(f"[CompaniesHouseAPI] Querying registry for ID: {company_number}")
        await asyncio.sleep(0.8)
        clean_num = company_number.strip().upper()
        if clean_num in MOCK_COMPANIES_HOUSE_REGISTRY:
            logger.info(f"[CompaniesHouseAPI] Match found: '{MOCK_COMPANIES_HOUSE_REGISTRY[clean_num]['company_name']}'")
            return MOCK_COMPANIES_HOUSE_REGISTRY[clean_num]
        logger.warning(f"[CompaniesHouseAPI] No registry match found for ID: {company_number}")
        return None
