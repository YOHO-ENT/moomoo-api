# -*- coding: utf-8 -*-
"""Tests for the local read-only account dashboard."""

import os
from contextlib import contextmanager

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from moomoo.examples.account_web import app as account_app
from moomoo.examples.account_web import market_data
from moomoo.examples.account_web import service


class FakeResponse(object):
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("bad status")

    def json(self):
        return self.payload


class FakeClient(object):
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error
        self.requests = []
        self.closed = False

    def get(self, url, params=None):
        self.requests.append((url, params))
        if self.error:
            raise self.error
        return FakeResponse(self.payload)

    def close(self):
        self.closed = True


class FakeWatchlistQuoteContext(object):
    def __init__(self):
        self.group_type = None
        self.security_requests = []

    def get_user_security_group(self, group_type):
        self.group_type = group_type
        return service.ft.RET_OK, pd.DataFrame(
            [
                {"group_name": "AI Watch", "group_type": "CUSTOM"},
                {"group_name": "Broken List", "group_type": "CUSTOM"},
            ]
        )

    def get_user_security(self, group_name):
        self.security_requests.append(group_name)
        if group_name == "Broken List":
            return service.ft.RET_ERROR, "list unavailable"
        return service.ft.RET_OK, pd.DataFrame(
            [
                {"code": "US.AAPL", "name": "Apple", "lot_size": 1, "stock_type": "STOCK"},
                {"code": "HK.00700", "name": "Tencent", "lot_size": 100, "stock_type": "STOCK"},
            ]
        )


class FakePositionsTradeContext(object):
    def __init__(self, ret=None, payload=None):
        self.ret = service.ft.RET_OK if ret is None else ret
        self.payload = payload
        self.trd_env = None

    def position_list_query(self, trd_env):
        self.trd_env = trd_env
        if self.ret != service.ft.RET_OK:
            return self.ret, self.payload
        payload = self.payload
        if payload is None:
            payload = pd.DataFrame(
                [
                    {
                        "code": "US.NVDA",
                        "stock_name": "NVIDIA",
                        "qty": 10,
                        "cost_price": 1,
                        "market_val": 2,
                        "pl_val": 3,
                        "pl_ratio": 4,
                        "acc_id": "1234567890",
                    }
                ]
            )
        return self.ret, payload


def test_map_moomoo_code_us_hk_and_unsupported():
    assert market_data.map_moomoo_code("US.AAPL")["ticker"] == "AAPL"
    assert market_data.map_moomoo_code("US.BRK.B")["ticker"] == "BRK.B"
    assert market_data.map_moomoo_code("HK.00700")["ticker"] == "0700.HK"
    assert market_data.map_moomoo_code("HK.00005")["ticker"] == "0005.HK"
    assert market_data.map_moomoo_code("HK.09988")["ticker"] == "9988.HK"
    assert market_data.map_moomoo_code("AU.BHP")["mapping_status"] == "unsupported"
    assert market_data.map_moomoo_code("")["mapping_status"] == "unsupported"


def test_market_data_snapshots_success_and_order_preserved():
    client = FakeClient(
        {
            "status": "ok",
            "snapshots": [
                {
                    "ticker": "AAPL",
                    "price": 10,
                    "trend": "bullish",
                    "rsi14": 55,
                    "as_of": "2026-06-05",
                    "data_quality": {"status": "ok"},
                },
                {
                    "ticker": "0700.HK",
                    "price": 20,
                    "trend": "neutral",
                    "rsi14": 45,
                    "as_of": "2026-06-05",
                    "data_quality": {"status": "partial"},
                },
            ],
        }
    )

    payload = market_data.fetch_market_data_snapshots(["US.AAPL", "HK.00700", "AU.BHP"], client=client)

    assert payload["available"] is True
    assert payload["mapped_count"] == 2
    assert [item["source_code"] for item in payload["results"]] == ["US.AAPL", "HK.00700", "AU.BHP"]
    assert payload["results"][0]["price"] == 10
    assert payload["results"][1]["ticker"] == "0700.HK"
    assert payload["results"][2]["mapping_status"] == "unsupported"
    assert client.requests[0][1]["tickers"] == "AAPL,0700.HK"


