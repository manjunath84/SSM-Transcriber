# Drive Source URL Passthrough — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second source to SSM-Transcriber that takes a public Google Drive file URL (or `drive://FILE_ID`), passes it directly to AssemblyAI's `audio_url` ingestion (no OAuth, no download, no upload), and produces the same enriched Markdown output as Slice 1.

**Architecture:** `LocalSource` and the new `DriveSource` both return `PreparedMedia` per F2 (extended additively with `remote_url: str | None`). `resolve_source(uri)` dispatches by URI shape with reject-not-swallow semantics. Provider branches once on `media.remote_url`: if set, POST `/transcript` with `audio_url=...` (skip upload entirely); else existing upload flow. Polling, retry, formatter all reuse Slice 1 plumbing.

**Tech Stack:** Python 3.12, typer (CLI), requests + tenacity (existing AssemblyAI provider), pytest with `responses` library for HTTP mocking, ruff + mypy. Zero new runtime dependencies.

**Pre-flight assumption:** the executor is on branch `impl/drive-source-passthrough` off post-PR-15 main. The spec triple (`requirements.md`, `plan.md`, `validation.md`) is on disk at `specs/2026-05-04-drive-source-passthrough/`. Run `git status` first to confirm a clean working tree.

---

## Task 1: Extend PreparedMedia with `remote_url` and validation

**Files:**
- Modify: `src/transcriber/sources/base.py`
- Test: `tests/unit/test_provider_types.py` (extend; the file's name is misleading — it's the home for frozen-dataclass `__post_init__` tests, including `Segment` and `TranscriptResult`. Add `PreparedMedia` validation tests at the bottom.)

- [ ] **Step 1: Write the failing tests** (in `tests/unit/test_provider_types.py`, append at the bottom)

```python
from pathlib import Path

from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedMedia


def _ws(tmp_path: Path) -> RunWorkspace:
    """Build a workspace whose root sits inside the test's tmp_path so the
    fixture cleanup leaves nothing behind."""
    import tempfile

    # tempfile.mkdtemp normally lands in /tmp. Redirecting via tempdir is
    # the simplest way to keep a workspace's root under tmp_path without
    # poking RunWorkspace internals.
    return RunWorkspace(prefix=str(tmp_path) + "/")


def test_prepared_media_rejects_both_local_path_and_remote_url(tmp_path: Path) -> None:
    """Exactly one source location may be set. Both set is a programming
    error in whichever source built the PreparedMedia."""
    with pytest.raises(ValueError, match="exactly one"):
        PreparedMedia(
            kind="local",
            original_uri="x",
            local_path=tmp_path / "x.wav",
            remote_url="https://example.com/x",
            title=None,
            duration_seconds=None,
            workspace=_ws(tmp_path),
            extra={},
        )


def test_prepared_media_rejects_neither_local_path_nor_remote_url(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        PreparedMedia(
            kind="local",
            original_uri="x",
            local_path=None,
            remote_url=None,
            title=None,
            duration_seconds=None,
            workspace=_ws(tmp_path),
            extra={},
        )


def test_prepared_media_accepts_local_path_only(tmp_path: Path) -> None:
    media = PreparedMedia(
        kind="local",
        original_uri="x",
        local_path=tmp_path / "x.wav",
        title=None,
        duration_seconds=None,
        workspace=_ws(tmp_path),
        extra={},
    )
    assert media.local_path == tmp_path / "x.wav"
    assert media.remote_url is None


def test_prepared_media_accepts_remote_url_only(tmp_path: Path) -> None:
    media = PreparedMedia(
        kind="google_drive",
        original_uri="drive://X",
        local_path=None,
        remote_url="https://drive.google.com/uc?export=download&id=X",
        title=None,
        duration_seconds=None,
        workspace=_ws(tmp_path),
        extra={"drive_file_id": "X"},
    )
    assert media.remote_url == "https://drive.google.com/uc?export=download&id=X"
    assert media.local_path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_provider_types.py -v`
Expected: 4 new tests fail with `TypeError` (`remote_url` is not a valid keyword), or `ValueError` not raised.

- [ ] **Step 3: Modify `src/transcriber/sources/base.py`** (replace the whole file)

```python
"""Source contract — every input source returns the same shape.

Per F2 in ``docs/PLAN.md``, ``PreparedMedia`` is the contract that Phase 1
(local), Phase 2 (YouTube), and Phase 4 (Google Drive) all return so the
pipeline downstream is source-agnostic.

Slice 2 (PR #15 spec) extended F2 additively: ``local_path`` is now
``Path | None`` and a new ``remote_url: str | None`` field lands.
Validation: exactly one of the two must be set. ``LocalSource`` keeps
populating ``local_path`` and leaves ``remote_url`` ``None``;
``DriveSource`` does the opposite. The provider branches once on
``media.remote_url`` — if set, AssemblyAI fetches the URL itself
(``audio_url`` ingestion, no upload); else the existing upload flow runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from transcriber.core.workspace import RunWorkspace


SourceKind = Literal["local", "youtube", "google_drive"]


@dataclass(frozen=True)
class PreparedMedia:
    """Everything downstream stages need to transcribe a piece of media.

    The ``workspace`` field owns cleanup — the caller that created the
    ``PreparedMedia`` owns the ``RunWorkspace`` and is responsible for
    cleanup on both success and failure (see F5 in ``docs/PLAN.md``).

    ``local_path`` and ``remote_url`` are mutually exclusive: exactly one
    must be set. ``LocalSource`` sets ``local_path``; ``DriveSource`` sets
    ``remote_url``.
    """

    kind: SourceKind
    original_uri: str
    local_path: Path | None
    title: str | None
    duration_seconds: float | None
    workspace: RunWorkspace
    extra: dict[str, str]
    remote_url: str | None = None

    def __post_init__(self) -> None:
        has_local = self.local_path is not None
        has_remote = self.remote_url is not None
        if has_local == has_remote:
            raise ValueError(
                "PreparedMedia requires exactly one of local_path or "
                "remote_url to be set; got "
                f"local_path={self.local_path!r}, remote_url={self.remote_url!r}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_provider_types.py -v`
Expected: all tests in the file pass (existing `Segment`/`TranscriptResult` tests + 4 new `PreparedMedia` tests).

- [ ] **Step 5: Run the full suite to verify nothing regressed**

Run: `env -u VIRTUAL_ENV uv run pytest -q`
Expected: 78 passed (74 existing + 4 new). If any existing test fails, the most likely cause is `LocalSource.prepare` or `tests/unit/test_cli.py` constructing `PreparedMedia` positionally; the new field is keyword-only so positional construction breaks. Switch the failing call to keyword form.

- [ ] **Step 6: Run lint + types**

Run: `env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/transcriber/sources/base.py tests/unit/test_provider_types.py
git commit -m "feat(sources): extend PreparedMedia with remote_url + validation

F2 contract change: local_path is now Path | None, new remote_url is
the URL-passthrough alternative. __post_init__ enforces exactly-one set.
Backward-compatible because remote_url defaults to None."
```

---

## Task 2: Drive URL parsing helper

**Files:**
- Create: `src/transcriber/sources/google_drive.py` (only the parser function in this task; class wrapper in Task 3)
- Create: `tests/unit/test_google_drive.py`

The five URL forms the parser must accept (from `requirements.md` §Reference calls):

```
drive://1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd
https://drive.google.com/file/d/1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd/view
https://drive.google.com/file/d/1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd/view?usp=sharing
https://drive.google.com/open?id=1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd
https://drive.google.com/uc?export=download&id=1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd
```

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_google_drive.py`)

```python
"""Tests for ``sources/google_drive.py`` — URL parsing + DriveSource.

URL parsing is a pure function over the five forms documented in
``specs/2026-05-04-drive-source-passthrough/requirements.md`` §"Reference
calls (verbatim)". The tests dogfood that section: each form pasted
verbatim from the spec.
"""

from __future__ import annotations

import pytest

from transcriber.sources.google_drive import _extract_file_id

_VALID_ID = "1Zdp9aYV9klOT5_3uAazbeV91eNUOe3Vd"


