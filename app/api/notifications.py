from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.dependencies.notifications import get_notification_service
from app.repositories.notification_repository import NotificationListFilters
from app.schemas.notification import (
    NotificationCreateRequest,
    NotificationCreateResponse,
    NotificationListResponse,
    NotificationResponse,
)
from app.services.notification_service import NotificationService


router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=NotificationCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_notification(
    payload: NotificationCreateRequest,
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationCreateResponse:
    try:
        return await notification_service.create_notification(payload)
    except RedisError as exc:
        logger.error("Failed to create notification job due to Redis error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unavailable",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Failed to persist notification")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to enqueue notification")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Task queue unavailable: {exc}",
        ) from exc


@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
)
async def get_notification(
    notification_id: UUID,
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    try:
        notification = await notification_service.get_notification(notification_id)
    except SQLAlchemyError as exc:
        logger.exception("Failed to fetch notification %s", notification_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return notification


@router.get(
    "",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_notifications(
    status_filter: str | None = Query(default=None, alias="status"),
    recipient: str | None = Query(default=None),
    external_id: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    notification_service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    filters = NotificationListFilters(
        status=status_filter,
        recipient=recipient,
        external_id=external_id,
        created_from=created_from,
        created_to=created_to,
        page=page,
        limit=limit,
    )

    try:
        return await notification_service.list_notifications(filters)
    except SQLAlchemyError as exc:
        logger.exception("Failed to list notifications")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
