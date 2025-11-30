# Architecture Notes

- **Agents**: Orchestrator, Portfolio, Analytics, Trader.
- **Observability**: OTLP gRPC exporter to Graylog at `0.0.0.0:4317`.
- **Control Plane**: MCP server `http://0.0.0.0:8085` plus Telegram human approvals.

Update this document with sequence diagrams, deployment topologies, or ADR links as the capstone evolves.
