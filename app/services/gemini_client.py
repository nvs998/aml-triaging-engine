import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger("AMLEngine.Gemini")


class GeminiAMLClient:
    """
    Asynchronous client to evaluate financial transaction risk using Google Gemini
    with strict structured JSON schema constraints and exponential backoff.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = "gemini-2.5-flash-preview-09-2025"
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

    async def evaluate_risk(self, transaction: Dict[str, Any], company_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not self.api_key:
            logger.warning("No GEMINI_API_KEY detected. Falling back to local deterministic rule assessment.")
            return self._compute_local_fallback(transaction, company_metadata)

        system_prompt = (
            "You are the Senior Compliance Officer at a Tier-1 UK Financial Institution. "
            "Analyze the provided ISO 20022 transaction and Companies House registry metadata. "
            "Evaluate flags against UK MLR 2017 and FCA criteria. Identify structuring, smurfing, "
            "and offshore shell company transfers. Return a justified score and concise audit rationale."
        )

        user_content = (
            f"ISO 20022 TRANSACTION METADATA:\n{json.dumps(transaction, indent=2)}\n\n"
            f"UK COMPANIES HOUSE REGISTRY METADATA:\n{json.dumps(company_metadata, indent=2) if company_metadata else 'None (Individual Payee)'}"
        )

        response_schema = {
            "type": "OBJECT",
            "properties": {
                "risk_score": {"type": "STRING", "enum": ["LOW", "MEDIUM", "HIGH"]},
                "confidence_score": {"type": "NUMBER"},
                "reasoning": {"type": "STRING"},
                "recommended_action": {"type": "STRING", "enum": ["ALLOW", "ESCALATE_TO_MLRO", "FREEZE_ACCOUNT"]}
            },
            "required": ["risk_score", "confidence_score", "reasoning", "recommended_action"]
        }

        payload = {
            "contents": [{"parts": [{"text": user_content}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": response_schema, "temperature": 0.1}
        }

        backoff_delays = [1.0, 2.0, 4.0, 8.0, 16.0]
        async with httpx.AsyncClient() as client:
            for attempt, delay in enumerate(backoff_delays):
                try:
                    logger.info(f"Transmitting to Gemini API (attempt {attempt + 1}/5)...")
                    response = await client.post(self.api_url, json=payload, timeout=12.0)
                    if response.status_code == 200:
                        text_output = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                        parsed = json.loads(text_output)
                        logger.info(f"Gemini returned: {parsed['risk_score']}")
                        return parsed
                    logger.error(f"Gemini API error {response.status_code}: {response.text}")
                except Exception as e:
                    logger.error(f"Exception on attempt {attempt + 1}: {e}")
                if attempt < len(backoff_delays) - 1:
                    await asyncio.sleep(delay)

        logger.warning("All Gemini retries failed. Activating deterministic fallback...")
        return self._compute_local_fallback(transaction, company_metadata)

    def _compute_local_fallback(self, transaction: Dict[str, Any], company_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        amount = transaction.get("amount", 0.0)

        if company_metadata:
            status = company_metadata.get("status")
            psc = company_metadata.get("person_with_significant_control", {})
            psc_residence = psc.get("country_of_residence")
            if status == "Dormant":
                return {"risk_score": "HIGH", "confidence_score": 0.95, "reasoning": "[Fallback] Target entity is DORMANT. Shell company risk detected.", "recommended_action": "FREEZE_ACCOUNT"}
            if psc_residence in ["Seychelles", "BVI"]:
                return {"risk_score": "HIGH", "confidence_score": 0.96, "reasoning": f"[Fallback] UBO resides in offshore tax-haven: {psc_residence}.", "recommended_action": "FREEZE_ACCOUNT"}

        if 9000 <= amount < 10000:
            return {"risk_score": "MEDIUM", "confidence_score": 0.85, "reasoning": f"[Fallback] £{amount} is suspiciously close to the £10,000 threshold.", "recommended_action": "ESCALATE_TO_MLRO"}

        return {"risk_score": "LOW", "confidence_score": 0.99, "reasoning": "[Fallback] Standard clearance. No alerts triggered.", "recommended_action": "ALLOW"}
