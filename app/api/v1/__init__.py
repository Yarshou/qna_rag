from fastapi import APIRouter

__all__ = ["router"]

from app.api.v1 import chats, events, health, messages

router = APIRouter(prefix="/v1")
router.include_router(chats.router)
router.include_router(messages.router)
router.include_router(events.router)
router.include_router(health.router)
