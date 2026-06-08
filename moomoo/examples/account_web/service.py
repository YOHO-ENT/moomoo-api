# -*- coding: utf-8 -*-
"""Read-only moomoo SDK access for the local account dashboard."""

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import moomoo as ft


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11111
DEFAULT_MARKET = "US"
DEFAULT_WATCHLIST_GROUP_TYPE = "CUSTOM"
WATCHLIST_CACHE_DIR_ENV = "MOOMOO_ACCOUNT_WEB_CACHE_DIR"
WATCHLIST_CACHE_FILE = "watchlists_cache.json"
WATCHLIST_SYNC_DELAY_SEC = 3.2
MARKETS = {
    "HK": ft.TrdMarket.HK,
    "US": ft.TrdMarket.US,
}
WATCHLIST_GROUP_TYPES = {
    "CUSTOM": ft.UserSecurityGroupType.CUSTOM,
    "ALL": ft.UserSecurityGroupType.ALL,
    "SYSTEM": ft.UserSecurityGroupType.SYSTEM,
}
SECURITY_FIRM = ft.SecurityFirm.FUTUAU
REAL_ENV = ft.TrdEnv.REAL
LOCAL_OPEND_HOSTS = {"127.0.0.1", "localhost", "::1"}
ALLOW_REMOTE_ENV = "MOOMOO_ACCOUNT_WEB_ALLOW_REMOTE"


def remote_opend_allowed():
    return os.environ.get(ALLOW_REMOTE_ENV) == "1"


def is_local_opend_host(host):
    return str(host or "").strip().lower() in LOCAL_OPEND_HOSTS


def validate_opend_host(host):
    if is_local_opend_host(host) or remote_opend_allowed():
        return
    raise ValueError(
        "Remote OpenD host is disabled for the local account dashboard. "
        "Use 127.0.0.1, localhost, or ::1, or set {}=1.".format(ALLOW_REMOTE_ENV)
    )


def normalize_watchlist_group_type(group_type):
    group_type = str(group_type or DEFAULT_WATCHLIST_GROUP_TYPE).strip().upper()
    if group_type not in WATCHLIST_GROUP_TYPES:
        raise ValueError("group_type must be one of CUSTOM, ALL, or SYSTEM.")
    return group_type, WATCHLIST_GROUP_TYPES[group_type]


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def watchlists_cache_dir():
    raw_path = os.environ.get(WATCHLIST_CACHE_DIR_ENV)
    if raw_path:
        return Path(raw_path).expanduser()
    return Path.home() / ".moomoo-api" / "account_web"


def watchlists_cache_path():
    return watchlists_cache_dir() / WATCHLIST_CACHE_FILE


def empty_watchlists_payload(group_type_name=DEFAULT_WATCHLIST_GROUP_TYPE, source="cache_missing", error=None):
    group_type_name, _ = normalize_watchlist_group_type(group_type_name)
    return {
        "source": source,
        "synced_at": None,
        "cache_path": str(watchlists_cache_path()),
        "group_type": group_type_name,
        "group_count": 0,
        "security_count": 0,
        "groups": [],
        "error": error,
    }


def watchlists_payload(source, group_type_name, groups, synced_at=None, error=None):
    group_type_name, _ = normalize_watchlist_group_type(group_type_name)
    groups = groups or []
    return {
        "source": source,
        "synced_at": synced_at,
        "cache_path": str(watchlists_cache_path()),
        "group_type": group_type_name,
        "group_count": len(groups),
        "security_count": sum(len(group.get("securities") or []) for group in groups if not group.get("error")),
        "groups": groups,
        "error": error,
    }


def mask_account_id(value):
    text = str(value)
    if len(text) <= 8:
        return "*" * len(text)
    return "{}...{}".format(text[:4], text[-4:])


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def records(frame, columns=None):
    if columns is not None:
        columns = [column for column in columns if column in frame.columns]
        frame = frame[columns]
    return [json_safe(row) for row in frame.to_dict(orient="records")]


@contextmanager
def quote_context(host, port):
    ctx = None
    try:
        ctx = ft.OpenQuoteContext(host=host, port=port)
        yield ctx
    finally:
        if ctx is not None:
            ctx.close()


@contextmanager
def trade_context(host, port, market):
    ctx = None
    try:
        ctx = ft.OpenSecTradeContext(
            filter_trdmarket=market,
            host=host,
            port=port,
            security_firm=SECURITY_FIRM,
        )
        yield ctx
    finally:
        if ctx is not None:
            ctx.close()


def load_global_state(host, port):
    with quote_context(host, port) as ctx:
        ret, data = ctx.get_global_state()
    if ret != ft.RET_OK:
        raise RuntimeError(data)
    return json_safe(data)


def watchlist_security_columns():
    return [
        "code",
        "name",
        "lot_size",
        "stock_type",
        "stock_child_type",
        "stock_owner",
        "stock_id",
        "suspension",
        "listing_date",
        "delisting",
    ]


