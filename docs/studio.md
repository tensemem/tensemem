# TenseMem Studio

Studio is a Next.js app that talks to `tensemem serve`. It is a memory inspector, not a chat window.

Studio lives in the git checkout. From the repo root:

```bash
git clone https://github.com/tensemem/tensemem.git
cd tensemem
pip install "tensemem[server]"
```

Terminal 1 — HTTP:

```bash
tensemem --db /absolute/path/tensemem.db serve --port 8080
```

Terminal 2 — Studio:

```bash
cd studio
npm install
npm run dev
```

Open `http://127.0.0.1:3000`. Studio rewrites `/v1` to the server. Optional bearer: paste `--token` / `TENSEMEM_TOKEN` or an issued key into the Token field.

## Screens

- **Board** — safe-to-act verdict; open jobs in a table (`LEASED` shows as In progress)
- **Memories** — browse, search, add, correct (deny / restore), forget, change timeline. Add shows a submitted-job notice.
- **Playground** — one message then one question; suggestions are past queries you typed, not fixed samples. Run path shows a submitted-job notice.
- **Lab** — same query through TenseMem, concat, and token-overlap; stale leaks highlighted
- **Map** — every lane in a table; interactive fact graph (pan, zoom, drag, inspect, SUPERSEDES)
- **Echo** — feed `context()` back in; fact count should stay flat
- **Ops** — extractor and optional search ranking. Access tokens stay folded away; they lock `/v1` and are not model keys.

**Load sample workspace** seeds `studio-demo` with GST / itinerary / invoice turns. It does not run on open.

Edit is `correct()`, not a free-text rewrite of a slot. Hosted extract (Ops) sends user text to that provider. Add extracts durable triples from that text — first-person profile lines, stories, or notes about any subject — not only facts about the speaker.

## Gemini extract

`GEMINI_API_KEY` (or `GOOGLE_API_KEY`) stays in the environment of `tensemem serve`. Do not paste it into Token.

```bash
# same terminal that runs serve
export GEMINI_API_KEY=your-key
cd /path/to/tensemem
.venv/bin/pip install "tensemem[server,litellm]"   # once
.venv/bin/tensemem --db ./studio.db serve --port 8080
```

In Studio **Ops**, set Extractor to **Gemini** and Save. **Memories → Add** then sends that text to Gemini (`gemini-3.6-flash`, then `gemini-3.5-flash-lite` / `gemini-3.8-flash` if a model is overloaded). Optional: `TENSEMEM_LLM=gemini` on serve start, or `TENSEMEM_LITELLM_MODEL` to pick another Gemini model id.
