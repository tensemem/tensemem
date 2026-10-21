"use client";

import { useEffect, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";

const EXTRACTORS = [
  { id: "fake", label: "Built-in rules", hint: "No API key. Fast, first-person patterns only." },
  { id: "gemini", label: "Gemini", hint: "Export GEMINI_API_KEY in the serve terminal. Do not paste the model key here." },
  { id: "openai", label: "OpenAI", hint: "Export OPENAI_API_KEY in the serve terminal." },
  { id: "anthropic", label: "Anthropic", hint: "Export ANTHROPIC_API_KEY in the serve terminal." },
  { id: "ollama", label: "Ollama (local)", hint: "Ollama must be running on this machine." },
  { id: "litellm", label: "LiteLLM", hint: "Uses the LiteLLM extra and that provider’s env key." },
] as const;

const SEARCH = [
  { id: "none", label: "Text match", hint: "Default. Full-text search, no vectors." },
  { id: "fastembed", label: "Local vectors", hint: "Needs tensemem[local]. Stays on this machine." },
  { id: "openai", label: "OpenAI vectors", hint: "Uses OPENAI_API_KEY for embeddings." },
] as const;

function envReady(llm: string, credentials: Record<string, unknown>): string {
  if (llm === "fake") {
    return "Ready — no hosted key needed.";
  }
  if (credentials.ok) {
    return "Ready — serve has an env key.";
  }
  return "Missing key in the serve process. Export it there, restart serve, then Save.";
}

export default function OpsPage() {
  const [keys, setKeys] = useState<Array<Record<string, unknown>>>([]);
  const [issued, setIssued] = useState("");
  const [requests, setRequests] = useState<Array<Record<string, unknown>>>([]);
  const [llm, setLlm] = useState("fake");
  const [embedder, setEmbedder] = useState("none");
  const [credentials, setCredentials] = useState<Record<string, unknown>>({});
  const [token, setTok] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");

  const extractor = EXTRACTORS.find((item) => item.id === llm) ?? EXTRACTORS[0];
  const search = SEARCH.find((item) => item.id === embedder) ?? SEARCH[0];
  const liveKeys = keys.filter((key) => !key.revoked_at);

  async function refresh() {
    setErr("");
    try {
      const [keyRows, log, provider] = await Promise.all([api.keys(), api.requests(), api.provider()]);
      setKeys(keyRows.keys);
      setRequests(log.requests);
      setLlm(provider.llm);
      setEmbedder(provider.embedder);
      setCredentials(provider.credentials ?? {});
      setLoaded(true);
    } catch (error) {
      setLoaded(false);
      const message = error instanceof Error ? error.message : "ops unavailable";
      setErr(
        message === "unauthorized"
          ? "Serve is locked. Paste the issued access token below, then Refresh."
          : message,
      );
    }
  }

  useEffect(() => {
    setTok(getToken());
    void refresh();
  }, []);

  return (
    <>
      <h1>Ops</h1>
      <p className="lead">Pick how Add turns text into facts. Model keys stay in the serve terminal, not here.</p>
      {err ? (
        <div className="card ops-unlock">
          <p className="err">{err}</p>
          <label className="field">
            <span>Access token</span>
            <input
              value={token}
              onChange={(event) => {
                setTok(event.target.value);
                setToken(event.target.value);
              }}
              placeholder="tm_…"
            />
          </label>
          <button type="button" onClick={() => void refresh()}>
            Refresh
          </button>
        </div>
      ) : null}

      <div className="card ops-card" style={{ marginTop: "1rem" }}>
        <label className="field">
          <span>Extractor</span>
          <select value={llm} onChange={(event) => setLlm(event.target.value)}>
            {EXTRACTORS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <small>{extractor.hint}</small>
        </label>
        <label className="field">
          <span>Search ranking</span>
          <select value={embedder} onChange={(event) => setEmbedder(event.target.value)}>
            {SEARCH.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <small>{search.hint}</small>
        </label>
        {loaded ? (
          <p className={credentials.ok || llm === "fake" ? "lead" : "err"}>{envReady(llm, credentials)}</p>
        ) : null}
        <button
          className="primary"
          type="button"
          disabled={busy === "save"}
          onClick={async () => {
            setBusy("save");
            setSaved(false);
            try {
              await api.setProvider(llm, embedder);
              setSaved(true);
              await refresh();
            } catch (error) {
              setErr(error instanceof Error ? error.message : "save failed");
            } finally {
              setBusy(null);
            }
          }}
        >
          {busy === "save" ? "Saving…" : "Save"}
        </button>
        {saved ? <span className="badge act">Saved</span> : null}
      </div>

      <h2>Recent requests</h2>
      {!loaded ? (
        <p className="lead">Load serve to see the request log.</p>
      ) : requests.length ? (
        <div className="table-wrap">
          <table className="facts">
            <thead>
              <tr>
                <th className="col-when">When</th>
                <th className="col-kind">Method</th>
                <th className="col-object">Path</th>
                <th className="col-status">Status</th>
                <th className="col-when">ms</th>
              </tr>
            </thead>
            <tbody>
              {requests.slice(0, 20).map((row, index) => (
                <tr key={`${row.at}-${index}`}>
                  <td className="col-when">{String(row.at ?? "—").replace("T", " ").slice(0, 19)}</td>
                  <td className="col-kind">{String(row.method)}</td>
                  <td className="col-object">{String(row.path)}</td>
                  <td className="col-status">{String(row.status)}</td>
                  <td className="col-when">{String(row.latency_ms ?? "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="lead">No requests logged yet.</p>
      )}

      <details className="ops-access">
        <summary>
          Access tokens (optional)
          {liveKeys.length > 0 ? <span className="badge act">{liveKeys.length} live</span> : null}
        </summary>
        <p className="lead">
          Skip this on a local laptop. Issue a token only to lock `/v1` for another machine, a script, or a second
          person. The first live token blocks anonymous calls — keep the copy-once value. This is not a model key.
        </p>
        <div className="row">
          <button
            type="button"
            disabled={busy === "issue"}
            onClick={async () => {
              setBusy("issue");
              try {
                const created = await api.issueKey("studio");
                setIssued(created.token);
                setToken(created.token);
                await refresh();
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === "issue" ? "Issuing…" : "Issue access token"}
          </button>
        </div>
        {issued ? <p className="mono">copy once: {issued}</p> : null}
        {!loaded ? null : keys.length ? (
          <div className="table-wrap" style={{ marginTop: "0.8rem" }}>
            <table className="facts">
              <thead>
                <tr>
                  <th className="col-subject">Prefix</th>
                  <th className="col-object">Label</th>
                  <th className="col-status">Status</th>
                  <th className="col-job-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={String(key.id)}>
                    <td className="col-subject">{String(key.prefix)}</td>
                    <td className="col-object">{String(key.label || "—")}</td>
                    <td className="col-status">
                      <span className={`badge ${key.revoked_at ? "was" : "act"}`}>
                        {key.revoked_at ? "Revoked" : "Live"}
                      </span>
                    </td>
                    <td className="col-job-actions">
                      {!key.revoked_at ? (
                        <button
                          type="button"
                          disabled={busy === `revoke:${String(key.id)}`}
                          onClick={async () => {
                            setBusy(`revoke:${String(key.id)}`);
                            try {
                              await api.revokeKey(String(key.id));
                              await refresh();
                            } finally {
                              setBusy(null);
                            }
                          }}
                        >
                          {busy === `revoke:${String(key.id)}` ? "Revoking…" : "Revoke"}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="lead">No access tokens issued.</p>
        )}
      </details>
    </>
  );
}