def read_watchlists_cache(group_type_name=DEFAULT_WATCHLIST_GROUP_TYPE):
    normalize_watchlist_group_type(group_type_name)
    path = watchlists_cache_path()
    if not path.exists():
        return empty_watchlists_payload(group_type_name, source="cache_missing", error="watchlists cache not found")

    try:
        with path.open("r", encoding="utf-8") as cache_file:
            payload = json.load(cache_file)
    except Exception as exc:
        return empty_watchlists_payload(group_type_name, source="cache_error", error="failed to read cache: {}".format(exc))

    groups = payload.get("groups")
    if not isinstance(groups, list):
        return empty_watchlists_payload(group_type_name, source="cache_error", error="cache payload is missing groups")

    cached_group_type = payload.get("group_type") or group_type_name
    return watchlists_payload(
        source="cache",
        group_type_name=cached_group_type,
        groups=groups,
        synced_at=payload.get("synced_at"),
        error=payload.get("error"),
    )


def write_watchlists_cache(payload):
    path = watchlists_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    cache_payload = dict(payload)
    cache_payload["cache_path"] = str(path)
    with tmp_path.open("w", encoding="utf-8") as cache_file:
        json.dump(cache_payload, cache_file, ensure_ascii=True, indent=2, sort_keys=True)
        cache_file.write("\n")
    tmp_path.replace(path)
    return cache_payload


def load_watchlist_groups_from_opend(ctx, sdk_group_type):
    ret, groups = ctx.get_user_security_group(sdk_group_type)
    if ret != ft.RET_OK:
        raise RuntimeError(groups)
    return records(groups, ["group_name", "group_type"])


def load_watchlist_securities_from_opend(ctx, group_name):
    ret, securities = ctx.get_user_security(group_name)
    if ret != ft.RET_OK:
        return ret, str(securities), []
    return ret, None, records(securities, watchlist_security_columns())


def watchlist_sync_sleep(seconds=WATCHLIST_SYNC_DELAY_SEC):
    time.sleep(seconds)


def build_watchlists_payload(host=None, port=None, group_type_name=DEFAULT_WATCHLIST_GROUP_TYPE):
    if host is not None:
        validate_opend_host(host)
    return read_watchlists_cache(group_type_name)


def sync_watchlists_cache(host, port, group_type_name=DEFAULT_WATCHLIST_GROUP_TYPE, sleep_func=watchlist_sync_sleep):
    validate_opend_host(host)
    group_type_name, sdk_group_type = normalize_watchlist_group_type(group_type_name)

    with quote_context(host, port) as ctx:
        group_records = load_watchlist_groups_from_opend(ctx, sdk_group_type)
        watchlists = []

        for index, group in enumerate(group_records):
            group_name = group.get("group_name")
            item = {
                "group_name": group_name,
                "group_type": group.get("group_type"),
                "count": 0,
                "securities": [],
                "error": None,
            }

            if not group_name:
                item["error"] = "group_name unavailable"
                watchlists.append(item)
                continue

            ret, error, security_records = load_watchlist_securities_from_opend(ctx, group_name)
            if ret != ft.RET_OK:
                item["error"] = error
                watchlists.append(item)
            else:
                item["securities"] = security_records
                item["count"] = len(security_records)
                watchlists.append(item)

            if index < len(group_records) - 1:
                sleep_func(WATCHLIST_SYNC_DELAY_SEC)

    payload = watchlists_payload(
        source="opend_sync",
        group_type_name=group_type_name,
        groups=watchlists,
        synced_at=utc_now_iso(),
    )
    return write_watchlists_cache(payload)


def load_account_data(host, port, market):
    with trade_context(host, port, market) as ctx:
        ret, accounts = ctx.get_acc_list()
        if ret != ft.RET_OK:
            raise RuntimeError(accounts)

        real_accounts = accounts[accounts["trd_env"] == REAL_ENV].copy()
        if real_accounts.empty:
            raise RuntimeError("No FUTUAU REAL account is available for the selected market.")

        ret, accinfo = ctx.accinfo_query(trd_env=REAL_ENV)
        if ret != ft.RET_OK:
            raise RuntimeError(accinfo)

        ret, positions = ctx.position_list_query(trd_env=REAL_ENV)
        if ret != ft.RET_OK:
            raise RuntimeError(positions)

    real_accounts["acc_id"] = real_accounts["acc_id"].map(mask_account_id)
    return real_accounts, accinfo, positions


def build_dashboard_payload(host, port, market_name):
    validate_opend_host(host)
    market = MARKETS[market_name]
    state = load_global_state(host, port)
    accounts, accinfo, positions = load_account_data(host, port, market)

    account_columns = [
        "acc_id",
        "trd_env",
        "acc_type",
        "security_firm",
        "trdmarket_auth",
        "acc_status",
        "acc_role",
    ]
    asset_columns = [
        "total_assets",
        "cash",
        "market_val",
        "power",
        "currency",
        "hk_cash",
        "hkd_assets",
        "us_cash",
        "usd_assets",
        "au_cash",
        "aud_assets",
    ]
    position_columns = [
        "code",
        "stock_name",
        "qty",
        "can_sell_qty",
        "cost_price",
        "nominal_price",
        "market_val",
        "pl_val",
        "pl_ratio",
        "position_side",
    ]

    account_records = records(accounts, account_columns)
    asset_records = records(accinfo, asset_columns)
    position_records = records(positions, position_columns)

    return {
        "connection": {
            "host": host,
            "port": port,
            "market": market_name,
            "security_firm": SECURITY_FIRM,
        },
        "state": state,
        "account": account_records[0] if account_records else {},
        "assets": asset_records[0] if asset_records else {},
        "positions": position_records,
        "position_count": len(position_records),
    }
