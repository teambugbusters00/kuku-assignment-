from pathlib import Path
import re
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os
import json
import time
from functools import lru_cache
from groq import Groq
from api.rag import retrieve_top_k, retrieval_stats

app = FastAPI(title="StoryBridge API", version="1.0.0")

GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

def groq_client():
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Groq is not configured. Add GROQ_API_KEY in Render environment variables.")
    return Groq(api_key=key)

def groq_json(system_prompt: str, user_prompt: str, max_tokens: int = 700):
    # Keep output budgets bounded and retry one OTPM 429 after Groq's suggested wait.
    for attempt in range(2):
        try:
            response = groq_client().chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt + " Return ONLY valid JSON. No markdown fences."},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except HTTPException:
            raise
        except Exception as exc:
            message = str(exc)
            is_rate_limit = "429" in message or "rate_limit_exceeded" in message
            if is_rate_limit and attempt == 0:
                match = re.search(r"try again in ([0-9.]+)s", message, re.IGNORECASE)
                wait_seconds = min(30.0, max(2.0, float(match.group(1)) + 1.0)) if match else 15.0
                time.sleep(wait_seconds)
                continue
            status = 429 if is_rate_limit else 502
            raise HTTPException(status_code=status, detail=f"Groq request failed: {message[:500]}")

class TagRequest(BaseModel):
    text: str = Field(min_length=20, max_length=30000)
    title: str = Field(default="Untitled episode", max_length=200)
    language: str = Field(default="auto", max_length=40)

class RecommendationRequest(BaseModel):
    user_profile: str = Field(min_length=5, max_length=10000)
    catalog: str = Field(min_length=10, max_length=30000)
    top_n: int = Field(default=5, ge=1, le=10)

@app.get("/api/ai-status")
def ai_status():
    return {"provider":"Groq","configured":bool(os.getenv("GROQ_API_KEY")),"model":GROQ_MODEL,"ps1":"Groq","ps2":"Groq","ps3":"Groq","tts_provider":"Groq","tts_model":os.getenv("GROQ_TTS_MODEL","canopylabs/orpheus-v1-english")}

@app.post("/api/ps1/tag")
def ps1_tag(req: TagRequest):
    # Retrieve only the top-K relevant passages. The model context window is unchanged.
    retrieved = retrieve_top_k(
        req.text,
        query=f"episode title {req.title} language {req.language} metadata genre themes characters emotions content warnings summary",
    )
    result = groq_json(
        "You are an audio-content metadata analyst. Extract grounded metadata from the retrieved transcript passages only. Do not invent facts. Use concise tags. If evidence is insufficient, say so.",
        f"""Analyze this episode using the retrieved transcript passages.
Title: {req.title}
Language hint: {req.language}
Retrieved passages (top-K):
{retrieved}

Return JSON with keys: title, summary (2-4 sentences), genre (array), tags (array of 5-15), themes (array), characters (array of objects with name and role_or_evidence), emotions (array), content_warnings (array), language, confidence (0-1), evidence_notes (array)."""
    )
    result["provider"] = "Groq"
    result["model"] = GROQ_MODEL
    result["retrieval"] = retrieval_stats(req.text, retrieved)
    return result

@app.post("/api/ps2/recommend")
def ps2_recommend(req: RecommendationRequest):
    # Each catalog line is a retrieval unit; only profile-relevant entries go to Groq.
    retrieved_catalog = retrieve_top_k(req.catalog, query=req.user_profile)
    result = groq_json(
        "You are a personalized audio-story recommendation engine. Recommend only items from the retrieved catalog passages. Never fabricate catalog titles or IDs. Explain relevance using profile signals. Return fewer recommendations if fewer suitable entries are retrieved.",
        f"""User/listener profile:
{req.user_profile}

Retrieved catalog entries (top-K only; preserve exact titles and IDs):
{retrieved_catalog}

Return JSON with keys: recommendations (array of objects with rank, title, id_or_catalog_reference, match_score (0-100), reasons (array), why_this_fits (string), content_notes (array)), profile_signals (array), diversity_note (string). Return at most {req.top_n} recommendations."""
    )
    result["provider"] = "Groq"
    result["model"] = GROQ_MODEL
    result["retrieval"] = retrieval_stats(req.catalog, retrieved_catalog)
    return result

