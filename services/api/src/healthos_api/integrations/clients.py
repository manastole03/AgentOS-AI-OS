import hashlib
import io
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from pypdf import PdfReader

from healthos_api.config import Settings


@dataclass(frozen=True)
class IntegrationResult:
    provider: str
    status: str
    external_reference: str | None
    data: dict[str, Any]


class OCRService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client

    async def extract(self, filename: str, content_type: str, content: bytes) -> IntegrationResult:
        if content_type.startswith("text/") or filename.lower().endswith((".txt", ".csv")):
            text = content.decode("utf-8", errors="replace")
            return IntegrationResult("local-text", "completed", None, {"text": text})
        if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages
            )
            if text.strip():
                return IntegrationResult("pypdf", "completed", None, {"text": text})
        if not self.settings.ocr_api_url:
            return IntegrationResult("ocr", "configuration_required", None, {"text": ""})
        response = await self.client.post(
            self.settings.ocr_api_url,
            headers={"Authorization": f"Bearer {self.settings.ocr_api_key.get_secret_value()}"},
            files={"file": (filename, content, content_type)},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        return IntegrationResult(
            "ocr",
            "completed",
            str(payload.get("id", "")) or None,
            {"text": str(payload.get("text", ""))},
        )


class FHIRClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client

    async def sync_patient(self, reference: str) -> IntegrationResult:
        if not self.settings.fhir_base_url:
            return IntegrationResult("fhir", "configuration_required", None, {"resources": []})
        response = await self.client.get(
            f"{self.settings.fhir_base_url.rstrip('/')}/Patient/{reference}/$everything",
            headers={
                "Authorization": f"Bearer {self.settings.fhir_access_token.get_secret_value()}",
                "Accept": "application/fhir+json",
            },
            timeout=60,
        )
        response.raise_for_status()
        bundle = response.json()
        resources = [entry.get("resource", {}) for entry in bundle.get("entry", [])]
        return IntegrationResult("fhir", "completed", reference, {"resources": resources})


class InsuranceClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client

    async def execute(self, operation: str, parameters: dict[str, Any]) -> IntegrationResult:
        if not self.settings.insurance_api_url:
            return IntegrationResult("insurance", "configuration_required", None, {"records": []})
        response = await self.client.post(
            f"{self.settings.insurance_api_url.rstrip('/')}/{operation}",
            headers={"X-API-Key": self.settings.insurance_api_key.get_secret_value()},
            json=parameters,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        return IntegrationResult(
            "insurance",
            "completed",
            str(payload.get("reference", "")) or None,
            {"records": payload.get("records", [])},
        )


class PaymentGateway:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings, self.client = settings, client

    async def create_intent(
        self, amount: int, currency: str, description: str, idempotency_key: str
    ) -> IntegrationResult:
        secret = self.settings.stripe_secret_key.get_secret_value()
        if not secret:
            reference = f"local_pi_{uuid4().hex}"
            return IntegrationResult(
                "local-payment",
                "requires_payment_method",
                reference,
                {"client_secret": None, "amount": amount, "currency": currency},
            )
        response = await self.client.post(
            f"{self.settings.stripe_api_url.rstrip('/')}/payment_intents",
            auth=(secret, ""),
            headers={"Idempotency-Key": idempotency_key},
            data={"amount": str(amount), "currency": currency.lower(), "description": description},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return IntegrationResult(
            "stripe",
            str(payload["status"]),
            str(payload["id"]),
            {"client_secret": payload.get("client_secret"), "amount": amount, "currency": currency},
        )


def request_digest(value: Any) -> str:
    return hashlib.sha256(repr(value).encode()).hexdigest()
