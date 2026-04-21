import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("mock_uazapi")

app = FastAPI(title="Mock Uazapi")


class SendTextPayload(BaseModel):
    phone: str
    message: str
    externalId: str | None = None
    metadata: dict[str, Any] | None = None
    instanceId: str | None = None


@app.post("/send/text")
async def send_text(payload: SendTextPayload) -> dict[str, Any]:
    logger.info(
        "Mock Uazapi received phone=%s external_id=%s message=%s",
        payload.phone,
        payload.externalId,
        payload.message,
    )

    if payload.phone.endswith("0000") or "invalid" in payload.message.lower():
        raise HTTPException(
            status_code=400,
            detail="Recipient invalid for mock provider",
        )

    if "unauthorized" in payload.message.lower():
        raise HTTPException(
            status_code=401,
            detail="Invalid token for mock provider",
        )

    if "retry" in payload.message.lower():
        raise HTTPException(
            status_code=503,
            detail="Temporary provider outage",
        )

    return {
        "messageId": f"mock-{payload.phone[-4:]}",
        "status": "success",
        "provider": "mock-uazapi",
        "echo": payload.model_dump(mode="json"),
    }
