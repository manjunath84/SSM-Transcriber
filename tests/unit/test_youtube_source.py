"""Tests for the YouTube captions source (Phase 2 Slice 1).

The source has three independently-testable concerns and they're
arranged in the file in roughly that order:

1. URL parsing — pure regex on the eight accepted YouTube URL forms
   plus the rejected playlist / channel / homepage forms.
2. Caption resolution — picking a track from ``ytt_api.list()`` results,
   preferring manual over auto-generated. ``YouTubeTranscriptApi`` is
   monkeypatched at the class level (not via ``responses``) — our code
   doesn't construct the outbound request body, so the CLAUDE.md
   body-matcher rule doesn't apply here.
3. Oembed title resolution — fail-soft GET against the public oembed
   endpoint, validated through the same ``validate_title`` helper Drive
   uses. Mocked via ``responses`` because our code constructs the
   request URL + params explicitly.

Plus retry semantics (tenacity wraps the captions fetch but never the
deterministic ``CouldNotRetrieveTranscript`` subclasses) and the
``PreparedTranscript`` shape this source produces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from transcriber.core.workspace import RunWorkspace
from transcriber.sources.base import PreparedTranscript, SourceInputError
from transcriber.sources.youtube import YouTubeSource, _extract_video_id

# ---------------------------------------------------------------------------
# Test doubles for youtube-transcript-api objects. The library exposes a
# narrow surface — list() returns an iterable of Transcript objects each
# with language_code / is_generated / fetch(); fetch() returns a
# FetchedTranscript iterable of snippets with start / duration / text.
# Reproducing that with @dataclass-based fakes is shorter and more
# transparent than MagicMock here.
# ---------------------------------------------------------------------------


@dataclass
class _FakeSnippet:
    start: float
    duration: float
    text: str


@dataclass
class _FakeFetched:
    video_id: str
    language_code: str
    is_generated: bool
    _snippets: list[_FakeSnippet]

    def __iter__(self) -> object:
        return iter(self._snippets)


class _FakeTranscript:
    def __init__(self, language_code: str, is_generated: bool, fetched: _FakeFetched):
        self.language_code = language_code
        self.is_generated = is_generated
        self._fetched = fetched

    def fetch(self) -> _FakeFetched:
        return self._fetched


class _FakeTranscriptList:
    def __init__(self, transcripts: list[_FakeTranscript]):
        self._transcripts = transcripts

    def __iter__(self) -> object:
        return iter(self._transcripts)


# ---------------------------------------------------------------------------
# URL parsing — validation.md cases 1-18.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1234&index=2",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=42",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
    ],
)
def test_extracts_video_id_from_all_accepted_url_forms(uri: str) -> None:
    """Every URL form the spec accepts round-trips to the same 11-char ID."""
    assert _extract_video_id(uri) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "uri",
    [
        "https://www.youtube.com/playlist?list=PLrAXtmRdnEQy6nuLMfO6P0bjOSf6ZmiZk",
        "https://www.youtube.com/channel/UC1234567890abcdefghijkl",
        "https://www.youtube.com/@channel-name",
        "https://www.youtube.com/",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/embed/",
    ],
)
def test_rejects_unsupported_url_forms(uri: str) -> None:
    """Playlist / channel / homepage / malformed forms exit cleanly with a
    ``SourceInputError`` (CLI maps to exit 2 — same path as Drive)."""
    with pytest.raises(SourceInputError):
        _extract_video_id(uri)


def test_rejects_url_with_id_too_long() -> None:
    """A v= parameter that extracts to >11 chars must be rejected, not
    silently truncated. The library would reject it too, but we'd rather
    fail at the parse layer with a clear error than at the network layer
    with a library-internal exception."""
    with pytest.raises(SourceInputError):
        _extract_video_id("https://www.youtube.com/watch?v=ThisIsTooLongAnId")


# ---------------------------------------------------------------------------
# Caption resolution — picking a track from list(), mapping to
# TranscriptResult, building PreparedTranscript.
# ---------------------------------------------------------------------------


def _stub_list_returning(
    list_payload: _FakeTranscriptList,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace ``YouTubeTranscriptApi.list`` with one that returns a fake
    list. Method is looked up on the class, so monkeypatching the class
    attribute substitutes for every instance.

    We mock at the library-API level (not via ``responses``) because our
    code doesn't construct the outbound request body — the body-shape
    matcher rule in CLAUDE.md targets code paths that build the request,
    not paths that delegate to an SDK that builds it for them.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    def fake_list(self: object, video_id: str) -> _FakeTranscriptList:
        return list_payload

    monkeypatch.setattr(YouTubeTranscriptApi, "list", fake_list)


def test_prefers_manual_when_both_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manual captions are higher-quality than auto-generated; the
    resolver must pick the manual track even if auto comes first in the
    iteration order. Frontmatter ``caption_type`` reflects the choice."""
    manual_fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.5, text="hello")],
    )
    auto_fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=True,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )
    # Auto first in iteration order — to verify the resolver doesn't
    # just take the first track.
    payload = _FakeTranscriptList(
        [
            _FakeTranscript("en", True, auto_fetched),
            _FakeTranscript("en", False, manual_fetched),
        ]
    )
    _stub_list_returning(payload, monkeypatch)

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare(
        "https://youtu.be/abc12345678", workspace, title="Test Title"
    )

    assert isinstance(prepared, PreparedTranscript)
    assert prepared.kind == "youtube_captions"
    assert prepared.extra["caption_type"] == "manual"
    assert prepared.extra["video_id"] == "abc12345678"
    assert prepared.transcript.text == "hello"
    assert prepared.transcript.provider == "youtube-captions"
    assert prepared.transcript.model is None
    assert prepared.transcript.job_id is None


