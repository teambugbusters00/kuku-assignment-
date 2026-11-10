"""Provider adapters and task routing for StoryBridge AI workloads."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from fastapi import HTTPException
from groq import Groq


def _groq_json(system_prompt: str, user_prompt: str, max_tokens: int) -> dict:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    for attempt in range(2):
        try:
            response = Groq(api_key=key).chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt + " Return ONLY valid JSON. No markdown fences."},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content or "{}")
        except Exception as exc:
            message = str(exc)
            if attempt == 0 and ("429" in message or "rate_limit_exceeded" in message):
                match = re.search(r"try again in ([0-9.]+)s", message, re.I)
                time.sleep(min(30.0, max(2.0, float(match.group(1)) + 1.0)) if match else 12.0)
                continue
            raise


def _gemini_json(system_prompt: str, user_prompt: str, max_tokens: int) -> dict:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt + " Return only valid JSON. No markdown fences."}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = "".join(
            part.get("text", "")
            for candidate in data.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
        )
        if not text.strip():
            raise RuntimeError("Gemini returned an empty response")
        return json.loads(text)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail}") from exc


def generate_json(task: str, system_prompt: str, user_prompt: str, max_tokens: int = 700):
    """Route a task to its preferred configured provider, then try the alternate."""
    task = task.upper()
    preferred = os.getenv(f"{task}_PROVIDER", "gemini" if task == "PS3" else "groq").lower()
    order = [preferred, "groq" if preferred == "gemini" else "gemini"]
    errors = []
    for provider in order:
        try:
            if provider == "gemini":
                result = _gemini_json(system_prompt, user_prompt, max_tokens)
                return result, "Gemini", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
            if provider == "groq":
                result = _groq_json(system_prompt, user_prompt, max_tokens)
                return result, "Groq", os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
            errors.append(f"Unsupported provider: {provider}")
        except Exception as exc:
            errors.append(f"{provider}: {str(exc)[:300]}")
    raise HTTPException(status_code=503, detail="AI providers unavailable. " + " | ".join(errors))


def provider_status() -> dict:
    return {
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "task_routing": {
            "PS1": os.getenv("PS1_PROVIDER", "groq"),
            "PS2": os.getenv("PS2_PROVIDER", "groq"),
            "PS3": os.getenv("PS3_PROVIDER", "gemini"),
        },
    }
