from typing import ClassVar

from fastapi import status


class BaseHTTPError(Exception):
    status_code: ClassVar[int]
    code: ClassVar[str]
    message: ClassVar[str] = ""

    def __init__(self) -> None:
        super().__init__(self.message)


class NotFoundError(BaseHTTPError):
    status_code = status.HTTP_404_NOT_FOUND


class BadRequestError(BaseHTTPError):
    status_code = status.HTTP_400_BAD_REQUEST


class TodoNotFoundError(NotFoundError):
    code = "todo_not_found"
    message = "Todo not found"


class DuplicateTitleError(BadRequestError):
    code = "duplicate_title"
    message = "Title already taken"


class TooManyTodosError(BadRequestError):
    code = "too_many_todos"
    message = "Todo limit reached"
