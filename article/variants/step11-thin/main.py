import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from errors import (
    BaseHTTPError,
    DuplicateTitleError,
    ErrorCode,
    InternalServerError,
    TodoNotFoundError,
    TooManyTodosDetails,
    TooManyTodosError,
    ValidationError,
    document_errors,
)

log = logging.getLogger(__name__)


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, examples=["Walk the dog"])


class Todo(BaseModel):
    id: int = Field(examples=[3])
    title: str = Field(examples=["Walk the dog"])


MAX_TODOS = 3
todos = {1: Todo(id=1, title="Buy milk"), 2: Todo(id=2, title="Call mom")}

app = FastAPI()


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


@app.post(
    "/todos",
    status_code=201,
    responses=document_errors(TooManyTodosError, DuplicateTitleError),
)
async def create_todo(data: TodoCreate) -> Todo:
    if any(todo.title == data.title for todo in todos.values()):
        raise DuplicateTitleError
    if len(todos) >= MAX_TODOS:
        raise TooManyTodosError(TooManyTodosDetails(limit=MAX_TODOS))
    todo = Todo(id=len(todos) + 1, title=data.title)
    todos[todo.id] = todo
    return todo


@app.get("/todos/{todo_id}", responses=document_errors(TodoNotFoundError))
async def get_todo(todo_id: int) -> Todo:
    if todo_id not in todos:
        raise TodoNotFoundError
    return todos[todo_id]
