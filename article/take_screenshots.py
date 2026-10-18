"""Screenshot the docs pages the article shows, from the steps' running apps.

Usage: uv run --no-project --with playwright python article/take_screenshots.py
It drives the installed Chrome. The pages load ReDoc and Swagger UI from a CDN.
"""

import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Locator, Page, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "article" / "images"
VENV = (
    ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
)


@contextmanager
def serve(step: str, port: int) -> Iterator[str]:
    """Run one step's app under uvicorn, and give its base URL."""
    server = subprocess.Popen(
        [str(VENV), "-m", "uvicorn", "main:app", "--port", str(port)],
        cwd=ROOT / "steps" / step,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/openapi.json", timeout=1)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        yield base
    finally:
        server.terminate()
        server.wait(timeout=10)


def redoc_operation(page: Page, base: str, operation: str) -> Locator:
    """The ReDoc section of one operation, scrolled into view and drawn."""
    page.goto(base + "/redoc")
    section = page.locator(f"[data-section-id*='{operation}']").first
    section.wait_for(timeout=60_000)
    section.scroll_into_view_if_needed()
    time.sleep(1.5)
    return section


def down_to(page: Page, section: Locator, last: Locator, path: pathlib.Path) -> None:
    """Screenshot the section only down to the last element worth showing."""
    top, bottom = section.bounding_box(), last.bounding_box()
    assert top and bottom
    height = bottom["y"] + bottom["height"] - top["y"] + 48
    page.screenshot(
        path=str(path),
        clip={"x": top["x"], "y": top["y"], "width": top["width"], "height": height},
    )


IMAGES.mkdir(exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    # Wide enough for ReDoc's samples panel to show a whole message.
    page = browser.new_page(
        viewport={"width": 1700, "height": 1100}, device_scale_factor=2
    )

    with serve("step00", 8941) as base:
        section = redoc_operation(page, base, "create_todo")
        section.screenshot(path=str(IMAGES / "before.png"))

    with serve("step05", 8942) as base:
        section = redoc_operation(page, base, "get_todo")
        last = section.get_by_text("Validation Error", exact=True).first
        down_to(page, section, last, IMAGES / "docs-step-6.png")

    with serve("step15", 8943) as base:
        section = redoc_operation(page, base, "create_todo")
        section.get_by_role("tab", name="400", exact=True).click()
        time.sleep(0.8)
        section.screenshot(path=str(IMAGES / "after.png"))

        page.goto(base + "/docs")
        page.locator("#operations-default-create_todo_todos_post").click()
        response = page.locator('tr.response[data-code="400"]')
        response.wait_for()
        time.sleep(0.8)
        response.screenshot(path=str(IMAGES / "swagger-400.png"))

    browser.close()

for path in sorted(IMAGES.iterdir()):
    print(path.name, path.stat().st_size // 1024, "KB")
