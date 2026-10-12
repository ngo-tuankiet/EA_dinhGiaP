import json

from valuation.data_access import macro_news


def test_macro_cache_calls_ai_only_when_news_content_changes(tmp_path, monkeypatch):
    cache_file = tmp_path / "macro.json"
    monkeypatch.setattr(macro_news, "_MACRO_CACHE_FILE", cache_file)
    current_news = {"text": "Tin A"}
    calls = []

    monkeypatch.setattr(macro_news, "fetch_rss_news", lambda: current_news["text"])

    def fake_generate(news_text=None):
        calls.append(news_text)
        return f"Phân tích: {news_text}"

    monkeypatch.setattr(macro_news, "generate_macro_bulletin", fake_generate)

    first = macro_news.get_macro_bulletin_cached(force=True)
    second = macro_news.get_macro_bulletin_cached(force=True)
    current_news["text"] = "Tin B"
    third = macro_news.get_macro_bulletin_cached(force=True)

    assert first == second == "Phân tích: Tin A"
    assert third == "Phân tích: Tin B"
    assert calls == ["Tin A", "Tin B"]
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["source_hash"]


def test_display_never_calls_network_even_when_cache_is_old(tmp_path, monkeypatch):
    import json
    from valuation.data_access import macro_news

    path = tmp_path / "macro.json"
    monkeypatch.setattr(macro_news, "_MACRO_CACHE_FILE", path)

    def forbidden():
        raise AssertionError("Hiển thị không được tải RSS hoặc gọi AI")

    monkeypatch.setattr(macro_news, "fetch_rss_news", forbidden)
    assert "Chưa có" in macro_news.get_macro_bulletin_cached()
    path.write_text(json.dumps({"ts": 1, "text": "Bản cũ"}))
    assert macro_news.get_macro_bulletin_cached() == "Bản cũ"
