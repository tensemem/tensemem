# What

- Replace the README status wall with install, a three-line first run, the Delhi → Bangalore walk-through, TenseBench numbers from `tensemem bench`, and an extras table.
- Add an Excalidraw architecture diagram (SVG in the README, source at `docs/architecture.excalidraw`) and a contributor file map.
- Restructure CONTRIBUTING (checks, Studio/serve, PR risk tag and changeset, no secrets or `*.db*`). Document that `main` cannot merge until **CI**, **PR quality**, and CodeQL are green.
- Spell out that Studio needs a git checkout, `tensemem[server]`, and two terminals (serve, then `npm run dev`).
- Add `CI` and `PR quality` aggregator jobs so branch protection can require one check per workflow.
- Mark the package 0.1.0 alpha. Add SECURITY.md, `examples/quickstart.py`, and ignore WAL/SHM files.

# Why

Launch needs a 60-second path and a contributor guide that matches the current engine, Studio, and review gates. The previous README listed every flag in one paragraph.
