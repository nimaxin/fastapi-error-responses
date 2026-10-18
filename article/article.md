# Documenting FastAPI errors

FastAPI generates an OpenAPI schema for you, but by default it says almost nothing about how your API fails. This guide builds that part of the schema up step by step: one error format and a schema that lists exactly which errors each route can return.

I've been designing and building APIs with FastAPI for over three years, and this guide is what that work taught me about errors.

Every API has to tell a client that something went wrong.

FastAPI gives you `HTTPException` for that, and it works.

```python
@app.get("/todos/{todo_id}")
async def get_todo(todo_id: int) -> Todo:
    if todo_id not in todos:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todos[todo_id]
```

Ask for a todo that isn't there and you get a 404 with this body:

```json
{
  "detail": "Todo not found"
}
```

Now send a body that fails validation to the same API, say a todo with an empty title. You get this:

```json
{
  "detail": [
    {
      "type": "string_too_short",
      "loc": ["body", "title"],
      "msg": "String should have at least 1 character",
      "input": "",
      "ctx": {
        "min_length": 1
      }
    }
  ]
}
```

Two errors from one API, and they have almost nothing in common.

In the first, `detail` is a string. In the second it is a list of objects.

But the response bodies are the smaller problem. The bigger one is that your `openapi.json` says almost nothing about any of it.

That matters because your schema is what everyone else builds against. It is what the docs page renders, what a client generator reads, and what another team checks when they want to know how your API fails. If it does not describe your errors, nobody can handle them properly, and they will end up matching on English sentences instead.

## Where this ends up

Before building anything, here is the difference this makes to the docs page.

This is `POST /todos` as FastAPI documents it today, in ReDoc, the docs page FastAPI serves at `/redoc`.

