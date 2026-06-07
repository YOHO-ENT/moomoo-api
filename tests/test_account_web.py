# -*- coding: utf-8 -*-
"""Tests for the local read-only account dashboard."""

import os

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


def test_dashboard_route_blocks_remote_before_opend():
    client = TestClient(account_app.app)
    response = client.get("/api/dashboard?host=192.168.1.20&port=11111&market=US")

    assert response.status_code == 400
    assert service.ALLOW_REMOTE_ENV in response.json()["detail"]


def test_dashboard_route_uses_masked_payload(monkeypatch):
    payload = {
        "connection": {"host": "127.0.0.1", "port": 11111, "market": "US", "security_firm": "FUTUAU"},
        "state": {"program_status_type": "READY", "qot_logined": True, "trd_logined": True},
        "account": {"acc_id": "1234...7890"},
        "assets": {"total_assets": 1000},
        "positions": [],
        "position_count": 0,
    }
    monkeypatch.setattr(account_app, "build_dashboard_payload", lambda host, port, market: payload)

    response = TestClient(account_app.app).get("/api/dashboard?host=127.0.0.1&port=11111&market=US")

    assert response.status_code == 200
    assert response.json()["account"]["acc_id"] == "1234...7890"


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


def test_mask_account_id():
    assert service.mask_account_id("1234567890") == "1234...7890"
    assert service.mask_account_id("12345678") == "********"