def test_falls_back_to_auto_when_no_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auto-generated is the second-choice track. Auto-translated tracks
    are NOT picked — we only iterate the source list, never call
    ``.translate()``."""
    auto_fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=True,
        _snippets=[_FakeSnippet(start=0.5, duration=2.0, text="auto only")],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", True, auto_fetched)])
    _stub_list_returning(payload, monkeypatch)

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare(
        "https://youtu.be/abc12345678", workspace, title="T"
    )
    assert prepared.extra["caption_type"] == "auto"


def test_segment_mapping_uses_milliseconds_and_last_segment_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Library snippets carry start/duration in seconds (float);
    TranscriptResult.segments use integer milliseconds. duration_seconds
    is the end of the last segment (Q4b: last-caption-end approximates
    speech duration; oembed has no duration field)."""
    fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=False,
        _snippets=[
            _FakeSnippet(start=0.0, duration=1.5, text="hello"),
            _FakeSnippet(start=1.5, duration=2.0, text="world"),
        ],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", False, fetched)])
    _stub_list_returning(payload, monkeypatch)

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare(
        "https://youtu.be/abc12345678", workspace, title="T"
    )
    segs = prepared.transcript.segments
    assert len(segs) == 2
    assert segs[0].start_ms == 0
    assert segs[0].end_ms == 1500
    assert segs[0].text == "hello"
    assert segs[0].speaker is None
    assert segs[1].start_ms == 1500
    assert segs[1].end_ms == 3500
    # 1.5 + 2.0 == 3.5 (end of last segment)
    assert prepared.transcript.duration_seconds == pytest.approx(3.5)


def test_no_usable_tracks_wraps_library_exception_in_no_captions_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty list → ``_pick_transcript`` raises ``NoTranscriptFound`` →
    ``prepare`` wraps it in ``NoCaptionsAvailable`` per Slice 2's
    spec. The original library exception is preserved in ``__cause__``
    so the CLI can still distinguish the two trigger reasons."""
    from youtube_transcript_api import NoTranscriptFound

    from transcriber.sources.youtube import NoCaptionsAvailable

    _stub_list_returning(_FakeTranscriptList([]), monkeypatch)

    workspace = RunWorkspace()
    with pytest.raises(NoCaptionsAvailable) as exc_info:
        YouTubeSource.prepare(
            "https://youtu.be/abc12345678", workspace, title="T"
        )
    assert isinstance(exc_info.value.__cause__, NoTranscriptFound)


# ---------------------------------------------------------------------------
# Oembed title resolution — fail-soft GET; ``responses`` mocking because
# our code constructs the URL + query params (body-shape matcher rule
# applies here, unlike the library-API calls above).
# ---------------------------------------------------------------------------


# Real verbatim response from the public oembed endpoint, retrieved 2026-05-12
# (pinned in ``specs/2026-05-12-youtube-captions-source/requirements.md``
# §"Reference calls (verbatim)").
_OEMBED_RICKROLL_BODY = (
    '{"title":"Rick Astley - Never Gonna Give You Up (Official Video) '
    '(4K Remaster)","author_name":"Rick Astley","author_url":'
    '"https://www.youtube.com/@RickAstleyYT","type":"video","height":113,'
    '"width":200,"version":"1.0","provider_name":"YouTube","provider_url":'
    '"https://www.youtube.com/","thumbnail_height":360,"thumbnail_width":480,'
    '"thumbnail_url":"https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",'
    '"html":"<iframe></iframe>"}'
)


def test_oembed_returns_video_title_on_200() -> None:
    """Happy path: 200 + the verbatim response shape from the spec →
    title extracted. Asserts the helper hits the canonical oembed URL
    with the right ``url=`` and ``format=`` query params."""
    import responses

    from transcriber.sources.youtube import _fetch_oembed_title

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://www.youtube.com/oembed",
            body=_OEMBED_RICKROLL_BODY,
            status=200,
            content_type="application/json",
            match=[
                responses.matchers.query_param_matcher(
                    {
                        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        "format": "json",
                    }
                )
            ],
        )
        title = _fetch_oembed_title("dQw4w9WgXcQ")

    assert title == (
        "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)"
    )


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_oembed_failure_status_returns_none(status: int) -> None:
    """Age-restricted (401), region-locked / privacy (403), deleted (404),
    server errors (500) all fail-soft. The captions path is unaffected;
    title falls back to the video ID stem."""
    import responses

    from transcriber.sources.youtube import _fetch_oembed_title

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://www.youtube.com/oembed",
            body="",
            status=status,
        )
        assert _fetch_oembed_title("dQw4w9WgXcQ") is None


def test_oembed_missing_title_field_returns_none() -> None:
    """200 with JSON body but no ``title`` key (unusual YouTube state)
    falls through to None — we never invent a title."""
    import responses

    from transcriber.sources.youtube import _fetch_oembed_title

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://www.youtube.com/oembed",
            body='{"author_name":"Rick Astley"}',
            status=200,
            content_type="application/json",
        )
        assert _fetch_oembed_title("dQw4w9WgXcQ") is None


def test_oembed_malformed_json_returns_none() -> None:
    """200 with non-JSON body (server-side bug or HTML error page with
    200 status) → None. We never crash on bad oembed responses."""
    import responses

    from transcriber.sources.youtube import _fetch_oembed_title

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://www.youtube.com/oembed",
            body="<html>oops</html>",
            status=200,
        )
        assert _fetch_oembed_title("dQw4w9WgXcQ") is None


@pytest.mark.parametrize(
    "hostile_title",
    [
        "../foo",
        "a/b/c.mp4",
        "back\\slash",
        ".hidden",
        "ok..bad",
    ],
)
def test_oembed_hostile_title_rejected_by_validate_title(hostile_title: str) -> None:
    """Public videos can be uploaded by anyone; a creator-controlled title
    with path-traversal characters or a leading dot must fall through to
    None — same defence as Drive Slice 2's filename probe. Without this,
    a malicious title could be written into the output filename or
    corrupt the YAML frontmatter via the literal string."""
    import json

    import responses

    from transcriber.sources.youtube import _fetch_oembed_title

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://www.youtube.com/oembed",
            body=json.dumps({"title": hostile_title}),
            status=200,
            content_type="application/json",
        )
        assert _fetch_oembed_title("dQw4w9WgXcQ") is None


def test_oembed_timeout_returns_none() -> None:
    """Network timeout → None. The captions path already succeeded
    before we got here; an oembed timeout doesn't fail the run."""
    import requests
    import responses

    from transcriber.sources.youtube import _fetch_oembed_title

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            "https://www.youtube.com/oembed",
            body=requests.exceptions.Timeout("timeout"),
        )
        assert _fetch_oembed_title("dQw4w9WgXcQ") is None


