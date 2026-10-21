"use client";

import { useEffect, useState } from "react";
import { api, setToken } from "@/lib/api";

export default function OpsPage() {
  const [keys, setKeys] = useState<Array<Record<string, unknown>>>([]);
  const [issued, setIssued] = useState("");
  const [requests, setRequests] = useState<Array<Record<string, unknown>>>([]);
  const [llm, setLlm] = useState("fake");
  const [embedder, setEmbedder] = useState("none");
  const [credentials, setCredentials] = useState<Record<string, unknown>>({});
  const [err, setErr] = useState("");

  async function refresh() {
    setErr("");
    try {
      const [keyRows, log, provider] = await Promise.all([api.keys(), api.requests(), api.provider()]);
      setKeys(keyRows.keys);
      setRequests(log.requests);
      setLlm(provider.llm);
      setEmbedder(provider.embedder);
      setCredentials(provider.credentials ?? {});
    } catch (error) {
      setErr(error instanceof Error ? error.message : "ops unavailable");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <>
      <h1>Ops</h1>
      <p className="lead">API keys, request log, and provider settings. Secrets stay in the environment, not this page.</p>
      {err ? <p className="err">{err}</p> : null}
      <div className="grid">
        <div className="card">
          <strong>Keys</strong>
          <div className="row" style={{ marginTop: "0.6rem" }}>
            <button
              className="primary"
              onClick={async () => {
                const created = await api.issueKey("studio");
                setIssued(created.token);
                setToken(created.token);
                await refresh();
              }}
            >
              Issue key
            </button>
          </div>
          {issued ? <p className="mono">copy once: {issued}</p> : null}
          {keys.map((key) => (
            <p key={String(key.id)}>
              {String(key.prefix)} {String(key.label)} {key.revoked_at ? "(revoked)" : ""}
              {!key.revoked_at ? (
                <button style={{ marginLeft: "0.5rem" }} onClick={async () => { await api.revokeKey(String(key.id)); await refresh(); }}>
                  Revoke
                </button>
              ) : null}
            </p>
          ))}
        </div>
        <div className="card">
          <strong>Provider</strong>
          <div className="row" style={{ marginTop: "0.6rem" }}>
            <select value={llm} onChange={(event) => setLlm(event.target.value)}>
              <option value="fake">fake</option>
              <option value="openai">openai</option>
              <option value="anthropic">anthropic</option>
              <option value="ollama">ollama</option>
              <option value="litellm">litellm</option>
              <option value="gemini">gemini</option>
            </select>
            <select value={embedder} onChange={(event) => setEmbedder(event.target.value)}>
              <option value="none">none</option>
              <option value="openai">openai</option>
              <option value="fastembed">fastembed</option>
            </select>
            <button onClick={async () => { await api.setProvider(llm, embedder); await refresh(); }}>Save</button>
          </div>
          {Object.keys(credentials).length ? (
            <p className={`mono ${credentials.ok ? "" : "err"}`} style={{ marginTop: "0.6rem" }}>
              {JSON.stringify(credentials)}
            </p>
          ) : null}
          <p className="lead">
            Hosted extract sends user text to that provider. For Gemini, export GEMINI_API_KEY in the serve
            terminal, save gemini here, then Add on Memories. Do not paste the key into Token.
          </p>
        </div>
      </div>
      <h2>Request log</h2>
      <pre className="mono">{JSON.stringify(requests.slice(0, 40), null, 2)}</pre>
    </>
  );
}