def split_episode_text(text: str, max_chars: int = 4500):
    """Split long transcripts into bounded, non-overlapping chunks without dropping content."""
    text = (text or "").strip()
    if not text:
        return [""]
    chunks = []
    while len(text) > max_chars:
        cut = text.rfind("\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = text.rfind(" ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


@lru_cache(maxsize=64)
def _cached_episode_continuity_notes(episode_text: str):
    """Retrieve continuity-relevant passages before creating grounded notes."""
    query = (
        "continuity character names aliases relationships alive dead status timeline "
        "locations objects props injuries promises secrets motivations knowledge "
        "unresolved cliffhanger contradictions"
    )
    retrieved = retrieve_top_k(episode_text, query=query)
    summary = groq_json(
        "You are preparing factual continuity notes for a script editor. Only report details stated in retrieved transcript passages. Preserve character names, aliases, relationships, life status, timeline, locations, important objects, injuries, promises, secrets, and unresolved cliffhangers. Do not infer missing facts. Mention when retrieved evidence is insufficient.",
        f"""Episode transcript
Retrieved transcript passages (top-K):
{retrieved}

Return JSON with keys: segment_summary, characters (array of objects with name, alias_or_relationship, status_or_actions), timeline, locations, important_props, established_facts, unresolved_threads, exact_quotes (up to 3 short quotes).""",
        max_tokens=280,
    )
    return [{"segment": 1, "notes": summary, "retrieval": retrieval_stats(episode_text, retrieved)}]


def summarize_episode_for_continuity(episode_text: str, episode_label: str):
    # Cache by transcript so adjacent full-series pairs do not summarize the same
    # episode repeatedly. Labels are added only to the comparison prompt.
    return _cached_episode_continuity_notes(episode_text)


def ai_story_review(show_name: str, previous_episode: str, next_episode: str):
    # A full episode pair can exceed Groq's free-tier 8K TPM single-request ceiling.
    # Summarize bounded chunks first, then compare the compact notes.
    previous_notes = summarize_episode_for_continuity(previous_episode, "Previous episode")
    next_notes = summarize_episode_for_continuity(next_episode, "Next episode")
    return groq_json(
        "You are a careful microdrama continuity editor. Compare compact, transcript-grounded notes from two episodes. Identify only plausible continuity issues supported by the notes. Distinguish explicit contradictions from unresolved questions and intentional cliffhangers. Do not invent details; human verification against original transcripts is required.",
        f"""Show: {show_name}

PREVIOUS EPISODE NOTES (summaries of all transcript segments):
{json.dumps(previous_notes, ensure_ascii=False)}

NEXT EPISODE NOTES (summaries of all transcript segments):
{json.dumps(next_notes, ensure_ascii=False)}

Return JSON with keys: summary (object with overall_assessment, risk_level, flags), findings (array of objects with severity [high/review/info], category, title, evidence (quote/paraphrase from each episode), explanation, recommendation, confidence 0-1), recurring_characters (array), unresolved_threads (array), continuity_checklist (array), limitations (array). Be explicit that evidence comes from chunk summaries and may need checking against the source transcript.""",
        max_tokens=700,
    )




app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE_DIR = ROOT / "original_assignment_files"

class Request(BaseModel):
    show_name: str = "Untitled show"
    previous_episode: str = Field(min_length=20, max_length=30000)
    next_episode: str = Field(min_length=20, max_length=30000)

class EpisodePairRequest(BaseModel):
    show_name: str = "KukuFM episode dataset"
    previous_episode_id: str
    next_episode_id: str

CONTRASTS = [
    (r"\b(alive|living|survived)\b", r"\b(dead|died|killed|murdered)\b", "Life status"),
    (r"\b(dead|died|killed|murdered)\b", r"\b(alive|living|survived)\b", "Life status"),
    (r"\b(married|husband|wife|wedding)\b", r"\b(single|unmarried|divorced)\b", "Relationship status"),
    (r"\b(single|unmarried|divorced)\b", r"\b(married|husband|wife|wedding)\b", "Relationship status"),
    (r"\b(owns|owner of|has the)\b", r"\b(sold|lost|stolen|gave away)\b", "Possession"),
    (r"\b(sold|lost|stolen|gave away)\b", r"\b(owns|owner of|has the)\b", "Possession"),
]
PLACES = ["hospital", "mansion", "office", "school", "airport", "hotel", "court", "prison", "farm", "restaurant", "warehouse", "church"]
STOP_NAMES = {"The", "Then", "When", "After", "Before", "Meanwhile", "Chapter", "Episode", "Scene", "But", "And", "She", "He", "They", "His", "Her"}

def episode_files():
    if not EPISODE_DIR.exists():
        return []
    return sorted(EPISODE_DIR.glob("episode-*.txt"), key=lambda p: p.name.lower())

def episode_id(path):
    return path.name

def get_episode_text(file_id):
    # Accept only an exact filename from the known dataset directory.
    if Path(file_id).name != file_id or not file_id.startswith("episode-") or not file_id.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Invalid episode identifier")
    path = EPISODE_DIR / file_id
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Episode not found")
    return path.read_text(encoding="utf-8", errors="replace")

def names(text):
    words = re.findall(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\b", text)
    return sorted({x for x in words if x not in STOP_NAMES})

def heuristic_analyze(req):
    a, b = req.previous_episode, req.next_episode
    al, bl = a.lower(), b.lower()
    an, bn = set(names(a)), set(names(b))
    findings = []
    for left, right, label in CONTRASTS:
        x, y = re.search(left, al), re.search(right, bl)
        if x and y:
            findings.append({
                "severity": "high", "category": "Possible contradiction",
                "title": "Review " + label.lower() + " across episodes",
                "evidence": "Previous episode cue: " + x.group(0) + "; next episode cue: " + y.group(0) + ".",
                "recommendation": "Inspect context and timeline. This keyword flag is not proof of an error."
            })
    new, missing = sorted(bn - an), sorted(an - bn)
    if new:
        findings.append({"severity": "review", "category": "Character introduction", "title": "New named characters appear", "evidence": ", ".join(new[:10]), "recommendation": "Check whether each needs an introduction or relationship cue."})
    if missing:
        findings.append({"severity": "info", "category": "Character continuity", "title": "Previous episode names are absent", "evidence": ", ".join(missing[:10]), "recommendation": "Check whether an unresolved thread needs payoff or recap; absence may be intentional."})
    pa, pb = {p for p in PLACES if p in al}, {p for p in PLACES if p in bl}
    if pa and pb and pa.isdisjoint(pb):
        findings.append({"severity": "review", "category": "Setting transition", "title": "Episode setting appears to change", "evidence": "Previous: " + ", ".join(sorted(pa)) + "; next: " + ", ".join(sorted(pb)) + ".", "recommendation": "Check whether the transition is established visually or in dialogue."})
    if not findings:
        findings = [{"severity": "info", "category": "No obvious flags", "title": "No rule-based flags found", "evidence": "The MVP checks only limited surface signals.", "recommendation": "Manually review the pair; no flags does not prove continuity."}]
    return {
        "show_name": req.show_name,
        "summary": {"previous_chars": len(a), "next_chars": len(b), "recurring_names": sorted(an & bn)[:15], "new_names": new[:15], "flags": len(findings)},
        "findings": findings,
        "review_checklist": ["Confirm timeline and elapsed time", "Verify relationships and motivations", "Check props, injuries, and wardrobe", "Ensure the opening gives returning viewers context", "Confirm cliffhangers have a deliberate payoff"],
        "limitations": ["Transparent regex/keyword baseline, not a trained LLM.", "Name extraction is heuristic; aliases and nicknames may be missed.", "Flags are review prompts, not factual conclusions.", "No video, timestamp, or multilingual analysis."]
    }



def analyze(req):
    """Run PS3 continuity analysis with Groq only; never silently downgrade to rules."""
    ai = ai_story_review(req.show_name, req.previous_episode, req.next_episode)
    if not isinstance(ai, dict):
        raise HTTPException(status_code=502, detail="Groq returned an invalid continuity-review payload.")

    findings = ai.get("findings", [])
    if not isinstance(findings, list):
        raise HTTPException(status_code=502, detail="Groq continuity response is missing a findings array.")
    findings = [item for item in findings if isinstance(item, dict)]
    summary = ai.get("summary", {})
    if not isinstance(summary, dict): summary = {}
    if not findings:
        findings = [{"severity":"info","category":"Review","title":"No findings returned","evidence":"Groq returned no findings for this episode pair.","explanation":"An empty finding list does not guarantee continuity correctness.","recommendation":"Review the episode pair manually.","confidence":0.1}]

    recurring = ai.get("recurring_characters", [])
    unresolved = ai.get("unresolved_threads", [])
    checklist = ai.get("continuity_checklist", [])
    if not isinstance(recurring, list): recurring = []
    if not isinstance(unresolved, list): unresolved = []
    if not isinstance(checklist, list): checklist = []
    return {
        "show_name": req.show_name,
        "summary": {"previous_chars":len(req.previous_episode),"next_chars":len(req.next_episode),"recurring_names":recurring,"new_names":[],"flags":len(findings),"overall_assessment":summary.get("overall_assessment","Groq semantic review; human verification required."),"risk_level":summary.get("risk_level","review")},
        "findings": findings,
        "review_checklist": checklist or ["Check chronology and time jumps","Verify aliases, character relationships, and motivations","Check props, injuries, settings, and character knowledge","Review cliffhangers and intentional reveals","Validate each finding against source text"],
        "recurring_characters": recurring,
        "unresolved_threads": unresolved,
        "analysis_provider": "Groq",
        "analysis_model": GROQ_MODEL,
        "fallback_used": False,
        "limitations": ["Groq can miss or misinterpret details; human review is required.","Aliases and nicknames may still be missed or merged.","Flags are review prompts, not factual conclusions.","Text-only: no video, audio, or visual evidence.","Multilingual quality depends on model coverage and is not independently benchmarked.","No findings does not prove continuity correctness."]
    }

class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    voice: str = Field(default=os.getenv("GROQ_TTS_VOICE", "autumn"), max_length=30)

@app.post("/api/voice")
def generate_voice(req: SpeechRequest):
    """Generate short audio previews through Groq TTS without exposing the API key."""
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Groq is not configured. Add GROQ_API_KEY in backend environment variables.")
    model = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
    try:
        response = Groq(api_key=key).audio.speech.create(
            model=model,
            voice=req.voice,
            input=req.text,
            response_format="wav",
        )

        # Groq's Python SDK documents BinaryAPIResponse.write_to_file().
        # It does not guarantee a .content attribute.
        import tempfile

        if isinstance(response, (bytes, bytearray)):
            audio_bytes = bytes(response)
        elif hasattr(response, "write_to_file"):
            with tempfile.NamedTemporaryFile(suffix=".wav") as audio_file:
                response.write_to_file(audio_file.name)
                audio_file.seek(0)
                audio_bytes = audio_file.read()
        elif hasattr(response, "iter_bytes"):
            audio_bytes = b"".join(response.iter_bytes())
        elif hasattr(response, "read"):
            audio_bytes = response.read()
        elif hasattr(response, "content") and isinstance(response.content, (bytes, bytearray)):
            audio_bytes = bytes(response.content)
        else:
            raise RuntimeError("Groq SDK binary response exposes no supported byte-reading interface.")

        if not audio_bytes:
            raise RuntimeError("Groq TTS returned an empty audio response.")

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={"Cache-Control": "no-store", "X-TTS-Provider": "Groq", "X-TTS-Model": model},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groq TTS request failed: {str(exc)[:400]}")

@app.get("/")
def health():
    return {"status": "ok", "service": "StoryBridge"}

@app.get("/api/episodes")
def list_episodes():
    items = []
    for index, path in enumerate(episode_files(), start=1):
        content = path.read_text(encoding="utf-8", errors="replace")
        items.append({
            "id": episode_id(path),
            "number": index,
            "name": path.stem.replace("episode-", "Episode ", 1),
            "characters": len(content),
            "preview": re.sub(r"\s+", " ", content[:220]).strip()
        })
    return {"count": len(items), "episodes": items}

@app.post("/api/analyze")
def analyze_endpoint(req: Request):
    return analyze(req)

@app.post("/api/analyze-episodes")
def analyze_episode_pair(req: EpisodePairRequest):
    previous = get_episode_text(req.previous_episode_id)
    next_text = get_episode_text(req.next_episode_id)
    result = analyze(Request(show_name=req.show_name, previous_episode=previous, next_episode=next_text))
    result["source_episodes"] = [req.previous_episode_id, req.next_episode_id]
    return result

@app.get("/api/analyze-series")
def analyze_series():
    files = episode_files()
    pairs = []
    total_flags = 0
    for previous, following in zip(files, files[1:]):
        result = analyze(Request(
            show_name="KukuFM episode dataset",
            previous_episode=previous.read_text(encoding="utf-8", errors="replace"),
            next_episode=following.read_text(encoding="utf-8", errors="replace")
        ))
        total_flags += result["summary"]["flags"]
        pairs.append({
            "previous": previous.name,
            "next": following.name,
            "flags": result["summary"]["flags"],
            "recurring_names": result["summary"]["recurring_names"],
            "findings": result["findings"]
        })
    return {
        "episode_count": len(files),
        "pair_count": len(pairs),
        "total_flags": total_flags,
        "pairs": pairs,
        "provider": "Groq", "model": GROQ_MODEL, "note": "Every adjacent pair is analyzed with Groq. All flags require human review."
    }

handler = app
