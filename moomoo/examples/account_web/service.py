# -*- coding: utf-8 -*-
"""Read-only moomoo SDK access for the local account dashboard."""

import os
from contextlib import contextmanager

import pandas as pd

import moomoo as ft


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11111
DEFAULT_MARKET = "US"
MARKETS = {
    "HK": ft.TrdMarket.HK,
    "US": ft.TrdMarket.US,
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
