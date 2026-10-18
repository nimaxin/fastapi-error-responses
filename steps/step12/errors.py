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
    message_template: ClassVar[str] = ""
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
        self.message = self.message_template.format(**self.details)
        super().__init__(self.message)

    @classmethod
    def example_details(cls) -> dict[str, Any]:
        if cls.details_schema is None:
            return {}
        return {
            name: field.examples[0]
            for name, field in cls.details_schema.model_fields.items()
            if field.examples
        }

    @classmethod
    def example_message(cls) -> str:
        return cls.message_template.format(**cls.example_details())

    @classmethod
    def example(cls) -> dict[str, Any]:
        return {
            "code": cls.code,
            "message": cls.example_message(),
            "details": cls.example_details(),
        }

    @classmethod
    def openapi_model(cls) -> type[BaseModel]:
        return create_model(
            f"{cls.__name__}Schema",
            code=(Literal[cls.code], ...),
            message=(str, Field(examples=[cls.example_message()])),
            details=(cls.details_schema or dict[str, Any], ...),
        )


class NotFoundError(BaseHTTPError):
    status_code = status.HTTP_404_NOT_FOUND


class BadRequestError(BaseHTTPError):
    status_code = status.HTTP_400_BAD_REQUEST


class TodoNotFoundError(NotFoundError):
    code = ErrorCode.todo_not_found
    message_template = "Todo not found"
    description = "No todo has this id."


class DuplicateTitleError(BadRequestError):
    code = ErrorCode.duplicate_title
    message_template = "Title already taken"
    description = "Another todo already has this title. Pick a different one."


class TooManyTodosDetails(BaseModel):
    limit: int = Field(description="The most todos you can have.", examples=[3])


class TooManyTodosError(BadRequestError):
    code = ErrorCode.too_many_todos
    message_template = "You can have at most {limit} todos"
    description = "Delete a todo before adding another."
    details_schema = TooManyTodosDetails


class ValidationError(BaseHTTPError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.validation_error
    message_template = "Invalid request data"


class InternalServerError(BaseHTTPError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = ErrorCode.internal_server_error
    message_template = "An unexpected error occurred"


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
            "content": {
                "application/json": {
                    "examples": {
                        error.code.value: {"value": error.example()} for error in group
                    }
                }
            },
        }
    return responses
