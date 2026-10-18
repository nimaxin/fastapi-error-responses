from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from errors import (
    BaseHTTPError,
    DuplicateTitleError,
    TodoNotFoundError,
    TooManyTodosError,
)


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, examples=["Walk the dog"])


class Todo(BaseModel):
    id: int = Field(examples=[3])
    title: str = Field(examples=["Walk the dog"])


MAX_TODOS = 3
todos = {1: Todo(id=1, title="Buy milk"), 2: Todo(id=2, title="Call mom")}

app = FastAPI()


async def http_error_handler(request: Request, e: BaseHTTPError) -> JSONResponse:
    return JSONResponse(
        {"code": e.code, "message": e.message, "details": {}},
        status_code=e.status_code,
    )


app.add_exception_handler(BaseHTTPError, http_error_handler)


@app.post("/todos", status_code=201)
async def create_todo(data: TodoCreate) -> Todo:
    if any(todo.title == data.title for todo in todos.values()):
        raise DuplicateTitleError
    if len(todos) >= MAX_TODOS:
        raise TooManyTodosError
    todo = Todo(id=len(todos) + 1, title=data.title)
    todos[todo.id] = todo
    return todo


@app.get("/todos/{todo_id}")
async def get_todo(todo_id: int) -> Todo:
    if todo_id not in todos:
        raise TodoNotFoundError
    return todos[todo_id]
