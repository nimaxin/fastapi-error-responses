"""Run every step and variant, and keep what each one answers for the article.

Writes article/out/<folder>.json with each response and the OpenAPI schema, and
article/out/pytest-<folder>.txt for the folders that have tests.

Usage: uv run python article/run_steps.py
"""

import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "article" / "out"
PROBE = ROOT / "article" / "probe.py"
FOLDERS = sorted((ROOT / "steps").iterdir()) + sorted(
    (ROOT / "article" / "variants").iterdir()
)


def run(command: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "COLUMNS": "200", "PYTHONIOENCODING": "utf-8"},
    )


OUT.mkdir(exist_ok=True)
for folder in FOLDERS:
    result = run([sys.executable, str(PROBE)], cwd=folder)
    if result.returncode:
        raise SystemExit(f"{folder.name} did not run:\n{result.stderr}")
    (OUT / f"{folder.name}.json").write_text(result.stdout, encoding="utf-8")

    if (folder / "test_main.py").exists():
        result = run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=no",
                "-rf",
                "-p",
                "no:cacheprovider",
                str(folder.relative_to(ROOT)),
            ],
            cwd=ROOT,
        )
        summary = re.sub(r" in [\d.]+s", "", result.stdout)
        (OUT / f"pytest-{folder.name}.txt").write_text(summary, encoding="utf-8")
    print(folder.name, "ok")
