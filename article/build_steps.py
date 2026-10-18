"""Write the app as it stands after each step of the article into steps/.

Every step is the step before it with the changes the article walks through,
made with change(), so no step can drift from the one before. The in-between
states the article also shows go to article/variants/.

Usage: uv run python article/build_steps.py
"""

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STEPS = ROOT / "steps"
VARIANTS = ROOT / "article" / "variants"

Files = dict[str, str]


def block(text: str) -> str:
    """A code block written on the lines after its opening quotes."""
    return text.removeprefix("\n")


def change(files: Files, name: str, *pairs: str) -> Files:
    """A copy of files where each old text, found once in name, became the new."""
    text = files[name]
    for old, new in zip(pairs[::2], pairs[1::2], strict=True):
        old, new = block(old), block(new)
        assert text.count(old) == 1, f"{name}: expected once: {old!r}"
        text = text.replace(old, new, 1)
    return {**files, name: text}


# Step 0: a todo API written the usual way, with HTTPException.
step00: Files = {
    "main.py": block(r"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, examples=["Walk the dog"])


class Todo(BaseModel):
    id: int = Field(examples=[3])
    title: str = Field(examples=["Walk the dog"])


MAX_TODOS = 3
todos = {1: Todo(id=1, title="Buy milk"), 2: Todo(id=2, title="Call mom")}

app = FastAPI()


@app.post("/todos", status_code=201)
async def create_todo(data: TodoCreate) -> Todo:
    if any(todo.title == data.title for todo in todos.values()):
        raise HTTPException(status_code=400, detail="Title already taken")
    if len(todos) >= MAX_TODOS:
        raise HTTPException(status_code=400, detail="Todo limit reached")
    todo = Todo(id=len(todos) + 1, title=data.title)
    todos[todo.id] = todo
    return todo


@app.get("/todos/{todo_id}")
async def get_todo(todo_id: int) -> Todo:
    if todo_id not in todos:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todos[todo_id]
"""),
}

# Step 1: every error body carries a code, inside FastAPI's detail.
step01 = change(
    step00,
    "main.py",
    r"""
        raise HTTPException(status_code=400, detail="Title already taken")
""",
    r"""
        raise HTTPException(
            status_code=400,
            detail={"code": "duplicate_title", "message": "Title already taken"},
        )
""",
    r"""
        raise HTTPException(status_code=400, detail="Todo limit reached")
""",
    r"""
        raise HTTPException(
            status_code=400,
            detail={"code": "too_many_todos", "message": "Todo limit reached"},
        )
""",
    r"""
        raise HTTPException(status_code=404, detail="Todo not found")
""",
    r"""
        raise HTTPException(
            status_code=404,
            detail={"code": "todo_not_found", "message": "Todo not found"},
        )
""",
)

# Step 2: an exception class and a handler, so the shape is ours.
step02 = change(
    step01,
    "main.py",
    r"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
""",
    r"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from errors import BaseHTTPError
""",
    r"""
app = FastAPI()
""",
    r"""
app = FastAPI()


async def http_error_handler(request: Request, e: BaseHTTPError) -> JSONResponse:
    return JSONResponse(
        {"code": e.code, "message": e.message, "details": {}},
        status_code=e.status_code,
    )


app.add_exception_handler(BaseHTTPError, http_error_handler)
""",
    r"""
        raise HTTPException(
            status_code=400,
            detail={"code": "duplicate_title", "message": "Title already taken"},
        )
""",
    r"""
        raise BaseHTTPError(400, "duplicate_title", "Title already taken")
""",
    r"""
        raise HTTPException(
            status_code=400,
            detail={"code": "too_many_todos", "message": "Todo limit reached"},
        )
""",
    r"""
        raise BaseHTTPError(400, "too_many_todos", "Todo limit reached")
""",
    r"""
        raise HTTPException(
            status_code=404,
            detail={"code": "todo_not_found", "message": "Todo not found"},
        )
""",
    r"""
        raise BaseHTTPError(404, "todo_not_found", "Todo not found")
""",
)
step02["errors.py"] = block(r"""
class BaseHTTPError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)
""")

# Step 3: one class per error, with the status code on a layer of its own.
step03 = change(
    step02,
    "main.py",
    r"""
from errors import BaseHTTPError
""",
    r"""
from errors import (
    BaseHTTPError,
    DuplicateTitleError,
    TodoNotFoundError,
    TooManyTodosError,
)
""",
    r"""
        raise BaseHTTPError(400, "duplicate_title", "Title already taken")
""",
    r"""
        raise DuplicateTitleError
""",
    r"""
        raise BaseHTTPError(400, "too_many_todos", "Todo limit reached")
""",
    r"""
        raise TooManyTodosError
""",
    r"""
        raise BaseHTTPError(404, "todo_not_found", "Todo not found")
""",
    r"""
        raise TodoNotFoundError
""",
)
step03["errors.py"] = block(r"""
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
""")

# Step 4: the codes live in one enum.
step04 = change(
    step03,
    "errors.py",
    r"""
from typing import ClassVar

from fastapi import status
""",
    r"""
from enum import StrEnum, auto
from typing import ClassVar

from fastapi import status


class ErrorCode(StrEnum):
    todo_not_found = auto()
    duplicate_title = auto()
    too_many_todos = auto()
""",
    "    code: ClassVar[str]\n",
    "    code: ClassVar[ErrorCode]\n",
    '    code = "todo_not_found"\n',
    "    code = ErrorCode.todo_not_found\n",
    '    code = "duplicate_title"\n',
    "    code = ErrorCode.duplicate_title\n",
    '    code = "too_many_todos"\n',
    "    code = ErrorCode.too_many_todos\n",
)

# Step 5: handlers for the failures FastAPI and Starlette raise themselves.
step05 = change(
    step04,
    "errors.py",
    "    too_many_todos = auto()\n",
    r"""
    too_many_todos = auto()
    validation_error = auto()
    http_error = auto()
    internal_server_error = auto()
""",
    "from typing import ClassVar\n",
    "from typing import Any, ClassVar\n",
    r"""
    def __init__(self) -> None:
        super().__init__(self.message)
""",
    r"""
    def __init__(self) -> None:
        self.details: dict[str, Any] = {}
        super().__init__(self.message)
""",
    r"""
    message = "Todo limit reached"
""",
    r"""
    message = "Todo limit reached"


class ValidationError(BaseHTTPError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.validation_error
    message = "Invalid request data"


class InternalServerError(BaseHTTPError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = ErrorCode.internal_server_error
    message = "An unexpected error occurred"
""",
)
step05 = change(
    step05,
    "main.py",
    r"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
""",
    r"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
""",
    r"""
from errors import (
    BaseHTTPError,
    DuplicateTitleError,
    TodoNotFoundError,
    TooManyTodosError,
)
""",
    r"""
from errors import (
    BaseHTTPError,
    DuplicateTitleError,
    ErrorCode,
    InternalServerError,
    TodoNotFoundError,
    TooManyTodosError,
    ValidationError,
)

log = logging.getLogger(__name__)
""",
    r"""
async def http_error_handler(request: Request, e: BaseHTTPError) -> JSONResponse:
    return JSONResponse(
        {"code": e.code, "message": e.message, "details": {}},
        status_code=e.status_code,
    )


app.add_exception_handler(BaseHTTPError, http_error_handler)
""",
    r"""
def error_to_response(error: BaseHTTPError) -> JSONResponse:
    return JSONResponse(
        {"code": error.code, "message": error.message, "details": error.details},
        status_code=error.status_code,
    )


async def http_error_handler(request: Request, e: BaseHTTPError) -> JSONResponse:
    return error_to_response(e)


def field_path(err: dict[str, Any]) -> str:
    # For broken JSON, FastAPI puts a character position where the field would be.
    if err["type"] == "json_invalid":
        return ""
    return ".".join(str(part) for part in err["loc"][1:])


async def validation_error_handler(
    request: Request, e: RequestValidationError
) -> JSONResponse:
    error = ValidationError()
    error.details = {
        "errors": [
            {
                "location": err["loc"][0],
                "field": field_path(err),
                "type": err["type"],
                "message": err["msg"],
            }
            for err in e.errors()
        ]
    }
    return error_to_response(error)


async def unexpected_error_handler(request: Request, e: Exception) -> JSONResponse:
    log.exception("unhandled: %s %s", request.method, request.url.path, exc_info=e)
    return error_to_response(InternalServerError())


async def framework_error_handler(
    request: Request, e: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        {"code": ErrorCode.http_error, "message": str(e.detail), "details": {}},
        status_code=e.status_code,
        headers=e.headers,
    )


app.add_exception_handler(BaseHTTPError, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, framework_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
""",
)

# The handlers of step 5 before error_to_response took their common part.
step05_before_refactor = change(
    step05,
    "main.py",
    "    return error_to_response(e)\n",
    r"""
    return JSONResponse(
        {"code": e.code, "message": e.message, "details": e.details},
        status_code=e.status_code,
    )
""",
    "    return error_to_response(error)\n",
    r"""
    return JSONResponse(
        {"code": error.code, "message": error.message, "details": error.details},
        status_code=error.status_code,
    )
""",
    "    return error_to_response(InternalServerError())\n",
    r"""
    error = InternalServerError()
    return JSONResponse(
        {"code": error.code, "message": error.message, "details": error.details},
        status_code=error.status_code,
    )
""",
)

# Step 7: the 404 declared on its route, with one model for every error.
step07 = change(
    step05,
    "main.py",
    r"""
    title: str = Field(examples=["Walk the dog"])
""",
    r"""
    title: str = Field(examples=["Walk the dog"])


class ErrorSchema(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any]
""",
    r"""
@app.get("/todos/{todo_id}")
""",
    r"""
@app.get("/todos/{todo_id}", responses={404: {"model": ErrorSchema}})
""",
)

# Step 8: a model per error, with its code pinned.
step08 = change(
    step07,
    "errors.py",
    r"""
from typing import Any, ClassVar

from fastapi import status
""",
    r"""
from typing import Any, ClassVar, Literal

from fastapi import status
from pydantic import BaseModel, create_model
""",
    r"""
        self.details: dict[str, Any] = {}
        super().__init__(self.message)
""",
    r"""
        self.details: dict[str, Any] = {}
        super().__init__(self.message)

    @classmethod
    def openapi_model(cls) -> type[BaseModel]:
        return create_model(
            f"{cls.__name__}Schema",
            code=(Literal[cls.code], ...),
            message=(str, ...),
            details=(dict[str, Any], ...),
        )
""",
)
step08 = change(
    step08,
    "main.py",
    r"""


class ErrorSchema(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any]
""",
    "",
    r"""
@app.get("/todos/{todo_id}", responses={404: {"model": ErrorSchema}})
""",
    r"""
@app.get(
    "/todos/{todo_id}", responses={404: {"model": TodoNotFoundError.openapi_model()}}
)
""",
)

# Step 9: a description for each error, and a helper for responses=.
step09 = change(
    step08,
    "errors.py",
    "from typing import Any, ClassVar, Literal\n",
    "from typing import Annotated, Any, ClassVar, Literal\n",
    "from pydantic import BaseModel, create_model\n",
    "from pydantic import BaseModel, Field, create_model\n",
    r"""
    message: ClassVar[str] = ""
""",
    r"""
    message: ClassVar[str] = ""
    description: ClassVar[str] = ""
""",
    r"""
    message = "Todo not found"
""",
    r"""
    message = "Todo not found"
    description = "No todo has this id."
""",
    r"""
    message = "Title already taken"
""",
    r"""
    message = "Title already taken"
    description = "Another todo already has this title. Pick a different one."
""",
    r"""
    message = "Todo limit reached"
""",
    r"""
    message = "Todo limit reached"
    description = "Delete a todo before adding another."
""",
    r"""
    message = "An unexpected error occurred"
""",
    r"""
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
""",
)
step09 = change(
    step09,
    "main.py",
    r"""
    ValidationError,
)
""",
    r"""
    ValidationError,
    document_errors,
)
""",
    r"""
@app.post("/todos", status_code=201)
""",
    r"""
@app.post(
    "/todos",
    status_code=201,
    responses=document_errors(TooManyTodosError, DuplicateTitleError),
)
""",
    r"""
@app.get(
    "/todos/{todo_id}", responses={404: {"model": TodoNotFoundError.openapi_model()}}
)
""",
    r"""
@app.get("/todos/{todo_id}", responses=document_errors(TodoNotFoundError))
""",
)

# Step 11: the facts behind an error travel in typed details.
step11 = change(
    step09,
    "errors.py",
    r"""
    description: ClassVar[str] = ""
""",
    r"""
    description: ClassVar[str] = ""
    details_schema: ClassVar[type[BaseModel] | None] = None
""",
    r"""
    def __init__(self) -> None:
        self.details: dict[str, Any] = {}
        super().__init__(self.message)
""",
    r"""
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
""",
    r"""
            details=(dict[str, Any], ...),
""",
    r"""
            details=(cls.details_schema or dict[str, Any], ...),
""",
    r"""
class TooManyTodosError(BadRequestError):
""",
    r"""
class TooManyTodosDetails(BaseModel):
    limit: int = Field(description="The most todos you can have.", examples=[3])


class TooManyTodosError(BadRequestError):
""",
    r"""
    description = "Delete a todo before adding another."
""",
    r"""
    description = "Delete a todo before adding another."
    details_schema = TooManyTodosDetails
""",
)
step11 = change(
    step11,
    "main.py",
    r"""
    TodoNotFoundError,
    TooManyTodosError,
""",
    r"""
    TodoNotFoundError,
    TooManyTodosDetails,
    TooManyTodosError,
""",
    r"""
        raise TooManyTodosError
""",
    r"""
        raise TooManyTodosError(TooManyTodosDetails(limit=MAX_TODOS))
""",
)

# Step 11 before its field had a description and an example.
step11_thin = change(
    step11,
    "errors.py",
    r"""
    limit: int = Field(description="The most todos you can have.", examples=[3])
""",
    r"""
    limit: int
""",
)

# Step 12: the message is a template filled from the details.
step12 = change(
    step11,
    "errors.py",
    r"""
    message: ClassVar[str] = ""
""",
    r"""
    message_template: ClassVar[str] = ""
""",
    r"""
        super().__init__(self.message)
""",
    r"""
        self.message = self.message_template.format(**self.details)
        super().__init__(self.message)
""",
    r"""
    @classmethod
    def openapi_model(cls) -> type[BaseModel]:
""",
    r"""
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
""",
    r"""
            message=(str, ...),
""",
    r"""
            message=(str, Field(examples=[cls.example_message()])),
""",
    '    message = "Todo not found"\n',
    '    message_template = "Todo not found"\n',
    '    message = "Title already taken"\n',
    '    message_template = "Title already taken"\n',
    '    message = "Todo limit reached"\n',
    '    message_template = "You can have at most {limit} todos"\n',
    '    message = "Invalid request data"\n',
    '    message_template = "Invalid request data"\n',
    '    message = "An unexpected error occurred"\n',
    '    message_template = "An unexpected error occurred"\n',
    r"""
                f"- `{error.code.value}`: {error.description}" for error in group
            ),
        }