def test_prepare_calls_oembed_when_no_explicit_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: when ``title=None`` is passed, ``prepare()`` invokes
    the oembed helper and stashes its result on the PreparedTranscript.
    --title flag overrides; this test exercises the no-flag fallback."""
    fetched = _FakeFetched(
        video_id="dQw4w9WgXcQ",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", False, fetched)])
    _stub_list_returning(payload, monkeypatch)

    # Monkeypatch the oembed helper to avoid real network calls.
    monkeypatch.setattr(
        "transcriber.sources.youtube._fetch_oembed_title",
        lambda _video_id: "Oembed Resolved Title",
    )

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare("https://youtu.be/dQw4w9WgXcQ", workspace)

    assert prepared.title == "Oembed Resolved Title"


def test_prepare_skips_oembed_when_explicit_title_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--title`` from the CLI overrides oembed. The helper must NOT be
    called when an explicit title is in hand — a network round-trip the
    user paid for nothing."""
    fetched = _FakeFetched(
        video_id="dQw4w9WgXcQ",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", False, fetched)])
    _stub_list_returning(payload, monkeypatch)

    oembed_calls: list[str] = []

    def fake_oembed(video_id: str) -> str | None:
        oembed_calls.append(video_id)
        return "should-not-be-used"

    monkeypatch.setattr(
        "transcriber.sources.youtube._fetch_oembed_title", fake_oembed
    )

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare(
        "https://youtu.be/dQw4w9WgXcQ", workspace, title="Explicit"
    )

    assert prepared.title == "Explicit"
    assert oembed_calls == []


# ---------------------------------------------------------------------------
# Tenacity retry — wrap transient network errors, never the deterministic
# CouldNotRetrieveTranscript subclasses.
# ---------------------------------------------------------------------------


def _instant_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make tenacity's backoff instant in tests. Real CLI runs see the
    documented 1s/2s/4s backoff."""
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def test_retries_transient_connection_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connection error on first attempt → tenacity retries → second
    attempt succeeds. Verifies the retry decorator wraps the captions
    fetch (validation #35)."""
    import requests

    _instant_sleep(monkeypatch)

    fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", False, fetched)])

    from youtube_transcript_api import YouTubeTranscriptApi

    call_count = {"n": 0}

    def flaky_list(self: object, video_id: str) -> _FakeTranscriptList:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise requests.ConnectionError("transient blip")
        return payload

    monkeypatch.setattr(YouTubeTranscriptApi, "list", flaky_list)
    monkeypatch.setattr(
        "transcriber.sources.youtube._fetch_oembed_title", lambda _: None
    )

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare(
        "https://youtu.be/abc12345678", workspace
    )

    assert call_count["n"] == 2  # retried once
    assert prepared.extra["caption_type"] == "manual"


def test_retries_exhaust_after_3_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Three consecutive transient errors → retries exhaust → final
    exception propagates. Validation #36."""
    import requests

    _instant_sleep(monkeypatch)

    from youtube_transcript_api import YouTubeTranscriptApi

    call_count = {"n": 0}

    def always_fail(self: object, video_id: str) -> None:
        call_count["n"] += 1
        raise requests.Timeout("never recovers")

    monkeypatch.setattr(YouTubeTranscriptApi, "list", always_fail)

    workspace = RunWorkspace()
    with pytest.raises(requests.Timeout):
        YouTubeSource.prepare("https://youtu.be/abc12345678", workspace)

    assert call_count["n"] == 3  # exactly 3 attempts, then propagate


def test_no_retry_on_transcripts_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``TranscriptsDisabled`` is deterministic — the creator turned off
    captions, retrying won't help. Single attempt, then propagate.
    Validation #38. Slice 2 update: ``prepare`` now wraps it in
    ``NoCaptionsAvailable`` so the CLI can route to the audio-fallback
    decision; the original ``TranscriptsDisabled`` survives in
    ``__cause__`` and the no-retry invariant is unchanged."""
    _instant_sleep(monkeypatch)

    from youtube_transcript_api import TranscriptsDisabled, YouTubeTranscriptApi

    from transcriber.sources.youtube import NoCaptionsAvailable

    call_count = {"n": 0}

    def disabled(self: object, video_id: str) -> None:
        call_count["n"] += 1
        raise TranscriptsDisabled(video_id)

    monkeypatch.setattr(YouTubeTranscriptApi, "list", disabled)

    workspace = RunWorkspace()
    with pytest.raises(NoCaptionsAvailable) as exc_info:
        YouTubeSource.prepare("https://youtu.be/abc12345678", workspace)

    assert isinstance(exc_info.value.__cause__, TranscriptsDisabled)
    assert call_count["n"] == 1  # NOT retried


def test_retries_backoff_sleeps_1s_then_2s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #31 test-analyzer Important 3: assert tenacity actually sleeps
    1s then 2s between attempts (validation #35 "backoff asserted via
    time.sleep mock or tenacity's before_sleep hook"). Without this a
    refactor that drops the wait_exponential config to no-wait would
    pass the retry-count test silently. Locking the backoff sequence
    catches the regression."""
    import requests

    fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", False, fetched)])

    from youtube_transcript_api import YouTubeTranscriptApi

    call_count = {"n": 0}

    def flaky_list(self: object, video_id: str) -> _FakeTranscriptList:
        call_count["n"] += 1
        if call_count["n"] <= 2:  # fail twice, succeed third time
            raise requests.ConnectionError("transient")
        return payload

    monkeypatch.setattr(YouTubeTranscriptApi, "list", flaky_list)
    monkeypatch.setattr(
        "transcriber.sources.youtube._fetch_oembed_title", lambda _: None
    )

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda secs: sleeps.append(secs))

    workspace = RunWorkspace()
    YouTubeSource.prepare("https://youtu.be/abc12345678", workspace)

    assert call_count["n"] == 3
    # tenacity's wait_exponential(multiplier=1, min=1, max=4) sleeps
    # 1.0 between attempts 1→2 and 2.0 between attempts 2→3.
    assert sleeps == [1.0, 2.0], (
        f"expected backoff sequence [1.0, 2.0], got {sleeps}"
    )


