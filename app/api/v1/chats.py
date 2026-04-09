from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.domain import Chat
from app.schemas.chats import ChatListResponse, ChatResponse, CreateChatRequest, DeleteChatResponse
from app.schemas.common import ErrorResponse
from app.services import ChatService

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
) -> ChatListResponse | JSONResponse:
    try:
        chats = await service.list_chats()
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to list chats.")

    return ChatListResponse(items=[_chat_to_response(chat) for chat in chats])


@router.delete(
    "/{chat_id}",
    response_model=DeleteChatResponse,
    responses=ERROR_RESPONSES,
)
async def delete_chat(
    chat_id: str,
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> DeleteChatResponse | JSONResponse:
    try:
        deleted = await service.delete_chat(chat_id)
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to delete chat.")

    if not deleted:
        return _error_response(status.HTTP_404_NOT_FOUND, "chat_not_found", f"Chat '{chat_id}' was not found.")

    return DeleteChatResponse(id=chat_id, deleted=True)