""",
    r"""
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
""",
)

# Step 13: every route documents the 500.
step13 = change(
    step12,
    "errors.py",
    r"""
    message_template = "An unexpected error occurred"
""",
    r"""
    message_template = "An unexpected error occurred"
    description = (
        "Something failed on our side. If the request changes data, "
        "check whether the change went through before you retry."
    )
""",
    "    for error in errors:\n",
    "    for error in (*errors, InternalServerError):\n",
)

# Step 14: every route documents the 422, in our shape, with typed details.
step14 = change(
    step13,
    "errors.py",
    r"""
class ValidationError(BaseHTTPError):
""",
    r"""
class InvalidField(BaseModel):
    location: Literal["body", "query", "path", "header", "cookie"] = Field(
        description="The part of the request with the bad value."
    )
    field: str = Field(
        description="The field, with dots between nested names. Empty for bad JSON."
    )
    type: str = Field(description="The rule that failed, such as string_too_short.")
    message: str = Field(description="What pydantic says is wrong, for developers.")


class ValidationDetails(BaseModel):
    errors: list[InvalidField] = Field(
        description="One entry for each problem.",
        examples=[
            [
                {
                    "location": "body",
                    "field": "title",
                    "type": "string_too_short",
                    "message": "String should have at least 1 character",
                }
            ]
        ],
    )


