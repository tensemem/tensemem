# TenseMem Studio

Studio is a Next.js app that talks to `tensemem serve`. It is a memory inspector, not a chat window.

```bash
pip install "tensemem[server]"
tensemem --db /absolute/path/tensemem.db serve --port 8080
cd studio
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. Studio rewrites `/v1` to the server. Optional bearer: paste `--token` / `TENSEMEM_TOKEN` or an issued key into the Token field.

## Screens

- **Board** — safe-to-act verdict from freshness, dead jobs, hedges, corrections
- **Memories** — browse, search, add, correct (deny / restore), forget, change timeline
- **Playground** — one message then one question through the real path
- **Lab** — same query through TenseMem, concat, and token-overlap; stale leaks highlighted
- **Map** — tense lanes and a fact graph (SUPERSEDES)
- **Echo** — feed `context()` back in; fact count should stay flat
- **Ops** — API keys, request log, provider name (secrets stay in the environment)

**Load sample workspace** seeds `studio-demo` with GST / itinerary / invoice turns. It does not run on open.

Edit is `correct()`, not a free-text rewrite of a slot. Hosted extract (Ops) sends user text to that provider.