@pytest.mark.parametrize(
    "uri",
    [
        f"drive://{_VALID_ID}",
        f"https://drive.google.com/file/d/{_VALID_ID}/view",
        f"https://drive.google.com/file/d/{_VALID_ID}/view?usp=sharing",
        f"https://drive.google.com/open?id={_VALID_ID}",
        f"https://drive.google.com/uc?export=download&id={_VALID_ID}",
    ],
)
def test_extract_file_id_accepts_all_documented_forms(uri: str) -> None:
    assert _extract_file_id(uri) == _VALID_ID


def test_extract_file_id_rejects_empty_drive_uri() -> None:
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("drive://")


def test_extract_file_id_rejects_drive_uri_with_invalid_chars() -> None:
    """Drive file IDs are URL-safe base64 (alnum + - + _). Fail loud on
    anything else rather than passing garbage through to AssemblyAI."""
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("drive://has spaces")


def test_extract_file_id_rejects_file_d_with_empty_segment() -> None:
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("https://drive.google.com/file/d//view")


def test_extract_file_id_rejects_open_without_id_param() -> None:
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("https://drive.google.com/open")


def test_extract_file_id_rejects_drive_url_with_unrecognised_path() -> None:
    """https://drive.google.com/folders/X — folders aren't in the supported
    URL forms; reject loudly so a user pasting a folder doesn't silently
    land in the wrong code path."""
    with pytest.raises(ValueError, match="could not extract"):
        _extract_file_id("https://drive.google.com/folders/abc")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_google_drive.py -v`
Expected: `ImportError` — the module doesn't exist yet.

- [ ] **Step 3: Create `src/transcriber/sources/google_drive.py`**

```python
"""Google Drive source — URL passthrough only (Slice 2).

This module accepts five URL forms documented in
``specs/2026-05-04-drive-source-passthrough/requirements.md`` §"Reference
calls (verbatim)" and returns a ``PreparedMedia`` whose ``remote_url`` is
the canonical Drive download URL AssemblyAI fetches directly. **No OAuth,
no local download, no upload.**

OAuth + private-file support is a deferred Slice 3; see PLAN.md
§"Phase 4 — Slice 3: Drive Source (OAuth + Private Files)".
"""

from __future__ import annotations

import re

# Drive file IDs are URL-safe base64 — alnum, dash, underscore. The
# minimum length isn't documented but the shortest IDs we see in practice
# are 25+ characters; we don't enforce a minimum to stay forward-compatible.
_FILE_ID_RE = re.compile(r"[A-Za-z0-9_-]+$")

# `/file/d/<ID>/...` — extract the ID segment regardless of trailing path.
_FILE_D_RE = re.compile(r"/file/d/([A-Za-z0-9_-]+)(?:/|$)")

# `?id=<ID>` or `&id=<ID>` — extract the ID query parameter value.
_ID_QUERY_RE = re.compile(r"[?&]id=([A-Za-z0-9_-]+)")


def _extract_file_id(uri: str) -> str:
    """Extract the Drive file ID from any of the five accepted URL forms.

    Raises ``ValueError`` if the URI doesn't match any form or yields an
    empty / invalid file ID. Failure mode is loud-and-correct: a user who
    pastes a Drive folder URL or a malformed link gets a clear error
    rather than a silent fallthrough to AssemblyAI returning a 4xx.
    """
    if uri.startswith("drive://"):
        candidate = uri[len("drive://"):]
        if candidate and _FILE_ID_RE.match(candidate):
            return candidate
        raise ValueError(
            f"could not extract a Drive file ID from {uri!r}: "
            "drive:// URIs must contain a non-empty alphanumeric ID."
        )

    if uri.startswith(("https://drive.google.com/", "http://drive.google.com/")):
        # /file/d/<ID>/...
        if match := _FILE_D_RE.search(uri):
            return match.group(1)
        # /open?id=<ID>  or  /uc?...&id=<ID>
        if match := _ID_QUERY_RE.search(uri):
            return match.group(1)
        raise ValueError(
            f"could not extract a Drive file ID from {uri!r}: "
            "Drive URL must include /file/d/<ID> or ?id=<ID>."
        )

    raise ValueError(
        f"could not extract a Drive file ID from {uri!r}: "
        "expected drive://FILE_ID or https://drive.google.com/..."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_google_drive.py -v`
Expected: 9 tests pass (5 parametrised + 5 rejection cases).

- [ ] **Step 5: Run lint + types + full suite**

Run: `env -u VIRTUAL_ENV uv run pytest -q && env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: 87 passed (78 + 9), ruff clean, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/transcriber/sources/google_drive.py tests/unit/test_google_drive.py
git commit -m "feat(sources): _extract_file_id parser for the 5 accepted Drive URL forms

Pure function. Reject-loud on anything that doesn't match a documented
form (folder URLs, missing ID, etc.) so the user sees a clear error
rather than a silent fallthrough."
```

---

## Task 3: `DriveSource.prepare` returning `PreparedMedia`

**Files:**
- Modify: `src/transcriber/sources/google_drive.py` (add the class wrapper)
- Test: `tests/unit/test_google_drive.py` (extend)

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_google_drive.py`)

```python
from pathlib import Path

from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedMedia
from transcriber.sources.google_drive import DriveSource


def test_drive_source_prepare_returns_correct_prepared_media(tmp_path: Path) -> None:
    workspace = RunWorkspace(prefix=str(tmp_path) + "/")
    media = DriveSource.prepare(f"drive://{_VALID_ID}", workspace)

    assert isinstance(media, PreparedMedia)
    assert media.kind == "google_drive"
    assert media.original_uri == f"drive://{_VALID_ID}"
    assert media.local_path is None
    assert media.remote_url == (
        f"https://drive.google.com/uc?export=download&id={_VALID_ID}"
    )
    assert media.title is None  # CLI fills in from --title
    assert media.duration_seconds is None
    assert media.extra == {"drive_file_id": _VALID_ID}


def test_drive_source_prepare_canonicalises_full_drive_url(tmp_path: Path) -> None:
    """Whatever URL form the user passes, original_uri normalises to
    drive://FILE_ID and remote_url to the public-download canonical form."""
    workspace = RunWorkspace(prefix=str(tmp_path) + "/")
    media = DriveSource.prepare(
        f"https://drive.google.com/file/d/{_VALID_ID}/view?usp=sharing",
        workspace,
    )

    assert media.original_uri == f"drive://{_VALID_ID}"
    assert media.remote_url == (
        f"https://drive.google.com/uc?export=download&id={_VALID_ID}"
    )


def test_drive_source_prepare_raises_on_unparseable_uri(tmp_path: Path) -> None:
    """Defence-in-depth: DriveSource.prepare validates even though
    resolve_source already filters at dispatch (see Task 4). Tests call
    DriveSource directly without going through dispatch."""
    workspace = RunWorkspace(prefix=str(tmp_path) + "/")
    with pytest.raises(ValueError, match="could not extract"):
        DriveSource.prepare("drive://", workspace)


def test_drive_source_prepare_raises_on_non_drive_host(tmp_path: Path) -> None:
    workspace = RunWorkspace(prefix=str(tmp_path) + "/")
    with pytest.raises(ValueError, match="could not extract"):
        DriveSource.prepare("https://example.com/foo", workspace)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_google_drive.py::test_drive_source_prepare_returns_correct_prepared_media -v`
Expected: `ImportError` (`DriveSource` not yet defined).

- [ ] **Step 3: Add the class to `src/transcriber/sources/google_drive.py`** (append at the bottom)

```python
from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedMedia


class DriveSource:
    """Wrap a Drive URL into ``PreparedMedia`` for URL-passthrough mode.

    Defence-in-depth: ``prepare`` validates the URL itself even though
    ``resolve_source`` already rejects non-Drive ``://`` URIs at dispatch.
    Tests call ``DriveSource.prepare`` directly without the dispatcher,
    and a future programmatic caller may also bypass dispatch. Same
    boundary pattern as ``providers/assemblyai.py:_api_headers``
    re-checking the API key after the budget gate.
    """

    @staticmethod
    def prepare(uri: str, workspace: RunWorkspace) -> PreparedMedia:
        file_id = _extract_file_id(uri)
        remote_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        return PreparedMedia(
            kind="google_drive",
            original_uri=f"drive://{file_id}",
            local_path=None,
            remote_url=remote_url,
            title=None,
            duration_seconds=None,
            workspace=workspace,
            extra={"drive_file_id": file_id},
        )
```

