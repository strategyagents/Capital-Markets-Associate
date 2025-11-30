# MCP Tool Catalog

| Tool Name | Description | Default Agent(s) |
|-----------|-------------|------------------|
| `get_positions` | Returns holdings and cash balances for a portfolio. | Portfolio, Orchestrator |
| `calculate_portfolio_health` | Computes allocation drift, VaR, or other metrics. | Portfolio |
| `generate_market_insight` | Provides analytics context for a security or theme. | Analytics |
| `execute_trade` | Submits an order for execution. | Trader |
| `record_trade_journal` | Persists trade notes, rationale, and fills. | Trader |

Extend this table whenever the MCP server exposes new tools. Keep the allowlists in `.env` synchronized with the "Default Agent(s)" column.
