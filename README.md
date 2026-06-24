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

## Safety note

This scaffold defaults to paper trading only. Do not connect live broker keys
until you have added proper testing, monitoring, logging, and operational
controls.

## Quick start

Run the built-in demo:

```bash
python3 -m trade_bot run --config config/demo.json
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

## Important limitations

- No live execution included yet
- No historical backtester yet
- No persistent storage
- No auth or secret management
- No slippage or exchange fee modeling beyond a simple per-trade fee

That said, this is a solid starting foundation for a serious bot.