(Add the new imports at the top of the file alongside the existing `import re`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_google_drive.py -v`
Expected: all tests in the file pass (5 parametrised + 5 rejection + 4 new DriveSource tests = 14).

- [ ] **Step 5: Full gates**

Run: `env -u VIRTUAL_ENV uv run pytest -q && env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: 91 passed, ruff clean, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/transcriber/sources/google_drive.py tests/unit/test_google_drive.py
git commit -m "feat(sources): DriveSource.prepare returns PreparedMedia for passthrough

Wraps _extract_file_id; canonicalises original_uri to drive://FILE_ID and
remote_url to the public-download form regardless of input URL shape.
local_path stays None — the AssemblyAI provider will branch on
remote_url and skip upload entirely (Task 5)."
```

---

## Task 4: Source dispatcher with reject-not-swallow semantics

**Files:**
- Create: `src/transcriber/sources/__init__.py` (or extend existing — check first; if it's empty/missing, create)
- Test: `tests/unit/test_source_dispatch.py` (new)

- [ ] **Step 1: Check existing `__init__.py`**

Run: `cat src/transcriber/sources/__init__.py 2>/dev/null || echo "MISSING"`
Expected: either empty (create from scratch) or contains existing exports (preserve them).

- [ ] **Step 2: Write the failing tests** (`tests/unit/test_source_dispatch.py`)

```python
"""Tests for ``sources/__init__.py``'s ``resolve_source`` dispatcher.

Reject-not-swallow contract: any URI containing ``://`` that doesn't
match a recognised pattern raises ``ValueError`` at dispatch (CLI exit
2). A user who typed ``://`` clearly meant a URL, not a file path —
silently routing to ``LocalSource`` would mislead them with a "file not
found" error.
"""

from __future__ import annotations

import pytest

from transcriber.sources import resolve_source
from transcriber.sources.google_drive import DriveSource
from transcriber.sources.local import LocalSource


def test_resolve_drive_uri() -> None:
    assert resolve_source("drive://1Zdp9aYV") is DriveSource


def test_resolve_full_drive_url() -> None:
    assert resolve_source(
        "https://drive.google.com/file/d/1Zdp9aYV/view"
    ) is DriveSource


def test_resolve_local_path_no_scheme() -> None:
    assert resolve_source("./video.mp4") is LocalSource


def test_resolve_local_path_absolute() -> None:
    assert resolve_source("/Users/foo/video.mp4") is LocalSource


def test_resolve_rejects_unknown_scheme_youtube() -> None:
    """YouTube lands in Phase 2; until then, reject-not-swallow."""
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("https://youtube.com/watch?v=abc")


def test_resolve_rejects_unknown_https_host() -> None:
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("https://example.com/foo")


def test_resolve_rejects_other_scheme() -> None:
    with pytest.raises(ValueError, match="URI scheme not supported"):
        resolve_source("s3://bucket/key")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_source_dispatch.py -v`
Expected: `ImportError` for `resolve_source`.

- [ ] **Step 4: Write `src/transcriber/sources/__init__.py`**

```python
"""Source dispatch — pattern-match on URI shape and return the source.

Reject-not-swallow design: any URI containing ``://`` that doesn't match
a recognised source pattern raises ``ValueError`` at dispatch. The CLI
catches and maps to exit 2. The alternative — silently routing
unrecognised ``://`` URIs to ``LocalSource`` — would mislead the user
with a "file not found" error when the real problem is "URL scheme
not supported."

Future sources (Phase 2 YouTube, Slice 3 OAuth-Drive) slot in as new
pattern arms above the catch-all ``ValueError``.
"""

from __future__ import annotations

from transcriber.sources.google_drive import DriveSource
from transcriber.sources.local import LocalSource


def resolve_source(uri: str) -> type[DriveSource] | type[LocalSource]:
    """Return the ``Source`` class that handles ``uri``.

    Raises ``ValueError`` if ``uri`` is URL-shaped but doesn't match any
    known source pattern.
    """
    if uri.startswith("drive://") or uri.startswith(
        ("https://drive.google.com/", "http://drive.google.com/")
    ):
        return DriveSource
    if "://" in uri:
        raise ValueError(
            f"URI scheme not supported: {uri!r}. "
            "Expected: a local file path, drive://FILE_ID, "
            "or a Google Drive URL (https://drive.google.com/...)."
        )
    return LocalSource


__all__ = ["resolve_source"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_source_dispatch.py -v`
Expected: 7 tests pass.

- [ ] **Step 6: Full gates**

Run: `env -u VIRTUAL_ENV uv run pytest -q && env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: 98 passed, ruff clean, mypy clean.

- [ ] **Step 7: Commit**

```bash
git add src/transcriber/sources/__init__.py tests/unit/test_source_dispatch.py
git commit -m "feat(sources): resolve_source dispatcher with reject-not-swallow

drive://, https?://drive.google.com/* → DriveSource; no scheme →
LocalSource; any other URI containing :// → ValueError. The CLI maps
ValueError to exit 2 with the documented 'URI scheme not supported'
message. Future YouTubeSource / OAuth-DriveSource slot in as new pattern
arms above the catch-all."
```

---

## Task 5: Provider `audio_url` passthrough branch

**Files:**
- Modify: `src/transcriber/providers/base.py` (change `transcribe()` signature)
- Modify: `src/transcriber/providers/assemblyai.py` (branch on `media.remote_url`)
- Test: `tests/unit/test_assemblyai_provider.py` (extend)

The existing `transcribe()` takes `(self, wav_path, *, language, diarize, speech_model, on_job_id)`. We change it to take `(self, media, *, language, diarize, speech_model, on_job_id)` — the implementer constructs the `PreparedMedia` upstream anyway, so passing it whole is the cleanest seam. All existing callers (CLI + tests) update to pass `media` instead of `wav_path`.

- [ ] **Step 1: Write the failing tests** (extend `tests/unit/test_assemblyai_provider.py`)

```python
def test_transcribe_passthrough_uses_audio_url_and_skips_upload(
    rsps: responses.RequestsMock, tmp_path: Path
) -> None:
    """Passthrough path: media.remote_url set → POST /transcript with
    audio_url=..., NO call to /upload. Body shape asserted via
    json_params_matcher per CLAUDE.md guardrail."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.base import PreparedMedia

    workspace = RunWorkspace(prefix=str(tmp_path) + "/")
    media = PreparedMedia(
        kind="google_drive",
        original_uri="drive://X",
        local_path=None,
        remote_url="https://drive.google.com/uc?export=download&id=X",
        title=None,
        duration_seconds=None,
        workspace=workspace,
        extra={"drive_file_id": "X"},
    )

    # Register /upload mock that MUST NOT be called.
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "should-not-fire"}, status=200)

    rsps.post(
        f"{API_BASE}/transcript",
        match=[
            matchers.json_params_matcher(
                {
                    "audio_url": "https://drive.google.com/uc?export=download&id=X",
                    "speech_models": ["universal-3-pro"],
                    "speaker_labels": True,
                }
            )
        ],
        json={"id": "drive-job", "status": "queued"},
        status=200,
    )
    rsps.get(
        f"{API_BASE}/transcript/drive-job",
        json=_completed_payload(job_id="drive-job"),
        status=200,
    )

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    result = provider.transcribe(
        media, language=None, diarize=True, speech_model="universal-3-pro"
    )

    assert result.job_id == "drive-job"
    # Confirm /upload was never hit.
    upload_calls = [c for c in rsps.calls if "/upload" in c.request.url]
    assert len(upload_calls) == 0


def test_transcribe_local_path_still_uploads(
    rsps: responses.RequestsMock, wav: Path, tmp_path: Path
) -> None:
    """Regression: existing upload flow still works after the
    transcribe() signature change. media.remote_url is None → upload
    runs as before."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.base import PreparedMedia

    workspace = RunWorkspace(prefix=str(tmp_path) + "/")
    media = PreparedMedia(
        kind="local",
        original_uri=str(wav),
        local_path=wav,
        title=None,
        duration_seconds=None,
        workspace=workspace,
        extra={},
    )

    rsps.post(f"{API_BASE}/upload", json={"upload_url": "https://cdn/u"}, status=200)
    rsps.post(
        f"{API_BASE}/transcript",
        json={"id": "local-job", "status": "queued"},
        status=200,
    )
    rsps.get(
        f"{API_BASE}/transcript/local-job",
        json=_completed_payload(job_id="local-job"),
        status=200,
    )

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    result = provider.transcribe(
        media, language="en", diarize=True, speech_model="universal-3-pro"
    )
    assert result.job_id == "local-job"
    upload_calls = [c for c in rsps.calls if "/upload" in c.request.url]
    assert len(upload_calls) == 1
```

- [ ] **Step 2: Update existing provider tests to use the new signature** (every call to `provider.transcribe(wav, ...)` becomes `provider.transcribe(media, ...)` where `media` is built from `wav`)

In `tests/unit/test_assemblyai_provider.py`, each test currently calling:
```python
provider.transcribe(wav, language=..., diarize=..., speech_model="universal-3-pro")
```
becomes:
```python
media = PreparedMedia(
    kind="local", original_uri=str(wav), local_path=wav,
    title=None, duration_seconds=None, workspace=workspace, extra={},
)
provider.transcribe(media, language=..., diarize=..., speech_model="universal-3-pro")
```

To avoid repetition: add a fixture at the top of the test file:

```python
@pytest.fixture
def local_media(wav: Path, tmp_path: Path) -> "PreparedMedia":
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.base import PreparedMedia

    workspace = RunWorkspace(prefix=str(tmp_path) + "/")
    return PreparedMedia(
        kind="local",
        original_uri=str(wav),
        local_path=wav,
        title=None,
        duration_seconds=None,
        workspace=workspace,
        extra={},
    )
```

Then sweep the file: every `provider.transcribe(wav, ...)` → `provider.transcribe(local_media, ...)` and add `local_media` to the function signature. Search-replace by hand to keep the diff reviewable; ~10 occurrences.

- [ ] **Step 3: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_assemblyai_provider.py -v`
Expected: many failures — the existing provider takes `wav_path: Path`, not `media: PreparedMedia`.

- [ ] **Step 4: Modify `src/transcriber/providers/base.py`**

Find the `transcribe` abstract method and change:

```python
@abstractmethod
def transcribe(
    self,
    wav_path: Path,
    *,
    language: str | None,
    diarize: bool,
    speech_model: str,
    on_job_id: Callable[[str], None] = _noop,
) -> TranscriptResult:
```

to:

```python
@abstractmethod
def transcribe(
    self,
    media: PreparedMedia,
    *,
    language: str | None,
    diarize: bool,
    speech_model: str,
    on_job_id: Callable[[str], None] = _noop,
) -> TranscriptResult:
    """Transcribe ``media`` and return the result.

    If ``media.remote_url`` is set, the implementation should pass that
    URL to the provider's URL-ingestion endpoint (no upload). Otherwise
    it uploads ``media.local_path`` and transcribes that.

    ``on_job_id`` fires once, immediately after the provider has a
    durable identifier for the job, so the CLI can surface it for
    recovery before the polling loop blocks.
    """
```

Add the import at the top: `from transcriber.sources.base import PreparedMedia`.

Drop the now-unused `from pathlib import Path` if nothing else in the file uses it.

- [ ] **Step 5: Modify `src/transcriber/providers/assemblyai.py`** — the `transcribe` method

Find:

```python
def transcribe(
    self,
    wav_path: Path,
    *,
    language: str | None,
    diarize: bool,
    speech_model: str,
    on_job_id: Callable[[str], None] = _noop,
) -> TranscriptResult:
    logger.info("Uploading %s to AssemblyAI", wav_path)
    upload_url = _upload(wav_path)

    create_payload = _create_transcript(
        upload_url,
        speech_models=[speech_model],
        language_code=language,
        speaker_labels=diarize,
    )
```

Replace with:

```python
def transcribe(
    self,
    media: PreparedMedia,
    *,
    language: str | None,
    diarize: bool,
    speech_model: str,
    on_job_id: Callable[[str], None] = _noop,
) -> TranscriptResult:
    if media.remote_url is not None:
        # URL-passthrough mode: AssemblyAI fetches the URL itself, no
        # upload from us. Saves the download+upload round-trip for
        # public Drive files (Slice 2). The audio_url field is
        # documented byte-for-byte in the spec's Reference calls
        # section.
        logger.info(
            "Submitting AssemblyAI transcript for audio_url %s", media.remote_url
        )
        audio_url = media.remote_url
    else:
        # Upload mode (Slice 1 path): stream the local WAV to /upload
        # and use the returned upload_url as audio_url.
        assert media.local_path is not None  # PreparedMedia invariant
        logger.info("Uploading %s to AssemblyAI", media.local_path)
        audio_url = _upload(media.local_path)

    create_payload = _create_transcript(
        audio_url,
        speech_models=[speech_model],
        language_code=language,
        speaker_labels=diarize,
    )
```

Update the type imports at the top: `from transcriber.sources.base import PreparedMedia`.

The `_upload` helper signature is unchanged. The `_create_transcript` helper signature is unchanged — it always took an `upload_url` (which is just a string AssemblyAI fetches); naming it `audio_url` upstream makes the URL-passthrough nature explicit but doesn't require a helper rename.

- [ ] **Step 6: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_assemblyai_provider.py -v`
Expected: all tests pass — both the 11 existing tests (now using `local_media` fixture) and the 2 new passthrough tests.

- [ ] **Step 7: Full gates**

Run: `env -u VIRTUAL_ENV uv run pytest -q && env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: 100 passed (98 + 2 new), ruff clean, mypy clean. (CLI tests will fail until Task 8 — they call the old `provider.transcribe(wav_path, ...)` shape via mocking. If they fail here, defer the failures and continue; Task 8 fixes them.)

If CLI tests fail with `transcribe() got an unexpected keyword argument` or similar, those are expected at this stage. Proceed to Task 6; Task 8 fixes the CLI side.

- [ ] **Step 8: Commit**

```bash
git add src/transcriber/providers/base.py src/transcriber/providers/assemblyai.py tests/unit/test_assemblyai_provider.py
git commit -m "feat(provider): branch transcribe() on media.remote_url for passthrough

If media.remote_url set: pass to AssemblyAI's audio_url field directly,
skip /upload entirely. Else: existing upload flow.

Signature change: transcribe(wav_path, ...) → transcribe(media, ...).
The CLI was already constructing PreparedMedia upstream; passing it
whole is cleaner than splitting into Path + URL parameters. ABC base
matches.

CLI integration lands in Task 8."
```

---

## Task 6: Title sanitization helper (CLI-layer)

**Files:**
- Modify: `src/transcriber/cli.py` (add `_sanitize_title` helper)
- Test: `tests/unit/test_cli.py` (extend with parametrised tests)

The `_sanitize_title` helper turns a `--title` value into a filename-safe stem. Per spec validation case 26a, it MUST reject `/`, `\`, `\0`, `..`, leading `.` (each would let a hostile or careless title write outside `settings.output_dir` because `atomic.write_text_atomic` creates parent dirs on demand).

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli.py`)

```python
@pytest.mark.parametrize(
    "title",
    [
        "../foo",
        "a/b",
        "back\\slash",
        ".hidden",
        "ok..bad",
        "with\0null",
    ],
)
def test_sanitize_title_rejects_unsafe_characters(title: str) -> None:
    from transcriber.cli import _sanitize_title

    with pytest.raises(ValueError, match="unsafe filename characters"):
        _sanitize_title(title)


def test_sanitize_title_replaces_whitespace_with_dash() -> None:
    from transcriber.cli import _sanitize_title

    assert _sanitize_title("Session 17") == "Session-17"
    assert _sanitize_title("multi   space") == "multi-space"
    # Tabs and other whitespace also collapse.
    assert _sanitize_title("with\ttab") == "with-tab"


def test_sanitize_title_passes_safe_characters_through() -> None:
    from transcriber.cli import _sanitize_title

    assert _sanitize_title("Session-17") == "Session-17"
    assert _sanitize_title("RAG_Intro") == "RAG_Intro"
    assert _sanitize_title("café") == "café"  # unicode round-trips


def test_sanitize_title_rejects_empty_after_strip() -> None:
    from transcriber.cli import _sanitize_title

    with pytest.raises(ValueError, match="empty"):
        _sanitize_title("")
    with pytest.raises(ValueError, match="empty"):
        _sanitize_title("   ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_cli.py -v -k sanitize`
Expected: `ImportError` (`_sanitize_title` not yet defined).

- [ ] **Step 3: Add `_sanitize_title` to `src/transcriber/cli.py`** (place it near `_confirm_or_decline`, right after the other module-level helpers)

```python
import re

_TITLE_FORBIDDEN = ("/", "\\", "\0", "..")


def _sanitize_title(title: str) -> str:
    """Return a filename-safe stem from a user-supplied ``--title``.

    Replaces whitespace runs with a single ``-``; rejects any title that
    is empty after stripping, or that contains ``/``, ``\\``, ``\\0``,
    ``..``, or starts with ``.``. Rejecting these is security-relevant:
    ``atomic.write_text_atomic`` creates parent directories on demand,
    so a title like ``../foo`` would write outside the configured
    ``output_dir``.
    """
    stripped = title.strip()
    if not stripped:
        raise ValueError("--title is empty (or whitespace-only)")
    if stripped.startswith("."):
        raise ValueError(
            f"--title contains unsafe filename characters: {title!r} "
            "(must not start with '.')"
        )
    for forbidden in _TITLE_FORBIDDEN:
        if forbidden in stripped:
            raise ValueError(
                f"--title contains unsafe filename characters: {title!r} "
                f"(must not contain {forbidden!r})"
            )
    # Collapse all whitespace runs into a single '-' for the filename stem.
    return re.sub(r"\s+", "-", stripped)
```

(Add `import re` to the top of `cli.py` if not already present — check first.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_cli.py -v -k sanitize`
Expected: all parametrised + non-parametrised sanitize tests pass.

- [ ] **Step 5: Full gates**

Run: `env -u VIRTUAL_ENV uv run pytest -q && env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: ~109 passed, ruff clean, mypy clean. (Existing CLI integration tests still failing if Task 5 left them broken — defer to Task 8.)

- [ ] **Step 6: Commit**

```bash
git add src/transcriber/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): _sanitize_title helper rejects path-traversal characters

Replaces whitespace with -, rejects /, \\, \\0, .., or leading '.'.
Empty (after strip) is also rejected. Security-relevant:
atomic.write_text_atomic creates parent dirs on demand, so an
unsanitized --title '../foo' would write outside output_dir."
```

---

## Task 7: Markdown formatter handles `local_path=None`

**Files:**
- Modify: `src/transcriber/formatters/markdown.py`
- Test: `tests/unit/test_markdown_formatter.py` (extend)

The two callsites that touch `media.local_path`:
1. `_source_uri(media)` — currently returns `media.local_path.as_uri()` for `kind == "local"`; needs a `kind == "google_drive"` branch.
2. `render(...)` — derives `title` from `media.title or media.local_path.stem`; needs a fallback for `local_path is None` (use `media.extra["drive_file_id"]`).

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_markdown_formatter.py`)

```python
def test_render_drive_media_uses_drive_source_uri(workspace: RunWorkspace) -> None:
    """Drive-shaped PreparedMedia (no local_path, remote_url set) →
    frontmatter source_uri is drive://FILE_ID, source_kind is
    google_drive. No file:/// appears anywhere."""
    media = PreparedMedia(
        kind="google_drive",
        original_uri="drive://1Zdp9aYV",
        local_path=None,
        remote_url="https://drive.google.com/uc?export=download&id=1Zdp9aYV",
        title="Session 17",
        duration_seconds=None,
        workspace=workspace,
        extra={"drive_file_id": "1Zdp9aYV"},
    )
    result = TranscriptResult(
        text="hello",
        segments=[Segment(start_ms=0, end_ms=1000, text="hello", speaker=None)],
        language="en",
        duration_seconds=10.0,
        model="universal-3-pro",
        job_id="drive-job",
    )

    output = render(result, media, created=date(2026, 5, 4))

    # Frontmatter assertions
    assert "source_uri: drive://1Zdp9aYV" in output
    assert "source_kind: google_drive" in output
    # Title from media.title (which the CLI fills in from --title)
    assert "title: Session 17" in output  # whitespace-OK in YAML
    assert "# Session 17" in output  # H1
    # Negative: no local file:// URI anywhere in the output.
    assert "file://" not in output


def test_render_drive_media_falls_back_to_file_id_when_no_title(
    workspace: RunWorkspace,
) -> None:
    """If --title wasn't passed, media.title is None and the formatter
    falls back to the file ID from extra['drive_file_id']."""
    media = PreparedMedia(
        kind="google_drive",
        original_uri="drive://1Zdp9aYV",
        local_path=None,
        remote_url="https://drive.google.com/uc?export=download&id=1Zdp9aYV",
        title=None,
        duration_seconds=None,
        workspace=workspace,
        extra={"drive_file_id": "1Zdp9aYV"},
    )
    result = TranscriptResult(
        text="hello",
        segments=[Segment(start_ms=0, end_ms=1000, text="hello", speaker=None)],
        language="en",
        duration_seconds=10.0,
        model="universal-3-pro",
        job_id="drive-job",
    )

    output = render(result, media, created=date(2026, 5, 4))

    assert "title: 1Zdp9aYV" in output
    assert "# 1Zdp9aYV" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_markdown_formatter.py -v -k drive`
Expected: failure — likely `AttributeError` on `media.local_path.stem` when `local_path is None`.

- [ ] **Step 3: Modify `src/transcriber/formatters/markdown.py`**

Find the title derivation in `render()`:

```python
title = media.title or media.local_path.stem
```

Replace with:

```python
if media.title:
    title = media.title
elif media.local_path is not None:
    title = media.local_path.stem
else:
    # Drive-source path, no --title given: fall back to the file ID.
    title = media.extra.get("drive_file_id", "untitled")
```

Find `_source_uri`:

```python
def _source_uri(media: PreparedMedia) -> str:
    """Return the canonical ``source_uri`` for the frontmatter field."""
    if media.kind == "local":
        return media.local_path.as_uri()
    return media.original_uri
```

Replace with:

```python
def _source_uri(media: PreparedMedia) -> str:
    """Return the canonical ``source_uri`` for the frontmatter field.

    For local sources, the absolute ``file:///`` URI of the input.
    For URL-passthrough sources (Drive in Slice 2), the canonical
    ``drive://FILE_ID`` form already stored in ``original_uri``.
    """
    if media.kind == "local" and media.local_path is not None:
        return media.local_path.as_uri()
    return media.original_uri
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_markdown_formatter.py -v`
Expected: all tests pass (existing local + 2 new Drive tests).

- [ ] **Step 5: Full gates**

Run: `env -u VIRTUAL_ENV uv run pytest -q && env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: ~111 passed, ruff clean, mypy clean. (CLI tests still failing — Task 8 fixes them.)

- [ ] **Step 6: Commit**

```bash
git add src/transcriber/formatters/markdown.py tests/unit/test_markdown_formatter.py
git commit -m "feat(formatter): handle local_path=None for Drive passthrough

_source_uri returns media.original_uri (drive://FILE_ID) for Drive
sources; render() falls back to extra['drive_file_id'] when neither
--title nor local_path.stem is available."
```

---

## Task 8: CLI integration — wire dispatch + `--title` + Drive-variant budget gate

**Files:**
- Modify: `src/transcriber/cli.py`
- Test: `tests/unit/test_cli.py` (extend with Drive happy-path scenarios)

This is the largest single task. It threads everything from Tasks 1-7 through the `transcribe` command.

The changes to `transcribe()`:

1. Add the `--title` typer option.
2. Replace `LocalSource.prepare(source, workspace)` with `resolve_source(source).prepare(source, workspace)`. Catch the new dispatch-layer `ValueError` (URI scheme not supported) and map to exit 2.
3. After `prepare`, branch on `media.remote_url`:
   - Drive: skip `extract_audio`; thread `--title` (sanitized) into `media` (rebuild as a frozen dataclass with `dataclasses.replace`); run the Drive-variant budget gate (no estimate, no soft cap, both hard gates fire).
   - Local: existing flow — `extract_audio`, then existing budget gate.
4. Output filename derivation:
   - Drive: `{sanitized_title or file_id}-{date}.md`.
   - Local: existing `{stem}-{date}.md`.

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli.py`)

```python
def test_drive_happy_path_with_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """transcribe drive://X --title 'Session 17' --budget low -y →
    writes Session-17-{date}.md with frontmatter title 'Session 17' and
    source_uri 'drive://X'. extract_audio NOT called (Drive path)."""
    from transcriber.providers.base import Segment, TranscriptResult

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    extract_called = []
    monkeypatch.setattr(
        "transcriber.cli.extract_audio",
        lambda *_: extract_called.append("CALLED") or (None, 0.0),
    )

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                model="universal-3-pro",
                job_id="drive-job",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "transcribe",
            "drive://1Zdp9aYV",
            "--title",
            "Session 17",
            "--budget",
            "low",
            "-y",
        ],
    )
    assert result.exit_code == 0, result.output
    assert extract_called == []  # Drive path skips ffmpeg
    expected_path = tmp_path / "Session-17-2026-05-04.md"
    # Date will vary; just check the title is in the filename.
    written = list(tmp_path.glob("Session-17-*.md"))
    assert len(written) == 1, f"expected one Session-17-*.md, got {written}"
    content = written[0].read_text(encoding="utf-8")
    assert "title: Session 17" in content
    assert "source_uri: drive://1Zdp9aYV" in content
    assert "source_kind: google_drive" in content


