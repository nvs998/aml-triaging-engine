import os
import json
import logging
from typing import Dict, Any, Optional, Literal

import anthropic
from pydantic import BaseModel, Field

logger = logging.getLogger("AMLEngine.Claude")


class RiskAssessment(BaseModel):
    risk_score: Literal["LOW", "MEDIUM", "HIGH"] = Field(description="Calculated transaction threat rating based on indicators")
    confidence_score: float = Field(description="Confidence index of risk score assessment from 0.00 to 1.00")
    reasoning: str = Field(description="Detailed, regulatory-compliant rationale citing specific MLR-2017 red flags (under 80 words).")
    recommended_action: Literal["ALLOW", "ESCALATE_TO_MLRO", "FREEZE_ACCOUNT"] = Field(description="Recommended immediate execution action trigger")


SYSTEM_PROMPT = (
    "You are the Senior Compliance Officer at a Tier-1 UK Financial Institution. "
    "Analyze the provided ISO 20022 transaction and Companies House registry metadata. "
    "Evaluate flags against the UK Money Laundering Regulations 2017 (MLR 2017) and FCA regulatory criteria. "
    "You must identify patterns of: 'Structuring' / 'Smurfing' (rapid transactions under £10,000 designed to evade limits), "
    "offshore shell company transfers (dormant companies, tax-haven PSCs in Seychelles/BVI), or unusual commercial transaction volumes. "
    "Return a justified score, a direct action, and a concise compliance audit rationale."
)


class ClaudeAMLClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model_name = "claude-opus-4-8"
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key) if self.api_key else None

    async def evaluate_risk(self, transaction: Dict[str, Any], company_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.client:
            logger.warning("No ANTHROPIC_API_KEY detected. Falling back to local deterministic rule assessment.")
            return self._compute_local_fallback(transaction, company_metadata)

        user_content = (
            f"ISO 20022 TRANSACTION METADATA:\n{json.dumps(transaction, indent=2)}\n\n"
            f"UK COMPANIES HOUSE REGISTRY METADATA:\n"
            f"{json.dumps(company_metadata, indent=2) if company_metadata else 'None (Individual Payee)'}"
        )

        try:
            logger.info("Transmitting prompt to Claude API for structured risk evaluation...")
            response = await self.client.messages.parse(
                model=self.model_name,
                max_tokens=2048,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                output_format=RiskAssessment,
            )
            evaluation: RiskAssessment = response.parsed_output
            logger.info(f"Claude returned structured risk evaluation: {evaluation.risk_score}")
            return evaluation.model_dump()
        except Exception as e:
            logger.error(f"Exception during Claude API call: {e}")
            return self._compute_local_fallback(transaction, company_metadata)

    def _compute_local_fallback(self, transaction: Dict[str, Any], company_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        amount = transaction.get("amount", 0.0)

        if company_metadata:
            status = company_metadata.get("status")
            psc = company_metadata.get("person_with_significant_control", {})
            psc_residence = psc.get("country_of_residence")

            if status == "Dormant":
                return {"risk_score": "HIGH", "confidence_score": 0.95, "reasoning": "[Fallback] Target corporate entity is DORMANT. Trade-based shell company invoice risk detected.", "recommended_action": "FREEZE_ACCOUNT"}
            if psc_residence in ["Seychelles", "BVI"]:
                return {"risk_score": "HIGH", "confidence_score": 0.96, "reasoning": f"[Fallback] Ultimate beneficial owner resides in offshore tax-haven: {psc_residence}.", "recommended_action": "FREEZE_ACCOUNT"}

        if 9000 <= amount < 10000:
            return {"risk_score": "MEDIUM", "confidence_score": 0.85, "reasoning": f"[Fallback] Payment of £{amount} is suspiciously close to the £10,000 threshold. Structuring indicators present.", "recommended_action": "ESCALATE_TO_MLRO"}

        return {"risk_score": "LOW", "confidence_score": 0.99, "reasoning": "[Fallback] Standard transactional clearance. No alerts triggered.", "recommended_action": "ALLOW"}