![POST /todos in ReDoc, documenting a 201 and FastAPI's 422 and nothing else](https://raw.githubusercontent.com/nimaxin/fastapi-error-responses/master/article/images/before.png)

And this is the same route at the end of this guide.

![The same route documenting a 400, a 422 and a 500, with the errors behind each](https://raw.githubusercontent.com/nimaxin/fastapi-error-responses/master/article/images/after.png)

Same two routes, and the same request and response models. The only thing that changed is how the errors are handled.

Two things in the second picture are worth looking at now, because most of this guide exists to produce them.

The 400 lists two errors, with a sentence saying what to do about each. One status code, two errors, told apart by name.

And the samples panel on the right has a dropdown, currently set to `too_many_todos`. That is a reader picking one error out of the two that share a status code, which is only possible because the schema says how to tell them apart.

Swagger UI, the docs page FastAPI serves at `/docs`, gets the same dropdown by the end.

That is what the rest of this guide builds, in fifteen steps.

## The example

Everything below is built on a tiny todo API with two routes. This is all of it:

`main.py`

```python
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
```

`POST /todos` adds a todo, and `GET /todos/{todo_id}` reads one back. They can fail in a few ways. The todo doesn't exist. Its title is taken, or you already have as many todos as you're allowed. The request is invalid. Or something broke on our side.

The code is on GitHub at [nimaxin/fastapi-error-responses](https://github.com/nimaxin/fastapi-error-responses), with a folder for every step that changes it. Each folder is a complete app, so you can run the API as it stands after any step:

```bash
git clone https://github.com/nimaxin/fastapi-error-responses
cd fastapi-error-responses
uv run fastapi dev steps/step05/main.py
```

## Step 1. Give the client something to branch on

### What is missing

Look again at what a client gets when it asks for a todo that isn't there.

```json
{
  "detail": "Todo not found"
}
```

There is nothing in there a program can act on.

It gets worse when two errors share a status code. "Title already taken" and "Todo limit reached" are both 400s, so the only way for a client to tell them apart is to compare the English sentence. And one day you will change that wording, because it is written for people to read.

So give it a short string that never changes instead.

### A quick fix

`HTTPException` takes any JSON-able value as `detail`, not only a string. So you can do this right now, with nothing else in place.

`main.py`

```python
    if len(todos) >= MAX_TODOS:
        raise HTTPException(
            status_code=400,
            detail={"code": "too_many_todos", "message": "Todo limit reached"},
        )
```

### The resulting response

```json
{
  "detail": {
    "code": "too_many_todos",
    "message": "Todo limit reached"
  }
}
```

That is real progress. A client can look at `detail.code`, see `too_many_todos`, and never read the sentence.

Two things are wrong with it, and the next two steps deal with one each.

The body is nested inside `detail`, which is FastAPI's field and not yours.

And `"too_many_todos"` is a string you typed by hand, inside a route, with nothing checking it.

The other two errors get the same change. The code so far: [steps/step01](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step01)

## Step 2. Own the shape of the response

### Why `detail` has to go

You want three fields at the top level, not two of yours wrapped in one of FastAPI's.

And there is a second reason. Send a bad body to that same route and you still get pydantic's nested `loc` array, which looks nothing like what you just built.

Both are the same problem. FastAPI is choosing the shape of your error responses, and you want to choose it.

You do that by registering an exception handler. And a handler needs an exception class of its own to be registered against.

### Write the exception class

`errors.py`

```python
class BaseHTTPError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)
```

Notice what it does not inherit from.

> **Warning**
>
> Subclassing `HTTPException` is the obvious move here, and it will bite you.
>
> Registering a handler for a subclass of `HTTPException` does work, to be clear. Starlette picks the most specific handler you have registered, including when the error is raised from a dependency.
>
> The problem is what happens the day you forget to register it. A subclass of `HTTPException` falls back to FastAPI's own handler and returns a 400 with `{"detail": ...}`. Right status, wrong shape, and no warning anywhere. A test that asserts `response.status_code == 400` still passes.
>
> Subclass `Exception` and the same mistake gives you a 500, which you notice immediately.
>
> There is a second reason. It comes up less often, but it is real. Any `except HTTPException` between the raise and the handler will catch your error, and that includes middleware you did not write.

### Write the handler

The handler turns the error into the three fields you want, at the top level.

`main.py`

```python
async def http_error_handler(request: Request, e: BaseHTTPError) -> JSONResponse:
    return JSONResponse(
        {"code": e.code, "message": e.message, "details": {}},
        status_code=e.status_code,
    )


app.add_exception_handler(BaseHTTPError, http_error_handler)
```

`details` is empty for now. Step 5 gives it something to hold.

### Raise it

Because it is a plain Python exception, you don't return it. You raise it.

```python
raise BaseHTTPError(400, "too_many_todos", "Todo limit reached")
```

### The resulting response

```json
{
  "code": "too_many_todos",
  "message": "Todo limit reached",
  "details": {}
}
```

Three fields, no wrapper, and the shape is yours.

> **Note**
>
> There is a standard for error bodies: [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457), Problem Details for HTTP APIs. It names the fields `type`, `title`, `status`, `detail` and `instance`, and sends them as `application/problem+json`.
>
> This guide uses `code`, `message` and `details` instead, the shape Stripe, Google and Microsoft each use in some form, because a short code like `too_many_todos` is easier to read and type than the URI the standard puts in `type`.
>
> The ideas carry over one to one. `code` becomes `type`, `message` becomes `detail`, and what this guide keeps in `details` moves to the top level. Pick one shape and use it everywhere. Everything below applies to either.

The code so far: [steps/step02](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step02)

## Step 3. Stop repeating yourself at every raise site

### What the last step left behind

Every raise now carries three arguments, and every one of them is the same every time that error happens.

```python
raise BaseHTTPError(400, "duplicate_title", "Title already taken")
raise BaseHTTPError(400, "too_many_todos", "Todo limit reached")
raise BaseHTTPError(404, "todo_not_found", "Todo not found")
```

Which means the status code for "todo limit reached" is written wherever you happen to raise it, and if two places disagree, nothing tells you.

These belong to the error, not to the place it is raised. So put them on a class.

### A class variable for each

`errors.py`

```python
class BaseHTTPError(Exception):
    status_code: ClassVar[int]
    code: ClassVar[str]
    message: ClassVar[str] = ""

    def __init__(self) -> None:
        super().__init__(self.message)
```

`ClassVar` because these describe the _kind_ of error, not one instance of it.

### A thin layer for the status code

Several errors will share a status code, so write it once.

`errors.py`

```python
class NotFoundError(BaseHTTPError):
    status_code = status.HTTP_404_NOT_FOUND


class BadRequestError(BaseHTTPError):
    status_code = status.HTTP_400_BAD_REQUEST
```

> **Tip**
>
> You can spend a long time deciding whether a given error is a 409, a 412 or a 422.
>
> Some APIs skip that and answer anything their business rules reject with `400`, letting `code` say which rule it was. Others pick the closest status: `409 Conflict`, `422 Unprocessable Content`, or `402`, which Stripe sends for a declined card. Both work, because a client branches on `code` either way. This guide uses 400.
>
> What you shouldn't fold into 400 are the statuses other software acts on. Auth middleware refreshes tokens on **401**, and **403** tells it the credentials are fine but not allowed, so a refresh won't help. Clients and proxies back off on **429**, where a 400 tells them not to retry at all. Caches and monitoring treat **404** differently from other failures. And the line between **4xx and 5xx** is what decides whether retrying is worth trying.
>
> So the status code is for the transport and for general infrastructure. `code` is for your application.

> **Note**
>
> Some statuses need a header as well. [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110#section-15.5.2), the HTTP standard, says a 401 must send `WWW-Authenticate` with a way to authenticate, and a 429 usually sends `Retry-After`. If your API returns those, give the base class a `headers` class variable, set it on the errors that need it, and send it from the handler.

### Then one class per error

Each real error is now three lines.

`errors.py`

```python
class TodoNotFoundError(NotFoundError):
    code = "todo_not_found"
    message = "Todo not found"


class DuplicateTitleError(BadRequestError):
    code = "duplicate_title"
    message = "Title already taken"


class TooManyTodosError(BadRequestError):
    code = "too_many_todos"
    message = "Todo limit reached"
```

### The raise gets shorter

```python
raise TooManyTodosError
```

And the response is the same as before, because the handler reads the same three attributes. It just does not care any more whether they came from an argument or a class.

> **Note**
>
> The message lives on the class, not at the place you raise it. So every "Todo not found" in your whole API is byte for byte identical.
>
> This matters for security. If the 404 for a todo that never existed read differently from the 404 for somebody else's todo, then anyone could use your API to work out which todo ids are real.

The code so far: [steps/step03](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step03)

## Step 4. Name the codes in one place

### Three hand-typed strings

Look at what you just wrote. Three classes, three string literals, and nothing connecting them.

Nothing stops you typing `"too_many_todo"`. Nothing stops two errors claiming the same code. And when you want to know every code your API can return, the only way to find out is to read every file.

An enum fixes all three.

`errors.py`

```python
from enum import StrEnum, auto


class ErrorCode(StrEnum):
    todo_not_found = auto()
    duplicate_title = auto()
    too_many_todos = auto()
```

`StrEnum` with `auto()` gives each member its own lowercase name as its value. So `ErrorCode.too_many_todos` is the string `"too_many_todos"`, and you never write that string twice.

Then the classes point at it, and a typo is an `AttributeError` at import time instead of a wrong string in a response body. The base class declares `code` as `ClassVar[ErrorCode]` now.

`errors.py`

```python
class TooManyTodosError(BadRequestError):
    code = ErrorCode.too_many_todos
    message = "Todo limit reached"
```

> **Tip**
>
> Name your codes for what the caller was trying to do, never for how you do it inside.
>
> `too_many_todos` is good. `todo_table_full` is not, because one day you will change how todos are stored and that code will still be there.
>
> These strings are public API. Once a client ships a branch on them, you are keeping them forever.

The code so far: [steps/step04](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step04)

## Step 5. The failures you did not write

### Your errors are consistent now, and nothing else is

Send a bad body and you still get pydantic's nested array. Ask for a path that doesn't exist and you get FastAPI's `{"detail": "Not Found"}`. Cause a crash and you get whatever Starlette decides.

All three are responses your API sends, so all three need the same treatment. Start with a code for each:

`errors.py`

```python
class ErrorCode(StrEnum):
    ...
    validation_error = auto()
    http_error = auto()
    internal_server_error = auto()
```

The validation error and the crash get classes like everything else.

`errors.py`

```python
class ValidationError(BaseHTTPError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.validation_error
    message = "Invalid request data"


class InternalServerError(BaseHTTPError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = ErrorCode.internal_server_error
    message = "An unexpected error occurred"
```

You will never raise these two yourself. The handlers build them.

And a validation error is the first one with something to put in `details`, so every error gets a `details` of its own now, empty until something fills it:

`errors.py`

```python
    def __init__(self) -> None:
        self.details: dict[str, Any] = {}
        super().__init__(self.message)
```

### Validation errors

When a request is invalid, FastAPI raises `RequestValidationError` internally, and you can handle it like anything else.

Each problem pydantic reports has a `loc`, a `type` and a `msg`. The `loc` is a tuple like `("body", "title")`. Its first element says which part of the request had the problem, and the rest say where in it.

So turn each problem into a small object with those parts named:

`main.py`

```python
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
    return JSONResponse(
        {"code": error.code, "message": error.message, "details": error.details},
        status_code=error.status_code,
    )
```

Send an empty title and here is what comes back:

```json
{
  "code": "validation_error",
  "message": "Invalid request data",
  "details": {
    "errors": [
      {
        "location": "body",
        "field": "title",
        "type": "string_too_short",
        "message": "String should have at least 1 character"
      }
    ]
  }
}
```

Compare that with the nested array from the top of the article. A frontend can find the problems with each input by `field`, and pick its own wording, in its own language, from `type`. It never has to show pydantic's English `message`, or parse anything.

`location` says which part of the request was wrong. Ask for `/todos/abc`, and the problem is in the path:

```json
{
  "code": "validation_error",
  "message": "Invalid request data",
  "details": {
    "errors": [
      {
        "location": "path",
        "field": "todo_id",
        "type": "int_parsing",
        "message": "Input should be a valid integer, unable to parse string as an integer"
      }
    ]
  }
}
```

And `field_path` takes care of the one `loc` that is not a path. When the body is not JSON at all, FastAPI puts the character position where the field name would go, so `field` stays empty:

```json
{
  "code": "validation_error",
  "message": "Invalid request data",
  "details": {
    "errors": [
      {
        "location": "body",
        "field": "",
        "type": "json_invalid",
        "message": "JSON decode error"
      }
    ]
  }
}
```

### Everything else

The last handler catches bare `Exception`, so an unhandled crash still comes back in your format rather than somebody else's.

It says nothing about what actually happened. Log the traceback, don't send it.

`main.py`

```python
async def unexpected_error_handler(request: Request, e: Exception) -> JSONResponse:
    log.exception("unhandled: %s %s", request.method, request.url.path, exc_info=e)
    error = InternalServerError()
    return JSONResponse(
        {"code": error.code, "message": error.message, "details": error.details},
        status_code=error.status_code,
    )
```

> **Warning**
>
> Watch out for `debug=True`.
>
> With debug on, Starlette serves its own traceback page and never calls your 500 handler. The handler above quietly stops running, and your API starts sending the full traceback, with your file paths and lines of your source code, to whoever made the request.
>
> One environment variable is all it takes. Reject that combination in your settings validation rather than trusting yourself to remember.

> **Warning**
>
> Starlette runs the handler for `Exception` outside every middleware, `CORSMiddleware` included. So a 500 goes out without CORS headers, and a browser app on another origin sees a CORS error instead of your body. Every other error keeps its CORS headers.

### Three handlers, one body

Look at the three handlers you now have. Every one of them ends by building the same three fields out of an error.

That is a third copy, so now it is worth pulling out.

`main.py`

```python
def error_to_response(error: BaseHTTPError) -> JSONResponse:
    return JSONResponse(
        {"code": error.code, "message": error.message, "details": error.details},
        status_code=error.status_code,
    )
```

And all three handlers end in one line.

`main.py`

```python
async def http_error_handler(request: Request, e: BaseHTTPError) -> JSONResponse:
    return error_to_response(e)


async def validation_error_handler(
    request: Request, e: RequestValidationError
) -> JSONResponse:
    error = ValidationError()
    ...
    return error_to_response(error)


async def unexpected_error_handler(request: Request, e: Exception) -> JSONResponse:
    log.exception("unhandled: %s %s", request.method, request.url.path, exc_info=e)
    return error_to_response(InternalServerError())
```

One place decides what an error response looks like, which is what you want before you start writing that shape down in the schema.

### FastAPI's own errors

There is one more kind of failure: the ones FastAPI raises itself. Its router raises an `HTTPException` of its own for a path that doesn't exist, or a method the route doesn't take, and those still come back as `{"detail": "Not Found"}`.

These don't get a class each. They mean nothing beyond their status code, and the router can raise them for any path at all. So they share one code, `http_error`, and keep FastAPI's status, message and headers.

`main.py`

```python
async def framework_error_handler(
    request: Request, e: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(
        {"code": ErrorCode.http_error, "message": str(e.detail), "details": {}},
        status_code=e.status_code,
        headers=e.headers,
    )
```

It writes the three fields itself, because there is no error class to hand to `error_to_response`. And `str()` is there because `detail` can be any JSON value, as step 1 showed.

Register it for Starlette's `HTTPException`, imported here as `StarletteHTTPException`, not FastAPI's. The router raises Starlette's, and FastAPI's is a subclass of it, so this one handler catches both.

Ask for a path that isn't there:

```json
{
  "code": "http_error",
  "message": "Not Found",
  "details": {}
}
```

The headers matter for a 405. HTTP says it has to list the methods the route does take, in an `Allow` header, and FastAPI has already put it there:

```http
HTTP/1.1 405 Method Not Allowed
allow: POST

{
  "code": "http_error",
  "message": "Method Not Allowed",
  "details": {}
}
```

FastAPI's security helpers, such as `OAuth2PasswordBearer`, `HTTPBearer` and `APIKeyHeader`, raise this same `HTTPException` when a credential is missing. So this handler catches those too, as `http_error`. If you want codes of your own for them, pass `auto_error=False` and raise your own errors.

### All four registered

`main.py`

```python
app.add_exception_handler(BaseHTTPError, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, framework_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
```

Every failure your API can produce now comes back as the same three fields, with a code a client can branch on.

The runtime side is done. The docs side has not started.

The code so far: [steps/step05](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step05)

## Step 6. Now go and look at your docs

### Open the docs page

Start the app, open `/redoc`, and find `GET /todos/{todo_id}`.

![GET /todos/{todo_id} in ReDoc, still documenting a 200 and FastAPI's 422 and nothing else](https://raw.githubusercontent.com/nimaxin/fastapi-error-responses/master/article/images/docs-step-6.png)

Nothing you did in the last five steps changed a single line of it. Every one of them changed what the route _returns_, and none of them changed what the route _declares_.

### Two problems, and the second is worse

The first is that your 404 is not there. That route raises `TodoNotFoundError` on its main path, and as far as your schema is concerned that never happens.

The second is the 422. It points at `HTTPValidationError`, which is FastAPI's schema for the nested `loc` format. Your API stopped sending that in step 5.

`openapi.json`

```json
{
  "description": "Validation Error",
  "content": {
    "application/json": {
      "schema": {
        "$ref": "#/components/schemas/HTTPValidationError"
      }
    }
  }
}
```

So the schema is both incomplete and inaccurate. It describes a response your API no longer sends.

A client generated from this schema would expect the wrong body for a 422, and nothing about it would look broken until it ran.

That page is the readable view. When you want the exact text behind it, `app.openapi()` hands you the same document as a dict.

## Step 7. Declare the errors on the route

### The `responses` argument

FastAPI lets you declare extra responses per route with `responses=`. It takes a dict keyed by status code, and each value can carry a `model`.

So the obvious first attempt is to describe that format once and point every error at it.

`main.py`

```python
class ErrorSchema(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any]


@app.get("/todos/{todo_id}", responses={404: {"model": ErrorSchema}})
```

### What that gives you

The 404 appears in the schema now.

`openapi.json`

```json
{
  "content": {
    "application/json": {
      "schema": {
        "$ref": "#/components/schemas/ErrorSchema"
      }
    }
  },
  "description": "Not Found"
}
```

### Now follow the reference

`openapi.json`

```json
{
  "type": "string",
  "enum": [
    "todo_not_found",
    "duplicate_title",
    "too_many_todos",
    "validation_error",
    "http_error",
    "internal_server_error"
  ],
  "title": "ErrorCode"
}
```

The schema now says the 404 from this route may carry any of the six codes, including `internal_server_error` and `too_many_todos`.

That is not true. The route returns exactly one 404, and it is always `todo_not_found`.

The description is no better. It says "Not Found", because that is the status phrase and you gave it nothing else.

So you have documented the format but not the errors. Anything reading this schema still cannot tell one of your errors from another.

The code so far: [steps/step07](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step07)

## Step 8. Pin each code to one value

### Build the model from the class

The fix is to give each error its own schema, with `code` typed as a `Literal` of exactly one value.

You don't want to hand-write a near-identical model for every error. So build them with `create_model`, from the class variables you already set.

`errors.py`

```python
class BaseHTTPError(Exception):
    status_code: ClassVar[int]
    code: ClassVar[ErrorCode]
    message: ClassVar[str] = ""

    def __init__(self) -> None:
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
```

Then point the route at that instead of the shared model.

```python
@app.get(
    "/todos/{todo_id}", responses={404: {"model": TodoNotFoundError.openapi_model()}}
)
```

### The resulting schema

`openapi.json`

```json
{
  "properties": {
    "code": {
      "type": "string",
      "const": "todo_not_found",
      "title": "Code"
    },
    "message": {
      "type": "string",
      "title": "Message"
    },
    "details": {
      "additionalProperties": true,
      "type": "object",
      "title": "Details"
    }
  },
  "type": "object",
  "required": ["code", "message", "details"],
  "title": "TodoNotFoundErrorSchema"
}
```

The code is now pinned: `"const": "todo_not_found"`.

The schema no longer says this response carries one of six codes. It says it carries this one, and no other.

> **Note**
>
> The `const` keyword is what makes the rest of this useful.
>
> A `const` turns a list of possible error bodies into a discriminated union. Because each member pins `code` to a different fixed value, anything reading the response can look at `code` and know immediately which shape it is holding.
>
> Tools that generate clients understand this. Given a `const` they produce code where checking `code` narrows the type. Given a plain string they cannot, and the best they can offer is an object you have to inspect by hand.

The code so far: [steps/step08](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step08)

## Step 9. A helper for the `responses` argument

### Why you want one

Writing `{404: {"model": TodoNotFoundError.openapi_model()}}` on every route gets old, and it goes wrong as soon as two errors share a status code.

### Say what each error means

You saw in step 7 that the description falls back to the status phrase. "Not Found" tells a reader nothing the number didn't already.

So before writing the helper, add one more class variable, `description`, empty on the base class, and write a real sentence in it for each error.

`errors.py`

```python
class TooManyTodosError(BadRequestError):
    code = ErrorCode.too_many_todos
    message = "Todo limit reached"
    description = "Delete a todo before adding another."
```

Say what the caller should do about it. That is the part the status code cannot tell them.

Write it for a developer integrating against your API, not for their end user. "Delete a todo before adding another" is right. "Your list is full, time to clean up!" is copy for the app's screen, and it is not your job to write it.

### Write the helper

`errors.py`

```python
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
```

Group by status first, then decide what to do with each group.

One error on a status is the easy case. You already know how to document it.

Several errors on one status need two things. A union of their models, and a description that stays readable when there are six of them.

The `|` is a type union, not a dict merge, so `ModelA | ModelB` is the union of the two. And `Field(discriminator="code")` is what tells pydantic that `code` is the field that tells them apart.

### Use it

`main.py`

```python
@app.post(
    "/todos",
    status_code=201,
    responses=document_errors(TooManyTodosError, DuplicateTitleError),
)
async def create_todo(data: TodoCreate) -> Todo:
    ...
```

`GET /todos/{todo_id}` gets the same, with `TodoNotFoundError`.

Both errors land in one 400, and the schema says exactly how to tell them apart:

`openapi.json`

```json
{
  "description": "- `too_many_todos`: Delete a todo before adding another.\n- `duplicate_title`: Another todo already has this title. Pick a different one.",
  "content": {
    "application/json": {
      "schema": {
        "oneOf": [
          {
            "$ref": "#/components/schemas/TooManyTodosErrorSchema"
          },
          {
            "$ref": "#/components/schemas/DuplicateTitleErrorSchema"
          }
        ],
        "title": "Response 400 Create Todo Todos Post",
        "discriminator": {
          "propertyName": "code",
          "mapping": {
            "too_many_todos": "#/components/schemas/TooManyTodosErrorSchema",
            "duplicate_title": "#/components/schemas/DuplicateTitleErrorSchema"
          }
        }
      }
    }
  }
}
```

> **Note**
>
> Two things changed there, and both matter more than they look.
>
> `anyOf` became `oneOf`. `anyOf` means one or more of these match. `oneOf` means exactly one does, which is the truth here, because no response can have two different values of `code`.
>
> And the `discriminator` block is OpenAPI's own way of saying what step 8 could only imply. It names the field that tells the variants apart, and maps each value of it to a schema. A generated client reads that and produces a type it can narrow by checking one field, instead of guessing from the shape.
>
> This matters most if you answer business rule failures with 400, because then one status carries every business error you have. The status stops distinguishing anything and `code` does all the work.

ReDoc reads this union and gives the 400 a dropdown with one entry per error. Swagger UI shows only the first error's example, so a reader there never sees `duplicate_title`. Step 12 fixes that.

> **Note**
>
> You have to do this on every route, and you might wonder whether you can declare it once on the router instead.
>
> You can pass `responses` to `APIRouter` and it applies to everything under it. But OpenAPI has no global responses element, so the output is the same text copied onto every operation anyway.
>
> More to the point, it hides from each route what that route returns. With the errors listed on the route, adding a `raise` and forgetting to document it shows up in the diff. Inherited from a router three files away, it doesn't.
>
> It is repetitive, and that repetition is what keeps each route's list correct.

The code so far: [steps/step09](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step09)

## Step 10. The message is not data

### Three fields, three readers

Before the rule itself, it is worth being clear about who each field is written for, because they are three different people.

`code` is for the client's code. It is the thing a `switch` branches on.

`message` is for a developer. It goes into a log line, a stack trace, an error tracker, a support ticket.

`details` is for the client to build its own sentence from, in its own language, for its own end user.

So your end user never sees your `message`. Nobody's does. That is worth saying out loud, because it changes how you write one.

### A message that says something useful

Suppose you improve the todo limit message, because "Todo limit reached" doesn't tell a developer very much.

```json
{
  "code": "too_many_todos",
  "message": "You can have at most 3 todos",
  "details": {}
}
```

That is a much better message. A developer reads that line in a log and knows exactly what happened.

Now think about the client.

It wants to show "You have used all 3 of your todos" in the end user's language. Or grey out the add button once there are 3. Or show "2 of 3" above the list.

All of those need the number 3, and the only place that number exists is inside an English sentence. So the client's only option is to pull it out with a regular expression.

### What breaks

That regex breaks the day you reword the message.

It breaks when you translate it.

It breaks when the number gets big enough that you print it as `1,000`.

None of those look like breaking changes from your side, because all you changed was some wording. But each one breaks a client that was parsing the message, and nothing in your test suite will report it.

### The rule

Anything the message states has to exist in `details` as a real field.

Not just numbers. An id, a name, a date, a status, a currency. If the sentence tells the reader something, the client has to be able to get it without reading the sentence.

```json
{
  "code": "too_many_todos",
  "message": "You can have at most 3 todos",
  "details": {
    "limit": 3
  }
}
```

The message is still there and still says the same thing, because a developer reading a log still wants a sentence.

But nothing has to parse it any more.

RFC 9457 says the same about its own `detail` field: clients should not parse it, and anything they need belongs in a field of its own.

### How to check it

Here is a test you can run against any error you write.

Cover up the message. Could you rebuild that sentence from `code` and `details` alone?

If you can, the error is fine. If you cannot, then some fact exists only in the message text, and any client that needs it will have to parse it out.

> **Note**
>
> This also makes translation possible.
>
> Once the facts are in `details`, a client can build its own sentence, in its own language, with its own formatting for dates and numbers.
>
> A regex written against an English sentence cannot be translated, so a client that parses your messages is tied to the language you wrote them in.
>
> This is the practical reason the three readers are worth separating. `message` never needs translating, because only developers read it. `details` always does, because it is what the end user's sentence gets built from.

## Step 11. Type the details

### Describe the payload

Right now `details` is an open object in the schema, which tells a reader nothing about what is in it. So describe it with a model.

`errors.py`

```python
class TooManyTodosDetails(BaseModel):
    limit: int
```

Add a `details_schema` class variable, defaulting to `None`, and have `openapi_model` use it when it is set. Then set `details_schema = TooManyTodosDetails` on `TooManyTodosError`.

`errors.py`

```python
class BaseHTTPError(Exception):
    status_code: ClassVar[int]
    code: ClassVar[ErrorCode]
    message: ClassVar[str] = ""
    description: ClassVar[str] = ""
    details_schema: ClassVar[type[BaseModel] | None] = None
    ...

    @classmethod
    def openapi_model(cls) -> type[BaseModel]:
        return create_model(
            f"{cls.__name__}Schema",
            code=(Literal[cls.code], ...),
            message=(str, ...),
            details=(cls.details_schema or dict[str, Any], ...),
        )
```

### Describe the fields too

That model works, and in the schema it comes out like this:

`openapi.json`

```json
{
  "limit": {
    "type": "integer",
    "title": "Limit"
  }
}
```

That is accurate but thin. A reader learns there is an integer called `limit`, but not what it limits, and the docs page shows `0` as its example.

So use `Field` and say what it means.

`errors.py`

```python
class TooManyTodosDetails(BaseModel):
    limit: int = Field(description="The most todos you can have.", examples=[3])
```

And now the schema carries both:

`openapi.json`

```json
{
  "limit": {
    "type": "integer",
    "title": "Limit",
    "description": "The most todos you can have.",
    "examples": [3]
  }
}
```

This helps in three places.

Swagger UI renders a filled in example instead of an empty shape, so somebody reading your docs sees `3` rather than `0`.

A generated client turns the description into a docstring or a comment on the property, so it reaches the person using it in their editor.

And anyone writing tests against your API has a real value to copy.

> **Tip**
>
> Do this on your request and response models too, not only on errors.
>
> A field declared as `name: str` shows up in the docs as `"string"`, which tells the reader nothing about what belongs in it. The same field with `Field(description="...", examples=["Alex"])` shows up as `"Alex"`.
>
> It costs one line per field, and it is the difference between a schema that is technically complete and one somebody can use without asking you questions.

> **Technical details**
>
> Pydantic writes `examples`, a list, which is the JSON Schema keyword. Current FastAPI emits OpenAPI 3.1, which uses JSON Schema as it is.
>
> The singular `example` you may have seen is the older OpenAPI 3.0 keyword. OpenAPI 3.1 still accepts it, but only as deprecated, so use `examples` in anything you write by hand.

### Stop yourself passing the wrong one

The error needs the facts handed to it when it is raised, so `__init__` takes them, as a model. And now that the schema makes a promise, something has to keep it. Passing the wrong model at a raise site is easy, and nothing would notice.

`errors.py`

```python
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
```

This way the mismatch is caught in your own test run, instead of being sent to a client that trusted the schema.

Raise the error with its facts:

```python
raise TooManyTodosError(TooManyTodosDetails(limit=MAX_TODOS))
```

```json
{
  "code": "too_many_todos",
  "message": "Todo limit reached",
  "details": {
    "limit": 3
  }
}
```

The limit is in `details` now, as a field. The message still says "Todo limit reached", and the next step puts the number back into it.

The code so far: [steps/step11](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step11)

## Step 12. Build the message from the details

### The message is a template

Step 10 asked you to keep the message and the details saying the same thing. That is a rule you have to remember every time you add an error.

You can remove the need to remember it. Make the message a format template and fill it from the details.

`errors.py`

```python
class BaseHTTPError(Exception):
    status_code: ClassVar[int]
    code: ClassVar[ErrorCode]
    message_template: ClassVar[str] = ""
    description: ClassVar[str] = ""
    details_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, details: BaseModel | None = None) -> None:
        ...
        self.details: dict[str, Any] = (
            details.model_dump(mode="json") if details else {}
        )
        self.message = self.message_template.format(**self.details)
        super().__init__(self.message)
```

The template lives on the class. The finished message lives on the instance.

`errors.py`

```python
class TooManyTodosError(BadRequestError):
    code = ErrorCode.too_many_todos
    message_template = "You can have at most {limit} todos"
    description = "Delete a todo before adding another."
    details_schema = TooManyTodosDetails
```

Every other error renames its `message` to `message_template` too.

Raise it with the details, exactly as in step 11, and the sentence writes itself:

```json
{
  "code": "too_many_todos",
  "message": "You can have at most 3 todos",
  "details": {
    "limit": 3
  }
}
```

Step 10's rule is no longer something you have to remember. The message cannot mention a number that isn't in `details`, because that is the only place it can get one.

Errors with nothing to say still work. `"Todo not found".format()` is just `"Todo not found"`.

### Now put the real message in the schema

Your details fields already carry examples from step 11. So you can render the example message from those examples, and put the result in the schema.

`errors.py`

```python
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
    def openapi_model(cls) -> type[BaseModel]:
        return create_model(
            f"{cls.__name__}Schema",
            code=(Literal[cls.code], ...),
            message=(str, Field(examples=[cls.example_message()])),
            details=(cls.details_schema or dict[str, Any], ...),
        )
```

Your schema used to describe the message like this:

`openapi.json`

```json
{
  "type": "string",
  "title": "Message"
}
```

And now it describes it like this:

`openapi.json`

```json
{
  "type": "string",
  "title": "Message",
  "examples": ["You can have at most 3 todos"]
}
```

Somebody reading your docs can now see what this error looks like without calling your API to find out.

> **Tip**
>
> This has a useful side effect.
>
> `openapi_model()` runs while your routes are being declared, which is at import time. So if you add a `{placeholder}` to a template and forget to give that field an example, you get `KeyError: 'limit'` and the app does not start.
>
> So a template with a missing example cannot reach production. It fails on your machine, the first time you start the app.

> **Technical details**
>
> Two edges of `str.format` to know about.
>
> A placeholder with no matching key raises `KeyError` when the error is raised. That is the right failure, and it will show up the first time that error fires.
>
> And a literal brace in a message has to be doubled. `"use {} for an empty object"` raises `IndexError`. Write `{{}}` instead.

### Show every error in Swagger UI too

Swagger UI doesn't build examples from a union, so step 9 left it showing one example for the 400. But it does show named examples, which OpenAPI lets a response carry, and now each error can build its own:

`errors.py`

```python
    @classmethod
    def example(cls) -> dict[str, Any]:
        return {
            "code": cls.code,
            "message": cls.example_message(),
            "details": cls.example_details(),
        }
```

Then `document_errors` gives every status that has several errors one example per error:

`errors.py`

```python
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
```

FastAPI puts those examples next to the schema it builds from `model`, and Swagger UI gets its dropdown:

![The 400 of POST /todos in Swagger UI, with an Examples dropdown set to too_many_todos](https://raw.githubusercontent.com/nimaxin/fastapi-error-responses/master/article/images/swagger-400.png)

ReDoc lists the same named examples in its own dropdown.

The code so far: [steps/step12](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step12)

## Step 13. The 500 that nobody documents

### Every route can return one

You wrote a handler for bare `Exception` in step 5. So every route in your app can return a 500 carrying `internal_server_error`.

Go and look at your schema. Not one route says so.

This is easy to miss because it feels like infrastructure rather than an error you designed. From outside there is no difference. It is a response your API sends, with a code a client may want to handle, and it isn't written down.

### Put it in the helper

You already made `InternalServerError` a real class in step 5, so it documents itself like anything else.

Don't ask people to remember it on every route. Append it inside `document_errors`.

`errors.py`

```python
def document_errors(*errors: type[BaseHTTPError]) -> dict[int | str, dict[str, Any]]:
    grouped: dict[int, list[type[BaseHTTPError]]] = {}
    for error in (*errors, InternalServerError):
        grouped.setdefault(error.status_code, []).append(error)
    ...
```

Now every route that documents anything documents this too.

### Be careful what it promises

Give it a description like any other error.

`errors.py`

```python
class InternalServerError(BaseHTTPError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = ErrorCode.internal_server_error
    message_template = "An unexpected error occurred"
    description = (
        "Something failed on our side. If the request changes data, "
        "check whether the change went through before you retry."
    )
```

It is tempting to write "safe to retry" there. For `GET /todos/{todo_id}` it would be true. For `POST /todos` it is not, because the crash can come after the todo was saved. If you want retries to be safe, accept an idempotency key, the way Stripe does.

`openapi.json`

```json
{
  "description": "Something failed on our side. If the request changes data, check whether the change went through before you retry.",
  "content": {
    "application/json": {
      "schema": {
        "$ref": "#/components/schemas/InternalServerErrorSchema"
      }
    }
  }
}
```

The code so far: [steps/step13](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step13)

## Step 14. The 422 that still has its own shape

### FastAPI adds it for you

Any route that takes input gets a 422 automatically, pointing at `HTTPValidationError`. That means a body, or any path, query, header or cookie parameter.

That is the wrong shape, as you saw in step 6.

### Declare your own instead

FastAPI only adds its 422 to a route that hasn't declared one. So declare yours, in the helper, the same way as the 500.

`errors.py`

```python
    for error in (*errors, ValidationError, InternalServerError):
```

Now the 422 on every route points at your schema:

`openapi.json`

```json
{
  "description": "The request is invalid. details lists each problem.",
  "content": {
    "application/json": {
      "schema": {
        "$ref": "#/components/schemas/ValidationErrorSchema"
      }
    }
  }
}
```

And because every route declares its own 422, FastAPI no longer adds its `HTTPValidationError` and `ValidationError` schemas to the document at all. Your schema stops shipping two competing descriptions of what an error looks like, which is the thing this whole article set out to remove.

> **Note**
>
> A route that takes no input at all can't fail validation, so for that route the helper documents a 422 that never comes. FastAPI wouldn't have added one there. Most routes take at least an id, so this rarely matters.

### Type its details too

Your validation handler builds a list of objects with the same four fields every time. Say so, rather than leaving `details` as an open object.

`errors.py`

```python
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
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = ErrorCode.validation_error
    message_template = "Invalid request data"
    description = "The request is invalid. details lists each problem."
    details_schema = ValidationDetails
```

And the handler builds those models, so the check from step 11 covers it too:

`main.py`

```python
async def validation_error_handler(
    request: Request, e: RequestValidationError
) -> JSONResponse:
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
```

The schema now describes every entry. `location` comes out as an enum of the five parts of a request, which a generated client turns into a type of its own:

`openapi.json`

```json
{
  "type": "string",
  "enum": ["body", "query", "path", "header", "cookie"],
  "title": "Location",
  "description": "The part of the request with the bad value."
}
```

> **Tip**
>
> Use a real example here, not a placeholder.
>
> `[{"field": "name", "message": "problem"}]` looks like it explains the shape, but it is the same mistake as a field showing up in the docs as `"string"`. It describes the type where an example should show an instance.

The code so far: [steps/step14](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step14)

## Step 15. The test that keeps it true

### Nothing above is enforced

None of this is checked by FastAPI or by pydantic.

Add a `raise SomethingError` to a route, forget to add it to that route's `document_errors` call, and nothing happens. No warning. No failing test. The route works perfectly.

The schema just silently stops being true.

Your own tests will not catch it either, because the route still behaves correctly. The problem only shows up when somebody generates a client from your schema and finds it has no branch for an error your API returns.

### Check every error your tests see

You can't tell from the code alone which errors a route raises. They come from the route, from its dependencies, and from whatever those call. But your tests make the API send them. So check each error a test receives against the route that sent it.

`test_main.py`

```python
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
```

`SCHEMA` is `app.openapi()`, read once at the top of the file. `check_documented` runs on every response the client receives, so a test doesn't have to call it. And it skips a response no route sent, such as a 404 for a path that doesn't exist, because there is no route to document it on.

`route_path` finds the route in the schema, not in `app.routes`. Since FastAPI 0.137, `app.routes` is a tree, and a route inside an included router isn't in that list itself.

The test client runs on `httpx2`, the successor of `httpx` by the same author, so install it next to pytest with `uv add --dev pytest httpx2`. FastAPI's testing page still says `httpx`, which works too, but current Starlette warns that it is deprecated.

Then write the tests you would write anyway, one for each error:

`test_main.py`

```python
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
```

Now take `DuplicateTitleError` out of the list on `POST /todos`, and run them:

```text
FAILED test_main.py::test_duplicate_title - AssertionError: POST /todos sent a 400 duplicate_title, which its responses= does not list
1 failed, 6 passed
```

The test for `duplicate_title` still gets its 400, and fails anyway, naming the route and the error its schema is missing.

### Check the schema as a whole

Two more tests look at the finished schema. Every route has to document a 500. And FastAPI's `HTTPValidationError` must be gone, which means no route fell back to FastAPI's own 422.

`test_main.py`

```python
def test_every_route_documents_a_500() -> None:
    for path, operations in SCHEMA["paths"].items():
        for method, operation in operations.items():
            assert "500" in operation["responses"], f"{method.upper()} {path}"


def test_no_route_falls_back_to_fastapis_422() -> None:
    assert "HTTPValidationError" not in SCHEMA["components"]["schemas"]
```

The finished code: [steps/step15](https://github.com/nimaxin/fastapi-error-responses/tree/master/steps/step15)

## What you have now

One format, from every route, with a stable machine-readable code.

A schema where each route lists the errors it can actually return, each pinned to one `code`, each with a sentence saying what to do about it, and each showing the message and the data it really carries.

And a test that tells you when that stops being true.

- One format: `code`, `message`, `details`
- Base error inherits `Exception`, never `HTTPException`
- One class per error, message and description on the class
- Four handlers, and `debug` off in production
- `code` pinned per error as a `Literal`, reaching the schema as `const`
- Every route lists every error it can return
- 422 and 500 documented like any other error
- No fact lives only inside `message`
- Messages written for a developer reading a log, never for an end user
- Errors sharing a status carry a `discriminator` on `code`, and an example each
- `details` typed, with a description and an example on every field
- The message built from the details, so the two cannot disagree
- A test that fails when routes and docs disagree

---

A follow-up post takes this schema and generates clients from it: Orval for TypeScript, `openapi-python-client` for httpx in Python, the exhaustive switch on `err.code` that the `const` in step 8 makes possible, and the places where generators still trip over a perfectly good schema.

The code for every step is at [nimaxin/fastapi-error-responses](https://github.com/nimaxin/fastapi-error-responses), and every response and schema excerpt shown as output here was copied from running it.