def test_drive_happy_path_no_title_uses_file_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No --title → output filename uses the file ID."""
    from transcriber.providers.base import Segment, TranscriptResult

    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    monkeypatch.setattr("transcriber.cli.settings.output_dir", tmp_path)

    class _OkProvider:
        def __init__(self, *_args: object, **_kwargs: object) -> None: ...

        def transcribe(self, *_args: object, **_kwargs: object) -> TranscriptResult:
            return TranscriptResult(
                text="hi",
                segments=[Segment(start_ms=0, end_ms=1000, text="hi", speaker=None)],
                language="en",
                duration_seconds=1.0,
                model="universal-3-pro",
                job_id="drive-job",
            )

    monkeypatch.setattr("transcriber.cli.AssemblyAIProvider", _OkProvider)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["transcribe", "drive://1Zdp9aYV", "--budget", "low", "-y"],
    )
    assert result.exit_code == 0, result.output
    written = list(tmp_path.glob("1Zdp9aYV-*.md"))
    assert len(written) == 1


def test_unknown_uri_scheme_exits_2(tmp_path: Path) -> None:
    """transcribe https://example.com/foo → exit 2 with 'URI scheme not
    supported' (NOT a 'file not found' fallthrough to LocalSource)."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["transcribe", "https://example.com/foo", "--budget", "low", "-y"],
    )
    assert result.exit_code == 2
    assert "URI scheme not supported" in result.output