def test_market_data_snapshots_unreachable_degrades():
    payload = market_data.fetch_market_data_snapshots(
        ["US.AAPL"],
        client=FakeClient(error=TimeoutError("timeout")),
    )

    assert payload["available"] is False
    assert payload["status"] == "unavailable"
    assert payload["results"][0]["data_quality"]["status"] == "unavailable"


def test_opend_host_guard(monkeypatch):
    monkeypatch.delenv(service.ALLOW_REMOTE_ENV, raising=False)
    service.validate_opend_host("127.0.0.1")
    service.validate_opend_host("localhost")
    service.validate_opend_host("::1")
    with pytest.raises(ValueError):
        service.validate_opend_host("192.168.1.20")

    monkeypatch.setenv(service.ALLOW_REMOTE_ENV, "1")
    service.validate_opend_host("192.168.1.20")


def test_watchlist_group_type_normalization():
    assert service.normalize_watchlist_group_type(None)[0] == "CUSTOM"
    assert service.normalize_watchlist_group_type("custom")[1] == service.ft.UserSecurityGroupType.CUSTOM
    assert service.normalize_watchlist_group_type("ALL")[1] == service.ft.UserSecurityGroupType.ALL
    assert service.normalize_watchlist_group_type("system")[1] == service.ft.UserSecurityGroupType.SYSTEM

    with pytest.raises(ValueError):
        service.normalize_watchlist_group_type("REAL")


def test_watchlists_cache_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))

    assert service.watchlists_cache_path() == tmp_path / service.WATCHLIST_CACHE_FILE


def test_build_watchlists_payload_cache_missing(monkeypatch, tmp_path):
    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))

    payload = service.build_watchlists_payload("127.0.0.1", 11111)

    assert payload["source"] == "cache_missing"
    assert payload["group_count"] == 0
    assert payload["security_count"] == 0
    assert payload["groups"] == []
    assert payload["error"] == "watchlists cache not found"


def test_build_watchlists_payload_reads_cache_without_opend(monkeypatch, tmp_path):
    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))
    cached_payload = service.watchlists_payload(
        source="opend_sync",
        group_type_name="CUSTOM",
        synced_at="2026-06-08T00:00:00+00:00",
        groups=[
            {
                "group_name": "AI Watch",
                "group_type": "CUSTOM",
                "count": 1,
                "securities": [{"code": "US.AAPL", "name": "Apple"}],
                "error": None,
            }
        ],
    )
    service.write_watchlists_cache(cached_payload)

    def fail_quote_context(host, port):
        raise AssertionError("GET /api/watchlists should not call OpenD")

    monkeypatch.setattr(service, "quote_context", fail_quote_context)

    payload = service.build_watchlists_payload("127.0.0.1", 11111)

    assert payload["source"] == "cache"
    assert payload["synced_at"] == "2026-06-08T00:00:00+00:00"
    assert payload["group_count"] == 1
    assert payload["security_count"] == 1
    assert payload["groups"][0]["securities"][0]["code"] == "US.AAPL"


def test_build_watchlists_payload_cache_error(monkeypatch, tmp_path):
    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))
    service.watchlists_cache_path().parent.mkdir(parents=True, exist_ok=True)
    service.watchlists_cache_path().write_text("{bad json", encoding="utf-8")

    payload = service.build_watchlists_payload("127.0.0.1", 11111)

    assert payload["source"] == "cache_error"
    assert payload["groups"] == []
    assert "failed to read cache" in payload["error"]


def test_watchlists_export_reads_cache_with_mapped_tickers(monkeypatch, tmp_path):
    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))
    service.write_watchlists_cache(
        service.watchlists_payload(
            source="opend_sync",
            group_type_name="CUSTOM",
            synced_at="2026-06-08T00:00:00+00:00",
            groups=[
                {
                    "group_name": "AI Watch",
                    "group_type": "CUSTOM",
                    "count": 3,
                    "securities": [
                        {"code": "US.NVDA", "name": "NVIDIA", "lot_size": 1},
                        {"code": "HK.00700", "name": "Tencent", "lot_size": 100},
                        {"code": "AU.BHP", "name": "BHP"},
                    ],
                    "error": None,
                }
            ],
        )
    )

    payload = service.build_watchlists_export_payload()

    assert payload["source"] == "moomoo-cache"
    assert payload["status"] == "ok"
    assert payload["synced_at"] == "2026-06-08T00:00:00+00:00"
    assert payload["group_count"] == 1
    assert "cache_path" not in payload
    assert payload["groups"][0]["order"] == 0
    securities = payload["groups"][0]["securities"]
    assert [security["order"] for security in securities] == [0, 1, 2]
    assert securities[0]["market_data_ticker"] == "NVDA"
    assert securities[1]["market_data_ticker"] == "0700.HK"
    assert securities[2]["mapping_status"] == "unsupported"
    assert "lot_size" not in securities[0]


