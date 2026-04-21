from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import httpx

from app.core.config import Settings


logger = logging.getLogger(__name__)


class UazapiError(Exception):
    pass


class UazapiRetryableError(UazapiError):
    pass


class UazapiPermanentError(UazapiError):
    pass


@dataclass(slots=True)
class UazapiDeliveryResult:
    provider_message_id: str | None
    raw_response: dict[str, Any]


class UazapiClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_text_message(
        self,
        *,
        recipient: str,
        message: str,
        external_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UazapiDeliveryResult:
        if not self.settings.uazapi_base_url:
            raise UazapiPermanentError("UAZAPI_BASE_URL is not configured")
        if not self.settings.uazapi_token:
            raise UazapiPermanentError("UAZAPI_TOKEN is not configured")

        payload: dict[str, Any] = {
            "phone": recipient,
            "message": message,
        }
        if external_id:
            payload["externalId"] = external_id
        if metadata:
            payload["metadata"] = metadata
        if self.settings.uazapi_instance_id:
            payload["instanceId"] = self.settings.uazapi_instance_id

        timeout = httpx.Timeout(self.settings.uazapi_timeout_seconds)
        async with httpx.AsyncClient(
            base_url=self.settings.uazapi_base_url,
            timeout=timeout,
        ) as client:
            logger.info(
                "Calling Uazapi recipient=%s external_id=%s path=%s base_url=%s",
                recipient,
                external_id,
                self._build_send_url(),
                self.settings.uazapi_base_url,
            )
            try:
                response = await client.post(
                    self._build_send_url(),
                    json=payload,
                    headers=self._build_headers(),
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                raise UazapiRetryableError(str(exc) or exc.__class__.__name__) from exc

        response_payload = self._parse_response(response)
        logger.info(
            "Uazapi response status_code=%s provider_message_id=%s",
            response.status_code,
            self._extract_message_id(response_payload),
        )

        if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
            raise UazapiRetryableError(self._extract_error_message(response_payload, response))
        if response.status_code >= 400:
            raise UazapiPermanentError(self._extract_error_message(response_payload, response))

        return UazapiDeliveryResult(
            provider_message_id=self._extract_message_id(response_payload),
            raw_response=response_payload,
        )

    def _build_send_url(self) -> str:
        instance_id = self.settings.uazapi_instance_id or ""
        return self.settings.uazapi_send_text_path.format(instance_id=instance_id)

    def _build_headers(self) -> dict[str, str]:
        token_value = self.settings.uazapi_token
        if self.settings.uazapi_token_prefix:
            token_value = f"{self.settings.uazapi_token_prefix} {token_value}"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            self.settings.uazapi_token_header: token_value,
        }
        if self.settings.uazapi_instance_id:
            headers["X-Instance-Id"] = self.settings.uazapi_instance_id
        return headers

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw_text": response.text}
        return payload if isinstance(payload, dict) else {"data": payload}

    @staticmethod
    def _extract_error_message(payload: dict[str, Any], response: httpx.Response) -> str:
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return f"Provider returned HTTP {response.status_code}"

    def _extract_message_id(self, payload: dict[str, Any]) -> str | None:
        keys = ("messageId", "message_id", "id")
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value

        data = payload.get("data")
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, str) and value:
                    return value

        return None
