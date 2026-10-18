"""Build article/article.md from article/template.md.

Code blocks in the template say where their content comes from:

- ```python step03/errors.py
  Every line has to appear in that file, in the same order, apart from blank
  lines and lines that are only "...". It gets the file's name as a caption,
  unless the opening line ends in "nocaption".
- ```json out:step05:quantity_zero
  The body of that response, as run_steps.py captured it.
- ```http out:step03:no_key www-authenticate
  Its status line, the headers named, and the body.
- ```json schema:step07:components>schemas>ErrorCode
  That part of the step's OpenAPI schema.
- ```text pytest:step15-forgot
  The failures and the summary line of that folder's tests.

Links to image:<file>, code:<path> and repo: become GitHub URLs. Prettier then
formats the result, the same Prettier an editor runs on save.

Usage: uv run python article/build_article.py
"""

import json
import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTICLE = ROOT / "article"
OUT = ARTICLE / "out"
REPO = "https://github.com/nimaxin/fastapi-error-responses"
BRANCH = "master"
RAW = f"https://raw.githubusercontent.com/nimaxin/fastapi-error-responses/{BRANCH}"
PRETTIER = "prettier@3.7.4"

AVOIDED_WORDS = [
    "delve",
    "leverage",
    "robust",
    "seamless",
    "it's worth noting",
    "crucial",
    "utilize",
    "in conclusion",
]


def folder(name: str) -> pathlib.Path:
    for parent in (ROOT / "steps", ARTICLE / "variants"):
        if (parent / name).is_dir():
            return parent / name
    raise SystemExit(f"No step or variant called {name}")


def captured(name: str) -> dict:
    return json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))


def check_snippet(code: list[str], source: str) -> None:
    step, filename = source.split("/", 1)
    text = (folder(step) / filename).read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    position = 0
    for line in code:
        wanted = line.strip()
        if not wanted or wanted == "...":
            continue
        try:
            position = lines.index(wanted, position) + 1
        except ValueError:
            raise SystemExit(f"{source} has no line, in this order: {line!r}") from None


def response_body(step: str, name: str) -> str:
    return json.dumps(captured(step)["responses"][name]["body"], indent=2)


def http_response(step: str, name: str, headers: list[str]) -> str:
    response = captured(step)["responses"][name]
    lines = [f"HTTP/1.1 {response['status']} {response['reason']}"]
    lines += [f"{header}: {response['headers'][header]}" for header in headers]
    return "\n".join(lines) + "\n\n" + response_body(step, name)


def schema_part(step: str, path: str) -> str:
    node = captured(step)["openapi"]
    for key in path.split(">"):
        node = node[key]
    return json.dumps(node, indent=2)


def pytest_summary(step: str) -> str:
    text = (OUT / f"pytest-{step}.txt").read_text(encoding="utf-8")
    prefix = folder(step).relative_to(ROOT).as_posix() + "/"
    kept = [
        line.replace(prefix, "")
        for line in text.splitlines()
        if line.startswith("FAILED") or re.match(r"\d+ (passed|failed)", line)
    ]
    return "\n".join(kept)


def fill(source: str) -> str:
    """The content of a block whose source is captured output."""
    kind, step, *rest = source.split(":")
    if kind == "out":
        name, *headers = rest[0].split(" ")
        return (
            http_response(step, name, headers) if headers else response_body(step, name)
        )
    if kind == "schema":
        return schema_part(step, rest[0])
    if kind == "pytest":
        return pytest_summary(step)
    raise SystemExit(f"Unknown source {source!r}")