def test_watchlists_export_cache_missing_is_consumable(monkeypatch, tmp_path):
    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))

    payload = service.build_watchlists_export_payload()
    status = service.build_watchlists_status_payload()

    assert payload["source"] == "moomoo-cache"
    assert payload["status"] == "cache_missing"
    assert payload["groups"] == []
    assert payload["error"] == "watchlists cache not found"
    assert status["status"] == "cache_missing"
    assert "cache_path" not in status


def test_sync_watchlists_cache_partial_error(monkeypatch, tmp_path):
    fake_ctx = FakeWatchlistQuoteContext()
    sleep_calls = []

    @contextmanager
    def fake_quote_context(host, port):
        yield fake_ctx

    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(service, "quote_context", fake_quote_context)

    payload = service.sync_watchlists_cache(
        "127.0.0.1",
        11111,
        sleep_func=lambda seconds: sleep_calls.append(seconds),
    )

    assert payload["source"] == "opend_sync"
    assert payload["group_type"] == "CUSTOM"
    assert payload["group_count"] == 2
    assert payload["security_count"] == 2
    assert fake_ctx.group_type == service.ft.UserSecurityGroupType.CUSTOM
    assert fake_ctx.security_requests == ["AI Watch", "Broken List"]
    assert sleep_calls == [service.WATCHLIST_SYNC_DELAY_SEC]
    assert payload["groups"][0]["count"] == 2
    assert payload["groups"][0]["securities"][0]["code"] == "US.AAPL"
    assert payload["groups"][1]["error"] == "list unavailable"
    assert service.watchlists_cache_path().exists()
    assert service.read_watchlists_cache()["source"] == "cache"


def test_positions_export_only_returns_research_safe_fields(monkeypatch):
    fake_ctx = FakePositionsTradeContext()

    @contextmanager
    def fake_trade_context(host, port, market):
        yield fake_ctx

    monkeypatch.setattr(service, "trade_context", fake_trade_context)

    payload = service.build_positions_export_payload("127.0.0.1", 11111, "US")

    assert payload["source"] == "moomoo-opend"
    assert payload["status"] == "ok"
    assert payload["available"] is True
    assert fake_ctx.trd_env == service.REAL_ENV
    assert payload["positions"] == [
        {
            "code": "US.NVDA",
            "name": "NVIDIA",
            "market_data_ticker": "NVDA",
            "mapping_status": "mapped",
            "mapping_warning": None,
            "held": True,
            "order": 0,
        }
    ]
    forbidden = {"qty", "cost_price", "market_val", "pl_val", "pl_ratio", "acc_id"}
    assert forbidden.isdisjoint(payload["positions"][0])


def test_positions_export_unavailable_is_consumable(monkeypatch):
    fake_ctx = FakePositionsTradeContext(ret=service.ft.RET_ERROR, payload="OpenD unavailable")

    @contextmanager
    def fake_trade_context(host, port, market):
        yield fake_ctx

    monkeypatch.setattr(service, "trade_context", fake_trade_context)

    payload = service.build_positions_export_payload("127.0.0.1", 11111, "US")

    assert payload["status"] == "unavailable"
    assert payload["available"] is False
    assert payload["positions"] == []
    assert payload["error"] == "OpenD unavailable"


