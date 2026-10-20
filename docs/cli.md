# CLI

The `tensemem` command reads a SQLite file (default `./tensemem.db`). Inspect commands do not start an extract worker.

```bash
tensemem inspect --user u1
tensemem history --user u1 lives_in
tensemem explain 01JB…
tensemem search --user u1 "where did I live"
tensemem jobs
tensemem jobs retry JOB_ID
tensemem jobs dismiss JOB_ID
tensemem jobs purge-dead
tensemem freshness --user u1
tensemem correct 01JB… --replace Bangalore
tensemem export --user u1 --out u1.jsonl
tensemem import --user u1 u1.jsonl
tensemem rebuild --user u1
tensemem backup copy.db
tensemem stats --user u1
tensemem bench
tensemem longmem
tensemem locomo
tensemem latency
tensemem mcp --user u1
tensemem mcp --http --token "$TENSEMEM_TOKEN"
tensemem serve --token "$TENSEMEM_TOKEN"
```

Global flags: `--db path.db`, `--json`, `--agent`, `--namespace`.

`tensemem bench` does not open a database. It scores the packaged TenseBench set (override with `--path`) against TenseMem, concatenated history, and token-overlap retrieval. See [TenseBench](tensebench.md).

`tensemem longmem` also skips the database. It loads a LongMemEval-shaped JSON array (or JSONL) and scores `context()` against each gold answer. Default is the packaged 7-item pilot. See [Long-session eval](longmem.md).

`tensemem locomo` also skips the database. It loads a LoCoMo-shaped JSON array (or JSONL), ingests each conversation once, and scores every QA row. Default is the packaged one-conversation pilot. See [LoCoMo eval](locomo.md).

`tensemem latency` also skips the database file. It seeds ACTIVE facts in memory and times empty-query `context()`. See [Context latency](latency.md).

`tensemem mcp` creates the SQLite file if missing and serves five tools on stdio (`remember`, `recall_context`, `get_state`, `get_history`, `forget`). `--http` is Streamable HTTP on `127.0.0.1:8081`. `--token` or `TENSEMEM_TOKEN` is a Bearer token for `--http`. `--db` is a root flag (`tensemem --db path.db mcp --user u1`). Needs `tensemem[mcp]`. See [MCP](mcp.md).

`tensemem serve` is the HTTP adapter for those same five operations (`tensemem --db path.db serve --port 8080`). Default bind is loopback. `--token` or `TENSEMEM_TOKEN` requires `Authorization: Bearer`. TLS stays in a proxy. Needs `tensemem[server]`. See [REST](server.md).

`rebuild` from the CLI replays explicit ops and re-queues messages. Re-extract those messages from Python with `Memory(..., llm=...).rebuild(user_id, wait=True)`.
