from valuation.ingest import vnstock_client as client_module


def test_vnstock_client_applies_configured_key_once(monkeypatch):
    calls = []
    monkeypatch.setattr(client_module.settings, "vnstock_api_key", "test-key")
    monkeypatch.setattr(
        client_module,
        "_configure_vnstock_api_key",
        lambda key: calls.append(key),
    )
    client = client_module.VnstockClient()

    client._ensure_api_key()
    client._ensure_api_key()

    assert calls == ["test-key"]


def test_vnstock_client_skips_setup_without_key(monkeypatch):
    calls = []
    monkeypatch.setattr(client_module.settings, "vnstock_api_key", "")
    monkeypatch.setattr(
        client_module,
        "_configure_vnstock_api_key",
        lambda key: calls.append(key),
    )

    client_module.VnstockClient()._ensure_api_key()

    assert calls == []
