# -*- coding: utf-8 -*-
"""API response schemas for the local account dashboard."""

from typing import Any, Dict, List

from pydantic import BaseModel


class DashboardPayload(BaseModel):
    connection: Dict[str, Any]
    state: Dict[str, Any]
    account: Dict[str, Any]
    assets: Dict[str, Any]
    positions: List[Dict[str, Any]]
    position_count: int


class MarketDataStatusPayload(BaseModel):
    available: bool
    api_url: str
    ui_url: str
    status: Dict[str, Any]
    error: Any = None


class MarketDataSnapshotsPayload(BaseModel):
    status: str
    available: bool
    api_url: str
    ui_url: str
    benchmark: str
    requested_count: int
    mapped_count: int
    count: int
    results: List[Dict[str, Any]]
    error: Any = None


class WatchlistsPayload(BaseModel):
    source: str
    synced_at: Any = None
    cache_path: str
    group_type: str
    group_count: int
    security_count: int
    groups: List[Dict[str, Any]]
    error: Any = None


class WatchlistsStatusPayload(BaseModel):
    source: str
    status: str
    synced_at: Any = None
    group_type: str
    group_count: int
    security_count: int
    error: Any = None


class WatchlistsExportPayload(BaseModel):
    source: str
    status: str
    synced_at: Any = None
    group_type: str
    group_count: int
    security_count: int
    groups: List[Dict[str, Any]]
    error: Any = None


class PositionsExportPayload(BaseModel):
    source: str
    status: str
    available: bool
    market: str
    position_count: int
    positions: List[Dict[str, Any]]
    error: Any = None


class RealizedPlPayload(BaseModel):
    status: str
    market: str
    start: str
    end: str
    first_realized_at: Any = None
    last_realized_at: Any = None
    currency_totals: Dict[str, Any]
    count: int
    items: List[Dict[str, Any]]
    error: Any = None


class ResearchUniverseExportPayload(BaseModel):
    source: str
    status: str
    synced_at: Any = None
    market: str
    positions_status: str
    watchlists_status: str
    item_count: int
    held_count: int
    watchlist_security_count: int
    items: List[Dict[str, Any]]
    error: Any = None
