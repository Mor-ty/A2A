# `agentic_os_infra.file_utils`

File fetching, storing, and local analysis utilities for AgenticOS agents.

---

## Contents

| Module | Purpose |
|---|---|
| `FileHandler` | Async HTTP fetch / upload, base64 conversion, A2A FilePart helpers |
| `FileAnalyzer` | Analyze 20+ file types locally (no network) |
| `ArchiveHandler` | ZIP, TAR, TAR.GZ |
| `ImageHandler` | PNG, JPG, GIF, WEBP (requires Pillow) |
| `CodeHandler` | Python, JS, TS, Java, Go, C/C++, Rust, and more |
| `DataHandler` | CSV, Excel, JSON, YAML |
| `XMLHandler` | XML, HTML, SVG, XHTML |
| `TextHandler` | TXT, Markdown, PDF, DOCX |
| `BaseHandler` | Abstract base for custom handlers |

---

## Installation

The package ships with `httpx`, `tenacity`, and `aiofiles` as core dependencies.

For full file-type support install the optional extras:

```bash
pip install "agentic_os_infra[file-utils]"
```

This adds: `Pillow` (images), `pandas` + `openpyxl` (CSV/Excel), `python-docx` (DOCX), `pypdf` (PDF).

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `FILE_SERVER_URL` | `https://agenticservices-uat:443` | Base URL used to **fetch** files |
| `UPLOAD_FILE_URL` | `https://illin4671:5995` | Base URL used to **upload** files |

Set them in your `.env` file or shell before running your agent.

---

## Import

```python
# Most common — FileHandler + FileAnalyzer
from agentic_os_infra.file_utils import FileHandler, FileAnalyzer

# Specific handlers (direct use)
from agentic_os_infra.file_utils import (
    ArchiveHandler,
    XMLHandler,
    ImageHandler,
    CodeHandler,
    DataHandler,
    TextHandler,
    BaseHandler,
)

# Exceptions
from agentic_os_infra.file_utils import FileHandlerError, FetchError, StoreError, ValidationError
```

---

## `FileHandler` — fetch & store files over HTTP

`FileHandler` is an async context manager. Always use it with `async with` to ensure the HTTP client is closed properly.

### Fetch a file

```python
import asyncio
from agentic_os_infra.file_utils import FileHandler

async def main():
    async with FileHandler() as handler:
        file_bytes = await handler.fetch_file(
            "https://myserver/uploads/report.pdf",
            file_name="report.pdf"   # optional, used in logs
        )
    print(f"Downloaded {len(file_bytes)} bytes")

asyncio.run(main())
```

### Store a file

```python
async with FileHandler() as handler:
    result = await handler.store_file(
        file_bytes=b"Hello, world!",
        file_name="hello.txt",
        mime_type="text/plain"
    )
# result = {"name": "hello.txt", "mime_type": "text/plain", "uri": "https://..."}
print(result["uri"])
```

### URI ↔ base64 conversion

```python
async with FileHandler() as handler:
    # URI → base64
    b64 = await handler.convert_uri_to_base64("https://myserver/uploads/photo.png")

    # base64 → URI (uploads and returns the new URI)
    uri = await handler.convert_base64_to_uri(b64, "photo_copy.png", "image/png")
```

### A2A FilePart helpers

```python
async with FileHandler() as handler:
    # Fetch from URI → create A2A FilePart dict (for passing to LLM / agent)
    file_part = await handler.create_file_part_from_uri(
        file_uri="https://myserver/uploads/diagram.png",
        file_name="diagram.png",
        mime_type="image/png"
    )
    # file_part = {"kind": "file", "name": "diagram.png", "mime_type": "image/png", "bytes": "<base64>"}

    # A2A FilePart → upload to server → get URI
    stored = await handler.process_file_part_to_uri(file_part)
    print(stored["uri"])
```

### Batch resolve file-refs in an `inputs` dict (orchestrator pattern)

When an orchestrator receives an `inputs` dict where some values are file-reference dicts
(`{"name": ..., "mime_type": ..., "uri": ...}`), use `convert_inputs_file_refs_to_bytes`
to resolve them all in one call. The `uri` key is replaced by `bytes` (base64); all other
keys are preserved unchanged.

