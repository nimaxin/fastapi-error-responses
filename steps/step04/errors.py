from enum import StrEnum, auto
from typing import ClassVar

from fastapi import status


class ErrorCode(StrEnum):
    todo_not_found = auto()
    duplicate_title = auto()
    too_many_todos = auto()


class BaseHTTPError(Exception):
    status_code: ClassVar[int]
    code: ClassVar[ErrorCode]
    message: ClassVar[str] = ""

    def __init__(self) -> None:
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
