"""Lightweight lexical RAG retrieval with no external dependency.

Retrieves top-K text passages using a BM25-style score. This does not alter the
LLM's configured context window; it limits the evidence sent in each prompt.
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter

DEFAULT_TOP_K = 5
MAX_TOP_K = 20
DEFAULT_PASSAGE_CHARS = 900

_STOPWORDS = set("""
a an the and or but if then else when while of to in on at for from by with as is
are was were be been being it its this that these those he she they them his her
their you your we our i me my do does did can could would should will may might
not no yes into over under up down out about after before again further more most
some such only own same so than too very just also each few many much other which
who whom what where why how
""".split())

def _tokens(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9_'-]{1,}", text)
            if w.lower() not in _STOPWORDS]

def _passages(text: str, max_chars: int = DEFAULT_PASSAGE_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    line_based = "\n" in text
    units = text.splitlines() if line_based else re.split(r"(?<=[.!?])\s+", text)
    passages, current = [], ""
    for unit in units:
        unit = unit.strip()
        if not unit:
            continue
        if line_based:
            while len(unit) > max_chars:
                passages.append(unit[:max_chars].strip())
                unit = unit[max_chars:].strip()
            if unit:
                passages.append(unit)
            continue
        while len(unit) > max_chars:
            if current:
                passages.append(current)
                current = ""
            passages.append(unit[:max_chars].strip())
            unit = unit[max_chars:].strip()
        candidate = f"{current}\n{unit}".strip() if current else unit
        if len(candidate) > max_chars and current:
            passages.append(current)
            current = unit
        else:
            current = candidate
    if current:
        passages.append(current)
    return passages

def _top_k() -> int:
    try:
        value = int(os.getenv("RAG_TOP_K", str(DEFAULT_TOP_K)))
    except (TypeError, ValueError):
        value = DEFAULT_TOP_K
    return max(1, min(value, MAX_TOP_K))

def retrieve_top_k(text: str, query: str, top_k: int | None = None,
                   passage_chars: int = DEFAULT_PASSAGE_CHARS) -> str:
    """Return ranked top-K passages as plain text; ties preserve source order."""
    passages = _passages(text, max_chars=passage_chars)
    if not passages:
        return ""
    k = max(1, min(top_k if top_k is not None else _top_k(), len(passages)))
    query_terms = set(_tokens(query))
    if not query_terms:
        return "\n\n".join(passages[:k])

    docs = [_tokens(p) for p in passages]
    df = Counter(term for doc in docs for term in set(doc))
    avg_len = sum(map(len, docs)) / max(1, len(docs))
    scores = []
    for i, doc in enumerate(docs):
        tf = Counter(doc)
        score = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = math.log(1 + (len(docs) - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            denom = freq + 1.2 * (1 - 0.75 + 0.75 * len(doc) / max(avg_len, 1))
            score += idf * (freq * 2.2) / denom
        scores.append((score, i))
    ranked = sorted(scores, key=lambda item: (-item[0], item[1]))
    selected = [i for score, i in ranked[:k] if score > 0]
    if not selected:
        selected = list(range(k))
    return "\n\n".join(f"[Passage {rank}] {passages[i]}" for rank, i in enumerate(selected, 1))

def retrieval_stats(source: str, retrieved: str) -> dict:
    return {
        "method": "BM25-style lexical passage retrieval",
        "top_k": _top_k(),
        "source_characters": len(source or ""),
        "retrieved_characters": len(retrieved or ""),
        "context_window_changed": False,
    }
