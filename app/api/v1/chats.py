from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse, Response

from app.schemas.chats import ChatListResponse, ChatResponse, CreateChatRequest
from app.schemas.common import ErrorResponse
from app.services import ChatService
from app.types import Chat

router = APIRouter(prefix="/chats", tags=["chats"])

ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Resource not found."},
    500: {"model": ErrorResponse, "description": "Internal server error."},
}


def get_chat_service() -> ChatService:
    return ChatService()


def _chat_to_response(chat: Chat) -> ChatResponse:
    return ChatResponse(
        id=chat.id,
        title=chat.title,
        status=chat.status.value,
        created_at=chat.created_at,
    )


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@router.post(
    "",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_chat(
    request: CreateChatRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse | JSONResponse:
    try:
        chat = await service.create_chat(title=request.title)
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to create chat.")

    return _chat_to_response(chat)


@router.get(
    "",
    response_model=ChatListResponse,
    response_model_exclude_none=True,
    responses=ERROR_RESPONSES,
)
async def list_chats(
    service: Annotated[ChatService, Depends(get_chat_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChatListResponse | JSONResponse:
    try:
        chats, total = await service.list_chats(limit=limit, offset=offset)
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to list chats.")

    return ChatListResponse(items=[_chat_to_response(chat) for chat in chats], total=total, limit=limit, offset=offset)


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**ERROR_RESPONSES, 204: {"description": "Chat deleted."}},
)
async def delete_chat(
    chat_id: str,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> Response:
    try:
        deleted = await service.delete_chat(chat_id)
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to delete chat.")

    if not deleted:
        return _error_response(status.HTTP_404_NOT_FOUND, "chat_not_found", f"Chat '{chat_id}' was not found.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