def test_retries_on_fetch_call_not_just_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PR #31 test-analyzer Suggestion 3: the retry decorator wraps the
    whole captions-fetch helper, so a transient error during
    ``chosen.fetch()`` (the second library call) must retry the same
    way a transient error during ``list()`` does. Without this lock, a
    well-meaning future refactor that narrows the decoration to
    ``list()`` only would pass every other retry test silently."""
    import requests

    _instant_sleep(monkeypatch)

    fetched_payload = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )

    fetch_count = {"n": 0}

    class _FlakyFetchTranscript:
        def __init__(self) -> None:
            self.language_code = "en"
            self.is_generated = False

        def fetch(self) -> _FakeFetched:
            fetch_count["n"] += 1
            if fetch_count["n"] == 1:
                raise requests.ConnectionError("transient on fetch")
            return fetched_payload

    flaky_transcript = _FlakyFetchTranscript()
    payload = _FakeTranscriptList([flaky_transcript])  # type: ignore[list-item]
    _stub_list_returning(payload, monkeypatch)
    monkeypatch.setattr(
        "transcriber.sources.youtube._fetch_oembed_title", lambda _: None
    )

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare(
        "https://youtu.be/abc12345678", workspace
    )

    assert fetch_count["n"] == 2  # retried fetch, not just list
    assert prepared.transcript.text == "hi"


def test_retries_chunked_encoding_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex/PR-review finding: ``ChunkedEncodingError`` and other
    ``requests.RequestException`` subclasses (``TooManyRedirects``,
    ``ContentDecodingError``, ``InvalidURL``) are NOT subclasses of
    ``Timeout`` or ``ConnectionError``. A retry whitelist narrowed
    to just those two would let mid-fetch errors escape unretried
    AND surface as a raw traceback at the CLI. Widening to
    ``RequestException`` covers the family."""
    import requests

    _instant_sleep(monkeypatch)

    fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", False, fetched)])

    from youtube_transcript_api import YouTubeTranscriptApi

    call_count = {"n": 0}

    def flaky_list(self: object, video_id: str) -> _FakeTranscriptList:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise requests.exceptions.ChunkedEncodingError("connection cut")
        return payload

    monkeypatch.setattr(YouTubeTranscriptApi, "list", flaky_list)
    monkeypatch.setattr(
        "transcriber.sources.youtube._fetch_oembed_title", lambda _: None
    )

    workspace = RunWorkspace()
    YouTubeSource.prepare("https://youtu.be/abc12345678", workspace)

    assert call_count["n"] == 2  # retried — not raised as a traceback


def test_no_retry_on_ip_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """``IpBlocked`` is terminal in a single run — the IP doesn't unblock
    in 4 seconds, so retrying just wastes time. Validation #37."""
    _instant_sleep(monkeypatch)

    from youtube_transcript_api import IpBlocked, YouTubeTranscriptApi

    call_count = {"n": 0}

    def ip_blocked(self: object, video_id: str) -> None:
        call_count["n"] += 1
        raise IpBlocked(video_id)

    monkeypatch.setattr(YouTubeTranscriptApi, "list", ip_blocked)

    workspace = RunWorkspace()
    with pytest.raises(IpBlocked):
        YouTubeSource.prepare("https://youtu.be/abc12345678", workspace)

    assert call_count["n"] == 1


def test_canonical_source_uri_is_short_form_regardless_of_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The frontmatter ``source_uri`` should be the canonical
    ``https://youtu.be/<ID>`` regardless of which URL form the user
    passed — same posture as Drive Slice 2's ``drive://FILE_ID``."""
    fetched = _FakeFetched(
        video_id="abc12345678",
        language_code="en",
        is_generated=False,
        _snippets=[_FakeSnippet(start=0.0, duration=1.0, text="hi")],
    )
    payload = _FakeTranscriptList([_FakeTranscript("en", False, fetched)])
    _stub_list_returning(payload, monkeypatch)

    workspace = RunWorkspace()
    prepared = YouTubeSource.prepare(
        "https://www.youtube.com/watch?v=abc12345678&t=42",
        workspace,
        title="T",
    )
    assert prepared.original_uri == "https://youtu.be/abc12345678"


# ---------------------------------------------------------------------------
# types + exceptions (Group 1).
# AudioProbe is the slice-local return shape of probe_audio().
# NoCaptionsAvailable wraps the two captions trigger exceptions
# (TranscriptsDisabled, NoTranscriptFound) so the CLI can route them
# distinctly from the other captions-library exit-2 arms.
# ProbeDurationUnknown signals a probe response with missing or
# non-positive duration — usually live streams / premieres — that
# we can't compute a reliable cost estimate for.
# ---------------------------------------------------------------------------


def test_audio_probe_dataclass_fields() -> None:
    """AudioProbe carries the two fields the CLI reads from a yt-dlp
    extract_info(download=False) call: integer seconds duration and
    string title."""
    from transcriber.sources.youtube import AudioProbe

    probe = AudioProbe(duration=727, title="RAG Explained in 12 Minutes")
    assert probe.duration == 727
    assert probe.title == "RAG Explained in 12 Minutes"


