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


def test_no_usable_tracks_raises_library_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty list (or one with only auto-translated tracks we'd never
    fetch) → NoTranscriptFound. CLI maps this to exit 2 with the
    documented no-captions message + issue #21 pointer."""
    from youtube_transcript_api import NoTranscriptFound

    _stub_list_returning(_FakeTranscriptList([]), monkeypatch)

    workspace = RunWorkspace()
    with pytest.raises(NoTranscriptFound):
        YouTubeSource.prepare(
            "https://youtu.be/abc12345678", workspace, title="T"
        )


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
    Validation #38."""
    _instant_sleep(monkeypatch)

    from youtube_transcript_api import TranscriptsDisabled, YouTubeTranscriptApi

    call_count = {"n": 0}

    def disabled(self: object, video_id: str) -> None:
        call_count["n"] += 1
        raise TranscriptsDisabled(video_id)

    monkeypatch.setattr(YouTubeTranscriptApi, "list", disabled)

    workspace = RunWorkspace()
    with pytest.raises(TranscriptsDisabled):
        YouTubeSource.prepare("https://youtu.be/abc12345678", workspace)

    assert call_count["n"] == 1  # NOT retried


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
