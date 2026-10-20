# What

- Add `TenseMemStore`: LangGraph-shaped `put` / `search` / `get` / `delete` over `add()` and `context()`. No slot writes. Extra `tensemem[langgraph]`.
- Add `tensemem mcp --http` Streamable HTTP on the same five tools (default `127.0.0.1:8081`).
- Optional bearer token on REST and Streamable HTTP (`--token` or `TENSEMEM_TOKEN`). `GET /health` stays open. Stdio MCP is unchanged.

# Why

A graph and a remote MCP host should hit the same engine. Non-loopback HTTP warns when a token and TLS are absent; a token stays optional. TLS stays in a proxy.