def test_audio_probe_is_frozen() -> None:
    """AudioProbe is immutable — matches the PreparedMedia / PreparedTranscript
    pattern (frozen=True dataclasses) and prevents accidental mutation
    of the probe result between budget_check and download_audio."""
    from dataclasses import FrozenInstanceError

    from transcriber.sources.youtube import AudioProbe

    probe = AudioProbe(duration=42, title="t")
    with pytest.raises(FrozenInstanceError):
        probe.duration = 99  # type: ignore[misc]


@pytest.mark.parametrize("bad_duration", [0, -1, -3600])
def test_audio_probe_rejects_non_positive_duration(bad_duration: int) -> None:
    """The "duration > 0" invariant belongs on the type, not at one
    callsite. A future second producer (test fixture, alternate prober)
    must not be able to construct an AudioProbe that would price a
    negative-duration video at $0 in the cost estimator."""
    from transcriber.sources.youtube import AudioProbe

    with pytest.raises(ValueError, match="duration"):
        AudioProbe(duration=bad_duration, title="t")


def test_audio_probe_accepts_none_title() -> None:
    """``title`` is ``str | None`` so the fail-soft path (validate_title
    rejected the creator-controlled title) produces ``None`` rather
    than the empty-string sentinel — aligns with PreparedMedia.title
    so the bridge in ``download_audio`` is honest about absence."""
    from transcriber.sources.youtube import AudioProbe

    probe = AudioProbe(duration=10, title=None)
    assert probe.title is None


def test_no_captions_available_subclasses_exception() -> None:
    from transcriber.sources.youtube import NoCaptionsAvailable

    assert issubclass(NoCaptionsAvailable, Exception)


def test_no_captions_available_preserves_cause_chain() -> None:
    """The spec requires the original captions-library exception to live
    in ``__cause__`` so the CLI can still report the underlying reason
    (TranscriptsDisabled vs NoTranscriptFound) when generating the
    budget-aware error message."""
    from youtube_transcript_api import NoTranscriptFound

    from transcriber.sources.youtube import NoCaptionsAvailable

    original = NoTranscriptFound("abc12345678", ["en"], None)  # type: ignore[arg-type]
    try:
        raise NoCaptionsAvailable("no captions") from original
    except NoCaptionsAvailable as exc:
        assert exc.__cause__ is original


def test_probe_duration_unknown_subclasses_exception() -> None:
    from transcriber.sources.youtube import ProbeDurationUnknown

    assert issubclass(ProbeDurationUnknown, Exception)


def test_probe_duration_unknown_carries_url_in_message() -> None:
    """Live streams and premieres are the realistic cause; the exception
    message should make this actionable, so the URL goes in the message."""
    from transcriber.sources.youtube import ProbeDurationUnknown

    exc = ProbeDurationUnknown("https://youtu.be/abc12345678")
    assert "abc12345678" in str(exc)