def test_research_universe_export_uses_watchlist_order_and_merges_positions(monkeypatch, tmp_path):
    monkeypatch.setenv(service.WATCHLIST_CACHE_DIR_ENV, str(tmp_path))
    service.write_watchlists_cache(
        service.watchlists_payload(
            source="opend_sync",
            group_type_name="CUSTOM",
            synced_at="2026-06-08T00:00:00+00:00",
            groups=[
                {
                    "group_name": "AI Watch",
                    "group_type": "CUSTOM",
                    "count": 2,
                    "securities": [
                        {"code": "US.NVDA", "name": "Nvidia from list"},
                        {"code": "HK.00700", "name": "Tencent"},
                    ],
                    "error": None,
                },
                {
                    "group_name": "Second List",
                    "group_type": "CUSTOM",
                    "count": 2,
                    "securities": [
                        {"code": "HK.00700", "name": "Tencent duplicate"},
                        {"code": "US.AAPL", "name": "Apple"},
                    ],
                    "error": None,
                }
            ],
        )
    )
    fake_ctx = FakePositionsTradeContext(
        payload=pd.DataFrame(
            [
                {"code": "US.NVDA", "stock_name": "NVIDIA"},
                {"code": "US.TSLA", "stock_name": "Tesla"},
            ]
        )
    )

    @contextmanager
    def fake_trade_context(host, port, market):
        yield fake_ctx

    monkeypatch.setattr(service, "trade_context", fake_trade_context)

    payload = service.build_research_universe_export_payload("127.0.0.1", 11111, "US")

    assert payload["source"] == "moomoo-account-web"
    assert payload["status"] == "ok"
    assert payload["item_count"] == 4
    assert [item["code"] for item in payload["items"]] == ["US.NVDA", "HK.00700", "US.AAPL", "US.TSLA"]
    assert [item["universe_order"] for item in payload["items"]] == [0, 1, 2, 3]
    nvda = payload["items"][0]
    assert nvda["name"] == "NVIDIA"
    assert nvda["held"] is True
    assert nvda["primary_source"] == "watchlist:AI Watch"
    assert nvda["sources"] == ["watchlist:AI Watch", "positions"]
    assert nvda["watchlist_refs"] == [{"group_name": "AI Watch", "group_order": 0, "security_order": 0}]
    tencent = payload["items"][1]
    assert tencent["market_data_ticker"] == "0700.HK"
    assert tencent["held"] is False
    assert tencent["primary_source"] == "watchlist:AI Watch"
    assert tencent["sources"] == ["watchlist:AI Watch", "watchlist:Second List"]
    assert tencent["watchlist_refs"] == [
        {"group_name": "AI Watch", "group_order": 0, "security_order": 1},
        {"group_name": "Second List", "group_order": 1, "security_order": 0},
    ]
    assert payload["items"][2]["primary_source"] == "watchlist:Second List"
    assert payload["items"][3]["code"] == "US.TSLA"
    assert payload["items"][3]["primary_source"] == "positions"
    assert payload["items"][3]["sources"] == ["positions"]
    assert {"qty", "cost_price", "market_val", "pl_val", "pl_ratio", "acc_id"}.isdisjoint(nvda)


def test_dashboard_route_blocks_remote_before_opend():
    client = TestClient(account_app.app)
    response = client.get("/api/dashboard?host=192.168.1.20&port=11111&market=US")

    assert response.status_code == 400
    assert service.ALLOW_REMOTE_ENV in response.json()["detail"]


def test_watchlists_route_blocks_remote_before_opend():
    client = TestClient(account_app.app)
    response = client.get("/api/watchlists?host=192.168.1.20&port=11111")

    assert response.status_code == 400
    assert service.ALLOW_REMOTE_ENV in response.json()["detail"]


def test_watchlists_sync_route_blocks_remote_before_opend():
    client = TestClient(account_app.app)
    response = client.post("/api/watchlists/sync?host=192.168.1.20&port=11111")

    assert response.status_code == 400
    assert service.ALLOW_REMOTE_ENV in response.json()["detail"]


def test_positions_export_route_blocks_remote_before_opend():
    client = TestClient(account_app.app)
    response = client.get("/api/positions/export?host=192.168.1.20&port=11111&market=US")

    assert response.status_code == 400
    assert service.ALLOW_REMOTE_ENV in response.json()["detail"]


def test_research_universe_export_route_blocks_remote_before_opend():
    client = TestClient(account_app.app)
    response = client.get("/api/research-universe/export?host=192.168.1.20&port=11111&market=US")

    assert response.status_code == 400
    assert service.ALLOW_REMOTE_ENV in response.json()["detail"]