class ValidationError(BaseHTTPError):
""",
    r"""
    message_template = "Invalid request data"
""",
    r"""
    message_template = "Invalid request data"
    description = "The request is invalid. details lists each problem."
    details_schema = ValidationDetails
""",
    "    for error in (*errors, InternalServerError):\n",
    "    for error in (*errors, ValidationError, InternalServerError):\n",
)
step14 = change(
    step14,
    "main.py",
    r"""
    InternalServerError,
    TodoNotFoundError,
""",
    r"""
    InternalServerError,
    InvalidField,
    TodoNotFoundError,
""",
    r"""
    TooManyTodosError,
    ValidationError,
""",
    r"""
    TooManyTodosError,
    ValidationDetails,
    ValidationError,
""",
    r"""
    error = ValidationError()
    error.details = {
        "errors": [
            {
                "location": err["loc"][0],
                "field": field_path(err),
                "type": err["type"],
                "message": err["msg"],
            }
            for err in e.errors()
        ]
    }
    return error_to_response(error)
""",
    r"""
    details = ValidationDetails(
        errors=[
            InvalidField(
                location=err["loc"][0],
                field=field_path(err),
                type=err["type"],
                message=err["msg"],
            )
            for err in e.errors()
        ]
    )
    return error_to_response(ValidationError(details))
