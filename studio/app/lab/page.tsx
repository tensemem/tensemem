"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ScopeBar } from "../scope";

export default function LabPage() {
  const [user, setUser] = useState("studio-demo");
  const [query, setQuery] = useState("which GST return do we file now");
  const [historyOn, setHistoryOn] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [retrieved, setRetrieved] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState("");

  return (
    <>
      <h1>Retrieval + stale-act compare</h1>
      <p className="lead">
        Same question through TenseMem, concat, and token-overlap. Stale values the baselines still treat as current are
        highlighted.
      </p>
      <ScopeBar onUser={setUser} />
      <div className="card row" style={{ marginTop: "1rem" }}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} style={{ flex: 1 }} />
        <label>
          <input type="checkbox" checked={historyOn} onChange={(event) => setHistoryOn(event.target.checked)} /> history
        </label>
        <button
          type="button"
          disabled={busy === "retrieve"}
          onClick={async () => {
            setErr("");
            setBusy("retrieve");
            try {
              const [hits, packed] = await Promise.all([
                api.search(user, query),
                api.context(user, query, historyOn),
              ]);
              setRetrieved({ hits: hits.hits, freshness: hits.freshness, debug: hits.debug, packed });
            } catch (error) {
              setErr(error instanceof Error ? error.message : "failed");
            } finally {
              setBusy(null);
            }
          }}
        >
          {busy === "retrieve" ? "Retrieving…" : "Retrieve"}
        </button>
        <button
          className="primary"
          type="button"
          disabled={busy === "compare"}
          onClick={async () => {
            setErr("");
            setBusy("compare");
            try {
              setResult(await api.compare(user, query, historyOn));
            } catch (error) {
              setErr(error instanceof Error ? error.message : "failed");
            } finally {
              setBusy(null);
            }
          }}
        >
          {busy === "compare" ? "Comparing…" : "Compare"}
        </button>
      </div>
      {err ? <p className="err">{err}</p> : null}
      {retrieved ? (
        <div className="card" style={{ marginTop: "1rem" }}>
          <strong>Retrieval tester</strong>
          <pre className="mono">{JSON.stringify(retrieved, null, 2)}</pre>
        </div>
      ) : null}
      {result ? (
        <div className="cmp" style={{ marginTop: "1rem" }}>
          {(["tensemem", "concat", "similarity"] as const).map((name) => {
            const block = result[name] as Record<string, unknown>;
            const stale = (block.stale_present as string[]) ?? [];
            return (
              <div className="card" key={name}>
                <strong>{name}</strong>
                {stale.length ? <p className="badge stop">stale: {stale.join(", ")}</p> : <p className="badge act">no stale leak</p>}
                <pre className="mono">{String(block.text)}</pre>
              </div>
            );
          })}
        </div>
      ) : null}
    </>
  );
}
