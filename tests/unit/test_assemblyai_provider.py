"""Tests for ``providers/assemblyai.py`` via mocked HTTP (``responses``).

Covers cases 1-9 in Slice 1's validation.md (happy path, transient retry
success, retry exhaustion, immediate-fail on permanent 4xx, polling
completion after N polls, polling-error response, polling wall-clock
timeout, ``on_job_id`` callback fires exactly once after create-transcript)
plus Slice 2's URL-passthrough cases (audio_url body, no-upload, polling
error on the passthrough branch).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import requests
import responses
from responses import matchers

from transcriber.core.workspace import RunWorkspace
from transcriber.providers.assemblyai import API_BASE, AssemblyAIProvider
from transcriber.providers.base import ProviderError
from transcriber.sources.base import PreparedMedia


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tenacity ``wait_exponential`` would add seconds per retry; mute it
    so retry tests don't actually wait."""
    import time

    monkeypatch.setattr(time, "sleep", lambda _seconds: None)


@pytest.fixture(autouse=True)
def _api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """The provider's ``_api_headers`` raises if no key is set; satisfy it
    in every test."""
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")


@pytest.fixture
def rsps() -> Iterator[responses.RequestsMock]:
    """``assert_all_requests_are_fired=False`` because some tests
    deliberately short-circuit before all mocked routes are consumed
    (timeout, retry-exhaustion)."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as r:
        yield r


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    p = tmp_path / "audio.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    return p


@pytest.fixture
def local_media(wav: Path) -> PreparedMedia:
    """A local-source PreparedMedia wrapping the test WAV.

    Slice 2 changed the provider signature from ``transcribe(wav_path)``
    to ``transcribe(media)``. Tests construct the media here once and
    pass it through; the workspace cleanup is handled per-test via the
    fixture's natural lifetime.
    """
    return PreparedMedia(
        kind="local",
        original_uri=str(wav),
        local_path=wav,
        title=None,
        duration_seconds=None,
        workspace=RunWorkspace(),
        extra={},
    )


def _completed_payload(job_id: str = "abc123") -> dict[str, object]:
    return {
        "id": job_id,
        "status": "completed",
        "text": "hello world",
        "audio_duration": 12.5,
        "language_code": "en",
        "speech_model": "universal-3-pro",
        "utterances": [
            {"start": 0, "end": 12500, "text": "hello world", "speaker": "A"},
        ],
    }


def test_happy_path(rsps: responses.RequestsMock, local_media: PreparedMedia) -> None:
    """Case 1: upload + create + poll-completed → populated TranscriptResult."""
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "https://cdn/u/x"}, status=200)
    rsps.post(f"{API_BASE}/transcript", json={"id": "abc123", "status": "queued"}, status=200)
    rsps.get(f"{API_BASE}/transcript/abc123", json=_completed_payload(), status=200)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    result = provider.transcribe(
        local_media, language="en", diarize=True, speech_model="universal-3-pro"
    )

    assert result.text == "hello world"
    assert result.job_id == "abc123"
    assert result.duration_seconds == 12.5
    assert result.language == "en"
    assert result.model == "universal-3-pro"
    assert len(result.segments) == 1
    assert result.segments[0].speaker == "A"


def test_create_transcript_body_uses_plural_speech_models(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Regression: AssemblyAI deprecated singular ``speech_model`` in favour
    of plural ``speech_models`` (array). The provider must send the new
    shape so the API doesn't reject the request with HTTP 400."""
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "https://cdn/u/x"}, status=200)
    rsps.post(
        f"{API_BASE}/transcript",
        match=[
            matchers.json_params_matcher(
                {
                    "audio_url": "https://cdn/u/x",
                    "speech_models": ["universal-3-pro"],
                    "speaker_labels": True,
                }
            ),
        ],
        json={"id": "abc123", "status": "queued"},
        status=200,
    )
    rsps.get(f"{API_BASE}/transcript/abc123", json=_completed_payload(), status=200)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    provider.transcribe(local_media, language=None, diarize=True, speech_model="universal-3-pro")


