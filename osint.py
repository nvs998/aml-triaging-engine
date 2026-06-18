import asyncio
import logging
from typing import Dict, Any, Optional

# Set up logger for tracking OSINT steps
logger = logging.getLogger("AMLEngine.OSINT")

# Mock Corporate Database representing the UK Companies House registry records
MOCK_COMPANIES_HOUSE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "UK12984401": {
        "company_name": "Apex Apex Ltd",
        "status": "Active",
        "incorporation_date": "2026-04-10",  # Newly formed (Red flag for shell companies)
        "company_type": "ltd",
        "nature_of_business": "64209 - Activities of financial holding companies",
        "registered_address": "85 Great Portland Street, London, W1W 7LT",
        "person_with_significant_control": {
            "name": "Dimitri Volkov",
            "nationality": "Cypriot",
            "country_of_residence": "Seychelles",  # Tax haven offshore residency (Red flag)
            "share_percentage": 75.0
        }
    },
    "UK99882211": {
        "company_name": "Vanguard Global Holdings Ltd",
        "status": "Dormant",  # Large transfer to dormant company (Severe Red Flag)
        "incorporation_date": "2019-11-23",
        "company_type": "ltd",
        "nature_of_business": "70229 - Management consultancy activities",
        "registered_address": "12 Laleham Road, London, SE13 5EH",
        "person_with_significant_control": {
            "name": "Hidden Beneficiary Corporation",
            "nationality": "British Virgin Islands",  # Offshore jurisdiction (Severe Red Flag)
            "country_of_residence": "BVI",
            "share_percentage": 100.0
        }
    },
    "UK00110022": {
        "company_name": "National Grid UK Utility Ltd",
        "status": "Active",
        "incorporation_date": "1999-04-10",  # Long standing (Low Risk)
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
    In production, this would make an authenticated HTTP call to:
    https://api.company-information.service.gov.uk/company/{company_number}
    """

    def __init__(self):
        # We simulate client latency or connection setup here
        pass

    async def lookup_company(self, company_number: str) -> Optional[Dict[str, Any]]:
        """
        Query corporate records asynchronously by registration company number.
        """
        logger.info(f"🔍 [CompaniesHouseAPI] Querying registry database for ID: {company_number}")
        
        # Simulate standard network API round-trip latency (e.g. 0.8 seconds)
        await asyncio.sleep(0.8)

        # Standardize company number string (remove common spacing errors)
        clean_num = company_number.strip().upper()

        if clean_num in MOCK_COMPANIES_HOUSE_REGISTRY:
            logger.info(f"✅ [CompaniesHouseAPI] Match found: '{MOCK_COMPANIES_HOUSE_REGISTRY[clean_num]['company_name']}'")
            return MOCK_COMPANIES_HOUSE_REGISTRY[clean_num]
        
        logger.warning(f"⚠️ [CompaniesHouseAPI] No active registry match found for ID: {company_number}")
        return None


# --- Quick validation test when run locally ---
if __name__ == "__main__":
    async def main_test():
        logging.basicConfig(level=logging.INFO)
        print("Testing Companies House Registry Search Client...")
        client = CompaniesHouseClient()

        # Test looking up a known high-risk shell registry ID
        record = await client.lookup_company("UK12984401")
        if record:
            print(f"Name: {record['company_name']}")
            print(f"UBO / Person with Significant Control: {record['person_with_significant_control']['name']}")
            print(f"UBO Residence: {record['person_with_significant_control']['country_of_residence']}")
        else:
            print("Failed: No record found.")

    asyncio.run(main_test())