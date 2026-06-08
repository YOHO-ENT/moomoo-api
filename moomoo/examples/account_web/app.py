# -*- coding: utf-8 -*-
"""FastAPI routes for the local read-only account dashboard."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .market_data import fetch_market_data_snapshots, fetch_market_data_status, split_codes_param
from .schemas import DashboardPayload, MarketDataSnapshotsPayload, MarketDataStatusPayload, WatchlistsPayload
from .service import (
    DEFAULT_HOST,
    DEFAULT_MARKET,
    DEFAULT_PORT,
    DEFAULT_WATCHLIST_GROUP_TYPE,
    build_dashboard_payload,
    build_watchlists_payload,
    sync_watchlists_cache,
)


STATIC_DIR = Path(__file__).with_name("static")

app = FastAPI(title="moomoo Account Dashboard", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=FileResponse)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/dashboard", response_model=DashboardPayload)
def api_dashboard(
    host: str = Query(DEFAULT_HOST),
    port: int = Query(DEFAULT_PORT, ge=1, le=65535),
    market: str = Query(DEFAULT_MARKET, pattern="^(HK|US)$"),
):
    try:
        return build_dashboard_payload(host, port, market)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/market-data/status", response_model=MarketDataStatusPayload)
def api_market_data_status():
    return fetch_market_data_status()


@app.get("/api/market-data/snapshots", response_model=MarketDataSnapshotsPayload)
def api_market_data_snapshots(
    codes: str = Query(..., min_length=1),
    benchmark: str = Query(None),
):
    requested_codes = split_codes_param(codes)
    if not requested_codes:
        raise HTTPException(status_code=400, detail="Provide at least one code.")
    return fetch_market_data_snapshots(requested_codes, benchmark=benchmark)


@app.get("/api/watchlists", response_model=WatchlistsPayload)
def api_watchlists(
    host: str = Query(DEFAULT_HOST),
    port: int = Query(DEFAULT_PORT, ge=1, le=65535),
    group_type: str = Query(DEFAULT_WATCHLIST_GROUP_TYPE),
):
    try:
        return build_watchlists_payload(host, port, group_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/api/watchlists/sync", response_model=WatchlistsPayload)
def api_watchlists_sync(
    host: str = Query(DEFAULT_HOST),
    port: int = Query(DEFAULT_PORT, ge=1, le=65535),
    group_type: str = Query(DEFAULT_WATCHLIST_GROUP_TYPE),
):
    try:
        return sync_watchlists_cache(host, port, group_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def main():
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8501)


if __name__ == "__main__":
    main()
