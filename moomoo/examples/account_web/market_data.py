# -*- coding: utf-8 -*-
"""Read-only Market Data Lab HTTP adapter for the local dashboard."""

import os
import re

import httpx


DEFAULT_API_URL = "http://127.0.0.1:8010"
DEFAULT_TIMEOUT_SEC = 2.5
DEFAULT_BENCHMARK = "SPY"
DEFAULT_UI_URL = "http://127.0.0.1:3020"

US_OPTION_RE = re.compile(r"\d{6}[CP]\d{8}$")


def market_data_api_url():
    return os.environ.get("MOOMOO_MARKET_DATA_API_URL", DEFAULT_API_URL).rstrip("/")


def market_data_ui_url():
    return os.environ.get("MOOMOO_MARKET_DATA_UI_URL", DEFAULT_UI_URL).rstrip("/")


def market_data_timeout_sec():
    raw_value = os.environ.get("MOOMOO_MARKET_DATA_TIMEOUT_SEC")
    if not raw_value:
        return DEFAULT_TIMEOUT_SEC
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_TIMEOUT_SEC


def market_data_benchmark(benchmark=None):
    value = benchmark or os.environ.get("MOOMOO_MARKET_DATA_BENCHMARK") or DEFAULT_BENCHMARK
    return str(value).strip().upper() or DEFAULT_BENCHMARK


def map_moomoo_code(code):
    source_code = str(code or "").strip().upper()
    result = {
        "source_code": source_code,
        "ticker": None,
        "mapping_status": "unsupported",
        "mapping_warning": None,
    }

    if not source_code:
        result["mapping_warning"] = "empty code"
        return result

    if "." not in source_code:
        result["mapping_warning"] = "missing market prefix"
        return result

    market, symbol = source_code.split(".", 1)
    if not symbol:
        result["mapping_warning"] = "missing symbol"
        return result

    if market == "US":
        if US_OPTION_RE.search(symbol):
            result["mapping_warning"] = "US derivatives are not supported"
            return result
        if not re.match(r"^[A-Z0-9][A-Z0-9.\-=]{0,31}$", symbol):
            result["mapping_warning"] = "unsupported US symbol"
            return result
        result["ticker"] = symbol
        result["mapping_status"] = "mapped"
        return result

    if market == "HK":
        if not symbol.isdigit():
            result["mapping_warning"] = "unsupported HK symbol"
            return result
        stripped = symbol.lstrip("0") or "0"
        ticker_symbol = stripped.zfill(4) if len(stripped) <= 4 else stripped
        result["ticker"] = "{}.HK".format(ticker_symbol)
        result["mapping_status"] = "mapped"
        return result

    result["mapping_warning"] = "unsupported market {}".format(market)
    return result


def unavailable_snapshot(mapping, warning):
    return {
        "source_code": mapping.get("source_code"),
        "ticker": mapping.get("ticker"),
        "mapping_status": mapping.get("mapping_status", "unsupported"),
        "mapping_warning": mapping.get("mapping_warning"),
        "as_of": None,
        "currency": "unavailable",
        "price": None,
        "trend": "unavailable",
        "rsi14": None,
        "breakout_status": "unavailable",
        "trend_score": None,
        "liquidity_score": None,
        "relative_strength_vs_spy": {"status": "unavailable", "periods": {}},
        "volume_signal": {"status": "unavailable"},
        "data_quality": {
            "status": "unavailable",
            "warnings": [warning],
            "source": "market-data-lab",
            "as_of": None,
        },
        "market_data_url": None,
    }


def market_data_url_for_ticker(ticker):
    if not ticker:
        return None
    return "{}/market/{}".format(market_data_ui_url(), ticker)


def split_codes_param(codes):
    return [item.strip() for item in str(codes or "").split(",") if item.strip()]


def build_status_payload(status_data=None, available=False, error=None):
    return {
        "available": available,
        "api_url": market_data_api_url(),
        "ui_url": market_data_ui_url(),
        "status": status_data or {},
        "error": error,
    }


def fetch_market_data_status(client=None):
    api_url = market_data_api_url()
    close_client = client is None
    client = client or httpx.Client(timeout=market_data_timeout_sec())
    try:
        response = client.get("{}/status".format(api_url))
        response.raise_for_status()
        return build_status_payload(response.json(), available=True)
    except Exception as exc:
        return build_status_payload(available=False, error="market-data-lab unreachable: {}".format(exc))
    finally:
        if close_client:
            client.close()


def fetch_market_data_snapshots(codes, benchmark=None, client=None):
    mappings = [map_moomoo_code(code) for code in codes]
    mapped_tickers = _unique([item["ticker"] for item in mappings if item["mapping_status"] == "mapped"])
    benchmark = market_data_benchmark(benchmark)
    api_url = market_data_api_url()

    if not mappings:
        return _snapshots_payload([], benchmark, available=True, status="ok")

    if not mapped_tickers:
        results = [unavailable_snapshot(item, item.get("mapping_warning") or "unsupported code") for item in mappings]
        return _snapshots_payload(results, benchmark, available=True, status="ok")

    close_client = client is None
    client = client or httpx.Client(timeout=market_data_timeout_sec())
    try:
        response = client.get(
            "{}/snapshots".format(api_url),
            params={
                "tickers": ",".join(mapped_tickers),
                "benchmark": benchmark,
                "limit": len(mapped_tickers),
            },
        )
        response.raise_for_status()
        snapshot_payload = response.json()
        snapshots_by_ticker = {
            str(item.get("ticker", "")).upper(): item
            for item in snapshot_payload.get("snapshots", [])
            if isinstance(item, dict)
        }
        results = [_result_for_mapping(mapping, snapshots_by_ticker) for mapping in mappings]
        return _snapshots_payload(results, benchmark, available=True, status=snapshot_payload.get("status", "ok"))
    except Exception as exc:
        warning = "market-data-lab unreachable: {}".format(exc)
        results = [
            unavailable_snapshot(mapping, warning if mapping["mapping_status"] == "mapped" else mapping.get("mapping_warning"))
            for mapping in mappings
        ]
        return _snapshots_payload(results, benchmark, available=False, status="unavailable", error=warning)
    finally:
        if close_client:
            client.close()


def _result_for_mapping(mapping, snapshots_by_ticker):
    if mapping["mapping_status"] != "mapped":
        return unavailable_snapshot(mapping, mapping.get("mapping_warning") or "unsupported code")

    snapshot = snapshots_by_ticker.get(mapping["ticker"])
    if not snapshot:
        return unavailable_snapshot(mapping, "snapshot unavailable")

    result = dict(snapshot)
    result["source_code"] = mapping["source_code"]
    result["ticker"] = mapping["ticker"]
    result["mapping_status"] = mapping["mapping_status"]
    result["mapping_warning"] = None
    result["market_data_url"] = market_data_url_for_ticker(mapping["ticker"])
    return result


def _snapshots_payload(results, benchmark, available, status, error=None):
    return {
        "status": status,
        "available": available,
        "api_url": market_data_api_url(),
        "ui_url": market_data_ui_url(),
        "benchmark": benchmark,
        "requested_count": len(results),
        "mapped_count": len([item for item in results if item.get("mapping_status") == "mapped"]),
        "count": len(results),
        "results": results,
        "error": error,
    }


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
