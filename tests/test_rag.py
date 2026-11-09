from api.rag import retrieve_top_k, retrieval_stats

def test_retrieval_selects_query_relevant_passage():
    text = (
        "The heroine visits a hospital and discovers a hidden medical file. "
        "A detective follows a suspect through the crowded market. "
        "The hospital doctor reveals that the medical file was forged."
    )
    result = retrieve_top_k(text, query="hospital doctor medical file", top_k=1)
    assert "hospital" in result.lower()
    assert "medical file" in result.lower()
    assert "crowded market" not in result.lower()

def test_top_k_is_bounded_and_context_window_is_not_changed(monkeypatch):
    monkeypatch.setenv("RAG_TOP_K", "2")
    text = "Alpha story clue one. Beta story clue two. Gamma story clue three."
    result = retrieve_top_k(text, query="story clue", top_k=2)
    assert result.count("[Passage") <= 2
    stats = retrieval_stats(text, result)
    assert stats["top_k"] == 2
    assert stats["context_window_changed"] is False

def test_empty_input_returns_empty_retrieval():
    assert retrieve_top_k("", query="story") == ""
