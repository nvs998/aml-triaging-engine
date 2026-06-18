import random
import uuid
import logging
from typing import Dict, Any
from faker import Faker

# Configure minimal execution logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("AML.Simulator")

# Initialize Faker with British locale to generate highly realistic UK names and addresses
fake = Faker('en_GB')

# High-Risk Offshore jurisdictions that trigger FCA warning flags
OFFSHORE_COUNTRIES = ["Seychelles", "BVI", "Cayman Islands", "Bahamas", "Panama"]

# Mock list of UK Companies House registration numbers for corporate checks
# This includes the mock companies we built in osint.py to guarantee endpoint routing matches
KNOWN_COMPANIES_HOUSE_NUMBERS = [
    "UK12984401",  # Apex Apex Ltd (High Risk - Seychelles PSC)
    "UK99882211",  # Vanguard Global Holdings Ltd (High Risk - Dormant Shell BVI UBO)
    "UK00110022",  # National Grid UK Utility Ltd (Low Risk - Active PLC)
]


def generate_uk_sort_code() -> str:
    """
    Generates a realistic UK banking sort code.
    Randomly formats it to test models.py parsing capabilities.
    """
    # Standard UK sort code prefixes (20 = Barclays, 40 = HSBC, 60 = NatWest)
    prefix = random.choice(["20", "30", "40", "50", "60", "70", "80"])
    digits = f"{prefix}{random.randint(1000, 9999)}"
    
    # Introduce messy data structures 40% of the time to test our sanitizers
    format_choice = random.random()
    if format_choice < 0.20:
        return f"{digits[0:2]} {digits[2:4]} {digits[4:6]}"  # Spaces: "20 45 12"
    elif format_choice < 0.40:
        return digits  # Unformatted raw: "204512"
    else:
        return f"{digits[0:2]}-{digits[2:4]}-{digits[4:6]}"  # Well-formatted: "20-45-12"


def generate_uk_account_number() -> str:
    """
    Generates a standard 8-digit UK account number.
    Occasionally injects spaces to test validation cleaning.
    """
    digits = "".join(str(random.randint(0, 9)) for _ in range(8))
    
    # Introduce human entry spacing 25% of the time
    if random.random() < 0.25:
        return f"{digits[0:4]} {digits[4:8]}"  # Spaced format: "1234 5678"
    return digits


def generate_synthetic_transaction() -> Dict[str, Any]:
    """
    Generates a single synthetic ISO 20022 customer credit transfer payload.
    Utilizes Faker to simulate realistic UK debtors, creditors, and transactional purposes.
    """
    is_corporate = random.choice([True, False])
    
    # Randomly determine the transfer amount and typology
    scenario_selector = random.random()
    
    if scenario_selector < 0.15:
        # Typology 1: Structuring / Smurfing Pattern (Medium Risk)
        # Generate an amount suspiciously close to, but under, the £10,000 threshold
        amount = round(random.uniform(9800.00, 9995.00), 2)
        reference = random.choice(["Consulting Deposit", "Project Retainer Payment", "Loan repayment partial", "GIFT"])
        companies_house_num = None
    elif scenario_selector < 0.30:
        # Typology 2: High Value Corporate Transfer (High Risk if tied to dormant shell)
        amount = round(random.uniform(110000.00, 500000.00), 2)
        reference = "IP Portfolio Acquisition Agreement / Management Services Contract"
        # Always assign a Companies House number to trigger deep registry verification
        companies_house_num = random.choice(KNOWN_COMPANIES_HOUSE_NUMBERS)
    else:
        # Typology 3: Standard retail clearing (Low Risk)
        amount = round(random.uniform(150.00, 4500.00), 2)
        reference = random.choice(["Monthly Salary Payment", "Electricity bill settlement", "Hardware invoice #1029", "Rent Payment"])
        companies_house_num = random.choice([None, "UK00110022"])

    # Generate Debtor details
    debtor_is_corp = random.choice([True, False])
    debtor_name = fake.company() if debtor_is_corp else fake.name()

    # Generate Creditor details
    creditor_name = fake.company() if is_corporate else fake.name()
    
    # If the transaction is matched with one of our known test companies, use its name
    if companies_house_num == "UK12984401":
        creditor_name = "Apex Apex Ltd"
    elif companies_house_num == "UK99882211":
        creditor_name = "Vanguard Global Holdings Ltd"
    elif companies_house_num == "UK00110022":
        creditor_name = "National Grid UK Utility Ltd"

    # Compile the final structured JSON matching our ISO 20022 payload format
    payload = {
        "message_identifier": f"pacs.008.{uuid.uuid4().hex[:12]}",
        "debtor": {
            "name": debtor_name,
            "sort_code": generate_uk_sort_code(),
            "account_number": generate_uk_account_number()
        },
        "creditor": {
            "name": creditor_name,
            "sort_code": generate_uk_sort_code(),
            "account_number": generate_uk_account_number(),
            "companies_house_number": companies_house_num
        },
        "transaction": {
            "amount": amount,
            "currency": "GBP",
            "reference": reference
        }
    }
    
    return payload


# --- Quick independent demonstration ---
if __name__ == "__main__":
    print("Initializing UK Transaction Simulator Engine...")
    print("Generating 3 random synthetic transactional payloads:\n")
    
    for i in range(3):
        tx = generate_synthetic_transaction()
        print(f"--- Transaction {i + 1} ({tx['message_identifier']}) ---")
        print(f"Debtor   : {tx['debtor']['name']} (Sort: {tx['debtor']['sort_code']}, Acc: {tx['debtor']['account_number']})")
        print(f"Creditor : {tx['creditor']['name']} (Sort: {tx['creditor']['sort_code']}, Acc: {tx['creditor']['account_number']})")
        print(f"Value    : {tx['transaction']['currency']} {tx['transaction']['amount']:,}")
        print(f"Ref      : {tx['transaction']['reference']}")
        print(f"Co House : {tx['creditor']['companies_house_number']}\n")