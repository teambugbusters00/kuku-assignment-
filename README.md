# KukuFM Assignment — AI-Powered Audio Intelligence Suite

A unified assignment workspace covering **three problem statements**:

1. **PS1 — AI Content Understanding & Tagging**
2. **PS2 — Personalized Audio Recommendation**
3. **PS3 — StoryBridge: Microdrama Episode Continuity**

The repository contains a React/Vite dashboard and FastAPI backend. PS1 metadata extraction, PS2 recommendations, PS3 episode continuity review, full-series scans, and narration use Groq APIs. PS3 no longer silently falls back to a local rule-based analyzer: if Groq is unavailable or errors, the endpoint returns an error.

> **Implementation status:** The frontend now includes interactive workspaces for PS1, PS2, and PS3. PS1, PS2, and PS3 call Groq backend endpoints; PS3 supports dataset/manual comparison and a Groq-powered series scan. Each successful run can be downloaded as JSON, and the Results page retains all run responses in the current browser session. Verify the latest Render deployment before treating the live site as updated.

## Quick Links

| Resource | Link |
|---|---|
| **Live frontend** | [KukuFM Assignment Dashboard](https://kukufm-assignment-frontend-kwao.onrender.com) |
| **Live backend** | [FastAPI backend](https://kukufm-assignment-api.onrender.com) |
| **Backend health check** | [GET /](https://kukufm-assignment-api.onrender.com/) |
| **AI configuration status** | [GET /api/ai-status](https://kukufm-assignment-api.onrender.com/api/ai-status) |
| **Episode library** | [GET /api/episodes](https://kukufm-assignment-api.onrender.com/api/episodes) |
| **Full-series continuity scan** | [GET /api/analyze-series](https://kukufm-assignment-api.onrender.com/api/analyze-series) |
| **Repository source** | [Browse source files](.) |
| **Assignment/collaboration repository** | [Vadrevuharipriya/Kukufm-assigment](https://github.com/Vadrevuharipriya/Kukufm-assigment) |
| **Frontend Render dashboard** | [Frontend service](https://dashboard.render.com/static/srv-dbmtv3vf3r2c73bkqa50) |
| **Backend Render dashboard** | [Backend service](https://dashboard.render.com/web/srv-dbmtu395efls738j9l7g) |
| **Solution document** | [solution_doc.md](solution_doc.md) |
| **Validation plan** | [docs/validation_plan.md](docs/validation_plan.md) |

Render free services may sleep when inactive. A link existing does not guarantee that the latest deployment is healthy; check the health endpoint and Render logs.

---

## Problem Statements & Features

### PS1 — AI Content Understanding & Tagging

**Goal:** Turn an episode transcript into structured, useful audio-content metadata.

**Backend route:** `POST /api/ps1/tag`

The route sends the supplied transcript to the Groq chat-completions API and asks for grounded metadata. The prompt instructs the model not to invent facts.

**Request fields**

| Field | Type | Validation / default |
|---|---|---|
| `text` | string | Required, 20–30,000 characters |
| `title` | string | Optional, default `Untitled episode`, max 200 characters |
| `language` | string | Optional, default `auto`, max 40 characters |

**Expected response fields**

- `title`
- `summary` — 2–4 sentences
- `genre` — array
- `tags` — array (prompt requests 5–15)
- `themes` — array
- `characters` — objects with name and role/evidence
- `emotions` — array
- `content_warnings` — array
- `language`
- `confidence` — model-provided value from 0 to 1
- `evidence_notes` — array
- `provider` and `model` — added by the backend

**Frontend:** The workspace includes transcript/title/language inputs, a run action, structured metadata display, JSON download/copy, and tag CSV export.

### PS2 — Personalized Audio Recommendation

**Goal:** Recommend catalog items that match a listener profile while restricting recommendations to the catalog provided in the request.

**Backend route:** `POST /api/ps2/recommend`

The Groq prompt tells the model to recommend only titles/items present in the supplied catalog and not fabricate titles or IDs.

**Request fields**

| Field | Type | Validation / default |
|---|---|---|
| `user_profile` | string | Required, 5–10,000 characters |
| `catalog` | string | Required, 10–30,000 characters |
| `top_n` | integer | Optional, default 5, allowed range 1–10 |

**Expected response fields**

- `recommendations` — list of ranked items, including title, catalog reference/ID, match score, reasons, fit explanation, and content notes
- `profile_signals` — extracted listener-interest signals
- `diversity_note` — recommendation diversity explanation
- `provider` and `model` — added by the backend

**Frontend:** The workspace includes listener-profile and catalog inputs, configurable top-N, recommendation cards with match score/reasons, JSON download/copy, and recommendation CSV export.

### PS3 — StoryBridge: Microdrama Episode Continuity

**Goal:** Help editors review possible inconsistencies between consecutive episodes.

**Current frontend workflow**

- Browse the episode library and previews.
- Select two dataset episodes and compare them.
- Paste two episode texts for manual comparison.
- Run a full-series scan across adjacent episode pairs.
- Inspect findings, evidence, severity/category, and suggested editorial actions.
- Use the human-review checklist.
- Copy the structured report as JSON.

**Analyzer:** Groq semantic continuity review using the configured `GROQ_MODEL`. It is an editorial aid, not a factual verdict. Groq failures are surfaced as API errors rather than silently switching to a weaker heuristic.

Signals include:

- possible life-status contradictions;
- possible relationship-status changes;
- possession-related keyword contrasts;
- newly appearing or missing named-character signals;
- selected setting changes.

The system returns findings and a checklist. A flag is a review prompt—not proof of a continuity error. No flags does not prove a script is error-free.

---

## Frontend

**Stack:** React 18, Vite 5, JavaScript.

**Main files**

- `frontend/src/main.jsx` — dashboard, problem cards, navigation, PS3 workflow, results panel
- `frontend/src/style.css` — dashboard styling
- `frontend/package.json` — frontend scripts and dependencies

**Dashboard sections**

- **Home:** assignment overview, three PS cards, recent run history, project/service links.
- **Problems:** problem statement cards and PS3 workspace.
- **Results:** displays the latest continuity report or series-scan result.
- **Docs:** project documentation link.

**PS3 UI components**

- Dataset episode selectors
- Manual previous/next episode text inputs
- Pair-comparison action
- Full-series scan action
- Analysis report panel
- Human-review checklist
- Limitations section
- Copy-report-JSON button

The problem-card voice-preview buttons call `POST /api/voice` and play the returned WAV audio in the browser. The backend uses Groq TTS model `canopylabs/orpheus-v1-english` (English) with voice `autumn` by default. The current preview text is capped at 200 characters. This is generated narration for the card description, not playback of original KukuFM audio.

### Frontend configuration

The frontend API base URL is resolved from:

1. `VITE_API_URL`, if configured;
2. production fallback: `https://kukufm-assignment-api.onrender.com`;
3. local development: same-origin relative API paths when no override is set.

Set `VITE_API_URL` in the frontend hosting environment if you need a different backend URL.

---

## Backend

**Stack:** Python, FastAPI, Pydantic, Uvicorn, Groq Python SDK.

**Main file:** `api/index.py`

### Backend responsibilities

- Exposes health, AI status, episode library, tagging, recommendation, and continuity endpoints.
- Validates request payloads with Pydantic.
- Calls Groq for PS1 metadata extraction and PS2 recommendation generation.
- Calls Groq for PS3 continuity review and full-series adjacent episode analysis.
- Returns JSON responses and HTTP errors for missing configuration or upstream AI failures.

### AI provider configuration

PS1, PS2, and PS3 use **Groq** through the Groq Python SDK.

Environment variables:

| Variable | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | Required secret for Groq requests | No default; configure privately in Render |
| `GROQ_MODEL` | Chat model for PS1/PS2 | `qwen/qwen3.8-27b` |\n| `GROQ_TTS_MODEL` | Text-to-speech model | `canopylabs/orpheus-v1-english` |\n| `GROQ_TTS_VOICE` | TTS voice persona | `autumn` |

Default is `qwen/qwen3.8-27b`. `GROQ_MODEL` controls PS1/PS2/PS3 text analysis; `GROQ_TTS_MODEL` remains a separate voice-preview model. Long PS3 transcripts are summarized in chunks before continuity comparison to reduce oversized prompts. Chunking increases the number of Groq calls and does not eliminate TPM/RPM limits; handle rate-limit responses and retry later when needed.

**Never put `GROQ_API_KEY` in source code, README examples, frontend environment variables, or Git commits.** Keep it in Render's backend environment settings or a local untracked `.env` file.

The `GET /api/ai-status` route reports whether the key is configured and which chat model name is set. It does not make a model inference request. The same `GROQ_API_KEY` is used by PS1/PS2 chat and the voice-preview TTS endpoint.

### PS3 implementation note

PS3 manual comparisons, dataset comparisons, and full-series scans call the `ai_story_review()` Groq helper through `analyze()`. There is no local heuristic fallback. Missing `GROQ_API_KEY` returns a configuration error; upstream Groq failures return an API error. Full-series scans make one Groq request per adjacent episode pair, so latency and rate limits depend on dataset size and Groq account limits.

---

## API Reference

| Method | Endpoint | Problem | Description |
|---|---|---|---|
| GET | `/` | General | Backend health check |
| GET | `/api/ai-status` | PS1/PS2 | Groq key/model configuration status |\n| POST | `/api/voice` | Voice preview | Generate short WAV narration using Groq TTS |
| POST | `/api/ps1/tag` | PS1 | Generate episode metadata/tags from transcript |
| POST | `/api/ps2/recommend` | PS2 | Generate catalog-constrained recommendations |
| GET | `/api/episodes` | PS3 | List dataset episode IDs, previews, and character counts |
| POST | `/api/analyze` | PS3 | Compare manually supplied episode text |
| POST | `/api/analyze-episodes` | PS3 | Compare two dataset episode IDs |
| GET | `/api/analyze-series` | PS3 | Scan adjacent episode pairs across the dataset |

### Deployed API URLs

- [Health check](https://kukufm-assignment-api.onrender.com/)
- [AI configuration status](https://kukufm-assignment-api.onrender.com/api/ai-status)\n- Voice preview: `POST https://kukufm-assignment-api.onrender.com/api/voice`
- [Episode library](https://kukufm-assignment-api.onrender.com/api/episodes)
- [Series scan](https://kukufm-assignment-api.onrender.com/api/analyze-series)

The PS1 and PS2 endpoints use `POST` and require JSON request bodies. The voice endpoint also uses `POST` with a short text body (max 200 characters). Test them with an HTTP client or API testing tool.

### Example PS1 request

```json
{
  "title": "Episode 1",
  "language": "Hindi",
  "text": "Paste at least 20 characters of episode transcript here..."
}
```

### Example PS2 request

```json
{
  "user_profile": "Likes suspense, mystery, short Hindi audio stories.",
  "catalog": "ID: A1 | Title: The Hidden Room | Genre: Mystery | Synopsis: ...",
  "top_n": 5
}
```

### Example PS3 manual request

```json
{
  "show_name": "Demo show",
  "previous_episode": "Paste at least 20 characters of previous episode text...",
  "next_episode": "Paste at least 20 characters of next episode text..."
}
```

---

## Repository Structure

```text
.
├── api/
│   └── index.py                  # FastAPI routes, Groq calls, PS3 analyzer
├── frontend/
│   ├── src/
│   │   ├── main.jsx              # React dashboard and PS3 workflow
│   │   └── style.css             # UI styles
│   └── package.json               # Vite/React scripts and dependencies
├── original_assignment_files/     # Episode TXT dataset (episode-001 to episode-050)
├── tests/                        # Test files, if present in this checkout
├── docs/
│   └── validation_plan.md         # Proposed validation approach
├── requirements.txt               # Python dependencies
├── solution_doc.md                # Solution document
└── README.md
```

---

## Run Locally

### 1. Backend setup

From the repository root:

```bash
python -m pip install -r requirements.txt
uvicorn api.index:app --reload
```

Backend default: `http://localhost:8000`

### 2. Frontend setup

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite development URL shown in the terminal.

For a separate local frontend/backend origin, configure:

```bash
VITE_API_URL=http://localhost:8000
```

### Requirements

Backend dependencies are declared in `requirements.txt`:

- FastAPI
- Pydantic
- Uvicorn
- Groq SDK

Frontend dependencies are declared in `frontend/package.json`:

- React
- React DOM
- Vite
- Vite React plugin

---

## Render Deployment

### Backend start command

```bash
uvicorn api.index:app --host 0.0.0.0 --port $PORT
```

### Backend environment variables

Configure these in the Render backend service:

- `GROQ_API_KEY` — required for PS1, PS2, PS3, and TTS
- `GROQ_MODEL` — optional override for the Groq chat model (default: `qwen/qwen3.8-27b`)
- `GROQ_TTS_MODEL` — optional TTS model override (default: `canopylabs/orpheus-v1-english`)
- `GROQ_TTS_VOICE` — optional TTS voice override (default: `autumn`; confirm supported voice/model combination)

### Frontend environment variable

- `VITE_API_URL` — optional backend URL override

### Deployment checklist

- [ ] Frontend opens without a blocking error.
- [ ] Backend health check returns `{"status":"ok","service":"StoryBridge"}`.
- [ ] `/api/ai-status` shows Groq configured when the key is set.
- [ ] PS1 tagging route works with valid transcript input.
- [ ] PS2 recommendation route returns items grounded in the submitted catalog.
- [ ] PS3 episode library loads.
- [ ] PS3 manual and dataset pair comparisons work with Groq configured.
- [ ] PS3 series scan returns Groq-generated adjacent-pair reports.
- [ ] Browser console and Render logs contain no blocking errors.
- [ ] PS1 and PS2 frontend workflows are integrated before claiming all three are end-to-end complete.

---

## Automated tests

Run from the repository root:

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
```

The regression suite covers Groq PS1/PS2/PS3 wiring, PS3 no-fallback behavior, chunked transcript handling, Groq provider error handling, and TTS binary audio response/empty-response behavior. Tests use mocked Groq responses and do not validate live API access. See [docs/validation_plan.md](docs/validation_plan.md) for the complete test matrix, API cases, frontend checklist, and deployment smoke test.

## Quality, Evaluation & Limitations

### PS1 limitations

- Output quality depends on transcript quality, language, prompt, and model response.
- Metadata is model-generated and should be reviewed.
- Confidence is model output, not a calibrated probability unless separately validated.
- The API asks the model not to invent details, but that instruction does not guarantee factual accuracy.

### PS2 limitations

- Recommendations depend on the quality and completeness of the supplied profile/catalog.
- Catalog-only recommendations are enforced through prompt instructions, not a deterministic post-generation catalog-ID validator.
- Match scores are model-generated and are not empirically calibrated.
- User profile information should be minimized and handled responsibly.

### PS3 limitations

- PS3 uses Groq semantic continuity analysis; it can still miss aliases/nicknames, misread context, or flag intentional twists.
- Complex timeline, video, wardrobe, blocking, prop visuals, and timestamp continuity are not comprehensively checked.
- Multilingual quality depends on the model and is not independently benchmarked.
- Findings are review prompts, not editorial verdicts. Groq failures are surfaced; PS3 does not silently fall back to regex rules.

### Suggested evaluation

Evaluate each problem independently:

- **PS1:** metadata/tag precision, reviewer acceptance, hallucination rate, and time saved.
- **PS2:** catalog validity, relevance ratings, diversity, and user/editor acceptance.
- **PS3:** precision, recall, false-positive rate, editor dismissal rate, and review time saved.

Any target in the validation document is a proposed target—not a measured result unless evaluation data has been collected.

---

## Data & Privacy

The repository includes episode text files under `original_assignment_files/`. If assignment materials are confidential or restricted to evaluation, do not publish or redistribute them without permission. Consider making the repository private or removing source scripts before public sharing. Avoid sending confidential scripts or identifiable listener profiles to third-party AI services without authorization.

## AI / Implementation Disclosure

AI assistance was used during drafting and implementation. PS1, PS2, and PS3 text analysis use Groq; voice preview uses Groq TTS. Outputs require human review. The developer should run tests, verify deployed behavior, understand the code, and be ready to explain architecture, API contracts, model limitations, and implementation trade-offs.

## Groq implementation and regression-test notes

All three problem statements (PS1, PS2, PS3) are intended to call Groq for text analysis. PS3 episode-pair comparisons and series scans use the Groq continuity-review helper; the service does not silently fall back to local regex analysis. Groq API errors should be surfaced clearly.

Voice preview uses Groq TTS. The backend uses the Groq Python SDK's documented `write_to_file(path)` method for the `BinaryAPIResponse`, then returns the audio bytes. It does not assume a `.content` attribute. Regression tests cover PS1/PS2/PS3 Groq wiring, PS3 no-fallback behavior, provider errors, and TTS binary response/empty response handling.

**Important:** Automated tests use mocked Groq responses and do not prove the live Groq API key, model access, TTS model availability, or Render deployment is working. Check GitHub Actions and perform a live Render smoke test before claiming production readiness.


## Top-K RAG retrieval

The backend now uses lightweight BM25-style lexical retrieval before the Groq calls in PS1, PS2, and PS3:

- **PS1:** selects transcript passages relevant to episode metadata extraction.
- **PS2:** retrieves catalog entries relevant to the listener profile before generating recommendations.
- **PS3:** retrieves passages matching continuity signals (characters, relationships, status, timeline, props, and unresolved threads) before summarizing each episode.
- Retrieval is local Python and adds no vector database or embedding dependency.
- The configured LLM/model context window is **not changed**. RAG limits the input evidence passed to the model; it does not expand the context window.
- Retrieval uses a BM25-style lexical score. It is not semantic embedding search, so paraphrases with no shared terms may be missed.

Configure the number of retrieved passages with `RAG_TOP_K` (default: `5`, maximum: `20`). The API response includes retrieval metadata such as selected top-K and source/retrieved character counts.
