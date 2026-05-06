# PR #18 — Fix AssemblyAI rate constant + factor in diarization

**Merged:** TBD  |  **Branch:** `fix/assemblyai-rate-constant`  |  **Codex review:** TBD
**Journey entry:** [`../journey.md#pr-18--fix-assemblyai-rate-constant--factor-in-diarization`](../journey.md#pr-18--fix-assemblyai-rate-constant--factor-in-diarization)

## The problem in one paragraph

PR #12 (Slice 1) hardcoded `ASSEMBLYAI_RATE_PER_MINUTE_USD = 0.009` in
`core/budget.py`. PR #17's manual runbook compared the CLI's pre-run
cost estimate ($0.567 for 63 min audio) against the actual AssemblyAI
billing dashboard ($0.2415 — see PR #17's explainer for the
side-by-side data). The constant was **2.35x too high**, and worse, the
cost-estimate function didn't factor in the Speaker Diarization
add-on charge separately even though diarization is on by default.
This PR splits the rate into two empirically-verified constants and
threads the `diarize` boolean through `estimate_assemblyai_cost` so
the user sees an accurate pre-run quote regardless of whether
`--no-speakers` is passed.

## What changed (high level)

- **`core/budget.py`**: split the single `ASSEMBLYAI_RATE_PER_MINUTE_USD`
  into two constants:
  - `UNIVERSAL_3_PRO_RATE_PER_MINUTE_USD = 0.0035` (speech-to-text base)
  - `SPEAKER_DIARIZATION_RATE_PER_MINUTE_USD = 0.000333` (add-on)
  - `ASSEMBLYAI_RATE_PER_MINUTE_USD` retained as a back-compat alias
    equal to their sum ($0.003833/min combined for the default
    diarization-on flow).
- **`estimate_assemblyai_cost(duration_seconds, *, diarize=True)`**:
  new keyword arg; when `False`, the diarization add-on is dropped
  from the estimate. Default matches the CLI's default (`--speakers`
  on).
- **`cli.py`**: the local-file path's call site now passes
  `diarize=not no_speakers` so a user invoking `--no-speakers` sees
  the lower estimate ($0.0035/min vs $0.003833/min).
- **`tests/unit/test_budget.py`**: replaced the two old "1 min ≈ $0.009"
  tests with four:
  - `test_estimate_cost_one_minute_with_diarization` (default path)
  - `test_estimate_cost_ten_minutes_with_diarization`
  - `test_estimate_cost_no_diarization_drops_speaker_addon`
  - `test_estimate_cost_matches_real_pr17_run` — locks the rate
    against the empirical PR #17 manual-run figure ($0.2415 for 63
    min, diarization on). If a future AssemblyAI rate change drops
    that assertion, the constants need re-verification against fresh
    dashboard data.

## How the rates were derived

Empirical observation across two independent days of AssemblyAI Cost
dashboard data, both consistent to 4 decimal places:

| Date | Audio | Universal-3 Pro | Speaker Diarization | Total |
|------|------:|------:|------:|------:|
| 2026-05-03 | 132m 43s | $0.464508 | $0.044239 | $0.508747 |
| 2026-05-05 | 63m 0s | $0.220500 | $0.021000 | $0.241500 |

Per-minute math:

| | $/min |
|---|------:|
| `$0.464508 / 132.72 min` | **$0.003500** |
| `$0.220500 / 63.00 min`  | **$0.003500** |
| `$0.044239 / 132.72 min` | **$0.000333** |
| `$0.021000 / 63.00 min`  | **$0.000333** |

Both days agree on both rates to 6 decimal places — strong evidence
the constants are dashboard-accurate, not approximations.

## Why this approach

**Two constants instead of one** because diarization is genuinely
optional (the CLI exposes `--no-speakers`) and AssemblyAI bills it
separately on the dashboard. Folding the diarization charge into a
single combined rate would mean the `--no-speakers` flow over-quotes
by ~10%; folding it out via a `diarize` kwarg keeps both flows
accurate.

**Empirical rate not published-rate** because AssemblyAI's pricing
page values can drift with promos, account-tier discounts, and rate
revisions. The empirical billing data is the source of truth for
what the user actually pays. The constants get re-verified at every
manual runbook execution — `test_estimate_cost_matches_real_pr17_run`
makes that explicit.

**No cache** of these rates and no per-tenant pricing logic — that
all lives in the deferred Phase 5 (provider registry + per-provider
rate hooks). This PR keeps Slice 1's "single hardcoded rate"
abstraction shape; just corrects the values and splits the
diarization slot for the default-on case.

## What a reviewer should notice

- **The PR is small** — 1 file changed in src/, 1 file changed in
  tests/, 1 line in cli.py. Each change maps to a specific cost
  inaccuracy.
- **Drive sources (Slice 2) are unaffected** — they use
  `cost_summary` and skip the per-minute estimate path entirely (PR
  #15 brainstorm decision #4). Inadvertently insulated themselves
  from this bug class while it was live.
- **`SOFT_CAP_USD = 5.0` semantics shift.** At the old (wrong) rate,
  the soft cap fired at ~556 min audio (9 hours). At the corrected
  combined rate, it fires at ~1304 min (21+ hours). If the spec's
  intent was "warn before this is a meaningful sum," 5.0 is now too
  high — file a follow-up to lower SOFT_CAP_USD to ~$1-2 if the
  warning should still fire on multi-hour files. Out of scope for
  this PR; just flagged.
- **No new dependencies, no API changes, no new tests beyond the
  rate update,** intentionally. This is a value-correction PR, not a
  feature.

## Interview angle

- **Story type:** end-to-end SDD self-correction — manual runbook
  caught a bug that 12 weeks of unit tests missed because the bug was
  in a constant, not a code path. The structural defence (PR #15's
  brainstorm decision to skip pre-estimates for Drive sources)
  inadvertently made Slice 2 immune.
- **One-sentence hook:** "PR #17's mandatory manual-runbook step
  surfaced that PR #12's hardcoded AssemblyAI rate was 2.35x too
  high. Fixed by splitting the rate into model + add-on constants
  verified against two independent days of dashboard billing data."
- **Pointer:** the cost-vs-estimate gap analysis in PR #17's
  explainer plus the empirical rate derivation table above.

## Further reading

- [`pr-017-drive-source-passthrough-impl.md`](pr-017-drive-source-passthrough-impl.md) — surfaced the bug.
- [`pr-012-assemblyai-mvp-slice-1-impl.md`](pr-012-assemblyai-mvp-slice-1-impl.md) — where the wrong constant landed originally.
- [`../../docs/PLAN.md#phase-5--cloud-transcription-providers-provider-abstraction`](../../docs/PLAN.md) — Phase 5 will replace this hardcoded rate with the per-provider registry.
