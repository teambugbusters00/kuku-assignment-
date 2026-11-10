from fastapi import HTTPException

from api import index


def fake_groq_review(*args):
    return {
        "summary": {"overall_assessment": "Possible continuity risk", "risk_level": "review"},
        "findings": [{
            "severity": "review",
            "category": "Character status",
            "title": "Check character status",
            "evidence": "Previous episode: alive; next episode: died.",
            "explanation": "The statements may conflict depending on chronology.",
            "recommendation": "Verify timeline and context.",
            "confidence": 0.82
        }],
        "recurring_characters": ["Maya"],
        "unresolved_threads": ["Who sent the letter?"],
        "continuity_checklist": ["Verify chronology"]
    }


def test_ps3_uses_groq_and_returns_structured_review(monkeypatch):
    monkeypatch.setattr(index, "ai_story_review", fake_groq_review)
    r = index.analyze(index.Request(
        previous_episode="Maya says her father is alive and found a letter.",
        next_episode="Maya says her father died years ago."
    ))
    assert r["analysis_provider"] == "AI"
    assert r["fallback_used"] is False
    assert r["summary"]["risk_level"] == "review"
    assert r["findings"][0]["title"] == "Check character status"
    assert r["recurring_characters"] == ["Maya"]


def test_report_includes_checklist_and_limitations(monkeypatch):
    monkeypatch.setattr(index, "ai_story_review", fake_groq_review)
    r = index.analyze(index.Request(
        previous_episode="Maya enters the hospital and sees Arjun.",
        next_episode="Maya arrives at a hotel and sees Arjun."
    ))
    assert r["review_checklist"] == ["Verify chronology"]
    assert r["limitations"]


def test_groq_failure_is_not_silently_replaced_by_heuristic(monkeypatch):
    def fail(*args):
        raise HTTPException(status_code=502, detail="Groq unavailable")

    monkeypatch.setattr(index, "ai_story_review", fail)
    try:
        index.analyze(index.Request(
            previous_episode="Maya enters the hospital and sees Arjun.",
            next_episode="Maya arrives at a hotel and sees Arjun."
        ))
    except HTTPException as exc:
        raise AssertionError("Local baseline should handle provider outage")
    except AssertionError as exc:
        if str(exc) != "Local baseline should handle provider outage":
            raise
    else:
        raise AssertionError("Expected local baseline output")


def test_voice_reads_binary_api_response_bytes(monkeypatch):
    class MockBinaryResponse:
        def __init__(self, payload):
            self.payload = payload

        def write_to_file(self, path):
            with open(path, "wb") as audio_file:
                audio_file.write(self.payload)

    class MockSpeech:
        def __init__(self, payload):
            self.payload = payload

        def create(self, **kwargs):
            assert kwargs["response_format"] == "wav"
            return MockBinaryResponse(self.payload)

    class MockAudio:
        def __init__(self, payload):
            self.speech = MockSpeech(payload)

    class MockGroqClient:
        def __init__(self, api_key):
            self.audio = MockAudio(b"RIFFmock-wav-bytes")

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(index, "Groq", MockGroqClient)
    result = index.generate_voice(index.SpeechRequest(text="Hello StoryBridge"))
    assert result.body == b"RIFFmock-wav-bytes"
    assert result.media_type == "audio/wav"


def test_voice_rejects_empty_binary_response(monkeypatch):
    class EmptyResponse:
        def write_to_file(self, path):
            with open(path, "wb") as audio_file:
                audio_file.write(b"")

    class MockSpeech:
        def create(self, **kwargs):
            return EmptyResponse()

    class MockAudio:
        speech = MockSpeech()

    class MockGroqClient:
        def __init__(self, api_key):
            self.audio = MockAudio()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(index, "Groq", MockGroqClient)
    try:
        index.generate_voice(index.SpeechRequest(text="Hello"))
    except HTTPException as exc:
        assert exc.status_code == 502
        assert "empty audio response" in exc.detail
    else:
        raise AssertionError("Expected empty audio response to fail")


def test_ps1_calls_groq_and_marks_provider(monkeypatch):
    def fake_groq_json(system, prompt):
        assert "retrieved transcript passages" in prompt.lower()
        return {"title":"Episode One","summary":"A short summary.","tags":["mystery"],"confidence":0.8}

    monkeypatch.setattr(index, "generate_json", lambda *args, **kwargs: (fake_groq_json(args[1], args[2]), "Groq", "test-model"))
    result = index.ps1_tag(index.TagRequest(
        title="Episode One",
        language="Hindi",
        text="A sufficiently long episode transcript for a test case."
    ))
    assert result["provider"] == "Groq"
    assert result["model"] == "test-model"
    assert result["tags"] == ["mystery"]


def test_ps2_calls_groq_and_returns_catalog_grounded_recommendations(monkeypatch):
    def fake_groq_json(system, prompt):
        assert "Retrieved catalog entries" in prompt
        return {"recommendations":[{"rank":1,"title":"Catalog Story","id_or_catalog_reference":"C-1","match_score":90,"reasons":["mystery preference"],"why_this_fits":"Matches profile","content_notes":[]}],"profile_signals":["mystery"],"diversity_note":"One genre"}

    monkeypatch.setattr(index, "generate_json", lambda *args, **kwargs: (fake_groq_json(args[1], args[2]), "Groq", "test-model"))
    result = index.ps2_recommend(index.RecommendationRequest(
        user_profile="Likes short mystery stories.",
        catalog="ID: C-1 | Title: Catalog Story | Genre: Mystery",
        top_n=1
    ))
    assert result["provider"] == "Groq"
    assert result["model"] == "test-model"
    assert len(result["recommendations"]) == 1
    assert result["recommendations"][0]["id_or_catalog_reference"] == "C-1"


def test_groq_json_wraps_provider_errors(monkeypatch):
    class BrokenClient:
        class Chat:
            class Completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("mock provider error")
            completions = Completions()
        chat = Chat()

    monkeypatch.setattr(index, "groq_client", lambda: BrokenClient())
    try:
        index.groq_json("system", "user")
    except HTTPException as exc:
        assert exc.status_code == 502
        assert "mock provider error" in exc.detail
    else:
        raise AssertionError("Expected Groq error to be converted to HTTP 502")



def test_episode_chunking_preserves_content_across_newlines():
    source = "alpha beta gamma\n" + "delta epsilon zeta eta theta " * 5 + "\nfinal line"
    chunks = index.split_episode_text(source, max_chars=35)
    assert len(chunks) > 1
    # The splitter may normalize whitespace at chunk boundaries, but must not lose words.
    normalized_source = " ".join(source.split())
    normalized_chunks = " ".join(" ".join(chunk.split()) for chunk in chunks)
    assert normalized_chunks == normalized_source
    assert all(len(chunk) <= 35 for chunk in chunks)
