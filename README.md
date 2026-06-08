# moomoo API

## Unofficial YOHO-ENT maintained fork

This repository is an unofficial YOHO-ENT maintained fork of the upstream moomoo Python OpenAPI SDK. It is not endorsed by, sponsored by, or affiliated with Moomoo, Futu, or their affiliates. The moomoo and Futu names, logos, trademarks, and service marks remain the property of their respective owners.

This project is based on upstream Apache-2.0 licensed work. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for attribution and fork notes.

Trading APIs can place real orders and may cause financial loss. Example code is for education and testing, defaults to paper trading where possible, and is not investment advice. Read [DISCLAIMER.md](DISCLAIMER.md) before using this SDK with any trading account.

For security guidance and vulnerability reporting, see [SECURITY.md](SECURITY.md).

## Introduction

[moomoo API](https://openapi.moomoo.com/moomoo-api-doc/) provides market data and trading interfaces through the moomoo OpenD gateway using Python and JSON/Protobuf protocols.

- [Official Documentation](https://openapi.moomoo.com/moomoo-api-doc/)

## Installation

Install from this fork:

```bash
pip install git+https://github.com/YOHO-ENT/moomoo-api.git
```

The upstream package may also be available as:

```bash
pip install moomoo-api
```

Note: The upstream SDK historically supports Python 2.7/Python 3.x. This fork has not yet changed that compatibility policy.

## Prerequisites

Before running Python scripts, start the [moomoo OpenD](https://openapi.moomoo.com/moomoo-api-doc/en/quick/opend-base.html) gateway client.

For remote OpenD hosts, protocol encryption is required by this fork. Configure your own RSA private key file before connecting:

```python
import moomoo as ft

ft.SysConfig.enable_proto_encrypt(True)
ft.SysConfig.set_init_rsa_file("/path/to/private_key.txt")
```

You can also set the key path with:

```bash
export MOOMOO_INIT_RSA_FILE=/path/to/private_key.txt
```

Do not commit trading passwords, RSA private keys, account exports, or debug logs.

## Quick Start

```python
import moomoo as ft

# Create a quote context object.
quote_ctx = ft.OpenQuoteContext(host="127.0.0.1", port=11111)

# Context control.
quote_ctx.start()
quote_ctx.set_handler(ft.TickerHandlerBase())

# Low-frequency data interfaces.
market = ft.Market.HK
code = "HK.00123"
code_list = [code]
plate = "HK.BK1107"
print(quote_ctx.get_stock_basicinfo(market, stock_type=ft.SecurityType.STOCK))
print(quote_ctx.get_market_snapshot(code_list))
print(quote_ctx.get_plate_list(market, ft.Plate.ALL))
print(quote_ctx.get_plate_stock(plate))

# High-frequency data interfaces.
quote_ctx.subscribe(
    code,
    [
        ft.SubType.QUOTE,
        ft.SubType.TICKER,
        ft.SubType.K_DAY,
        ft.SubType.ORDER_BOOK,
        ft.SubType.RT_DATA,
        ft.SubType.BROKER,
    ],
)
print(quote_ctx.get_stock_quote(code))
print(quote_ctx.get_rt_ticker(code))
print(quote_ctx.get_cur_kline(code, num=100, ktype=ft.KLType.K_DAY))
print(quote_ctx.get_order_book(code))
print(quote_ctx.get_rt_data(code))
print(quote_ctx.get_broker_queue(code))

quote_ctx.stop()
quote_ctx.close()

# Paper trading example. Real trading requires explicit user configuration.
trade_env = ft.TrdEnv.SIMULATE
trade_hk_ctx = ft.OpenHKTradeContext(host="127.0.0.1", port=11111)
print(trade_hk_ctx.accinfo_query(trd_env=trade_env))
print(
    trade_hk_ctx.place_order(
        price=1.1,
        qty=2000,
        code=code,
        trd_side=ft.TrdSide.BUY,
        order_type=ft.OrderType.NORMAL,
        trd_env=trade_env,
    )
)
print(trade_hk_ctx.order_list_query(trd_env=trade_env))
print(trade_hk_ctx.position_list_query(trd_env=trade_env))
trade_hk_ctx.close()
```

To run examples against a real trading account, you must explicitly opt in:

```bash
export MOOMOO_ALLOW_REAL_TRADING=1
export MOOMOO_TRADE_UNLOCK_PASSWORD='your-trading-password'
```

Use real trading only after reviewing the code path and your local regulatory obligations.

## Example Strategies

Example files are located in `moomoo/examples`. They are intended as learning material and default to paper trading where a trading environment is used.

## Local Read-only GUI

This fork includes a small local web dashboard for viewing OpenD status,
FUTUAU real-account assets, and positions. The browser frontend calls the
local FastAPI endpoint served by this project; the API then reads data through
the existing SDK/OpenD connection. The dashboard is read-only: it does not
unlock trading and does not call order APIs.

Install the GUI dependencies:

```bash
python3 -m pip install -r requirements.txt -r requirements-gui.txt
```

Start the local API and frontend:

```bash
python3 -m moomoo.examples.account_web
```

Open `http://127.0.0.1:8501` in your browser while OpenD is running and logged
in. The JSON API is available at `/api/dashboard`; the default connection is
`127.0.0.1:11111` with `security_firm=FUTUAU`.

The browser UI is split into two local pages. `Overview` shows OpenD status,
account assets, Signals, and Positions. `Watchlists` is a separate page for
your moomoo account watchlists, keeping the account view compact.

The dashboard defaults to privacy mode in the browser. Asset balances, cash,
position quantities, costs, market value, and P/L are hidden until you click
`Reveal` locally. Account IDs remain masked by the API.

For account safety, `/api/dashboard` only connects to local OpenD hosts by
default: `127.0.0.1`, `localhost`, or `::1`. To allow a remote OpenD host for
your own local setup, explicitly opt in:

```bash
export MOOMOO_ACCOUNT_WEB_ALLOW_REMOTE=1
```

### Connect Market Data Lab

The local dashboard can optionally enrich positions with technical snapshots
from the separate `market-data-lab` service. This integration stays read-only:
the moomoo dashboard calls fixed Market Data Lab endpoints through its own
local API, and Market Data Lab does not receive account identifiers.

Start Market Data Lab first:

```bash
cd /Users/yongnahwa/Desktop/Firn/market-data-lab
./scripts/start_api.sh
```

Then start the moomoo dashboard:

```bash
cd /Users/yongnahwa/Desktop/py-moomoo-api
python3 -m moomoo.examples.account_web
```

Defaults can be overridden with:

```bash
export MOOMOO_MARKET_DATA_API_URL=http://127.0.0.1:8010
export MOOMOO_MARKET_DATA_TIMEOUT_SEC=2.5
export MOOMOO_MARKET_DATA_BENCHMARK=SPY
export MOOMOO_MARKET_DATA_UI_URL=http://127.0.0.1:3020
```

The proxy endpoints are `/api/market-data/status` and
`/api/market-data/snapshots?codes=US.AAPL,HK.00700&benchmark=SPY`. If
Market Data Lab is not running, account assets and positions still load, while
market-data columns show `unavailable`.

The Signals section ranks current holdings into `Momentum`, `Breakout Watch`,
`Risk Review`, `Protect Gains`, `Data Gap`, and `Neutral` using the read-only
position data plus Market Data Lab snapshots.

### Watchlists

The local dashboard can also show your moomoo account watchlists, but it reads
from a local cache by default. This avoids repeatedly calling OpenD and hitting
the watchlist detail limit (`10 times / 30 seconds`). The browser's
`Watchlists` page shows all cached user-created lists in OpenD order, and each
list can be enriched with the same read-only Market Data Lab snapshots used by
the Positions and Signals views.

Use `Sync from OpenD` after you create, rename, delete, or edit lists in moomoo.
The sync is intentionally slow because it waits between list-detail requests,
then overwrites the local cache.

The JSON endpoint is `/api/watchlists?group_type=CUSTOM`; it only reads the
cache and returns `source="cache"`, `source="cache_missing"`, or
`source="cache_error"`. Manual sync uses `POST /api/watchlists/sync` and
returns `source="opend_sync"`. Supported `group_type` values are `CUSTOM`,
`ALL`, and `SYSTEM`, though the UI uses `CUSTOM`.

The default cache file is:

```text
~/.moomoo-api/account_web/watchlists_cache.json
```

Set `MOOMOO_ACCOUNT_WEB_CACHE_DIR` to store that cache somewhere else. The cache
contains only watchlist names, types, securities, and `synced_at`; it does not
store assets, positions, trading data, or credentials. Watchlists remain
read-only: the dashboard does not create, rename, delete, or modify watchlists,
and it does not send watchlist membership back to Market Data Lab.

### GUI development checks

```bash
python3 -m pip install -r requirements.txt -r requirements-gui.txt -r requirements-dev.txt
python3 -m py_compile moomoo/examples/account_web/*.py
python3 -m pytest -q
python3 -m build
```

## Debug Switch and Push Logs

- `set_futu_debug_model(True)` enables debug-level push logging.
- Debug logs may contain market data, account-related data, order data, or other sensitive information. Keep this disabled unless troubleshooting locally.
- Log files are stored under the user's moomoo/Futu OpenD log directory.

## Project Structure

```text
moomoo/
├── common/              # Core module: networking, constants, Protobuf, etc.
│   └── pb/              # Protobuf definitions and generated files
├── quote/               # Market data module
├── trade/               # Trading module
├── tools/               # Utility tools
└── examples/            # Example code
```

## API and moomoo OpenD Gateway Architecture

- [Architecture Overview](https://openapi.moomoo.com/futu-api-doc/en/intro/intro.html)

## Usage

Please read the official API documentation carefully when using a new OpenD version. Suggestions and feature requests for this fork can be submitted to the YOHO-ENT repository.