def test_drive_budget_free_still_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive sources don't bypass Gate 2."""
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "fake-key")
    runner = CliRunner()
    result = runner.invoke(
        app, ["transcribe", "drive://1Zdp9aYV", "-y"]  # default --budget=free
    )
    assert result.exit_code == 2
    assert "paid provider" in result.output.lower()


def test_drive_unsanitized_title_exits_2(tmp_path: Path) -> None:
    """transcribe drive://X --title '../foo' → exit 2 (sanitization)."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["transcribe", "drive://1Zdp9aYV", "--title", "../foo", "--budget", "low", "-y"],
    )
    assert result.exit_code == 2
    assert "unsafe filename" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_cli.py -v -k drive`
Expected: tests fail — current CLI hardcodes `LocalSource`, has no `--title` flag, has no Drive-variant budget gate.

- [ ] **Step 3: Modify `src/transcriber/cli.py`** — apply all wiring changes in one logical update

Add the new imports at the top:

```python
from dataclasses import replace as dataclass_replace

from transcriber.sources import resolve_source
```

Drop `from transcriber.sources.local import LocalSource` (no longer directly used; goes through `resolve_source`).

Add `--title` to `transcribe()` parameters (between `--language` and `--model` for alphabetical-ish grouping):

```python
title: Annotated[
    str | None,
    typer.Option("--title", help="Frontmatter + filename stem (Drive sources). Defaults to file ID."),
] = None,
```

Replace the source-prep block. Find:

```python
            # Resolve source (local only in Slice 1).
            try:
                media = LocalSource.prepare(source, workspace)
            except FileNotFoundError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=4) from exc
            except ValueError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc

            # Extract audio + duration via ffprobe.
            try:
                wav_path, duration_seconds = extract_audio(media.local_path, workspace)
            except AudioExtractError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=4) from exc

            # Two-gate spend check.
            cost_usd = estimate_assemblyai_cost(duration_seconds)
            try:
                proceed = budget_check(
                    provider_name="AssemblyAI",
                    budget=budget.value,
                    key_configured=settings.assemblyai_configured,
                    cost_usd=cost_usd,
                    yes=yes,
                    prompt=_confirm_or_decline,
                    notify=lambda msg: console.print(msg),
                )
            except BudgetError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc
            if not proceed:
                console.print("[yellow]Cancelled by user; no charge incurred.[/yellow]")
                raise typer.Exit(code=0)
```

Replace with:

```python
            # Resolve and prepare the source. The dispatcher reject-not-
            # swallows unknown :// URIs (exit 2) so the user gets a clear
            # "URI scheme not supported" rather than a misleading "file
            # not found" from LocalSource fallthrough.
            try:
                source_cls = resolve_source(source)
            except ValueError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc

            try:
                media = source_cls.prepare(source, workspace)
            except FileNotFoundError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=4) from exc
            except ValueError as exc:
                console.print(f"[red]error:[/red] {exc}")
                raise typer.Exit(code=2) from exc

            # Sanitize --title (security: rejects path-traversal chars)
            # and thread into the (frozen) PreparedMedia.
            if title is not None:
                try:
                    sanitized_title = _sanitize_title(title)
                except ValueError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc
                # Frontmatter shows the user's typed title (whitespace-
                # preserved); the *filename* uses the dash-collapsed stem.
                media = dataclass_replace(media, title=title.strip())
            else:
                sanitized_title = None

            # Branch: Drive passthrough skips ffmpeg + per-call cost
            # estimate; local upload runs both.
            if media.remote_url is not None:
                # Drive variant of the budget gate: both hard gates still
                # fire; only the cost-estimate number is replaced with a
                # "no pre-estimate" notify message and the soft cap is
                # silenced (no duration → no number).
                try:
                    proceed = _drive_budget_check(budget=budget.value, yes=yes)
                except BudgetError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc
                if not proceed:
                    console.print(
                        "[yellow]Cancelled by user; no charge incurred.[/yellow]"
                    )
                    raise typer.Exit(code=0)
            else:
                # Local path: existing extract + budget flow.
                try:
                    wav_path, duration_seconds = extract_audio(
                        media.local_path, workspace
                    )
                except AudioExtractError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=4) from exc

                cost_usd = estimate_assemblyai_cost(duration_seconds)
                try:
                    proceed = budget_check(
                        provider_name="AssemblyAI",
                        budget=budget.value,
                        key_configured=settings.assemblyai_configured,
                        cost_usd=cost_usd,
                        yes=yes,
                        prompt=_confirm_or_decline,
                        notify=lambda msg: console.print(msg),
                    )
                except BudgetError as exc:
                    console.print(f"[red]error:[/red] {exc}")
                    raise typer.Exit(code=2) from exc
                if not proceed:
                    console.print(
                        "[yellow]Cancelled by user; no charge incurred.[/yellow]"
                    )
                    raise typer.Exit(code=0)
```

Add the `_drive_budget_check` helper near `_confirm_or_decline`:

```python
def _drive_budget_check(*, budget: str, yes: bool) -> bool:
    """Drive-variant of the budget gate: both hard gates (key + budget)
    still fire via the existing budget_check; the cost-estimate number is
    replaced with a "no pre-estimate" notify message and the soft cap is
    silenced because we have no local duration to estimate against.
    """
    return budget_check(
        provider_name="AssemblyAI",
        budget=budget,
        key_configured=settings.assemblyai_configured,
        cost_usd=0.0,  # Sentinel: no estimate; soft cap silenced because cost_usd <= SOFT_CAP_USD.
        yes=yes,
        prompt=_confirm_or_decline,
        notify=lambda msg: console.print(msg),
    )
```

(The `cost_usd=0.0` sentinel is acceptable because: Gate 1 + Gate 2 fire BEFORE the soft-cap check; if both pass, the soft-cap branch silently no-ops since `0.0 <= SOFT_CAP_USD`. The `notify` line will print "Estimated cost: ~$0.00" — not ideal. Override the notify message: pass a custom notify that prints the Drive-specific message instead of the default cost line. To avoid duplicating the gate logic, refactor the call:)

Actually, replace the body of `_drive_budget_check` with this cleaner version that doesn't fake a cost number:

```python
def _drive_budget_check(*, budget: str, yes: bool) -> bool:
    """Drive-variant of the budget gate: both hard gates (key + budget)
    still fire; the per-minute cost-estimate notify is replaced with a
    Drive-specific message; the soft cap is silenced (no local duration
    to estimate against)."""
    # Gate 1 + Gate 2 by hand (intentional duplication to avoid coupling
    # budget.check to source kinds). Same messages as budget.check.
    if not settings.assemblyai_configured:
        raise BudgetError(
            "AssemblyAI key not configured. "
            "Add `ASSEMBLYAI_API_KEY=...` to `.env` (see `.env.example`)."
        )
    if budget == "free":
        raise BudgetError(
            "AssemblyAI is a paid provider ($0.009/min). "
            "Current budget is `free`. Rerun with `--budget low` "
            "(or `--budget best`)."
        )

    console.print(
        "[cyan]Provider: AssemblyAI · URL passthrough[/cyan] — "
        "AssemblyAI bills per-minute against the public URL; exact cost "
        "in the AssemblyAI dashboard after the run."
    )

    if yes:
        return True
    return _confirm_or_decline("Proceed? [y/N]")
```

Update the provider call. Find:

```python
            provider = AssemblyAIProvider(max_wait_seconds=max_wait * 60)
            try:
                result = provider.transcribe(
                    wav_path,
                    language=language,
                    diarize=not no_speakers,
                    speech_model=model,
                    on_job_id=lambda job_id: console.print(
                        f"[cyan]AssemblyAI job ID:[/cyan] {job_id}"
                    ),
                )
```

Replace with:

```python
            provider = AssemblyAIProvider(max_wait_seconds=max_wait * 60)
            try:
                result = provider.transcribe(
                    media,
                    language=language,
                    diarize=not no_speakers,
                    speech_model=model,
                    on_job_id=lambda job_id: console.print(
                        f"[cyan]AssemblyAI job ID:[/cyan] {job_id}"
                    ),
                )
```

Update the output-filename derivation. Find:

```python
            # Resolve output path with collision-suffix policy.
            if output is None:
                stem = media.local_path.stem
                date_str = date.today().isoformat()
                output = settings.output_dir / f"{stem}-{date_str}.md"
            output = atomic.resolve_collision(output)
```

Replace with:

```python
            # Resolve output path with collision-suffix policy.
            if output is None:
                if sanitized_title is not None:
                    stem = sanitized_title
                elif media.local_path is not None:
                    stem = media.local_path.stem
                else:
                    # Drive source, no --title: fall back to the file ID.
                    stem = media.extra.get("drive_file_id", "untitled")
                date_str = date.today().isoformat()
                output = settings.output_dir / f"{stem}-{date_str}.md"
            output = atomic.resolve_collision(output)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `env -u VIRTUAL_ENV uv run pytest tests/unit/test_cli.py -v`
Expected: all CLI tests pass — both the Slice-1 regression tests (which broke after Task 5's signature change) and the 5 new Drive tests.

- [ ] **Step 5: Run the full suite**

Run: `env -u VIRTUAL_ENV uv run pytest -q`
Expected: ~116 passed (everything green).

- [ ] **Step 6: Lint + types**

Run: `env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: clean. (Likely fixes: unused import of `LocalSource`, unused `Path` import. Apply `ruff check --fix` if any auto-fixable.)

- [ ] **Step 7: Commit**

```bash
git add src/transcriber/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): wire Drive source — dispatch + --title + drive-variant budget gate

- resolve_source() routes drive://* / drive.google.com URLs to
  DriveSource; unknown :// URIs reject-not-swallow with exit 2.
- New --title <str> flag (sanitized via _sanitize_title for path
  traversal safety); whitespace replaced with - in the filename;
  YAML title preserves whitespace.
- Drive-variant budget gate: both hard gates fire as today; cost
  estimate replaced with 'AssemblyAI bills per-minute · exact cost in
  dashboard'; soft cap silenced (no duration to compare against).
- Provider.transcribe() now takes media instead of wav_path; CLI
  passes the constructed PreparedMedia through.
- Output filename: --title (sanitized) > local_path.stem > drive_file_id."
```

---

## Task 9: Manual end-to-end runbook — Drive scenario

**Files:**
- Modify: `tests/manual/end_to_end.md` (extend with a second scenario)

This is doc-only; no test code, no commit-during-loop pattern. One commit at the end.

- [ ] **Step 1: Read the existing runbook** so the additions match its tone

Run: `cat tests/manual/end_to_end.md`

- [ ] **Step 2: Append the Drive scenario** at the bottom of the file (before the "Recording the result" trailer if there is one — check the structure):

```markdown
---

## Scenario 2: Drive source (URL passthrough)

This scenario verifies the second source path: a Drive video the user
has already shared as anyone-with-link, transcribed via AssemblyAI's
``audio_url`` ingestion (no OAuth, no download, no upload). Expected
cost: same as the local-file scenario (~$0.009/min).

### Prerequisites

- A Google Drive video file already shared as "anyone with link can view."
- The file ID (the long alphanumeric segment after `/d/` in the Drive URL).

### Steps

1. **Smoke: Drive URL parses + dispatches.** With `--budget free` to
   confirm Gate 2 still fires for Drive sources:

   ```bash
   uv run ssm-transcriber transcribe \
     "https://drive.google.com/file/d/<FILE_ID>/view" \
     -y
   echo "exit: $?"
   ```

   **Expected:** error message naming AssemblyAI as paid + the
   `--budget low|best` rerun hint, exit code `2`. No charge incurred.

2. **Real run:** with `--budget low` and a real `--title`:

   ```bash
   uv run ssm-transcriber transcribe \
     "https://drive.google.com/file/d/<FILE_ID>/view" \
     --title "Drive Test Run" \
     --budget low -y
   echo "exit: $?"
   ```

   **Expected:**
   - The "Provider: AssemblyAI · URL passthrough" notify line prints
     **without** a numeric estimate (deliberate — see spec §"Cost
     pre-estimation").
   - `AssemblyAI job ID:` line prints once (recoverable identifier).
   - **No `Uploading ...` log line appears** (the URL-passthrough path
     skips `_upload`).
   - A polling spinner runs for ~real-time × 0.5 to × 1.0 (AssemblyAI
     takes longer for URL fetches than for already-uploaded WAVs).
   - `✓ Saved to: ./output/Drive-Test-Run-YYYY-MM-DD.md`.
   - Exit code `0`.

3. **Verify the markdown** — open the produced file:
   - Frontmatter `source_kind: google_drive`, `source_uri: drive://<FILE_ID>`,
     `model: universal-3-pro`, `title: Drive Test Run` (whitespace
     preserved in YAML).
   - Body H1 is `# Drive Test Run`.
   - Transcript content matches the Drive video.

4. **Sanitization smoke test** — confirm the CLI rejects path-traversal
   titles **without** charging AssemblyAI:

   ```bash
   uv run ssm-transcriber transcribe \
     "drive://<FILE_ID>" \
     --title "../escape" \
     --budget low -y
   echo "exit: $?"
   ```

   **Expected:** error "unsafe filename characters" + exit code `2`. No
   AssemblyAI call (and therefore no charge) — the sanitization fires
   before the provider is invoked.

### Recording the result

Append to the PR's verification evidence:

- Drive scenario steps 1, 2, and 4 exit codes observed.
- The output markdown filename produced by step 2.
- The actual AssemblyAI cost shown in the dashboard.
```

- [ ] **Step 3: Verify markdown renders cleanly**

Open `tests/manual/end_to_end.md` in an editor or run a quick markdown lint if available. Visually check the new scenario integrates without breaking existing structure.

- [ ] **Step 4: Commit**

```bash
git add tests/manual/end_to_end.md
git commit -m "test(manual): add Drive URL passthrough scenario to runbook

Scenario 2: Drive source. Three observable differences from Scenario 1:
no numeric cost estimate (deliberate), no Uploading log line, polling
takes longer (AssemblyAI fetches the URL itself). Plus a sanitization
smoke test confirming path-traversal --title rejection happens before
the AssemblyAI call (so no charge incurred for malformed input)."
```

---

## Task 10: Per-PR teaching artifacts + roadmap update

**Files:**
- Create: `docs/learn/prs/pr-NNN-drive-source-passthrough-impl.md` (NN = the actual PR number; check via `gh pr list --json number` after pushing the branch and opening the PR. If draft-before-PR-number-known per repo convention, use a placeholder slug and rename at PR-open time.)
- Modify: `docs/learn/journey.md` (top entry)
- Modify: `docs/learn/prs/README.md` (index row)
- Modify: `specs/roadmap.md` (Phase 4 status update)

The implementation-PR explainer focus is on **implementation-phase learnings**, NOT spec-phase decisions (those are already in `pr-015-drive-source-passthrough-spec.md`). Per `plan.md` §9, the prompts are: F2 friction, polling edge cases on `audio_url`, body-shape mock guardrail application, cost-vs-estimate gap from manual run, dispatcher's reject-not-swallow UX.

- [ ] **Step 1: Draft the explainer** (`docs/learn/prs/pr-NNN-drive-source-passthrough-impl.md`)

Use this template; fill in the empirical findings *after* the manual runbook step has produced concrete numbers and observations to cite. Do NOT ship the explainer with placeholder findings — wait until the manual runbook (Task 9) has been executed and the results are in hand.

```markdown
# PR #NN — Implementation: Drive Source (URL Passthrough)

**Merged:** TBD  |  **Branch:** `impl/drive-source-passthrough`  |  **Codex review:** TBD
**Journey entry:** [`../journey.md#pr-NN--implementation-drive-source-url-passthrough`](../journey.md#pr-NN--implementation-drive-source-url-passthrough)

## The problem in one paragraph

Slice 2's spec landed in PR #15: take a public Drive URL, hand it
straight to AssemblyAI's `audio_url` ingestion, no OAuth, no download.
This PR is the implementation of that spec. The interesting bits aren't
the design choices (those are in `pr-015-drive-source-passthrough-spec.md`)
but the implementation-phase learnings — friction encountered, edge
cases, what the spec did and didn't predict.

## Implementation-phase learnings

[Fill in after the manual runbook completes. Use the empirical findings
to answer the five prompts from plan.md §9:]

1. **F2 contract extension friction** — did `local_path: Path | None` +
   `remote_url: str | None` feel additive in practice, or did the
   downstream branching push complexity that suggests a Phase-5
   refactor?
2. **Polling-status edge cases on `audio_url`** — did AssemblyAI's
   behaviour on URL-passthrough differ from upload-mode in any way
   the spec didn't predict?
3. **Body-shape mock guardrail application** — how was PR #13's
   `responses.matchers.json_params_matcher` rule applied to the new
   `audio_url`-bearing POST, and would it have caught a regression?
4. **Cost-vs-estimate gap from the manual run** — Slice 2 deliberately
   skips pre-estimate; the manual runbook is the only visibility.
   Capture the gap (or "matches per-minute math" if predictable).
5. **Dispatcher reject-not-swallow UX** — did the rule feel right in
   practice, or did any plausible user input get unexpectedly
   rejected?

## What changed (high level, not file-by-file)

[Generate from `git log impl/drive-source-passthrough --oneline` after
all commits land.]

## What a reviewer should notice

[Fill in based on the actual implementation and any pre-PR Codex
review findings.]

## Further reading

- [`pr-015-drive-source-passthrough-spec.md`](pr-015-drive-source-passthrough-spec.md) — the spec this implements.
- [`pr-013-prevent-vendor-api-shape-regressions.md`](pr-013-prevent-vendor-api-shape-regressions.md) — the prevention layer this PR continues to dogfood.
- [`pr-012-assemblyai-mvp-slice-1-impl.md`](pr-012-assemblyai-mvp-slice-1-impl.md) — Slice 1 implementation that this slice extends.
```

- [ ] **Step 2: Append the journey entry** (top of `docs/learn/journey.md`, above the PR #15 entry)

Use parallel structure to recent journey entries (PR #14, #15) — 3 paragraphs, ~250 words. Same draft-after-runbook discipline as the explainer.

- [ ] **Step 3: Append the index row** to `docs/learn/prs/README.md`:

```markdown
| #NN | Implementation: Drive Source (URL passthrough) | feature (impl) | [`pr-NNN-drive-source-passthrough-impl.md`](pr-NNN-drive-source-passthrough-impl.md) |
```

- [ ] **Step 4: Update `specs/roadmap.md` Phase 4 status**

Find:

```markdown
## [Phase 4 — Google Drive Source](../docs/PLAN.md#phase-4--google-drive-source)

**Status:** pending.
```

Replace with:

```markdown
## [Phase 4 — Google Drive Source](../docs/PLAN.md#phase-4--google-drive-source)

**Status:** partial — public-link passthrough only (Slice 2, PR #NN). OAuth + private-file support deferred to Slice 3 per the PLAN.md sub-headed split.
```

- [ ] **Step 5: Run gates one last time**

Run: `env -u VIRTUAL_ENV uv run pytest -q && env -u VIRTUAL_ENV uv run ruff check src/ tests/ && env -u VIRTUAL_ENV uv run mypy src/ tests/`
Expected: green.

- [ ] **Step 6: Commit teaching artifacts**

```bash
git add docs/learn/prs/pr-NNN-drive-source-passthrough-impl.md docs/learn/journey.md docs/learn/prs/README.md specs/roadmap.md
git commit -m "docs: per-PR teaching artifacts for Slice 2 implementation

Explainer focuses on implementation-phase learnings (F2 friction,
polling edge cases on audio_url, body-shape mock guardrail
application, cost-vs-estimate gap from manual run, dispatcher UX) —
spec-phase decisions are already documented in pr-015-...spec.md and
re-stating them here would duplicate.

Roadmap Phase 4 status: pending → partial — public-link passthrough
only (Slice 2). OAuth + private files deferred to Slice 3."
```

- [ ] **Step 7: Push and open the PR**

```bash
git push -u origin impl/drive-source-passthrough
gh pr create --title "feat: Drive source URL passthrough — Slice 2 implementation" --body "$(cat <<'EOF'
[PR body — generate from the explainer once finalized; include test
plan section listing all 7 success criteria from validation.md.]
EOF
)"
```

After the PR opens, replace `pr-NNN-` with `pr-XX-` (the actual number) in: the explainer filename, the journey-entry header anchor, the README index row, and the roadmap status line. Commit the rename + cross-link updates as a follow-up small commit.

---

## Self-review checklist

Before declaring this plan complete, the writer should verify:

- [ ] **Spec coverage.** Each scenario in `requirements.md` (1–10), each
  decision in §"Feature-specific decisions," each F-contract status
  row, each test case (1–27 + 26a/26b) maps to at least one task above.
- [ ] **No placeholders.** No "TBD" / "TODO" / "implement later" /
  "fill in details" in any task body. (One exception: the explainer
  template in Task 10 explicitly defers content to *after* the manual
  runbook produces empirical findings — this is the documented
  draft-after-runbook pattern, not a planning placeholder.)
- [ ] **Type consistency.** `_sanitize_title`, `_drive_budget_check`,
  `_extract_file_id`, `resolve_source`, `DriveSource.prepare`,
  `PreparedMedia.remote_url` — all referenced consistently across
  tasks.
- [ ] **Test commands.** Every `pytest` invocation uses
  `env -u VIRTUAL_ENV uv run pytest` (per the session's recurring
  finding that `VIRTUAL_ENV` from another project leaks if not
  unset).
- [ ] **Commit messages.** Each task ends in a commit with a Conventional
  Commits prefix (`feat`, `fix`, `docs`, `test`, `refactor`); body
  explains the *why* in 1-3 lines.
