"""Print, as JSON, how one step's app answers each request the article shows.

Run it from inside a step's folder, as run_steps.py does.
"""

import json
import logging
import pathlib
import sys
import warnings

sys.path.insert(0, str(pathlib.Path.cwd()))
warnings.simplefilter("ignore")
logging.disable(logging.CRITICAL)

from fastapi.testclient import TestClient

import main

REQUESTS = {
    # name: (method, path, JSON body or raw bytes), sent in this order
    "missing_todo": ("GET", "/todos/99", None),
    "bad_id": ("GET", "/todos/abc", None),
    "empty_title": ("POST", "/todos", {"title": ""}),
    "duplicate_title": ("POST", "/todos", {"title": "Buy milk"}),
    "created": ("POST", "/todos", {"title": "Water the plants"}),
    "too_many": ("POST", "/todos", {"title": "Read a book"}),
    "broken_json": ("POST", "/todos", b'{"title": '),
    "unknown_path": ("GET", "/nowhere", None),
    "wrong_method": ("DELETE", "/todos", None),
}

client = TestClient(main.app, raise_server_exceptions=False)
responses = {}
for name, (method, path, body) in REQUESTS.items():
    if isinstance(body, bytes):
        headers = {"content-type": "application/json"}
        response = client.request(method, path, headers=headers, content=body)
    else:
        response = client.request(method, path, json=body)
    try:
        content = response.json()
    except ValueError:
        content = response.text
    responses[name] = {
        "status": response.status_code,
        "reason": response.reason_phrase,
        "headers": dict(response.headers),
        "body": content,
    }

print(json.dumps({"responses": responses, "openapi": main.app.openapi()}))
