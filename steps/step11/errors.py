from enum import StrEnum, auto
from typing import Annotated, Any, ClassVar, Literal

from fastapi import status
from pydantic import BaseModel, Field, create_model


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
    description: ClassVar[str] = ""
    details_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, details: BaseModel | None = None) -> None:
        expected = self.details_schema
        if expected and details and not isinstance(details, expected):
            raise TypeError(
                f"{type(self).__name__} documents details as {expected.__name__}, "
                f"got {type(details).__name__}"
            )
        self.details: dict[str, Any] = (
            details.model_dump(mode="json") if details else {}
        )
        super().__init__(self.message)

    @classmethod
    def openapi_model(cls) -> type[BaseModel]:
        return create_model(
            f"{cls.__name__}Schema",
            code=(Literal[cls.code], ...),
            message=(str, ...),
            details=(cls.details_schema or dict[str, Any], ...),
        )


class NotFoundError(BaseHTTPError):
    status_code = status.HTTP_404_NOT_FOUND


class BadRequestError(BaseHTTPError):
    status_code = status.HTTP_400_BAD_REQUEST


class TodoNotFoundError(NotFoundError):
    code = ErrorCode.todo_not_found
    message = "Todo not found"
    description = "No todo has this id."


class DuplicateTitleError(BadRequestError):
    code = ErrorCode.duplicate_title
    message = "Title already taken"
    description = "Another todo already has this title. Pick a different one."


class TooManyTodosDetails(BaseModel):
    limit: int = Field(description="The most todos you can have.", examples=[3])


class TooManyTodosError(BadRequestError):
    code = ErrorCode.too_many_todos
    message = "Todo limit reached"
    description = "Delete a todo before adding another."
    details_schema = TooManyTodosDetails


class ValidationError(BaseHTTPError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.validation_error
    message = "Invalid request data"


class InternalServerError(BaseHTTPError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = ErrorCode.internal_server_error
    message = "An unexpected error occurred"


def document_errors(*errors: type[BaseHTTPError]) -> dict[int | str, dict[str, Any]]:
    grouped: dict[int, list[type[BaseHTTPError]]] = {}
    for error in errors:
        grouped.setdefault(error.status_code, []).append(error)

    responses: dict[int | str, dict[str, Any]] = {}
    for status_code, group in grouped.items():
        if len(group) == 1:
            responses[status_code] = {
                "model": group[0].openapi_model(),
                "description": group[0].description,
            }
            continue

        union = group[0].openapi_model()
        for error in group[1:]:
            union = union | error.openapi_model()
        responses[status_code] = {
            "model": Annotated[union, Field(discriminator="code")],
            "description": "\n".join(
                f"- `{error.code.value}`: {error.description}" for error in group
            ),
        }
    return responses
