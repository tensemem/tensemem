# What

- Add `tensemem serve`: HTTP adapter with `POST /v1/memories:add`, `POST /v1/context`, `GET /v1/state`, `GET /v1/history`, `DELETE /v1/scopes/{user_id}`, and `GET /health`, on the same SQLite file as the CLI.
- Optional extra `tensemem[server]` (FastAPI + uvicorn). Route dispatch does not import it, so tests cover the mapping without the extra.
- Same FakeExtractor + starter registry as MCP. Background worker stays off; add waits in the request.

# Why

Non-Python clients and several processes sharing one writer need HTTP. The routes ingest text and read state; they do not let the model SET/UPDATE slots.
