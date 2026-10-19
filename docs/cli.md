# CLI

The `tensemem` command reads a SQLite file (default `./tensemem.db`). It does not start an extract worker.

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
```

Global flags: `--db path.db`, `--json`, `--agent`, `--namespace`.

`rebuild` from the CLI replays explicit ops and re-queues messages. Re-extract those messages from Python with `Memory(..., llm=...).rebuild(user_id, wait=True)`.
