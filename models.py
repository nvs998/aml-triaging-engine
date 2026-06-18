import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Debtor(BaseModel):
    """
    Represents the sending party (Debtor) in a pacs.008 credit transfer.
    Includes custom validation to ensure standard UK banking formats.
    """
    name: str = Field(
        ..., 
        min_length=2, 
        max_length=70, 
        description="Legal name of the ordering customer/debtor",
        examples=["Sir Arthur Sterling"]
    )
    sort_code: str = Field(
        ..., 
        description="6-digit UK bank sort code (formats accepted: XX-XX-XX or XXXXXX)",
        examples=["20-45-12"]
    )
    account_number: str = Field(
        ..., 
        description="Standard 8-digit UK bank account number",
        examples=["44891023"]
    )

    @field_validator("sort_code")
    @classmethod
    def clean_and_validate_sort_code(cls, v: str) -> str:
        # Strip out any hyphens or spaces
        clean_code = re.sub(r"\D", "", v)
        if len(clean_code) != 6:
            raise ValueError("UK Sort Code must contain exactly 6 digits.")
        # Return structured formatted sort code: XX-XX-XX
        return f"{clean_code[0:2]}-{clean_code[2:4]}-{clean_code[4:6]}"

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str) -> str:
        # Strip spaces and verify it is exactly 8 numeric digits
        clean_account = re.sub(r"\s", "", v)
        if not clean_account.isdigit() or len(clean_account) != 8:
            raise ValueError("UK Account Number must be exactly 8 digits.")
        return clean_account


class Creditor(BaseModel):
    """
    Represents the receiving party (Creditor / Beneficiary).
    Includes optional UK Companies House registration tracking for corporate entities.
    """
    name: str = Field(
        ..., 
        min_length=2, 
        max_length=70, 
        description="Legal name of the beneficiary/creditor",
        examples=["Apex Holdings Ltd"]
    )
    sort_code: str = Field(
        ..., 
        description="6-digit UK bank sort code (formats accepted: XX-XX-XX or XXXXXX)",
        examples=["60-83-01"]
    )
    account_number: str = Field(
        ..., 
        description="Standard 8-digit UK bank account number",
        examples=["99201145"]
    )
    companies_house_number: Optional[str] = Field(
        None, 
        description="UK Companies House registration number (optional, for corporate entities)",
        examples=["UK12984401"]
    )

    @field_validator("sort_code")
    @classmethod
    def clean_and_validate_sort_code(cls, v: str) -> str:
        clean_code = re.sub(r"\D", "", v)
        if len(clean_code) != 6:
            raise ValueError("UK Sort Code must contain exactly 6 digits.")
        return f"{clean_code[0:2]}-{clean_code[2:4]}-{clean_code[4:6]}"

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str) -> str:
        clean_account = re.sub(r"\s", "", v)
        if not clean_account.isdigit() or len(clean_account) != 8:
            raise ValueError("UK Account Number must be exactly 8 digits.")
        return clean_account


class TransactionDetails(BaseModel):
    """
    Models the specific transfer details accompanying the transaction message.
    """
    amount: float = Field(
        ..., 
        gt=0.0, 
        description="Total transfer amount clearing the account, must be greater than 0",
        examples=[9850.00]
    )
    currency: str = Field(
        default="GBP", 
        description="3-letter ISO currency code",
        examples=["GBP"]
    )
    reference: str = Field(
        ..., 
        min_length=1, 
        max_length=140, 
        description="Remittance reference or purpose narrative",
        examples=["Consulting Fees Phase 1"]
    )


class ISO20022Payload(BaseModel):
    """
    Unified pacs.008 credit transfer envelope model.
    """
    message_identifier: str = Field(
        ..., 
        description="Unique identifier assigned to the ISO credit transfer message",
        examples=["pacs.008.001.08.77192"]
    )
    debtor: Debtor
    creditor: Creditor
    transaction: TransactionDetails


# --- Quick validation test when run locally ---
if __name__ == "__main__":
    print("Testing parser validation logic...")
    try:
        # Example validation run with some messy raw sort code formatting
        test_payload = ISO20022Payload(
            message_identifier="pacs.008.test.123",
            debtor=Debtor(
                name="John Doe",
                sort_code="20 45 12",  # spaces should get removed and formatted
                account_number="44891023"
            ),
            creditor=Creditor(
                name="Shell Corp Ltd",
                sort_code="60-83-01",
                account_number="99201145",
                companies_house_number="UK12984401"
            ),
            transaction=TransactionDetails(
                amount=9850.00,
                reference="Payment for invoice #2"
            )
        )
        print("✅ Validation Successful!")
        print(f"Formatted Debtor Sort Code: {test_payload.debtor.sort_code}")
        print(f"ISO Message ID: {test_payload.message_identifier}")
    except Exception as e:
        print(f"❌ Validation Failed: {e}")