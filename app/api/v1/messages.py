from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from app.domain import Message
from app.guardrails import GuardrailViolationError
from app.llm import InvalidToolArgumentsError, LLMClientConfigurationError, LLMProviderError, UnsupportedToolError
from app.schemas.common import ErrorResponse
from app.schemas.messages import MessageListResponse, MessageResponse, PostMessageRequest, PostMessageResponse
from app.services import ChatNotFoundError, MessageProcessingError, MessageService

router = APIRouter(tags=["messages"])

ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "Guardrail violation."},
    404: {"model": ErrorResponse, "description": "Chat not found."},
    422: {"model": ErrorResponse, "description": "Invalid request payload."},
    500: {"model": ErrorResponse, "description": "Internal server error."},
    502: {"model": ErrorResponse, "description": "Provider failure."},
}


def get_message_service() -> MessageService:
    return MessageService()


def _message_to_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        chat_id=message.chat_id,
        role=message.role.value,
        content=message.content,
        created_at=message.created_at,
        metadata=message.metadata,
    )


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@router.get(
    "/chats/{chat_id}/messages",
    response_model=MessageListResponse,
    response_model_exclude_none=True,
    responses=ERROR_RESPONSES,
)
async def list_messages(
    chat_id: str,
    service: Annotated[MessageService, Depends(get_message_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MessageListResponse | JSONResponse:
    try:
        messages, total = await service.list_messages(chat_id, limit=limit, offset=offset)
    except ChatNotFoundError as exc:
        return _error_response(status.HTTP_404_NOT_FOUND, "chat_not_found", str(exc))
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to list messages.")

    return MessageListResponse(items=[_message_to_response(message) for message in messages], total=total, limit=limit, offset=offset)


@router.post(
    "/chats/{chat_id}/messages",
    response_model=PostMessageResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def post_message(
    chat_id: str,
    request: PostMessageRequest,
    service: Annotated[MessageService, Depends(get_message_service)],
) -> PostMessageResponse | JSONResponse:
    try:
        result = await service.post_user_message(chat_id, request.content)
    except GuardrailViolationError as exc:
        return _error_response(status.HTTP_400_BAD_REQUEST, "guardrail_violation", str(exc))
    except ChatNotFoundError as exc:
        return _error_response(status.HTTP_404_NOT_FOUND, "chat_not_found", str(exc))
    except LLMProviderError:
        return _error_response(status.HTTP_502_BAD_GATEWAY, "provider_error", "The model provider request failed.")
    except LLMClientConfigurationError as exc:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "configuration_error", str(exc))
    except (InvalidToolArgumentsError, UnsupportedToolError, MessageProcessingError) as exc:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "message_processing_failed", str(exc))
    except Exception:
        return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "Failed to process message.")

    return PostMessageResponse(
        chat_id=result.chat_id,
        user_message=_message_to_response(result.user_message),
        assistant_message=_message_to_response(result.assistant_message),
        tool_calls_executed=result.tool_calls_executed,
        used_knowledge_files=result.used_knowledge_files,
    )
