"""AssemblyAI provider implementation.

Slice 1 talks to AssemblyAI's v2 REST API directly (``requests`` +
``tenacity``) rather than the official SDK. The SDK has its own retry
logic that would compound with ours; the spec's test cases ("first 429
then 200 succeeds", "three 429s fail after retry exhaustion", "401 fails
immediately") are HTTP-level assertions that are far cleaner to verify
against a thin client we control.

Phase 5 generalizes this behind the provider registry and adds the
per-provider cost-estimation hook.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from transcriber.providers.base import (
    ProviderError,
    Segment,
    TranscriptionProvider,
    TranscriptResult,
    _noop,
)

logger = logging.getLogger(__name__)

API_BASE = "https://api.assemblyai.com/v2"
DEFAULT_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_MAX_WAIT_SECONDS = 30 * 60  # 30 min wall clock

# Statuses AssemblyAI returns while the job is still in flight. Anything
# else (other than ``"completed"`` or ``"error"``) is unexpected — we log
# at WARNING and keep polling so a future status doesn't silently spin.
_KNOWN_PENDING_STATUSES = frozenset({"queued", "processing"})


class _Transient(Exception):
    """Internal sentinel — wraps 429/503/504/timeout/connection errors so
    tenacity retries exactly the codes we want and nothing else."""


_RETRYABLE_EXC = (_Transient, requests.Timeout, requests.ConnectionError)

# Retry policy: 3 attempts, exponential backoff (1s/2s/4s), retry only on
# transient HTTP statuses + network timeouts. Permanent 4xx (other than
# 429) and parse errors raise immediately.
_retry_policy = retry(
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    before_sleep=before_sleep_log(logger, logging.INFO),
    reraise=True,
)


def _api_headers() -> dict[str, str]:
    """Build the auth header. ``ProviderError`` if the key is missing.

    The check here is a defence-in-depth against the budget gate being
    bypassed; the budget gate is the primary check on the CLI path.
    """
    key = os.getenv("ASSEMBLYAI_API_KEY")
    if not key:
        raise ProviderError(
            "ASSEMBLYAI_API_KEY not set in the environment; "
            "cannot call AssemblyAI."
        )
    return {"authorization": key}


def _handle_response(resp: requests.Response) -> dict[str, Any]:
    """Map an HTTP response to either a parsed body or an exception."""
    status = resp.status_code

    if status == 429 or status in (502, 503, 504):
        raise _Transient(f"AssemblyAI returned HTTP {status}")
    if 400 <= status < 500:
        # Permanent 4xx (auth, validation, etc.) — never retry.
        try:
            error_msg = resp.json().get("error", resp.text)
        except ValueError:
            error_msg = resp.text or "(no body)"
        raise ProviderError(f"AssemblyAI HTTP {status}: {error_msg}")
    if status >= 500:
        raise _Transient(f"AssemblyAI server error HTTP {status}")

    try:
        body: dict[str, Any] = resp.json()
    except ValueError as exc:
        raise ProviderError(f"AssemblyAI returned non-JSON response: {exc}") from exc
    return body


@_retry_policy
def _upload(wav_path: Path) -> str:
    """Stream-upload the WAV to AssemblyAI; return the upload URL."""
    with wav_path.open("rb") as f:
        resp = requests.post(
            f"{API_BASE}/upload",
            headers=_api_headers(),
            data=f,
            timeout=120,
        )
    payload = _handle_response(resp)
    return str(payload["upload_url"])


@_retry_policy
def _create_transcript(
    upload_url: str,
    *,
    speech_models: list[str],
    language_code: str | None,
    speaker_labels: bool,
) -> dict[str, Any]:
    # AssemblyAI deprecated the singular `speech_model` field in favour of
    # the plural `speech_models` array. We always send a single-element list
    # in Slice 1; multi-model cascade is a Phase 5 concern.
    body: dict[str, Any] = {
        "audio_url": upload_url,
        "speech_models": speech_models,
        "speaker_labels": speaker_labels,
    }
    if language_code:
        body["language_code"] = language_code
    resp = requests.post(
        f"{API_BASE}/transcript",
        headers={**_api_headers(), "content-type": "application/json"},
        json=body,
        timeout=30,
    )
    return _handle_response(resp)


@_retry_policy
def _get_transcript(job_id: str) -> dict[str, Any]:
    resp = requests.get(
        f"{API_BASE}/transcript/{job_id}",
        headers=_api_headers(),
        timeout=30,
    )
    return _handle_response(resp)


def _segments_from_response(
    payload: dict[str, Any],
    diarize: bool,
) -> list[Segment]:
    """Build the ``Segment`` list from the AssemblyAI completion payload.

    Preference order: ``utterances`` (when diarization is on and AssemblyAI
    returned them), then ``paragraphs``, then a single fallback segment
    spanning the full duration. The fallbacks matter for very short audio
    and for when speaker labels were requested but no utterances came back.
    """
    if diarize:
        utterances = payload.get("utterances")
        if utterances:
            return [
                Segment(
                    start_ms=int(u["start"]),
                    end_ms=int(u["end"]),
                    text=str(u["text"]),
                    speaker=u.get("speaker"),
                )
                for u in utterances
            ]

    raw_paragraphs = payload.get("paragraphs")
    if isinstance(raw_paragraphs, dict):
        paragraphs = raw_paragraphs.get("paragraphs")
        if paragraphs:
            return [
                Segment(
                    start_ms=int(p["start"]),
                    end_ms=int(p["end"]),
                    text=str(p["text"]),
                    speaker=None,
                )
                for p in paragraphs
            ]

    text = str(payload.get("text", ""))
    duration_ms = int(float(payload.get("audio_duration") or 0) * 1000)
    # Reaching this fallback means AssemblyAI returned the raw transcript
    # text without any utterance- or paragraph-level structure. The output
    # collapses to a single full-duration segment, which looks valid but is
    # effectively undiarized + unsegmented. Surface that loudly so the user
    # doesn't quietly receive a degraded transcript.
    logger.warning(
        "AssemblyAI job %s returned no utterances or paragraphs; "
        "falling back to single-segment transcript spanning the full duration. "
        "Diarization and per-utterance timestamps are unavailable for this run.",
        payload.get("id", "<unknown>"),
    )
    return [Segment(start_ms=0, end_ms=duration_ms, text=text, speaker=None)]


class AssemblyAIProvider(TranscriptionProvider):
    """AssemblyAI implementation of the transcription contract.

    The polling loop's ``sleep`` and ``clock`` are injectable so tests can
    advance time without sleeping the test runner.
    """

    def __init__(
        self,
        *,
        max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_wait_seconds = max_wait_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep
        self._clock = clock

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
        job_id = str(create_payload["id"])
        logger.info("AssemblyAI job created: %s", job_id)
        on_job_id(job_id)

        deadline = self._clock() + self.max_wait_seconds
        while True:
            # Check the deadline *before* the next GET so we never fire one
            # extra HTTP call past the cap. Test 8 verifies this ordering.
            if self._clock() >= deadline:
                raise ProviderError(
                    f"AssemblyAI polling exceeded {self.max_wait_seconds:.0f}s "
                    f"for job {job_id}. Recover via the AssemblyAI dashboard."
                )
            payload = _get_transcript(job_id)
            status = payload.get("status")

            if status == "completed":
                break
            if status == "error":
                raise ProviderError(
                    f"AssemblyAI job {job_id} failed: "
                    f"{payload.get('error', '(no error message returned)')}"
                )
            if status not in _KNOWN_PENDING_STATUSES:
                # Unknown / future status — keep polling but make it visible
                # so a stuck job doesn't sit silent for the full max_wait.
                logger.warning(
                    "AssemblyAI job %s returned unknown status %r; "
                    "continuing to poll until completion or deadline.",
                    job_id,
                    status,
                )

            self._sleep(self.poll_interval_seconds)

        segments = _segments_from_response(payload, diarize)
        return TranscriptResult(
            text=str(payload.get("text", "")),
            segments=segments,
            language=str(payload.get("language_code") or "auto"),
            duration_seconds=float(payload.get("audio_duration") or 0.0),
            model=speech_model,
            job_id=job_id,
        )