def _build_yt_exception(name: str) -> Exception:
    """Constructor signatures vary across the captions library's exception
    hierarchy — VideoUnplayable needs 3 args, YouTubeRequestFailed needs
    an HTTPError, etc. Mirrors the helper in test_cli.py."""
    import requests as _requests
    import youtube_transcript_api as y

    video_id = "abc12345678"
    if name == "VideoUnplayable":
        return y.VideoUnplayable(video_id, "test reason", [])
    if name == "YouTubeRequestFailed":
        return y.YouTubeRequestFailed(
            video_id, _requests.exceptions.HTTPError("503 transient")
        )
    cls = getattr(y, name)
    return cls(video_id)  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "exception_name",
    [
        "VideoUnavailable",
        "VideoUnplayable",
        "InvalidVideoId",
        "AgeRestricted",
        "PoTokenRequired",
        "RequestBlocked",
        "FailedToCreateConsentCookie",
        "IpBlocked",
        "YouTubeRequestFailed",
    ],
)
def test_prepare_propagates_non_trigger_captions_errors_unchanged(
    exception_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Slice 2 trigger condition is conservative: only
    ``TranscriptsDisabled`` and ``NoTranscriptFound`` flow into the
    audio-fallback decision. Every other captions-library exception
    preserves Slice 1's behaviour 1:1 — same type, no
    ``NoCaptionsAvailable`` wrapping. The CLI's matrix maps these to
    their existing exit codes."""
    _instant_sleep(monkeypatch)

    from youtube_transcript_api import YouTubeTranscriptApi

    from transcriber.sources.youtube import NoCaptionsAvailable

    exc_instance = _build_yt_exception(exception_name)

    def raise_it(self: object, video_id: str) -> None:
        raise exc_instance

    monkeypatch.setattr(YouTubeTranscriptApi, "list", raise_it)

    workspace = RunWorkspace()
    with pytest.raises(type(exc_instance)) as exc_info:
        YouTubeSource.prepare("https://youtu.be/abc12345678", workspace)

    # Negative assertion: must NOT have been wrapped.
    assert not isinstance(exc_info.value, NoCaptionsAvailable)


def test_source_kind_literal_includes_youtube_audio() -> None:
    """Type-system smoke: the Literal must accept ``youtube_audio``
    so PreparedMedia(kind="youtube_audio", ...) typechecks. Asserting on
    typing.get_args avoids reaching into mypy at test time."""
    from typing import get_args

    from transcriber.sources.base import SourceKind

    assert "youtube_audio" in get_args(SourceKind)


# ---------------------------------------------------------------------------
# yt-dlp helpers (Group 3).
# YoutubeDL is mocked via monkeypatch at the yt_dlp module path because
# the helpers do a local ``from yt_dlp import YoutubeDL`` (deferred-
# import pattern for module weight). The helpers don't construct an
# outbound HTTP request body themselves — yt-dlp does — so we don't
# need the ``responses`` body-shape matcher; class-level monkeypatching
# is the right granularity.
# ---------------------------------------------------------------------------


class _FakeYoutubeDL:
    """Drop-in replacement for ``yt_dlp.YoutubeDL`` honouring the
    context-manager + ``extract_info(url, download=...)`` surface.

    Per-test behaviour: set class attributes ``probe_info`` (returned
    for ``download=False``) and ``download_info`` (returned for
    ``download=True``). ``raise_on_probe`` / ``raise_on_download``
    override to raise.
    """

    captured_opts: dict[str, Any] = {}
    probe_info: dict[str, Any] = {}
    download_info: dict[str, Any] = {}
    raise_on_probe: Exception | None = None
    raise_on_download: Exception | None = None

    def __init__(self, opts: dict[str, Any]) -> None:
        _FakeYoutubeDL.captured_opts = opts

    def __enter__(self) -> _FakeYoutubeDL:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def extract_info(
        self, url: str, download: bool = True
    ) -> dict[str, Any]:
        if download:
            if _FakeYoutubeDL.raise_on_download is not None:
                raise _FakeYoutubeDL.raise_on_download
            return _FakeYoutubeDL.download_info
        if _FakeYoutubeDL.raise_on_probe is not None:
            raise _FakeYoutubeDL.raise_on_probe
        return _FakeYoutubeDL.probe_info


@pytest.fixture
def _yt_dlp_mock(monkeypatch: pytest.MonkeyPatch) -> type[_FakeYoutubeDL]:
    """Reset class state between tests and patch yt_dlp.YoutubeDL."""
    _FakeYoutubeDL.captured_opts = {}
    _FakeYoutubeDL.probe_info = {}
    _FakeYoutubeDL.download_info = {}
    _FakeYoutubeDL.raise_on_probe = None
    _FakeYoutubeDL.raise_on_download = None
    monkeypatch.setattr("yt_dlp.YoutubeDL", _FakeYoutubeDL)
    return _FakeYoutubeDL


def test_ydl_opts_base_matches_spec_verbatim() -> None:
    """CLAUDE.md vendor-API guardrail: the ``_YDL_OPTS_BASE`` constant
    in production code must match the dict in
    ``specs/2026-05-13-youtube-audio-fallback/requirements.md``
    ``## Reference calls (verbatim)`` byte-for-byte. This pins the
    seven keys (quiet, no_warnings, format, retries, fragment_retries,
    socket_timeout, noplaylist) against the ctx7 retrieval; a typo or
    silent value change breaks this test, not the YouTube production
    UX (cf. PR #12's two-bug lesson)."""
    from transcriber.sources.youtube import _YDL_OPTS_BASE

    assert _YDL_OPTS_BASE == {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "noplaylist": True,
    }


def test_probe_metadata_returns_audio_probe(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """Happy path: extract_info(download=False) → AudioProbe(duration,
    title). Duration is integer seconds (yt-dlp returns int or float;
    we coerce)."""
    from transcriber.sources.youtube import AudioProbe, _probe_metadata

    _yt_dlp_mock.probe_info = {
        "title": "Test Video",
        "duration": 727,
    }

    probe = _probe_metadata("https://youtu.be/abc12345678")

    assert isinstance(probe, AudioProbe)
    assert probe.duration == 727
    assert probe.title == "Test Video"


def test_probe_metadata_coerces_float_duration_to_int(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """yt-dlp can return ``duration`` as float in some extractors. The
    AudioProbe contract is integer seconds (Q3 (c) cost estimate is
    rounded to int); coerce here so downstream callers don't need to."""
    from transcriber.sources.youtube import _probe_metadata

    _yt_dlp_mock.probe_info = {"title": "Test", "duration": 727.4}

    probe = _probe_metadata("https://youtu.be/abc12345678")
    assert probe.duration == 727
    assert isinstance(probe.duration, int)


def test_probe_metadata_raises_probe_duration_unknown_on_none(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """Live streams / premieres can return ``duration=None``. Without
    duration we can't compute a reliable cost estimate, so raise
    rather than show a fake $0 cost prompt (spec edge case)."""
    from transcriber.sources.youtube import (
        ProbeDurationUnknown,
        _probe_metadata,
    )

    _yt_dlp_mock.probe_info = {"title": "Live!", "duration": None}

    with pytest.raises(ProbeDurationUnknown):
        _probe_metadata("https://youtu.be/abc12345678")


def test_probe_metadata_raises_probe_duration_unknown_on_zero(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """``duration == 0`` is the other "no usable duration" sentinel
    yt-dlp can emit (e.g., for malformed metadata). Same treatment."""
    from transcriber.sources.youtube import (
        ProbeDurationUnknown,
        _probe_metadata,
    )

    _yt_dlp_mock.probe_info = {"title": "Broken", "duration": 0}

    with pytest.raises(ProbeDurationUnknown):
        _probe_metadata("https://youtu.be/abc12345678")


def test_probe_metadata_handles_missing_title(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """If ``title`` is missing or None, AudioProbe carries ``None`` so
    the CLI's filename derivation falls back to ``video_id`` cleanly.
    ``None`` (not ``""``) matches PreparedMedia.title's sentinel so the
    bridge in ``download_audio`` doesn't conflate "no title returned"
    with "title set to empty by the user"."""
    from transcriber.sources.youtube import _probe_metadata

    _yt_dlp_mock.probe_info = {"title": None, "duration": 100}
    probe = _probe_metadata("https://youtu.be/abc12345678")
    assert probe.title is None


def test_probe_metadata_raises_probe_duration_unknown_on_none_info(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """yt-dlp can return ``None`` from ``extract_info`` in edge cases
    (no info extracted). Without a guard, ``info.get("duration")``
    blows up with ``AttributeError`` — escaping the CLI's catch tuple
    and surfacing a raw traceback. Route through the existing
    "duration unknown" exit instead."""
    from transcriber.sources.youtube import (
        ProbeDurationUnknown,
        _probe_metadata,
    )

    _yt_dlp_mock.probe_info = None  # type: ignore[assignment]

    with pytest.raises(ProbeDurationUnknown):
        _probe_metadata("https://youtu.be/abc12345678")


def test_probe_metadata_raises_probe_duration_unknown_on_string_duration(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """Some yt-dlp extractors emit ``duration`` as a string. Without an
    isinstance guard, ``duration <= 0`` raises ``TypeError``. Treat
    non-numeric durations as "duration unknown" so the CLI maps to
    the user-actionable exit 2."""
    from transcriber.sources.youtube import (
        ProbeDurationUnknown,
        _probe_metadata,
    )

    _yt_dlp_mock.probe_info = {"title": "x", "duration": "3600"}

    with pytest.raises(ProbeDurationUnknown):
        _probe_metadata("https://youtu.be/abc12345678")


def test_probe_metadata_raises_probe_duration_unknown_on_negative_duration(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """Defensive — yt-dlp shouldn't emit a negative duration but a
    broken extractor could. Treat the same as ``None`` / ``0``."""
    from transcriber.sources.youtube import (
        ProbeDurationUnknown,
        _probe_metadata,
    )

    _yt_dlp_mock.probe_info = {"title": "x", "duration": -10}

    with pytest.raises(ProbeDurationUnknown):
        _probe_metadata("https://youtu.be/abc12345678")


@pytest.mark.parametrize(
    "hostile_title",
    [
        "../outside",
        "subdir/name",
        "C:\\windows\\system32",
        ".",
        "..",
        "..\\evilevil",
    ],
)
def test_probe_metadata_validates_title_against_path_traversal(
    hostile_title: str, _yt_dlp_mock: type[_FakeYoutubeDL]
) -> None:
    """``probe.title`` is creator-controlled YouTube metadata that the
    CLI uses as the default filename stem after only whitespace
    collapsing. An unvalidated probe title like ``../outside`` could
    redirect the transcript write outside ``settings.output_dir``;
    fail-soft to ``None`` so the video_id stem is used instead
    (mirrors the oembed probe's behaviour)."""
    from transcriber.sources.youtube import _probe_metadata

    _yt_dlp_mock.probe_info = {"title": hostile_title, "duration": 100}
    probe = _probe_metadata("https://youtu.be/abc12345678")
    assert probe.title is None, (
        f"hostile title {hostile_title!r} must be rejected, "
        f"got {probe.title!r}"
    )


def test_probe_metadata_keeps_safe_titles_with_whitespace_and_unicode(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """Validation must not over-reject legitimate titles. A title with
    spaces, punctuation, or unicode passes through unchanged (or
    slightly normalised by validate_title's canonical-NFC pass)."""
    from transcriber.sources.youtube import _probe_metadata

    _yt_dlp_mock.probe_info = {
        "title": "RAG Explained in 12 Minutes — Part 1",
        "duration": 727,
    }
    probe = _probe_metadata("https://youtu.be/abc12345678")
    assert probe.title is not None
    assert "RAG Explained in 12 Minutes" in probe.title


def test_probe_metadata_passes_base_opts(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """The probe call constructs ``YoutubeDL(_YDL_OPTS_BASE)`` directly —
    no per-call overrides, no extra keys. Asserting captured_opts
    matches _YDL_OPTS_BASE locks the byte-for-byte parity between the
    spec reference and the production call."""
    from transcriber.sources.youtube import _YDL_OPTS_BASE, _probe_metadata

    _yt_dlp_mock.probe_info = {"title": "T", "duration": 10}
    _probe_metadata("https://youtu.be/abc12345678")
    assert _yt_dlp_mock.captured_opts == _YDL_OPTS_BASE


def test_probe_metadata_propagates_extractor_error(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """yt-dlp's ``ExtractorError`` (video unavailable, age-restricted,
    geo-restricted) propagates straight to the CLI for exit-code
    mapping. The helper does NOT swallow or wrap."""
    from yt_dlp.utils import ExtractorError

    from transcriber.sources.youtube import _probe_metadata

    _yt_dlp_mock.raise_on_probe = ExtractorError("video unavailable")

    with pytest.raises(ExtractorError):
        _probe_metadata("https://youtu.be/abc12345678")


def test_download_audio_returns_path_from_yt_dlp(
    _yt_dlp_mock: type[_FakeYoutubeDL], tmp_path: object
) -> None:
    """yt-dlp picks the extension (m4a / opus / webm); we read it from
    ``info["requested_downloads"][0]["filepath"]`` rather than guessing.
    Returned Path is the on-disk artifact PreparedMedia.local_path
    will reference."""
    from pathlib import Path

    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.youtube import _download_audio

    workspace = RunWorkspace()
    _yt_dlp_mock.download_info = {
        "requested_downloads": [
            {"filepath": str(workspace.path("audio.m4a"))}
        ]
    }

    path = _download_audio("https://youtu.be/abc12345678", workspace)

    assert isinstance(path, Path)
    assert path == workspace.path("audio.m4a")


def test_download_audio_augments_base_opts_with_outtmpl(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """The download call layers ``outtmpl`` on top of ``_YDL_OPTS_BASE``
    so yt-dlp writes into the workspace. Asserts the merge: every key
    from base is present unchanged AND ``outtmpl`` points into the
    workspace path."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.youtube import _YDL_OPTS_BASE, _download_audio

    workspace = RunWorkspace()
    _yt_dlp_mock.download_info = {
        "requested_downloads": [
            {"filepath": str(workspace.path("audio.m4a"))}
        ]
    }
    _download_audio("https://youtu.be/abc12345678", workspace)

    # Every base key carried through unchanged.
    for key, value in _YDL_OPTS_BASE.items():
        assert _yt_dlp_mock.captured_opts[key] == value
    # And outtmpl points into the workspace.
    assert _yt_dlp_mock.captured_opts["outtmpl"].startswith(
        str(workspace.root)
    )


def test_download_audio_propagates_download_error(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """Network exhaustion after yt-dlp's retries surfaces as
    ``DownloadError``; helper propagates for CLI exit-3 mapping."""
    from yt_dlp.utils import DownloadError

    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.youtube import _download_audio

    workspace = RunWorkspace()
    _yt_dlp_mock.raise_on_download = DownloadError(
        "network failure after retries"
    )

    with pytest.raises(DownloadError):
        _download_audio("https://youtu.be/abc12345678", workspace)


@pytest.mark.parametrize(
    "broken_info",
    [
        pytest.param({}, id="missing-requested_downloads"),
        pytest.param({"requested_downloads": []}, id="empty-list"),
        pytest.param(
            {"requested_downloads": [{}]}, id="missing-filepath"
        ),
    ],
)
def test_download_audio_raises_download_error_on_malformed_yt_dlp_response(
    broken_info: dict[str, Any], _yt_dlp_mock: type[_FakeYoutubeDL]
) -> None:
    """If yt-dlp's ``extract_info(download=True)`` returns a dict
    without a usable ``requested_downloads[0]["filepath"]``, the raw
    ``KeyError`` / ``IndexError`` would escape the CLI's
    ``(YoutubeDLError, OSError)`` catch and the user would see a
    raw traceback — and miss the "(no AssemblyAI charge incurred)"
    reassurance. Surface as a yt-dlp ``DownloadError`` so the
    existing catch + exit-3 mapping fire."""
    from yt_dlp.utils import DownloadError

    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.youtube import _download_audio

    workspace = RunWorkspace()
    _yt_dlp_mock.download_info = broken_info

    with pytest.raises(DownloadError, match="abc12345678"):
        _download_audio("https://youtu.be/abc12345678", workspace)


# ---------------------------------------------------------------------------
# YouTubeSource.probe_audio / download_audio (Group 4).
# Thin wrappers over the module helpers; the surface the CLI calls.
# ---------------------------------------------------------------------------


def test_probe_audio_returns_audio_probe(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    from transcriber.sources.youtube import AudioProbe

    _yt_dlp_mock.probe_info = {"title": "Test Video", "duration": 600}

    probe = YouTubeSource.probe_audio("https://youtu.be/abc12345678")

    assert isinstance(probe, AudioProbe)
    assert probe.duration == 600
    assert probe.title == "Test Video"


def test_probe_audio_accepts_any_url_form(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """The eight URL forms supported by ``_extract_video_id`` are all
    valid here too — Shorts (the most common captionless content
    type) goes through the same probe path."""
    _yt_dlp_mock.probe_info = {"title": "Shorts!", "duration": 30}

    probe = YouTubeSource.probe_audio(
        "https://www.youtube.com/shorts/abc12345678"
    )
    assert probe.duration == 30


def test_probe_audio_raises_source_input_error_on_invalid_url(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """Parser-level rejection happens before yt-dlp is even invoked."""
    with pytest.raises(SourceInputError):
        YouTubeSource.probe_audio("not-a-youtube-url")


def test_download_audio_returns_prepared_media_with_correct_shape(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """The PreparedMedia construction is the single hottest spot in
    this slice — gets every field right or the downstream pipeline
    breaks at type-check (kind), construction (workspace), or render
    (title/extra) time. Pins all fields."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.base import PreparedMedia
    from transcriber.sources.youtube import AudioProbe

    workspace = RunWorkspace()
    _yt_dlp_mock.download_info = {
        "requested_downloads": [
            {"filepath": str(workspace.path("audio.m4a"))}
        ]
    }
    probe = AudioProbe(duration=727, title="RAG Explained")

    media = YouTubeSource.download_audio(
        "https://youtu.be/abc12345678", workspace, probe
    )

    assert isinstance(media, PreparedMedia)
    assert media.kind == "youtube_audio"
    assert media.original_uri == "https://youtu.be/abc12345678"
    assert media.local_path == workspace.path("audio.m4a")
    assert media.remote_url is None
    assert media.title == "RAG Explained"
    assert media.duration_seconds == 727.0
    assert media.workspace is workspace


def test_download_audio_extra_carries_video_id_and_stringified_probe_duration(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """``extra`` is typed ``dict[str, str]`` — probe_duration is
    stringified. video_id supports the filename-fallback path in the
    CLI when ``media.title`` is empty."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.youtube import AudioProbe

    workspace = RunWorkspace()
    _yt_dlp_mock.download_info = {
        "requested_downloads": [
            {"filepath": str(workspace.path("audio.m4a"))}
        ]
    }
    probe = AudioProbe(duration=727, title="t")

    media = YouTubeSource.download_audio(
        "https://youtu.be/abc12345678", workspace, probe
    )

    assert media.extra == {
        "video_id": "abc12345678",
        "probe_duration": "727",
    }


def test_download_audio_canonical_original_uri_regardless_of_input_form(
    _yt_dlp_mock: type[_FakeYoutubeDL],
) -> None:
    """``original_uri`` is the canonical ``https://youtu.be/<ID>`` form
    regardless of the input URL shape — matches Slice 1's contract
    so the frontmatter ``source_uri`` field is stable. Also the spec
    contract that the formatter's ``_source_uri`` arm reads this for
    ``youtube_audio`` (NOT ``file://``)."""
    from transcriber.core.workspace import RunWorkspace
    from transcriber.sources.youtube import AudioProbe

    workspace = RunWorkspace()
    _yt_dlp_mock.download_info = {
        "requested_downloads": [
            {"filepath": str(workspace.path("audio.m4a"))}
        ]
    }
    probe = AudioProbe(duration=10, title="t")

    media = YouTubeSource.download_audio(
        "https://www.youtube.com/watch?v=abc12345678&t=42",
        workspace,
        probe,
    )

    assert media.original_uri == "https://youtu.be/abc12345678"
