# StoryBridge Hybrid AI Architecture

## Goals
- Keep PS1, PS2, and PS3 behind stable FastAPI endpoints.
- Route model work through provider adapters instead of coupling business logic to one vendor.
- Prefer Gemini for PS3 continuity comparison; retain Groq as the alternate.
- Keep deterministic local methods available when provider calls fail.
- Never call PS1 analysis while a user is typing or opening the workspace. Analysis starts only after the Analyze button is clicked.

## High-level flow

```text
React UI
  | explicit Analyze action
  v
FastAPI routes
  |
  +--> Input validation + BM25 top-K retrieval
  |
  +--> Task router (PS1_PROVIDER / PS2_PROVIDER / PS3_PROVIDER)
  |       |--> Gemini adapter
  |       |--> Groq adapter
  |
  +--> Local deterministic baseline on provider failure
  |
  v
Normalized JSON response -> UI -> download/run history
```

## Provider policy
- PS1: Groq by default; Gemini can be selected with `PS1_PROVIDER=gemini`.
- PS2: Groq by default; Gemini can be selected with `PS2_PROVIDER=gemini`.
- PS3: Gemini by default; Groq is attempted when Gemini is unavailable or errors.
- Set `GEMINI_API_KEY` and `GROQ_API_KEY` in Render backend environment variables.
- Optional model overrides: `GEMINI_MODEL` (default `gemini-2.5-flash`) and `GROQ_MODEL`.
- Optional routing overrides: `PS1_PROVIDER`, `PS2_PROVIDER`, `PS3_PROVIDER` (values: `gemini` or `groq`).

## Problem statement execution
### PS1 — Content understanding and tagging
1. User enters transcript, title, and language.
2. No model request occurs during typing or page load.
3. Clicking Analyze calls `POST /api/ps1/tag`.
4. BM25 top-K passages are sent to the configured provider.
5. If both providers fail, a local keyword/sentence baseline returns a clearly identified baseline result.

### PS2 — Personalized recommendation
1. User supplies a listener profile and catalog.
2. `POST /api/ps2/recommend` retrieves the top-K catalog entries.
3. AI ranks only retrieved entries; provider routing is configurable.
4. If providers fail, a deterministic lexical-overlap ranker returns a baseline result.

### PS3 — Story continuity
1. User selects two dataset episodes or pastes two transcripts.
2. The backend retrieves continuity-relevant passages locally from each episode.
3. A single provider request compares both retrieved evidence sets. Gemini is preferred; Groq is the alternate.
4. If both providers fail, the existing deterministic rule-based continuity checks run.
5. Full-series scan reuses the same pair-analysis path; production-scale scans should be moved to a background job queue with progress tracking and bounded concurrency.

## Reliability and scaling
- Provider adapters isolate vendor SDKs, request formats, and model names.
- Provider fallback prevents one vendor outage from disabling the entire app.
- Groq 429 responses honor the suggested wait once; local baselines prevent repeated failures from blocking users.
- Retrieval reduces prompt size but does not change the model's configured context window.
- For larger deployments, add Redis caching, a durable job queue (Celery/RQ/Cloud Tasks), PostgreSQL run history, per-provider concurrency limits, request idempotency, and metrics for latency, token use, 429s, and fallback frequency.
- Never expose API keys to the React client. Keep secrets in Render environment variables.

## Local baseline scope
- PS1: sentence extraction, keyword tags, and simple genre cues. It is not a trained classifier.
- PS2: lexical overlap ranking. It is not a learned recommendation model.
- PS3: regex/keyword continuity flags. It is not a semantic judge.
- A genuinely trained model requires labeled examples, train/validation/test splits, evaluation metrics, versioned artifacts, and a deployment strategy. Do not describe these deterministic baselines as trained models.
