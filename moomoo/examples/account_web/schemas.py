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