def build(template: str) -> tuple[str, list[str]]:
    """The article, and the first lines of the code blocks nothing checked."""
    output: list[str] = []
    unchecked: list[str] = []
    lines = iter(template.splitlines())
    for line in lines:
        opening = re.fullmatch(r"```(\w+) (.+)", line)
        if not opening and line.startswith("```") and line != "```":
            language = line[3:]
            code = []
            for code_line in lines:
                if code_line == "```":
                    break
                code.append(code_line)
            unchecked.append(f"{language}: {code[0] if code else ''}")
            output += [line, *code, "```"]
            continue
        if not opening:
            output.append(line)
            continue
        language, source = opening.groups()
        nocaption = source.endswith(" nocaption")
        source = source.removesuffix(" nocaption")
        code = []
        for code_line in lines:
            if code_line == "```":
                break
            code.append(code_line)
        if source.split(":")[0] in ("out", "schema", "pytest"):
            # Prettier leaves one blank line in an empty block.
            filled = any(line.strip() for line in code)
            assert not filled, f"{source}: the block is filled in, so leave it empty"
            if source.startswith("schema:"):
                output += ["`openapi.json`", ""]
            output += [f"```{language}", fill(source), "```"]
        else:
            check_snippet(code, source)
            if not nocaption:
                output += [f"`{source.split('/', 1)[1]}`", ""]
            output += [f"```{language}", *code, "```"]
    return "\n".join(output) + "\n", unchecked


def links(text: str) -> str:
    def image(match: re.Match[str]) -> str:
        path = ARTICLE / "images" / match[1]
        assert path.exists(), f"No image {path}"
        return f"]({RAW}/article/images/{match[1]})"

    def code(match: re.Match[str]) -> str:
        path = ROOT / match[1]
        assert path.exists(), f"No file or folder {path}"
        kind = "tree" if path.is_dir() else "blob"
        return f"]({REPO}/{kind}/{BRANCH}/{match[1]})"

    text = re.sub(r"\]\(image:([^)]+)\)", image, text)
    text = re.sub(r"\]\(code:([^)]+)\)", code, text)
    return text.replace("](repo:)", f"]({REPO})")


def prose(text: str) -> str:
    """The text outside code blocks, with inline code and links taken out."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", "", text)
    return re.sub(r"\]\([^)]*\)", "]", text)


def check(article: str) -> None:
    assert "a—b".count("—") == 1, "the dash check itself is broken"
    for dash in ("—", "–"):
        assert dash not in article, f"{dash!r} appears {article.count(dash)} times"
    words = prose(article)
    for number, line in enumerate(words.splitlines(), start=1):
        assert ";" not in line, f"semicolon in prose: {line.strip()!r}"
        for word in AVOIDED_WORDS:
            assert word not in line.lower(), f"{word!r} in: {line.strip()!r}"
        assert not re.search(r"not just [^.]*, but", line, flags=re.IGNORECASE), line
    for marker in ("](image:", "](code:", "](repo:", "nocaption"):
        assert marker not in article, f"{marker!r} was left in the article"
    for line in article.splitlines():
        assert not re.match(r"```\w+ ", line), f"a block source was left: {line}"
    steps = re.findall(r"^## Step (\d+)\. ", article, flags=re.MULTILINE)
    assert steps == [str(n) for n in range(1, 16)], f"step headings: {steps}"
    for mention in re.findall(r"\b[Ss]tep (\d+)", words):
        assert 1 <= int(mention) <= 15, f"step {mention} does not exist"
    # The prose counts these, so the build checks them.
    codes = captured("step07")["openapi"]["components"]["schemas"]["ErrorCode"]["enum"]
    assert len(codes) == 6, "step 7 says six codes"


template = (ARTICLE / "template.md").read_text(encoding="utf-8")
article, unchecked = build(template)
article = links(article)
output = ARTICLE / "article.md"
output.write_text(article, encoding="utf-8", newline="\n")
npx = shutil.which("npx") or "npx"
subprocess.run([npx, "--yes", PRETTIER, "--write", str(output)], check=True)
article = output.read_text(encoding="utf-8")
check(article)
print(f"wrote article/article.md, {len(prose(article).split())} words of prose")
print("blocks nothing checks:")
for first_line in unchecked:
    print("  ", first_line)