def test_upload_429_then_200_succeeds(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 2: first call 429, second 200 → succeeds via tenacity retry."""
    rsps.post(f"{API_BASE}/upload", json={"error": "rate limited"}, status=429)
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "https://cdn/u/x"}, status=200)
    rsps.post(f"{API_BASE}/transcript", json={"id": "j", "status": "queued"}, status=200)
    rsps.get(f"{API_BASE}/transcript/j", json=_completed_payload(job_id="j"), status=200)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    result = provider.transcribe(
        local_media, language=None, diarize=True, speech_model="universal-3-pro"
    )
    assert result.job_id == "j"


def test_upload_three_429s_fails(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 3: three consecutive 429s → ProviderError after retry exhaustion.

    Tightened from a generic ``Exception`` match: the retry-exhaustion path
    must raise ``ProviderError`` so the CLI's exit-code matrix maps it to
    exit 3. A bare tenacity decorator with ``reraise=True`` would propagate
    the underlying ``_Transient`` and the CLI would emit an uncaught
    traceback instead — exactly the bug the ``_with_retry`` wrapper closes.
    """
    for _ in range(3):
        rsps.post(f"{API_BASE}/upload", json={"error": "rate limited"}, status=429)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with pytest.raises(ProviderError) as exc:
        provider.transcribe(
            local_media, language=None, diarize=False, speech_model="universal-3-pro"
        )

    assert "after retries" in str(exc.value)
    # Exactly 3 upload calls were registered; if a 4th had been attempted, it
    # would raise ConnectionError because no mock matches it.
    assert len(rsps.calls) == 3


def test_upload_timeout_exhausted_raises_provider_error(
    rsps: responses.RequestsMock,
    local_media: PreparedMedia,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defence against the same class for ``requests.Timeout``: the
    retry-exhaustion path must surface as ``ProviderError`` regardless of
    which transient exception class drove the retries."""

    def _always_timeout(*_args: object, **_kwargs: object) -> object:
        raise requests.Timeout("simulated timeout")

    monkeypatch.setattr("transcriber.providers.assemblyai.requests.post", _always_timeout)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with pytest.raises(ProviderError) as exc:
        provider.transcribe(
            local_media, language=None, diarize=False, speech_model="universal-3-pro"
        )

    assert "after retries" in str(exc.value)


def test_upload_401_no_retry(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 4: 401 → fails immediately, NO retry."""
    rsps.post(f"{API_BASE}/upload", json={"error": "auth failed"}, status=401)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with pytest.raises(ProviderError) as exc:
        provider.transcribe(
            local_media, language=None, diarize=False, speech_model="universal-3-pro"
        )

    assert "401" in str(exc.value)
    assert len(rsps.calls) == 1  # No retry on permanent 4xx.


def test_upload_422_no_retry(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 5: other 4xx (validation) → fails immediately."""
    rsps.post(f"{API_BASE}/upload", json={"error": "bad audio"}, status=422)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with pytest.raises(ProviderError) as exc:
        provider.transcribe(
            local_media, language=None, diarize=False, speech_model="universal-3-pro"
        )

    assert "422" in str(exc.value)
    assert len(rsps.calls) == 1


def test_polling_completes_after_n_polls(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 6: poll returns 'completed' after N — assert poll count."""
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "u"}, status=200)
    rsps.post(f"{API_BASE}/transcript", json={"id": "j", "status": "queued"}, status=200)
    rsps.get(f"{API_BASE}/transcript/j", json={"id": "j", "status": "queued"}, status=200)
    rsps.get(f"{API_BASE}/transcript/j", json={"id": "j", "status": "processing"}, status=200)
    rsps.get(f"{API_BASE}/transcript/j", json=_completed_payload(job_id="j"), status=200)

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    result = provider.transcribe(
        local_media, language=None, diarize=True, speech_model="universal-3-pro"
    )

    # 1 upload + 1 create + 3 polls = 5 total calls.
    assert len(rsps.calls) == 5
    assert result.job_id == "j"


def test_polling_status_error_surfaces_message(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 7: poll returns status='error' → ProviderError carries message."""
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "u"}, status=200)
    rsps.post(f"{API_BASE}/transcript", json={"id": "j", "status": "queued"}, status=200)
    rsps.get(
        f"{API_BASE}/transcript/j",
        json={"id": "j", "status": "error", "error": "Audio too short to transcribe"},
        status=200,
    )

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with pytest.raises(ProviderError) as exc:
        provider.transcribe(
            local_media, language=None, diarize=False, speech_model="universal-3-pro"
        )

    msg = str(exc.value)
    assert "Audio too short" in msg
    assert "j" in msg  # job ID surfaces for recovery


def test_polling_timeout_with_job_id(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 8: polling exceeds wall-clock cap → ProviderError with job ID.

    Sleep is wired to advance the fake clock by more than ``max_wait_seconds``
    so the deadline check fires deterministically without real waiting.
    """
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "u"}, status=200)
    rsps.post(f"{API_BASE}/transcript", json={"id": "stuck-job", "status": "queued"}, status=200)
    # Multiple "queued" responses; only the first 1-2 will be consumed.
    for _ in range(5):
        rsps.get(
            f"{API_BASE}/transcript/stuck-job",
            json={"id": "stuck-job", "status": "queued"},
            status=200,
        )

    fake_time = [0.0]

    def fake_clock() -> float:
        return fake_time[0]

    def fake_sleep(_secs: float) -> None:
        # Advance past the deadline so the next loop check fails.
        fake_time[0] += 100.0

    provider = AssemblyAIProvider(
        max_wait_seconds=10.0,
        poll_interval_seconds=1.0,
        sleep=fake_sleep,
        clock=fake_clock,
    )

    with pytest.raises(ProviderError) as exc:
        provider.transcribe(
            local_media, language=None, diarize=False, speech_model="universal-3-pro"
        )

    msg = str(exc.value)
    assert "stuck-job" in msg
    assert "exceeded" in msg.lower()