def test_watchlists_route_defaults_to_custom(monkeypatch):
    captured = {}

    def fake_build_watchlists_payload(host, port, group_type):
        captured["host"] = host
        captured["port"] = port
        captured["group_type"] = group_type
        return {
            "source": "cache_missing",
            "synced_at": None,
            "cache_path": "/tmp/watchlists_cache.json",
            "group_type": group_type,
            "group_count": 0,
            "security_count": 0,
            "groups": [],
            "error": "watchlists cache not found",
        }

    monkeypatch.setattr(account_app, "build_watchlists_payload", fake_build_watchlists_payload)

    response = TestClient(account_app.app).get("/api/watchlists?host=127.0.0.1&port=11111")

    assert response.status_code == 200
    assert captured == {"host": "127.0.0.1", "port": 11111, "group_type": "CUSTOM"}
    assert response.json()["group_type"] == "CUSTOM"
    assert response.json()["source"] == "cache_missing"


def test_watchlists_export_route_defaults_to_custom(monkeypatch):
    captured = {}

    def fake_build_watchlists_export_payload(group_type):
        captured["group_type"] = group_type
        return {
            "source": "moomoo-cache",
            "status": "ok",
            "synced_at": "2026-06-08T00:00:00+00:00",
            "group_type": group_type,
            "group_count": 1,
            "security_count": 1,
            "groups": [
                {
                    "name": "AI Watch",
                    "type": "CUSTOM",
                    "count": 1,
                    "securities": [
                        {
                            "code": "US.NVDA",
                            "name": "NVIDIA",
                            "market_data_ticker": "NVDA",
                            "mapping_status": "mapped",
                            "mapping_warning": None,
                            "held": False,
                        }
                    ],
                    "error": None,
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(account_app, "build_watchlists_export_payload", fake_build_watchlists_export_payload)

    response = TestClient(account_app.app).get("/api/watchlists/export")

    assert response.status_code == 200
    payload = response.json()
    assert captured == {"group_type": "CUSTOM"}
    assert payload["groups"][0]["securities"][0]["market_data_ticker"] == "NVDA"
    assert "cache_path" not in payload


def test_watchlists_sync_route_defaults_to_custom(monkeypatch):
    captured = {}

    def fake_sync_watchlists_cache(host, port, group_type):
        captured["host"] = host
        captured["port"] = port
        captured["group_type"] = group_type
        return {
            "source": "opend_sync",
            "synced_at": "2026-06-08T00:00:00+00:00",
            "cache_path": "/tmp/watchlists_cache.json",
            "group_type": group_type,
            "group_count": 1,
            "security_count": 1,
            "groups": [
                {
                    "group_name": "AI Watch",
                    "group_type": "CUSTOM",
                    "count": 1,
                    "securities": [{"code": "US.AAPL", "name": "Apple"}],
                    "error": None,
                }
            ],
            "error": None,
        }

    monkeypatch.setattr(account_app, "sync_watchlists_cache", fake_sync_watchlists_cache)

    response = TestClient(account_app.app).post("/api/watchlists/sync?host=127.0.0.1&port=11111")

    assert response.status_code == 200
    assert captured == {"host": "127.0.0.1", "port": 11111, "group_type": "CUSTOM"}
    assert response.json()["source"] == "opend_sync"
    assert response.json()["groups"][0]["securities"][0]["code"] == "US.AAPL"


def test_dashboard_route_uses_masked_payload(monkeypatch):
    captured = []
    payload = {
        "connection": {
            "host": "127.0.0.1",
            "port": 11111,
            "market": "US",
            "security_firm": "FUTUAU",
            "asset_currency": "USD",
            "asset_currency_options": ["USD", "HKD", "AUD"],
        },
        "state": {"program_status_type": "READY", "qot_logined": True, "trd_logined": True},
        "account": {"acc_id": "1234...7890"},
        "assets": {"total_assets": 1000, "currency": "USD"},
        "positions": [],
        "position_count": 0,
    }

    def fake_build_dashboard_payload(host, port, market, currency):
        captured.append((host, port, market, currency))
        return payload

    monkeypatch.setattr(account_app, "build_dashboard_payload", fake_build_dashboard_payload)

    response = TestClient(account_app.app).get("/api/dashboard?host=127.0.0.1&port=11111&market=US")

    assert response.status_code == 200
    assert response.json()["account"]["acc_id"] == "1234...7890"
    assert captured == [("127.0.0.1", 11111, "US", "USD")]

    response = TestClient(account_app.app).get("/api/dashboard?host=127.0.0.1&port=11111&market=US&currency=AUD")

    assert response.status_code == 200
    assert captured[-1] == ("127.0.0.1", 11111, "US", "AUD")


def test_market_data_route_without_network_for_unsupported_code():
    response = TestClient(account_app.app).get("/api/market-data/snapshots?codes=AU.BHP")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["results"][0]["mapping_status"] == "unsupported"


def test_privacy_defaults_and_static_files_present():
    root = os.path.dirname(os.path.dirname(__file__))
    app_js = open(os.path.join(root, "moomoo/examples/account_web/static/app.js"), encoding="utf-8").read()
    assert "let privacyMode = true;" in app_js
    assert '"pl_val"' in app_js
    assert "sensitiveColumns" in app_js
    assert os.path.exists(os.path.join(root, "moomoo/examples/account_web/static/index.html"))
    assert os.path.exists(os.path.join(root, "moomoo/examples/account_web/static/style.css"))


def test_position_detail_modal_static_contract():
    root = os.path.dirname(os.path.dirname(__file__))
    index_html = open(os.path.join(root, "moomoo/examples/account_web/static/index.html"), encoding="utf-8").read()
    app_js = open(os.path.join(root, "moomoo/examples/account_web/static/app.js"), encoding="utf-8").read()
    style_css = open(os.path.join(root, "moomoo/examples/account_web/static/style.css"), encoding="utf-8").read()

    assert 'id="position-detail"' in index_html
    assert 'class="detail-modal"' in index_html
    assert 'role="dialog"' in index_html
    assert 'id="detail-backdrop"' in index_html
    assert 'id="detail-lab-action"' in index_html
    assert 'id="detail-privacy"' in index_html
    assert index_html.index('id="detail-lab-action"') < index_html.index('id="detail-privacy"')
    assert "let activeDetailCode = null;" in app_js
    assert "function togglePrivacyMode()" in app_js
    assert "function selectedPosition()" in app_js
    assert "function renderDetailLabAction(item)" in app_js
    assert "renderDetailLabAction(position)" in app_js
    assert "renderDetailLabAction(security)" in app_js
    assert "renderDetailLabAction(null)" in app_js
    assert "function renderPositionDetail(position)" in app_js
    assert "function openPositionDetail(code)" in app_js
    assert "function closePositionDetail()" in app_js
    assert "function renderPositionsTable(rows)" in app_js
    assert "market_data_url" in app_js
    position_quality = app_js[
        app_js.index('const quality = detailSection("Data Quality", ['):
        app_js.index("content.replaceChildren(summary, signal, market, quality);")
    ]
    watchlist_quality = app_js[
        app_js.rindex('const quality = detailSection("Data Quality", ['):
        app_js.index('content.replaceChildren(summary, detailSection("Holding Match", holdingItems), market, quality);')
    ]
    assert "marketDataLink" not in position_quality
    assert "marketDataLink" not in watchlist_quality
    assert ".detail-modal" in style_css
    assert ".detail-lab-action" in style_css
    assert ".detail-drawer" not in style_css
    assert "width: min(880px, calc(100vw - 48px))" in style_css
    assert "transform: translate(-50%, -50%)" in style_css


def test_watchlists_static_contract():
    root = os.path.dirname(os.path.dirname(__file__))
    index_html = open(os.path.join(root, "moomoo/examples/account_web/static/index.html"), encoding="utf-8").read()
    app_js = open(os.path.join(root, "moomoo/examples/account_web/static/app.js"), encoding="utf-8").read()
    style_css = open(os.path.join(root, "moomoo/examples/account_web/static/style.css"), encoding="utf-8").read()

    assert index_html.count('class="nav-item') == 3
    assert 'data-page-target="overview"' in index_html
    assert 'data-page-target="watchlists"' in index_html
    assert 'data-page-target="signals"' in index_html
    assert 'data-page="overview"' in index_html
    assert 'data-page="watchlists" hidden' in index_html
    assert 'data-page="signals" hidden' in index_html
    assert 'href="#watchlists"' in index_html
    assert 'href="#signals"' in index_html
    assert 'id="watchlist-select"' not in index_html
    assert 'id="watchlist-table"' not in index_html
    assert 'id="watchlists-sync"' in index_html
    assert 'id="watchlist-search"' in index_html
    assert 'id="watchlists-expand"' in index_html
    assert 'id="watchlists-collapse"' in index_html
    assert 'id="watchlists-list"' in index_html
    assert 'id="asset-currency"' in index_html
    assert 'id="detail-kicker"' in index_html
    overview_start = index_html.index('data-page="overview"')
    watchlists_start = index_html.index('data-page="watchlists"')
    signals_start = index_html.index('data-page="signals"')
    assert watchlists_start < signals_start
    assert index_html.index('data-page="watchlists"') < index_html.index('id="watchlists"')
    assert index_html.index('data-page="signals"') < index_html.index('id="signals"')
    assert 'id="signals"' not in index_html[overview_start:watchlists_start]
    assert "let activePage" in app_js
    assert 'const appPages = ["overview", "watchlists", "signals"]' in app_js
    assert 'const defaultAssetCurrencies = ["USD", "HKD", "AUD", "CNH", "SGD", "JPY"]' in app_js
    assert "let watchlistSearchQuery" in app_js
    assert "let watchlistExpansionMode" in app_js
    assert "let activeDetailMode" in app_js
    assert "function pageFromHash()" in app_js
    assert "function setActivePage(page)" in app_js
    assert "function assetCurrency()" in app_js
    assert "function setAssetCurrencyOptions" in app_js
    assert "currency: assetCurrency()" in app_js
    assert "let currentWatchlists" in app_js
    assert "function renderSignals()" in app_js
    assert "function renderPositions()" in app_js
    assert "function renderAccountResearch()" in app_js
    assert "renderPositionsTable(sortedPositions(currentPositions))" in app_js
    assert "renderSignalsAndPositions" not in app_js
    assert "function renderWatchlistTable(rows)" in app_js
    assert "function renderWatchlists(groups)" in app_js
    assert "function visibleWatchlistGroups(groups)" in app_js
    assert "function isWatchlistCollapsed(group, index)" in app_js
    assert "function setWatchlistExpansionMode(mode)" in app_js
    assert "function holdingStatusForSecurity(security)" in app_js
    assert "function bindOpenWatchlistDetail(node, security)" in app_js
    assert "function openWatchlistDetail(code)" in app_js
    assert "function renderWatchlistDetail(security)" in app_js
    assert 'table.className = "watchlist-table"' in app_js
    assert 'if (column === "name") cell.title = text(value);' in app_js
    assert "Held" in app_js
    assert "Watchlist research" in app_js
    assert "function fetchMarketDataSnapshotsInBatches(codes)" in app_js
    assert "function watchlistsWithSnapshots(groups, snapshotsByCode)" in app_js
    assert "function setWatchlistsSyncing(syncing)" in app_js
    assert "function syncWatchlistsFromOpenD()" in app_js
    assert "function loadWatchlists(loadId)" in app_js
    assert "function loadOverview()" in app_js
    assert "function loadWatchlistsPage" in app_js
    assert "/api/watchlists" in app_js
    assert "/api/watchlists/sync" in app_js
    assert "cache_missing" in app_js
    assert "Loaded from cache" in app_js
    assert 'group_type: "CUSTOM"' in app_js
    assert ".page-panel" in style_css
    assert ".page-panel[hidden]" in style_css
    assert ".watchlist-toolbar" in style_css
    assert ".watchlist-table" in style_css
    assert ".asset-currency-control" in style_css
    assert "table-layout: fixed" in style_css
    assert "min-width: 1160px" not in style_css
    assert "text-overflow: ellipsis" in style_css
    assert ".watchlists-stack" in style_css
    assert ".watchlist-card" in style_css
    assert ".watchlist-toggle" in style_css


def test_account_web_remains_read_only_static_boundary():
    root = os.path.dirname(os.path.dirname(__file__))
    account_web_root = os.path.join(root, "moomoo/examples/account_web")
    forbidden = [
        "unlock_trade(",
        "place_order(",
        "modify_order(",
        "cancel_all_order(",
        "password",
        "pwd_unlock",
        "unlock_pwd",
    ]

    for directory, _, filenames in os.walk(account_web_root):
        for filename in filenames:
            if not filename.endswith((".py", ".js", ".html", ".css")):
                continue
            content = open(os.path.join(directory, filename), encoding="utf-8").read()
            for needle in forbidden:
                assert needle not in content


def test_mask_account_id():
    assert service.mask_account_id("1234567890") == "1234...7890"
    assert service.mask_account_id("12345678") == "********"
