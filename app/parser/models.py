import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Debtor(BaseModel):
    name: str = Field(..., min_length=2, max_length=70, description="Legal name of the ordering customer/debtor", examples=["Sir Arthur Sterling"])
    sort_code: str = Field(..., description="6-digit UK bank sort code (formats accepted: XX-XX-XX or XXXXXX)", examples=["20-45-12"])
    account_number: str = Field(..., description="Standard 8-digit UK bank account number", examples=["44891023"])

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


class Creditor(BaseModel):
    name: str = Field(..., min_length=2, max_length=70, description="Legal name of the beneficiary/creditor", examples=["Apex Holdings Ltd"])
    sort_code: str = Field(..., description="6-digit UK bank sort code (formats accepted: XX-XX-XX or XXXXXX)", examples=["60-83-01"])
    account_number: str = Field(..., description="Standard 8-digit UK bank account number", examples=["99201145"])
    companies_house_number: Optional[str] = Field(None, description="UK Companies House registration number (optional, for corporate entities)", examples=["UK12984401"])

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
    amount: float = Field(..., gt=0.0, description="Total transfer amount, must be greater than 0", examples=[9850.00])
    currency: str = Field(default="GBP", description="3-letter ISO currency code", examples=["GBP"])
    reference: str = Field(..., min_length=1, max_length=140, description="Remittance reference or purpose narrative", examples=["Consulting Fees Phase 1"])


class ISO20022Payload(BaseModel):
    message_identifier: str = Field(..., description="Unique identifier assigned to the ISO credit transfer message", examples=["pacs.008.001.08.77192"])
    debtor: Debtor
    creditor: Creditor
    transaction: TransactionDetails