```python
inputs = {
    "query": "Summarize the attached document",
    "document": {
        "name": "report.pdf",
        "mime_type": "application/pdf",
        "uri": "https://myserver/uploads/report.pdf"
    },
    "attachments": [
        {"name": "chart.png", "mime_type": "image/png", "uri": "https://myserver/uploads/chart.png"},
        {"name": "notes.txt", "mime_type": "text/plain", "uri": "https://myserver/uploads/notes.txt"},
    ]
}

async with FileHandler() as handler:
    resolved = await handler.convert_inputs_file_refs_to_bytes(inputs, element_id="step-1")

# resolved["document"] = {"name": "report.pdf", "mime_type": "application/pdf", "bytes": "<base64>"}
# resolved["attachments"][0] = {"name": "chart.png", ..., "bytes": "<base64>"}
# resolved["query"] is unchanged
```

### Verbose mode

Pass `verbose=True` to print detailed step-by-step output — useful during development:

```python
async with FileHandler(verbose=True) as handler:
    file_bytes = await handler.fetch_file(uri)
```

### Custom server URLs

```python
handler = FileHandler(
    file_server_url="https://my-fetch-server:443",
    upload_file_url="https://my-upload-server:5995"
)
```

### Error handling

```python
from agentic_os_infra.file_utils import FetchError, StoreError, ValidationError

async with FileHandler() as handler:
    try:
        data = await handler.fetch_file("https://myserver/uploads/missing.txt")
    except ValidationError as e:
        print(f"Bad URI: {e}")
    except FetchError as e:
        print(f"Fetch failed: {e}")
```

---

## `FileAnalyzer` — analyze files locally (no network)

`FileAnalyzer` routes a file to the correct handler based on its name and MIME type,
and returns a human-readable `summary` and structured `metadata`.

### Basic usage

```python
from agentic_os_infra.file_utils import FileAnalyzer

analyzer = FileAnalyzer(max_preview_lines=5)

with open("data.csv", "rb") as f:
    file_bytes = f.read()

result = analyzer.analyze_file(file_bytes, "data.csv", mime_type="text/csv")
print(result["summary"])    # human-readable description
print(result["metadata"])   # structured dict
```

### Combined with FileHandler

```python
import asyncio
from agentic_os_infra.file_utils import FileHandler, FileAnalyzer

async def analyze_remote_file(uri: str, file_name: str):
    async with FileHandler() as handler:
        file_bytes = await handler.fetch_file(uri, file_name)

    analyzer = FileAnalyzer()
    result = analyzer.analyze_file(file_bytes, file_name)
    return result

result = asyncio.run(analyze_remote_file(
    "https://myserver/uploads/report.xlsx", "report.xlsx"
))
print(result["summary"])
```

---

## Handler chain (detection order)

`FileAnalyzer` tries handlers in this order — first match wins:

```
ArchiveHandler  →  .zip  .tar  .gz  .tgz
ImageHandler    →  .png  .jpg  .jpeg  .gif  .webp  .bmp
CodeHandler     →  .py  .js  .ts  .java  .go  .cpp  .rs  .sh  ...
DataHandler     →  .csv  .xlsx  .xls  .json  .yaml  .yml
XMLHandler      →  .xml  .html  .htm  .svg  .xhtml
TextHandler     →  .txt  .md  .pdf  .docx  (and any text/* MIME)
```

---

## `XMLHandler` — direct usage

```python
from agentic_os_infra.file_utils import XMLHandler

handler = XMLHandler()

# -- XML file --
xml_bytes = b"""<?xml version="1.0"?>
<catalog>
  <book id="1"><title>Python Cookbook</title><author>Beazley</author></book>
  <book id="2"><title>Fluent Python</title><author>Ramalho</author></book>
</catalog>"""

result = handler.analyze(xml_bytes, "catalog.xml")
print(result["summary"])
# 📋 catalog.xml
# Root element: <catalog>
# Child nodes: 2
# Attributes: 0
#
# 🔖 Structure:
#   <catalog>
#     <book> (2 children)
#     <book> (2 children)

print(result["metadata"])
# {'root_tag': 'catalog', 'child_count': 2, 'attribute_count': 0}

# -- HTML file (same handler) --
html_bytes = b"<html><head><title>Home</title></head><body><p>Hello</p></body></html>"
result = handler.analyze(html_bytes, "index.html")
print(result["metadata"]["root_tag"])   # "html"

# -- Invalid XML (graceful fallback to text preview) --
bad_bytes = b"<unclosed><tag>some content"
result = handler.analyze(bad_bytes, "broken.xml")
print(result["summary"])   # shows line count + raw preview
print(result["metadata"]["parsed"])  # False
```

