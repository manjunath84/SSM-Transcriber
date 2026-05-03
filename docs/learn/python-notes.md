# Python Notes (for a Java Developer)

> Living doc. Entries land here as the codebase introduces them. Each entry
> has three parts: a **Java analogue**, a **Python idiom**, and a **pointer**
> to where this shows up in the repo. If it isn't in the repo yet, it doesn't
> belong here.
>
> Alphabetical within sections; sections added as categories fill up.

---

## Table of contents

- [Typing & type hints](#typing--type-hints)
  - [`from __future__ import annotations`](#from-__future__-import-annotations)
  - [Union syntax (`X | Y`) vs `Optional[X]`](#union-syntax)
  - [`Literal` types](#literal-types)
  - [`Annotated` and CLI parameters](#typer-and-annotated)
  - [`typing.Protocol`](#typing-protocol)
- [Data objects](#data-objects)
  - [Frozen dataclasses](#frozen-dataclasses)
  - [`@property`](#property)
- [Resource management](#resource-management)
  - [Context managers (`with`)](#context-managers)
  - [`pathlib.Path`](#pathlib-path)
- [Module structure](#module-structure)
  - [Module-level singletons](#module-level-singletons)
  - [Lazy imports inside functions](#lazy-imports)
- [External calls and resilience](#external-calls-and-resilience)
  - [`tenacity.retry` decorator](#tenacity-retry)

---

## Typing & type hints

### `from __future__ import annotations`

**Java analogue:** there isn't a direct one. The closest thing is
generics with bounded type parameters being written but not fully resolved
at compile time.

**Python idiom.** Put this as the first import in every file:

```python
from __future__ import annotations
```

It turns all type hints in the file into **strings** that are only
evaluated when explicitly asked (e.g. by `mypy` or `typing.get_type_hints()`).
The practical effect: you can write `def f(x: RunWorkspace) -> None:` in a
file where `RunWorkspace` is defined later in the same module, or imported
from a module that would otherwise cause a circular import. Without it,
Python evaluates the annotation at function-definition time and crashes.

**When to use it.** Always, unless you're doing runtime type checking via
`get_type_hints()` and need the real classes. The cost is zero.

**Where it shows up:** [`src/transcriber/cli.py:3`](../../src/transcriber/cli.py).

---

### Union syntax

**Java analogue:** `Optional<String>` (with the understanding that Python's
`None` plays the role of Java's `null`).

**Python idiom.** Python 3.10+ supports `X | Y` as a union type at runtime.
It replaces the older `Optional[X]` / `Union[X, Y]` forms:

```python
def find(name: str) -> User | None:    # <- instead of Optional[User]
    ...

def parse(s: str | bytes) -> dict:      # <- instead of Union[str, bytes]
    ...
```

**When to use it.** Always, on Python 3.10+. It's shorter, reads like math
notation, and doesn't require importing from `typing`. `Optional[X]` is now
considered legacy — keep it only if you're supporting very old Python.

**Where it shows up:** [`src/transcriber/cli.py`](../../src/transcriber/cli.py) —
e.g. `output: Path | None = None` as a CLI parameter type.

---

### `Literal` types

**Java analogue:** an enum, but *by value* rather than by reference. Python's
`Literal["fast", "balanced", "best"]` is closest to `@Pattern` in
javax.validation applied to a `String` — the type *is* the set of allowed values.

**Python idiom.**

```python
from typing import Literal

Quality = Literal["fast", "balanced", "best"]

def transcribe(quality: Quality) -> None:
    if quality == "fast":
        ...
```

`mypy` will flag `transcribe("maximum")` as a type error. At runtime, Python
does not enforce this — so you still need runtime validation for user input
(e.g. a `typer.Option` default or a `pydantic` validator).

**When to use it.** Whenever a parameter has a small, closed set of string
values that the whole codebase uses the same way. Prefer `Literal` over
`Enum` unless you need the enum's methods or ordering — enums add ceremony
Python doesn't ask for.

**Where it shows up:** not yet in code — will land in Phase 1 as
`SourceKind = Literal["local", "youtube", "google_drive"]` on `PreparedMedia`.
Pointer will be updated when the file is merged.

---

### `typer` and `Annotated`

**Java analogue:** `picocli` CLI definitions — method parameters annotated
with `@Option` / `@Parameters` / `@Mixin`, where the annotation metadata
drives both parsing and help text.

**Python idiom.** `typer` uses `typing.Annotated[type, metadata]` to
attach CLI parameter metadata to a plain function parameter:

```python
from typing import Annotated
import typer

app = typer.Typer()

@app.command()
def transcribe(
    source: Annotated[str, typer.Argument(help="File path or URL")],
    output: Annotated[Path | None, typer.Option("-o", "--output")] = None,
    quality: Annotated[str, typer.Option("-q", "--quality")] = "balanced",
) -> None:
    ...
```

`Annotated[X, Y]` says "the **type** is `X`, and the *metadata* is `Y`".
Type checkers treat it as `X`; `typer` reads `Y` to build the command-line
parser. It's how Python layers CLI framework metadata on top of standard
type hints without a separate decorator per parameter.

**When to use it.** Always, for `typer` CLIs. Prefer `Annotated[...]` over
assigning a `typer.Option(...)` instance as the default — `mypy` treats the
Annotated form as a plain default value, which is what you want.

**Where it shows up:** [`src/transcriber/cli.py`](../../src/transcriber/cli.py)
— every CLI parameter uses this form.

---

### `typing.Protocol`

**Java analogue:** an `interface`. Anything that has methods of the
right shape "implements" it; you don't have to inherit explicitly.
Python's twist on Java's interface: structural typing — duck-typing
that the type checker can verify.

**Python idiom.**

```python
from typing import Protocol

class Formatter(Protocol):
    def render(self, result: TranscriptResult, media: PreparedMedia) -> str: ...

# A function that takes any Formatter:
def write_output(fmt: Formatter, ...) -> None:
    content = fmt.render(result, media)
    ...

# MarkdownFormatter doesn't inherit Formatter — it just has the right shape.
class MarkdownFormatter:
    def render(self, result: TranscriptResult, media: PreparedMedia) -> str: ...

write_output(MarkdownFormatter(), ...)   # mypy accepts this
```

`Protocol` is structural: anything with a matching `render(...)`
satisfies it, even if it's a class from a different package that has
never heard of `Formatter`. This is the opposite of Java's nominal
typing, where `MarkdownFormatter` would have to write
`implements Formatter` for the assignment to compile.

**When to use it.** When you want a type-checked contract but don't
control all the implementations (third-party providers, plugins,
test doubles), or when adding a base class would force unrelated
classes into a hierarchy they don't naturally belong to. ABCs
(`abc.ABC` + `@abstractmethod`) are the heavier alternative — use
those when you also want concrete shared behaviour.

**Where it shows up:** [`src/transcriber/formatters/base.py`](../../src/transcriber/formatters/base.py)
defines the `Formatter` Protocol; [`src/transcriber/formatters/markdown.py`](../../src/transcriber/formatters/markdown.py)
satisfies it without inheriting. Phase 3's other formatters
(`txt.py`, `srt.py`, `json_fmt.py`) will satisfy it the same way.

---

## Data objects

### Frozen dataclasses

**Java analogue:** a `record` — immutable data holder with auto-generated
`equals`, `hashCode`, and constructor. Java 14+ syntax:
`record PreparedMedia(String kind, Path localPath) {}`.

**Python idiom.**

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PreparedMedia:
    kind: str
    local_path: Path
    title: str | None
    extra: dict[str, str]
```

`frozen=True` makes instances immutable (`pm.kind = "x"` raises
`FrozenInstanceError`), hashable (so you can put them in sets / dict keys),
and gives you `__eq__` and `__repr__` for free. Without `frozen=True`, you
get equality and `__repr__` but the object is mutable and unhashable.

**When to use it.** Default to `frozen=True` for every dataclass that
represents a value, not an entity. "Value" here has the same meaning as in
DDD: you don't track it by identity, only by contents. `PreparedMedia` is a
value (two `PreparedMedia` with the same fields are interchangeable). A
`RunWorkspace` is *not* a value (it owns a real filesystem directory with
identity), so it's a regular class.

**Gotcha Java devs hit:** `@dataclass(frozen=True)` does NOT deep-freeze.
If you have `extra: dict[str, str]`, the dict itself is still mutable — you
just can't rebind the field. For truly immutable nested containers, use
`frozenset` / `tuple` / custom wrappers. In practice, "don't mutate"
documentation is enough for internal code.

**Where it shows up:** not yet in code — will land in Phase 1 as
`PreparedMedia` (F2) and `CacheKey` (F3). Pointer will be updated when
the files are merged.

---

### `@property`

**Java analogue:** a getter method (`public String getName() { ... }`) that
you call without parentheses on the caller side — except that in Java, you
always have to type the parentheses.

**Python idiom.**

```python
class Circle:
    def __init__(self, radius: float) -> None:
        self.radius = radius

    @property
    def area(self) -> float:
        return 3.14159 * self.radius ** 2

# Usage:
c = Circle(2.0)
c.area    # no parentheses — reads like an attribute
```

Under the hood, `@property` turns the method into a descriptor, so attribute
access (`c.area`) calls the method. The caller doesn't see the difference
between a plain attribute and a property. This lets you start with a plain
attribute and refactor to a computed value later without changing any
callers — a fluency Java doesn't have.

**When to use it.** When the value is computed or validated but looks
conceptually like an attribute. Over-using `@property` for things that are
cheap plain attributes just adds indirection.

**Where it shows up:** not in `src/` yet. The closest planned use is the
Phase 5 cost-estimation hook on `TranscriptionProvider`, described in
[`docs/PLAN.md`](../PLAN.md#phase-5--cloud-transcription-providers-provider-abstraction).
The previous `cost_per_minute` scalar shape was retired in PR #6, and the
replacement contract is still being designed; this entry will be revisited
with a real `src/transcriber/providers/` pointer once that code lands.

---

## Resource management

### Context managers

**Java analogue:** try-with-resources.

```java
try (FileInputStream in = new FileInputStream(path)) {
    // ...
}   // in.close() called automatically
```

**Python idiom.**

```python
with open(path) as f:
    # ...
# f.close() called automatically on exit (including exceptions)
```

Any object with `__enter__` and `__exit__` methods can be used with `with`.
You write your own with a class or a `@contextlib.contextmanager`
generator function:

```python
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from pathlib import Path

@contextmanager
def run_workspace():
    tmp = TemporaryDirectory(prefix="ssm-transcriber-")
    try:
        yield Path(tmp.name)
    finally:
        tmp.cleanup()

with run_workspace() as ws:
    (ws / "audio.wav").write_bytes(...)
# ws is deleted here, even on exception or Ctrl-C
```

**When to use it.** Any time you have paired setup / cleanup: files, sockets,
locks, database transactions, temp directories. F5 in `docs/PLAN.md`
specifies `RunWorkspace` as a context manager for exactly this reason.

**Gotcha Java devs hit:** Python's `with` doesn't support multiple
variables as cleanly as Java's chained resources. You can write
`with open("a") as a, open("b") as b:` but deeper nesting gets ugly —
prefer `contextlib.ExitStack` for dynamic or >2 resources.

**Where it shows up:** not yet in code — will land in Phase 1 as
`RunWorkspace` in `src/transcriber/core/workspace.py`. Pointer will be
updated when the file is merged.

---

### `pathlib.Path`

**Java analogue:** `java.nio.file.Path`. The API shapes are similar enough
that muscle memory transfers, but the operator overload (`/`) is a genuine
improvement.

**Python idiom.**

```python
from pathlib import Path

cache_dir = Path.home() / ".cache" / "transcriber"
cache_dir.mkdir(parents=True, exist_ok=True)

for wav_file in cache_dir.glob("*.wav"):
    if wav_file.stat().st_size > 0:
        text = wav_file.read_text()
```

The `/` operator composes path segments. `.home()`, `.cwd()`, `.glob()`,
`.read_text()`, `.write_bytes()` are all methods on the `Path` itself — no
helper `Files` class indirection.

**When to use it.** Always. Legacy Python code still uses `os.path.join(...)`
string-based APIs, but new code should be pure `pathlib.Path`. Only drop to
strings at system boundaries (subprocess args, JSON serialization).

**Where it shows up:** everywhere — [`src/transcriber/cli.py`](../../src/transcriber/cli.py)
types its output argument as `Path | None`,
[`src/transcriber/config.py`](../../src/transcriber/config.py) stores cache
and output directories as `Path`.

---

## Module structure

### Module-level singletons

**Java analogue:** a Spring `@Bean` with default (singleton) scope, or the
classic `public static final` instance pattern.

**Python idiom.** Python modules are themselves singletons — every `import`
statement returns the same module object — so the simplest singleton is a
module-level variable:

```python
# src/transcriber/config.py
from pydantic_settings import BaseSettings

class TranscriberSettings(BaseSettings):
    ...

settings = TranscriberSettings()   # evaluated once, at first import
```

```python
# Anywhere else:
from transcriber.config import settings
print(settings.cache_dir)
```

Every importer gets the *same* `settings` object. There is no DI container;
the module system is the DI container. If you need test isolation, you
override fields on the instance or (preferred) pass the config object into
the function that needs it instead of importing the singleton.

**When to use it.** For genuinely process-wide, read-mostly state: config,
loggers, shared HTTP clients, model caches. Don't use it for request-scoped
or mutable state.

**Gotcha Java devs hit:** because modules are singletons, module-level
side effects run on first import and are *not easy to re-run*. Don't put
"start a background thread" or "open a DB connection" at module level —
put them in a `lazy_init()` function or inside `if __name__ == "__main__"`.

**Where it shows up:** [`src/transcriber/config.py`](../../src/transcriber/config.py)
exports `settings` as the canonical module-level singleton.

---

### Lazy imports

**Java analogue:** there isn't one — Java imports are free at compile time.
The closest cousin is deliberately deferring a class load by using reflection.

**Python idiom.** Imports are statements, not declarations, so you can put
them inside a function:

```python
def config() -> None:
    from transcriber.config import settings    # only imported when this command runs
    print(settings.redacted_dump())
```

**When to use it.**

1. **CLI startup speed.** Top-level imports run every time `uv run
   ssm-transcriber --help` runs. If you import `faster_whisper` at the top
   of `cli.py`, every `--help` invocation pays the model-framework import
   cost. Pushing heavy imports into the specific command that uses them
   keeps `--help` snappy.
2. **Breaking import cycles.** If `A` imports `B` at module level and `B`
   imports `A` at module level, you get `ImportError`. Moving one of them
   inside a function defers it until after both modules have finished loading.
3. **Optional dependencies.** `if use_deepgram: from deepgram import Client`
   lets you avoid failing on startup if the user hasn't installed the paid
   provider's SDK.

**When *not* to use it.** Import cycles you can *actually* break by
restructuring modules — lazy imports hide the cycle but don't fix the
architectural mistake. Code clarity beats micro-optimization for non-CLI code.

**Where it shows up:** No live example yet — Slice 1's CLI rewrite (commit
`1847a17`) imports `settings` at module top because the load is already
cheap. The pattern returns when a heavy import (e.g. `faster-whisper`'s
model files in Phase 1, or LangGraph in Phase 6b) needs to stay out of
`--help` startup.

---

## External calls and resilience

### `tenacity.retry` decorator

**Java analogue:** Spring Retry's `@Retryable` or Resilience4j's
`Retry` decorator. Wrap a method so transient failures auto-retry with
backoff before giving up.

**Python idiom.**

```python
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

@retry(
    retry=retry_if_exception_type((ConnectionError, _Transient)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def upload(wav_path: Path) -> str:
    resp = requests.post(URL, data=wav_path.read_bytes(), timeout=120)
    resp.raise_for_status()
    return resp.json()["upload_url"]
```

This wraps `upload` with a retry policy: at most 3 attempts, exponential
backoff (1s → 2s → 4s), retry only on the named exception types,
re-raise the original exception (not tenacity's wrapper) if all
attempts fail.

**When to use it.** Any external network call where 429 / 503 / network
timeouts are recoverable transient failures. NOT for permanent failures
like 401 (auth) or 422 (validation) — retrying those just wastes your
quota. The trick is to translate "permanent" responses into a
non-retryable exception type before tenacity sees them, and "transient"
responses into a retryable type.

**Pattern in this repo:** an internal sentinel exception (`_Transient`)
wraps the transient HTTP statuses; permanent 4xx raise the public
`ProviderError` immediately. The `retry_if_exception_type` filter only
includes `_Transient` and the network errors, so `ProviderError` skips
the retry loop entirely.

**Where it shows up:** [`src/transcriber/providers/assemblyai.py`](../../src/transcriber/providers/assemblyai.py)
`_retry_policy` decorates each of the three HTTP functions
(`_upload`, `_create_transcript`, `_get_transcript`). Future Phase 5
provider implementations (Deepgram, OpenAI Whisper) will reuse the
same shape.
