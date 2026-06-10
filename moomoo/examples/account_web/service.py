# -*- coding: utf-8 -*-
"""Read-only moomoo SDK access for the local account dashboard."""

import ast
import json
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

import moomoo as ft

from .market_data import map_moomoo_code, market_data_url_for_ticker


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11111
DEFAULT_MARKET = "US"
DEFAULT_ASSET_CURRENCY = "USD"
DEFAULT_WATCHLIST_GROUP_TYPE = "CUSTOM"
REALIZED_PL_START = "2010-01-01"
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
ASSET_CURRENCIES = {
    "USD": ft.Currency.USD,
    "HKD": ft.Currency.HKD,
    "AUD": ft.Currency.AUD,
    "CNH": ft.Currency.CNH,
    "SGD": ft.Currency.SGD,
    "JPY": ft.Currency.JPY,
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


def normalize_asset_currency(currency):
    currency = str(currency or DEFAULT_ASSET_CURRENCY).strip().upper()
    if currency not in ASSET_CURRENCIES:
        raise ValueError("currency must be one of {}.".format(", ".join(ASSET_CURRENCIES)))
    return currency, ASSET_CURRENCIES[currency]


def normalize_market(market_name):
    market_name = str(market_name or DEFAULT_MARKET).strip().upper()
    if market_name not in MARKETS:
        raise ValueError("market must be one of {}.".format(", ".join(MARKETS)))
    return market_name, MARKETS[market_name]


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


def watchlists_export_status(cache_payload):
    source = cache_payload.get("source")
    if source == "cache":
        return "ok"
    return source or "unknown"


def export_security_record(security, name_key="name", held=False, order=None):
    code = security.get("code")
    mapping = map_moomoo_code(code)
    record = {
        "code": mapping.get("source_code") or str(code or "").strip().upper(),
        "name": security.get(name_key) or security.get("name") or security.get("stock_name"),
        "market_data_ticker": mapping.get("ticker"),
        "mapping_status": mapping.get("mapping_status"),
        "mapping_warning": mapping.get("mapping_warning"),
        "held": held,
    }
    if order is not None:
        record["order"] = order
    return record


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


def decimal_value(value):
    if value is None:
        return Decimal("0")
    try:
        if pd.isna(value):
            return Decimal("0")
    except (TypeError, ValueError):
        pass
    text = str(value).strip().replace(",", "")
    if text in {"", "N/A", "NA", "None", "nan"}:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def text_value(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def decimal_json(value, places="0.01"):
    return float(decimal_value(value).quantize(Decimal(places)))


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


def build_watchlists_status_payload(group_type_name=DEFAULT_WATCHLIST_GROUP_TYPE):
    cache_payload = read_watchlists_cache(group_type_name)
    return {
        "source": "moomoo-cache",
        "status": watchlists_export_status(cache_payload),
        "synced_at": cache_payload.get("synced_at"),
        "group_type": cache_payload.get("group_type"),
        "group_count": cache_payload.get("group_count", 0),
        "security_count": cache_payload.get("security_count", 0),
        "error": cache_payload.get("error"),
    }


def build_watchlists_export_payload(group_type_name=DEFAULT_WATCHLIST_GROUP_TYPE):
    cache_payload = read_watchlists_cache(group_type_name)
    groups = []

    for group_order, group in enumerate(cache_payload.get("groups") or []):
        securities = [
            export_security_record(security, order=security_order)
            for security_order, security in enumerate(group.get("securities") or [])
        ]
        groups.append(
            {
                "name": group.get("group_name"),
                "type": group.get("group_type"),
                "order": group_order,
                "count": len(securities),
                "securities": securities,
                "error": group.get("error"),
            }
        )

    return {
        "source": "moomoo-cache",
        "status": watchlists_export_status(cache_payload),
        "synced_at": cache_payload.get("synced_at"),
        "group_type": cache_payload.get("group_type"),
        "group_count": len(groups),
        "security_count": sum(len(group["securities"]) for group in groups if not group.get("error")),
        "groups": groups,
        "error": cache_payload.get("error"),
    }


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


def realized_pl_end_date():
    return date.today().isoformat()


def dedupe_frame(frame, columns):
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    columns = [column for column in columns if column in frame.columns]
    if not columns:
        return frame.copy()
    return frame.drop_duplicates(subset=columns).copy()


def order_ids_from_orders(orders):
    ids = []
    seen = set()
    if orders.empty or "order_id" not in orders.columns:
        return ids
    for value in orders["order_id"].tolist():
        order_id = text_value(value)
        if order_id and order_id not in seen:
            seen.add(order_id)
            ids.append(order_id)
    return ids


def load_realized_pl_data_from_opend(host, port, market, start, end):
    with trade_context(host, port, market) as ctx:
        ret, deals = ctx.history_deal_list_query(start=start, end=end, trd_env=REAL_ENV)
        if ret != ft.RET_OK:
            raise RuntimeError(deals)

        ret, orders = ctx.history_order_list_query(start=start, end=end, trd_env=REAL_ENV)
        if ret != ft.RET_OK:
            raise RuntimeError(orders)

        fee_frames = []
        for index in range(0, len(order_ids_from_orders(orders)), 20):
            order_ids = order_ids_from_orders(orders)[index:index + 20]
            ret, fees = ctx.order_fee_query(order_id_list=order_ids, trd_env=REAL_ENV)
            if ret == ft.RET_OK and isinstance(fees, pd.DataFrame) and not fees.empty:
                fee_frames.append(fees.copy())
            elif ret != ft.RET_OK:
                raise RuntimeError(fees)

    fees = pd.concat(fee_frames, ignore_index=True) if fee_frames else pd.DataFrame()
    return deals, orders, fees


def fee_amounts_by_order(fees):
    amounts = defaultdict(Decimal)
    if fees.empty:
        return amounts
    for _, row in fees.iterrows():
        amounts[text_value(row.get("order_id"))] += decimal_value(row.get("fee_amount"))
    return amounts


def order_currency_map(orders):
    currencies = {}
    if orders.empty:
        return currencies
    for _, row in orders.iterrows():
        order_id = text_value(row.get("order_id"))
        currency = text_value(row.get("currency")).upper()
        code = text_value(row.get("code")).upper()
        if not currency or currency == "N/A":
            if code.startswith("US."):
                currency = "USD"
            elif code.startswith("HK."):
                currency = "HKD"
            else:
                currency = "UNKNOWN"
        if order_id:
            currencies[order_id] = currency
    return currencies


def currency_for_deal(row, order_currencies):
    order_id = text_value(row.get("order_id"))
    if order_id in order_currencies:
        return order_currencies[order_id]
    code = text_value(row.get("code")).upper()
    if code.startswith("US."):
        return "USD"
    if code.startswith("HK."):
        return "HKD"
    return "UNKNOWN"


def allocated_deal_fees(deals, fees):
    order_fees = fee_amounts_by_order(fees)
    order_notional = defaultdict(Decimal)
    for _, row in deals.iterrows():
        order_notional[text_value(row.get("order_id"))] += decimal_value(row.get("qty")) * decimal_value(row.get("price"))

    allocated = []
    for _, row in deals.iterrows():
        order_id = text_value(row.get("order_id"))
        total_notional = order_notional.get(order_id, Decimal("0"))
        total_fee = order_fees.get(order_id, Decimal("0"))
        if total_notional <= 0 or total_fee == 0:
            allocated.append(Decimal("0"))
        else:
            notional = decimal_value(row.get("qty")) * decimal_value(row.get("price"))
            allocated.append(total_fee * notional / total_notional)
    return allocated


def realized_item_key(currency, code, name):
    return "{}|{}|{}".format(currency, code, name)


def realized_item(items, currency, code, name):
    key = realized_item_key(currency, code, name)
    if key not in items:
        items[key] = {
            "code": code,
            "stock_name": name,
            "currency": currency,
            "gross_realized_pl": Decimal("0"),
            "realized_fee": Decimal("0"),
            "net_realized_pl": Decimal("0"),
            "closed_qty": Decimal("0"),
            "realized_trade_count": 0,
            "first_realized_at": None,
            "last_realized_at": None,
        }
    return items[key]


def add_realized_event(items, currency, code, name, closed_qty, gross_pl, realized_fee, realized_at):
    item = realized_item(items, currency, code, name)
    item["gross_realized_pl"] += gross_pl
    item["realized_fee"] += realized_fee
    item["net_realized_pl"] += gross_pl - realized_fee
    item["closed_qty"] += closed_qty
    item["realized_trade_count"] += 1
    realized_at = text_value(realized_at)
    if realized_at and (not item["first_realized_at"] or realized_at < item["first_realized_at"]):
        item["first_realized_at"] = realized_at
    if realized_at and (not item["last_realized_at"] or realized_at > item["last_realized_at"]):
        item["last_realized_at"] = realized_at


def realized_items_to_json(items):
    output = []
    for item in items.values():
        mapping = map_moomoo_code(item["code"])
        output.append({
            "code": mapping.get("source_code") or item["code"],
            "stock_name": item["stock_name"],
            "currency": item["currency"],
            "market_data_ticker": mapping.get("ticker"),
            "mapping_status": mapping.get("mapping_status"),
            "mapping_warning": mapping.get("mapping_warning"),
            "market_data_url": market_data_url_for_ticker(mapping.get("ticker")),
            "gross_realized_pl": decimal_json(item["gross_realized_pl"]),
            "realized_fee": decimal_json(item["realized_fee"]),
            "net_realized_pl": decimal_json(item["net_realized_pl"]),
            "closed_qty": decimal_json(item["closed_qty"], "0.0001"),
            "realized_trade_count": item["realized_trade_count"],
            "first_realized_at": item["first_realized_at"],
            "last_realized_at": item["last_realized_at"],
        })
    return sorted(output, key=lambda row: row["net_realized_pl"], reverse=True)


def realized_currency_totals(items):
    totals = {}
    for item in items.values():
        currency = item["currency"] or "UNKNOWN"
        if currency not in totals:
            totals[currency] = {
                "gross_realized_pl": Decimal("0"),
                "realized_fee": Decimal("0"),
                "net_realized_pl": Decimal("0"),
                "closed_qty": Decimal("0"),
                "realized_trade_count": 0,
            }
        totals[currency]["gross_realized_pl"] += item["gross_realized_pl"]
        totals[currency]["realized_fee"] += item["realized_fee"]
        totals[currency]["net_realized_pl"] += item["net_realized_pl"]
        totals[currency]["closed_qty"] += item["closed_qty"]
        totals[currency]["realized_trade_count"] += item["realized_trade_count"]

    return {
        currency: {
            "gross_realized_pl": decimal_json(values["gross_realized_pl"]),
            "realized_fee": decimal_json(values["realized_fee"]),
            "net_realized_pl": decimal_json(values["net_realized_pl"]),
            "closed_qty": decimal_json(values["closed_qty"], "0.0001"),
            "realized_trade_count": values["realized_trade_count"],
        }
        for currency, values in sorted(totals.items())
    }


def calculate_realized_pl(deals, orders, fees):
    deals = dedupe_frame(deals, ["deal_id", "order_id", "code", "qty", "price", "trd_side", "create_time"])
    orders = dedupe_frame(orders, ["order_id", "code", "dealt_qty", "dealt_avg_price", "trd_side", "create_time"])
    fees = dedupe_frame(fees, ["order_id", "fee_amount"])
    if deals.empty:
        return {}, [], None, None

    order_currencies = order_currency_map(orders)
    deals = deals.copy()
    deals["currency_calc"] = deals.apply(lambda row: currency_for_deal(row, order_currencies), axis=1)
    deals["fee_alloc"] = allocated_deal_fees(deals, fees)
    deals["create_time_sort"] = pd.to_datetime(deals.get("create_time"), errors="coerce")
    deals = deals.sort_values(["create_time_sort", "order_id", "deal_id"], kind="mergesort")

    states = defaultdict(lambda: {"gross_qty": Decimal("0"), "gross_cost": Decimal("0"), "net_qty": Decimal("0"), "net_cost": Decimal("0")})
    items = {}
    first_realized_at = None
    last_realized_at = None

    for _, row in deals.iterrows():
        side = text_value(row.get("trd_side")).upper()
        code = text_value(row.get("code")).upper()
        name = text_value(row.get("stock_name"))
        currency = text_value(row.get("currency_calc")).upper() or "UNKNOWN"
        qty = decimal_value(row.get("qty"))
        price = decimal_value(row.get("price"))
        fee = decimal_value(row.get("fee_alloc"))
        if not code or qty <= 0:
            continue

        state = states[(currency, code, name)]
        if side == "BUY":
            state["gross_qty"] += qty
            state["gross_cost"] += price * qty
            state["net_qty"] += qty
            state["net_cost"] += price * qty + fee
            continue

        if side != "SELL" or state["gross_qty"] <= 0 or state["net_qty"] <= 0:
            continue

        closing_qty = min(qty, state["gross_qty"], state["net_qty"])
        if closing_qty <= 0:
            continue

        avg_gross = state["gross_cost"] / state["gross_qty"]
        avg_net = state["net_cost"] / state["net_qty"]
        closing_fee = fee * (closing_qty / qty) if qty else Decimal("0")
        gross_pl = (price - avg_gross) * closing_qty
        net_pl = (price * closing_qty - closing_fee) - (avg_net * closing_qty)
        realized_fee = gross_pl - net_pl
        realized_at = text_value(row.get("create_time"))

        add_realized_event(items, currency, code, name, closing_qty, gross_pl, realized_fee, realized_at)
        if realized_at and (not first_realized_at or realized_at < first_realized_at):
            first_realized_at = realized_at
        if realized_at and (not last_realized_at or realized_at > last_realized_at):
            last_realized_at = realized_at

        state["gross_qty"] -= closing_qty
        state["gross_cost"] -= avg_gross * closing_qty
        state["net_qty"] -= closing_qty
        state["net_cost"] -= avg_net * closing_qty

    return realized_currency_totals(items), realized_items_to_json(items), first_realized_at, last_realized_at


def build_realized_pl_payload(host, port, market_name=DEFAULT_MARKET):
    validate_opend_host(host)
    market_name, market = normalize_market(market_name)
    start = REALIZED_PL_START
    end = realized_pl_end_date()

    try:
        deals, orders, fees = load_realized_pl_data_from_opend(host, port, market, start, end)
        currency_totals, items, first_realized_at, last_realized_at = calculate_realized_pl(deals, orders, fees)
    except Exception as exc:
        return {
            "status": "unavailable",
            "market": market_name,
            "start": start,
            "end": end,
            "first_realized_at": None,
            "last_realized_at": None,
            "currency_totals": {},
            "count": 0,
            "items": [],
            "error": str(exc),
        }

    return {
        "status": "ok",
        "market": market_name,
        "start": start,
        "end": end,
        "first_realized_at": first_realized_at,
        "last_realized_at": last_realized_at,
        "currency_totals": currency_totals,
        "count": len(items),
        "items": items,
        "error": None,
    }


def load_account_data(host, port, market, asset_currency):
    with trade_context(host, port, market) as ctx:
        ret, accounts = ctx.get_acc_list()
        if ret != ft.RET_OK:
            raise RuntimeError(accounts)

        real_accounts = accounts[accounts["trd_env"] == REAL_ENV].copy()
        if real_accounts.empty:
            raise RuntimeError("No FUTUAU REAL account is available for the selected market.")

        ret, accinfo = ctx.accinfo_query(trd_env=REAL_ENV, currency=asset_currency)
        if ret != ft.RET_OK:
            raise RuntimeError(accinfo)

        ret, positions = ctx.position_list_query(trd_env=REAL_ENV)
        if ret != ft.RET_OK:
            raise RuntimeError(positions)

    real_accounts["acc_id"] = real_accounts["acc_id"].map(mask_account_id)
    return real_accounts, accinfo, positions


def load_position_export_records(host, port, market):
    with trade_context(host, port, market) as ctx:
        ret, positions = ctx.position_list_query(trd_env=REAL_ENV)
        if ret != ft.RET_OK:
            raise RuntimeError(positions)
    return records(positions, ["code", "stock_name"])


def build_positions_export_payload(host, port, market_name=DEFAULT_MARKET):
    validate_opend_host(host)
    market_name, market = normalize_market(market_name)

    try:
        position_records = load_position_export_records(host, port, market)
    except Exception as exc:
        return {
            "source": "moomoo-opend",
            "status": "unavailable",
            "available": False,
            "market": market_name,
            "position_count": 0,
            "positions": [],
            "error": str(exc),
        }

    positions = [
        export_security_record(position, name_key="stock_name", held=True, order=position_order)
        for position_order, position in enumerate(position_records)
    ]
    return {
        "source": "moomoo-opend",
        "status": "ok",
        "available": True,
        "market": market_name,
        "position_count": len(positions),
        "positions": positions,
        "error": None,
    }


def add_watchlist_ref(existing, group_name, group_order, security_order):
    ref = {
        "group_name": group_name,
        "group_order": group_order,
        "security_order": security_order,
    }
    if ref not in existing["watchlist_refs"]:
        existing["watchlist_refs"].append(ref)


def add_universe_item(items_by_code, item, source, universe_order, primary_source=None, watchlist_ref=None):
    code = item.get("code")
    if not code:
        return

    if code not in items_by_code:
        items_by_code[code] = {
            "code": code,
            "name": item.get("name"),
            "market_data_ticker": item.get("market_data_ticker"),
            "mapping_status": item.get("mapping_status"),
            "mapping_warning": item.get("mapping_warning"),
            "held": bool(item.get("held")),
            "universe_order": universe_order,
            "primary_source": primary_source or source,
            "watchlist_refs": [],
            "sources": [],
        }
    else:
        existing = items_by_code[code]
        if item.get("held"):
            existing["held"] = True
        if item.get("held") and item.get("name"):
            existing["name"] = item.get("name")
        elif not existing.get("name") and item.get("name"):
            existing["name"] = item.get("name")
        if not existing.get("market_data_ticker") and item.get("market_data_ticker"):
            existing["market_data_ticker"] = item.get("market_data_ticker")
            existing["mapping_status"] = item.get("mapping_status")
            existing["mapping_warning"] = item.get("mapping_warning")

    if source not in items_by_code[code]["sources"]:
        items_by_code[code]["sources"].append(source)
    if watchlist_ref is not None:
        add_watchlist_ref(
            items_by_code[code],
            watchlist_ref.get("group_name"),
            watchlist_ref.get("group_order"),
            watchlist_ref.get("security_order"),
        )


def research_universe_status(positions_payload, watchlists_payload, items):
    positions_ok = positions_payload.get("available") is True
    watchlists_ok = watchlists_payload.get("status") == "ok"
    if positions_ok and watchlists_ok:
        return "ok"
    if items:
        return "partial"
    return "unavailable"


def build_research_universe_export_payload(host, port, market_name=DEFAULT_MARKET, group_type_name=DEFAULT_WATCHLIST_GROUP_TYPE):
    positions_payload = build_positions_export_payload(host, port, market_name)
    watchlists_payload = build_watchlists_export_payload(group_type_name)
    items_by_code = {}
    next_order = 0

    for group in watchlists_payload.get("groups") or []:
        group_name = group.get("name") or "Unnamed"
        group_order = group.get("order")
        for security in group.get("securities") or []:
            code = security.get("code")
            source = "watchlist:{}".format(group_name)
            if code not in items_by_code:
                universe_order = next_order
                next_order += 1
            else:
                universe_order = items_by_code[code]["universe_order"]
            add_universe_item(
                items_by_code,
                security,
                source,
                universe_order,
                primary_source=source,
                watchlist_ref={
                    "group_name": group_name,
                    "group_order": group_order,
                    "security_order": security.get("order"),
                },
            )

    for position in positions_payload.get("positions") or []:
        code = position.get("code")
        if code not in items_by_code:
            universe_order = next_order
            next_order += 1
        else:
            universe_order = items_by_code[code]["universe_order"]
        add_universe_item(items_by_code, position, "positions", universe_order)

    items = sorted(items_by_code.values(), key=lambda item: item["universe_order"])
    errors = {}
    if positions_payload.get("error"):
        errors["positions"] = positions_payload.get("error")
    if watchlists_payload.get("error"):
        errors["watchlists"] = watchlists_payload.get("error")

    return {
        "source": "moomoo-account-web",
        "status": research_universe_status(positions_payload, watchlists_payload, items),
        "synced_at": watchlists_payload.get("synced_at"),
        "market": positions_payload.get("market"),
        "positions_status": positions_payload.get("status"),
        "watchlists_status": watchlists_payload.get("status"),
        "item_count": len(items),
        "held_count": len([item for item in items if item.get("held")]),
        "watchlist_security_count": watchlists_payload.get("security_count", 0),
        "items": items,
        "error": errors or None,
    }


def build_dashboard_payload(host, port, market_name, asset_currency_name=DEFAULT_ASSET_CURRENCY):
    validate_opend_host(host)
    market_name, market = normalize_market(market_name)
    asset_currency_name, asset_currency = normalize_asset_currency(asset_currency_name)
    state = load_global_state(host, port)
    accounts, accinfo, positions = load_account_data(host, port, market, asset_currency)

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
            "asset_currency": asset_currency_name,
            "asset_currency_options": list(ASSET_CURRENCIES),
        },
        "state": state,
        "account": account_records[0] if account_records else {},
        "assets": asset_records[0] if asset_records else {},
        "positions": position_records,
        "position_count": len(position_records),
    }
