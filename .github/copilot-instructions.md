# GitHub Copilot Instructions — SSM-Transcriber

Start with:
- [`docs/ai/README.md`](../docs/ai/README.md)
- [`docs/PLAN.md`](../docs/PLAN.md)
- [`docs/learn/README.md`](../docs/learn/README.md) for PR/docs changes

## Project

Python 3.12 transcription pipeline. Phase 0 implements only the CLI stub and
config singleton.

## Config access

```python
from transcriber.config import settings
```

Never read `os.environ` directly.

## Adding a provider or source later

- Keep the core sync through Phase 4
- Match URL sources by hostname, not generic scheme
- Route temp artifacts through `RunWorkspace`
- Use the versioned cache-key inputs from F3
- Do not hardcode provider strings outside the registry

## What NOT to do

- Do not use `print()` in library code
- Do not call cloud APIs without the two-gate spend check
- Do not cache on `SHA256(file + quality)`
- Do not strip canonical audio with VAD
- Do not create speculative living-doc entries
