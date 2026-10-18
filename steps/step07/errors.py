from enum import StrEnum, auto
from typing import Any, ClassVar

from fastapi import status


class ErrorCode(StrEnum):
    todo_not_found = auto()
    duplicate_title = auto()
    too_many_todos = auto()
    validation_error = auto()
    http_error = auto()
    internal_server_error = auto()


class BaseHTTPError(Exception):
    status_code: ClassVar[int]
    code: ClassVar[ErrorCode]
    message: ClassVar[str] = ""

    def __init__(self) -> None:
        self.details: dict[str, Any] = {}
        super().__init__(self.message)


class NotFoundError(BaseHTTPError):
    status_code = status.HTTP_404_NOT_FOUND


class BadRequestError(BaseHTTPError):
    status_code = status.HTTP_400_BAD_REQUEST


class TodoNotFoundError(NotFoundError):
    code = ErrorCode.todo_not_found
    message = "Todo not found"


class DuplicateTitleError(BadRequestError):
    code = ErrorCode.duplicate_title
    message = "Title already taken"


class TooManyTodosError(BadRequestError):
    code = ErrorCode.too_many_todos
    message = "Todo limit reached"


class ValidationError(BaseHTTPError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.validation_error
    message = "Invalid request data"


class InternalServerError(BaseHTTPError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = ErrorCode.internal_server_error
    message = "An unexpected error occurred"
