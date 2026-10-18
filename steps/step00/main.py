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