""",
)

# Step 15: a test that fails when an error is missing from the schema.
step15 = dict(step14)
step15["test_main.py"] = block(r"""
import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from main import app

SCHEMA = app.openapi()


def matches(template: str, path: str) -> bool:
    pieces, parts = template.split("/"), path.split("/")
    return len(pieces) == len(parts) and all(
        piece == part or piece.startswith("{") for piece, part in zip(pieces, parts)
    )


def route_path(method: str, path: str) -> str | None:
    for template, operations in SCHEMA["paths"].items():
        if method.lower() in operations and matches(template, path):
            return template
    return None


def documented_codes(method: str, path: str, status_code: int) -> set[str]:
    responses = SCHEMA["paths"][path][method.lower()]["responses"]
    if str(status_code) not in responses:
        return set()
    body = responses[str(status_code)]["content"]["application/json"]["schema"]
    schemas = SCHEMA["components"]["schemas"]
    return {
        schemas[option["$ref"].rsplit("/", 1)[1]]["properties"]["code"]["const"]
        for option in body.get("oneOf", [body])
    }


def check_documented(response: Response) -> None:
    if response.status_code < 400:
        return
    response.read()
    method = response.request.method
    path = route_path(method, response.request.url.path)
    if path is None:
        return
    code = response.json()["code"]
    assert code in documented_codes(method, path, response.status_code), (
        f"{method} {path} sent a {response.status_code} {code}, "
        "which its responses= does not list"
    )


