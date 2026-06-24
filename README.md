# Trade Bot

A paper-trading-first Python scaffold for building multi-asset trading bots.

This project is designed so you can start safely in simulation and later add
live broker adapters for:

- Stocks and ETFs
- Cryptocurrencies
- Forex
- Options and futures
- Commodities

## What is included

- Broker abstraction layer
- Paper broker with portfolio tracking
- Synthetic market data feed for local testing
- Momentum strategy example
- Risk manager with configurable guardrails
- CLI entry point for running simulations
- Browser dashboard with candlestick charts and signal review
- Broker-backed news feed for Alpaca watchlists
- First live-market integration path via Alpaca for stocks and crypto
- OANDA integration path for forex
- IBKR integration path for options, futures, and commodities

## Trading Modes

The app is now shaped around three clear modes:

- `Demo`: synthetic market data and simulated fills
- `Paper`: broker-backed market data with paper or preview execution
- `Live`: broker-backed market data with real account access

This separation is important. Real-money trading should never feel ambiguous in
the UI or config.

## Safety note

This scaffold defaults to paper trading only. Do not connect live broker keys
until you have added proper testing, monitoring, logging, and operational
controls.

## Quick start

Run the built-in demo:

```bash
python3 -m trade_bot run --config config/demo.json
```

Run the web dashboard:

```bash
python3 -m trade_bot web --config config/demo.json --host 127.0.0.1 --port 8000
```

Run one live market cycle with Alpaca:

```bash
python3 -m trade_bot live --config config/alpaca_live.json --iterations 1
```

Run one forex cycle with OANDA practice:

```bash
python3 -m trade_bot live --config config/oanda_paper.json --iterations 1
```

Run one IBKR cycle for futures and commodities:

```bash
python3 -m trade_bot live --config config/ibkr_paper.json --iterations 1
```

Run tests:

```bash
python3 -m unittest discover -s tests
```

## Project layout

```text
trade_bot/
  brokers/       Broker interfaces and paper broker
  data/          Market data interfaces and synthetic feed
  strategies/    Trading strategy interfaces and examples
  cli.py         Command-line entry point
  config.py      JSON config loader
  engine.py      Trading engine
  models.py      Shared trading domain models
  risk.py        Risk checks
```

## How it works

1. The data feed emits candles for each configured instrument.
2. The strategy reads recent candles and decides whether to buy, sell, or hold.
3. The risk manager approves or rejects the order.
4. The broker simulates fills and updates positions and cash.
5. The engine prints a session summary with equity, cash, and trades.

## Supported asset classes in the model

The domain model already supports:

- `stock`
- `etf`
- `crypto`
- `forex`
- `option`
- `future`
- `commodity`

The included demo uses synthetic prices, but the same model can be extended to
real broker or exchange adapters later.

## Next steps for live trading

Once you are happy with the paper-trading behavior, the next layer is usually:

1. Add a real market data adapter.
2. Add a real broker adapter.
3. Store orders, fills, and PnL in a database.
4. Add structured logging and alerts.
5. Add backtesting with historical data.
6. Add rate-limit handling, retries, and health checks.

## Possible integrations

These are common choices you could add later:

- Crypto: CCXT-backed exchange adapters
- Stocks and ETFs: Alpaca or Interactive Brokers
- Forex: OANDA or Interactive Brokers
- Futures and options: Interactive Brokers or a specialized futures broker
- Commodities: Usually through futures brokers or CFDs, depending on venue

## Example config

The demo config lives at `config/demo.json` and shows:

- starting cash
- symbols and asset classes
- strategy window sizes
- risk limits
- synthetic market settings

The default demo uses fractional trade sizes so one configuration can work
across high-priced assets like Bitcoin and lower-priced ETFs in the same run.

The Alpaca paper template lives at `config/alpaca_paper.json`.
The live Alpaca template lives at `config/alpaca_live.json`.
The OANDA practice template lives at `config/oanda_paper.json`.
The OANDA live template lives at `config/oanda_live.json`.
The IBKR paper template lives at `config/ibkr_paper.json`.
The IBKR live template lives at `config/ibkr_live.json`.

For Alpaca-backed dashboards, `market_data.news_limit` controls how many recent
matching market news articles are requested for the watchlist snapshot.

## Live trading setup

This repo now includes broker-backed live or paper-preview paths for multiple
markets:

- Alpaca for stocks, ETFs, and crypto
- OANDA for forex
- IBKR for stocks, forex, options, futures, and commodities

Recommended progression:

1. `config/demo.json`
2. `config/alpaca_paper.json` or `config/oanda_paper.json` or `config/ibkr_paper.json`
3. A live broker config with `execute_orders: false`
4. The same live broker config with `execute_orders: true` only after repeated safe checks

The app will automatically load `.env` and `.env.local` from the repo root.

Alpaca notes:

1. Create an Alpaca account and API keys.
2. Copy `.env.example` to `.env` and fill in your Alpaca keys.
3. Start in paper mode with `config/alpaca_paper.json`.
4. Keep `live.execute_orders` as `false` until you are confident in the
   signals.
5. When you are ready, change `live.execute_orders` to `true`.
6. Only after successful paper testing should you switch `broker.paper` to
   `false`.

OANDA notes:

- Add `OANDA_API_TOKEN` and `OANDA_ACCOUNT_ID` to `.env`.
- Start with `config/oanda_paper.json` before switching to `config/oanda_live.json`.

IBKR notes:

- The IBKR path expects a local TWS or IB Gateway session with API access enabled.
- The repo uses `ib_insync` for the IBKR adapter. Install it with:

```bash
pip install ib-insync
```

- The included IBKR configs use example futures contracts. You may need to adjust
  contract months, exchanges, or option details before trading.

You can also point the web dashboard at the live config:

```bash
python3 -m trade_bot web --config config/alpaca_live.json --host 127.0.0.1 --port 8000
```

## Important limitations

- No historical backtester yet
- No persistent storage
- No auth or secret management
- No slippage or exchange fee modeling beyond a simple per-trade fee

That said, this is a solid starting foundation for a serious bot.
