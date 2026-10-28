
import logging
import uuid

from fastapi import HTTPException, Request, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from app.core.exceptions import AppException
from app.schemas.errors import ErrorResponse, ErrorDetail
from app.utils.sse import format_sse


logger = logging.getLogger(__name__)



def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    headers: dict | None = None,
):
    """
    Build a standardized SSE error response.

    SSE events:
        event: error
        event: done

    The HTTP status code is preserved.
    """

    correlation_id = (
        getattr(
            request.state,
            "correlation_id",
            None,
        )
        or str(uuid.uuid4())
    )

    session_id = getattr(
        request.state,
        "session_id",
        None,
    )

    error_payload = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            session_id=(
                str(session_id)
                if session_id is not None
                else None
            ),
            correlation_id=correlation_id,
            retryable=retryable,
        )
    )

    async def error_stream():

        yield format_sse(
            "error",
            error_payload.model_dump(
                mode="json"
            ),
        )

        yield format_sse(
            "done",
            {
                "status": "failed",
            },
        )

    return StreamingResponse(
        error_stream(),
        status_code=status_code,
        media_type="text/event-stream",
        headers={
            **(headers or {}),
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Correlation-ID": correlation_id,
        },
    )


def register_exception_handlers(
    app: FastAPI,
):
    """
    Register application exception handlers.
    """

    handlers = {
        AppException: app_exception_handler,
        HTTPException: http_exception_handler,
        RequestValidationError: validation_exception_handler,
        Exception: unexpected_exception_handler,
    }

    for exception_type, handler in handlers.items():
        app.add_exception_handler(
            exception_type,
            handler,
        )


async def app_exception_handler(
    request: Request,
    exc: AppException,
):
    """
    Handle application-specific exceptions.
    """

    return error_response(
        request=request,
        status_code=exc.status_code,
        code=exc.error_code,
        message=exc.message,
        retryable=False,
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    """
    Handle FastAPI HTTP exceptions.
    """

    return error_response(
        request=request,
        status_code=exc.status_code,
        code="HTTP_ERROR",
        message=str(exc.detail),
        retryable=False,
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """
    Handle request validation failures.
    """

    logger.warning(
        "REQUEST_VALIDATION_FAILED | "
        "correlation_id=%s | errors=%s",
        getattr(
            request.state,
            "correlation_id",
            None,
        ),
        exc.errors(),
    )

    return error_response(
        request=request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Invalid request data.",
        retryable=False,
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
):
    """
    Handle unexpected application failures.
    """

    logger.error(
        "Unhandled request error; correlation_id=%s",
        getattr(
            request.state,
            "correlation_id",
            None,
        ),
        exc_info=(
            type(exc),
            exc,
            exc.__traceback__,
        ),
    )

    return error_response(
        request=request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message=(
            "An unexpected error occurred. "
            "Please try again."
        ),
        retryable=True,
    )