@pytest.fixture
def client() -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.event_hooks = {"response": [check_documented]}
    return client


def test_missing_todo(client: TestClient) -> None:
    response = client.get("/todos/99")
    assert response.json()["code"] == "todo_not_found"


def test_duplicate_title(client: TestClient) -> None:
    response = client.post("/todos", json={"title": "Buy milk"})
    assert response.json()["code"] == "duplicate_title"


def test_too_many_todos(client: TestClient) -> None:
    client.post("/todos", json={"title": "Water the plants"})
    response = client.post("/todos", json={"title": "Read a book"})
    assert response.json()["code"] == "too_many_todos"


def test_empty_title(client: TestClient) -> None:
    response = client.post("/todos", json={"title": ""})
    assert response.json()["code"] == "validation_error"


def test_unknown_path_and_method(client: TestClient) -> None:
    assert client.get("/nowhere").json()["code"] == "http_error"
    assert client.delete("/todos").json()["code"] == "http_error"


def test_every_route_documents_a_500() -> None:
    for path, operations in SCHEMA["paths"].items():
        for method, operation in operations.items():
            assert "500" in operation["responses"], f"{method.upper()} {path}"


def test_no_route_falls_back_to_fastapis_422() -> None:
    assert "HTTPValidationError" not in SCHEMA["components"]["schemas"]
""")

# Step 15 with duplicate_title left out of the route's list, to watch the test fail.
step15_forgot = change(
    step15,
    "main.py",
    r"""
    responses=document_errors(TooManyTodosError, DuplicateTitleError),
""",
    r"""
    responses=document_errors(TooManyTodosError),
""",
)

STEP_FILES = {
    "step00": step00,
    "step01": step01,
    "step02": step02,
    "step03": step03,
    "step04": step04,
    "step05": step05,
    "step07": step07,
    "step08": step08,
    "step09": step09,
    "step11": step11,
    "step12": step12,
    "step13": step13,
    "step14": step14,
    "step15": step15,
}
VARIANT_FILES = {
    "step05-before-refactor": step05_before_refactor,
    "step11-thin": step11_thin,
    "step15-forgot": step15_forgot,
}


def write(folder: pathlib.Path, groups: dict[str, Files]) -> None:
    shutil.rmtree(folder, ignore_errors=True)
    for name, files in groups.items():
        (folder / name).mkdir(parents=True)
        for filename, text in files.items():
            (folder / name / filename).write_text(text, encoding="utf-8", newline="\n")


write(STEPS, STEP_FILES)
write(VARIANTS, VARIANT_FILES)
# What an editor running ruff does on save: sort the imports, then format.
for command in (["check", "--select", "I", "--fix", "--quiet"], ["format", "--quiet"]):
    ruff = [sys.executable, "-m", "ruff", *command, str(STEPS), str(VARIANTS)]
    subprocess.run(ruff, check=True)
print("wrote", ", ".join(STEP_FILES), "and", ", ".join(VARIANT_FILES))