---

## `ArchiveHandler` — direct usage

```python
import zipfile, io
from agentic_os_infra.file_utils import ArchiveHandler

handler = ArchiveHandler()

# -- Build an in-memory ZIP for the example --
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("src/main.py", "print('hello')")
    zf.writestr("src/utils.py", "def helper(): pass")
    zf.writestr("tests/test_main.py", "import pytest")
    zf.writestr("README.md", "# My Project")
zip_bytes = buf.getvalue()

# -- Analyze --
result = handler.analyze(zip_bytes, "my_project.zip")
print(result["summary"])
# 📦 my_project.zip
# Total files: 4
# Size: 312.0 B
#
# 📂 Structure:
#    src/ (2 files)
#    tests/ (1 files)
#    ...

print(result["metadata"])
# {
#   'total_files': 4,
#   'total_size': 312,
#   'directories': ['src/', 'tests/']
# }

# -- TAR.GZ file (same handler, auto-detected by extension) --
import tarfile
tar_buf = io.BytesIO()
with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
    info = tarfile.TarInfo(name="config/settings.yaml")
    content = b"debug: true\nport: 8080\n"
    info.size = len(content)
    tf.addfile(info, io.BytesIO(content))
tar_bytes = tar_buf.getvalue()

result = handler.analyze(tar_bytes, "release.tar.gz")
print(result["metadata"]["total_files"])   # 1
print(result["metadata"]["directories"])   # ['config/']
```

---

## `DataHandler` — direct usage

Handles CSV, Excel (`.xlsx` / `.xls`), JSON, and YAML files.
Requires `pandas` + `openpyxl` for CSV/Excel (included in the `file-utils` extras).

```python
import json, io
from agentic_os_infra.file_utils import DataHandler

handler = DataHandler()

# -- CSV --
csv_bytes = b"name,age,city\nAlice,30,NY\nBob,25,LA\nCarol,35,Chicago\n"
result = handler.analyze(csv_bytes, "users.csv")
print(result["summary"])
# 📊 users.csv
# Columns (3): name, age, city
# Rows: 3

print(result["metadata"])
# {'rows': 3, 'columns': 3, 'column_names': ['name', 'age', 'city']}

# Access specific metadata fields
print(result["metadata"]["column_names"])   # ['name', 'age', 'city']
print(result["metadata"]["rows"])           # 3

# -- JSON (dict) --
json_bytes = json.dumps({
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 1024,
    "stop": None
}).encode()

result = handler.analyze(json_bytes, "config.json")
print(result["summary"])
# 📋 config.json (JSON)
# Type: Object/Dict
# Keys (4): model, temperature, max_tokens, stop

print(result["metadata"])
# {'type': 'dict', 'size': 4}

# -- JSON (list) --
list_bytes = json.dumps([{"id": 1}, {"id": 2}, {"id": 3}]).encode()
result = handler.analyze(list_bytes, "items.json")
print(result["summary"])
# 📋 items.json (JSON)
# Type: Array/List
# Items: 3

# -- YAML --
yaml_bytes = b"""
agent:
  name: my-agent
  version: 1.0
  capabilities:
    - file_analysis
    - code_review
"""
result = handler.analyze(yaml_bytes, "agent_config.yaml")
print(result["summary"])
# 📋 agent_config.yaml (YAML)
# Type: Object/Dict
# Keys (1): agent

print(result["metadata"])
# {'type': 'dict'}
```

---

## Extending with a custom handler

```python
from agentic_os_infra.file_utils import BaseHandler, FileAnalyzer
from typing import Dict

class YamlSchemaHandler(BaseHandler):
    def can_handle(self, file_name: str, mime_type: str) -> bool:
        return file_name.endswith(".schema.yaml")

    def analyze(self, file_bytes: bytes, file_name: str, max_preview_lines: int = 5) -> Dict:
        text = self.safe_decode(file_bytes)
        lines = text.splitlines()
        return {
            "summary": f"YAML Schema: {file_name}\nLines: {len(lines)}",
            "metadata": {"lines": len(lines)}
        }

# Inject before the default handlers
analyzer = FileAnalyzer()
analyzer.handlers.insert(0, YamlSchemaHandler())
```