def test_on_job_id_fires_once_after_create(
    rsps: responses.RequestsMock, local_media: PreparedMedia
) -> None:
    """Case 9: ``on_job_id`` callback fires exactly once."""
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "u"}, status=200)
    rsps.post(
        f"{API_BASE}/transcript",
        json={"id": "callback-job", "status": "queued"},
        status=200,
    )
    rsps.get(
        f"{API_BASE}/transcript/callback-job",
        json=_completed_payload(job_id="callback-job"),
        status=200,
    )

    captured: list[str] = []
    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    provider.transcribe(
        local_media,
        language=None,
        diarize=True,
        speech_model="universal-3-pro",
        on_job_id=lambda jid: captured.append(jid),
    )

    assert captured == ["callback-job"]


def test_polling_unknown_status_logs_warning_and_continues(
    rsps: responses.RequestsMock,
    local_media: PreparedMedia,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unknown / future statuses should not silently spin until deadline.
    Log at WARNING and keep polling so a stuck or future-status job is
    visible to the operator within the first few poll cycles."""
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "u"}, status=200)
    rsps.post(f"{API_BASE}/transcript", json={"id": "unk-job", "status": "queued"}, status=200)
    rsps.get(
        f"{API_BASE}/transcript/unk-job",
        json={"id": "unk-job", "status": "future-not-yet-known"},
        status=200,
    )
    rsps.get(
        f"{API_BASE}/transcript/unk-job",
        json=_completed_payload(job_id="unk-job"),
        status=200,
    )

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with caplog.at_level("WARNING", logger="transcriber.providers.assemblyai"):
        result = provider.transcribe(
            local_media, language=None, diarize=False, speech_model="universal-3-pro"
        )

    assert result.job_id == "unk-job"
    assert any(
        "unknown status" in rec.message and "future-not-yet-known" in rec.message
        for rec in caplog.records
    )


def test_segments_fallback_logs_warning_when_no_utterances_or_paragraphs(
    rsps: responses.RequestsMock,
    local_media: PreparedMedia,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When AssemblyAI returns text but no utterance/paragraph structure,
    the result is a single full-duration segment — looks valid but is
    effectively undiarized and unsegmented. Log a WARNING so the user
    doesn't quietly accept a degraded transcript."""
    rsps.post(f"{API_BASE}/upload", json={"upload_url": "u"}, status=200)
    rsps.post(
        f"{API_BASE}/transcript",
        json={"id": "fallback-job", "status": "queued"},
        status=200,
    )
    rsps.get(
        f"{API_BASE}/transcript/fallback-job",
        json={
            "id": "fallback-job",
            "status": "completed",
            "text": "lots of text here",
            "audio_duration": 12.5,
            "language_code": "en",
        },
        status=200,
    )

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with caplog.at_level("WARNING", logger="transcriber.providers.assemblyai"):
        result = provider.transcribe(
            local_media, language=None, diarize=True, speech_model="universal-3-pro"
        )

    assert len(result.segments) == 1
    assert result.segments[0].text == "lots of text here"
    assert any(
        "no utterances or paragraphs" in rec.message and "fallback-job" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Slice 2: URL-passthrough branch (media.remote_url is set, no /upload).
# ---------------------------------------------------------------------------


def test_transcribe_passthrough_uses_audio_url_and_skips_upload(
    rsps: responses.RequestsMock,
) -> None:
    """Passthrough path: media.remote_url set → POST /transcript with
    audio_url=..., NO call to /upload. Body shape asserted via
    json_params_matcher per CLAUDE.md guardrail."""
    workspace = RunWorkspace()
    media = PreparedMedia(
        kind="google_drive",
        original_uri="drive://X",
        local_path=None,
        remote_url="https://drive.usercontent.google.com/download?id=X&export=download&confirm=t",
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
                    "audio_url": "https://drive.usercontent.google.com/download?id=X&export=download&confirm=t",
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
    upload_calls = [c for c in rsps.calls if "/upload" in (c.request.url or "")]
    assert len(upload_calls) == 0


def test_transcribe_passthrough_polling_error_surfaces_message(
    rsps: responses.RequestsMock,
) -> None:
    """Validation case 18 (review I1): when AssemblyAI's polling status
    returns ``error`` on the URL-passthrough branch (e.g., Drive sharing
    was revoked between command issue and AssemblyAI fetch, or the file
    is video-only), the provider must raise ``ProviderError`` with
    AssemblyAI's error message preserved. CLI maps to exit 3.

    Also covers edge cases 1 (sharing revoked) and 2 (video-only file)
    from validation.md §"Edge cases / what could break".
    """
    workspace = RunWorkspace()
    media = PreparedMedia(
        kind="google_drive",
        original_uri="drive://X",
        local_path=None,
        remote_url="https://drive.usercontent.google.com/download?id=X&export=download&confirm=t",
        title=None,
        duration_seconds=None,
        workspace=workspace,
        extra={"drive_file_id": "X"},
    )

    rsps.post(f"{API_BASE}/upload", json={"upload_url": "should-not-fire"}, status=200)
    # CLAUDE.md guardrail (PR #13): every body-bearing mock must use
    # json_params_matcher so a wire-shape regression in the passthrough
    # branch surfaces here. Without this, a refactor that drops audio_url
    # in the polling-error code path would only be caught by the happy-
    # path test — guardrail intent is per-mock body locking.
    rsps.post(
        f"{API_BASE}/transcript",
        match=[
            matchers.json_params_matcher(
                {
                    "audio_url": "https://drive.usercontent.google.com/download?id=X&export=download&confirm=t",
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
        json={
            "id": "drive-job",
            "status": "error",
            "error": "Unable to fetch audio_url: 403 Forbidden",
        },
        status=200,
    )

    provider = AssemblyAIProvider(poll_interval_seconds=0.0)
    with pytest.raises(ProviderError) as excinfo:
        provider.transcribe(
            media, language=None, diarize=True, speech_model="universal-3-pro"
        )
    assert "Unable to fetch audio_url" in str(excinfo.value)
    upload_calls = [c for c in rsps.calls if "/upload" in (c.request.url or "")]
    assert len(upload_calls) == 0
