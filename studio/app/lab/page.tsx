"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ScopeBar } from "../scope";

type Hit = {
  kind?: string;
  id?: string;
  text?: string;
  score?: number;
  status?: string;
  predicate?: string | null;
};

type Freshness = {
  as_of_seq?: number;
  latest_seq?: number;
  pending?: number;
  failed?: number;
  is_current?: boolean;
};

type Packed = {
  text?: string;
  token_count?: number;
  facts_used?: string[];
};

export default function LabPage() {
  const [user, setUser] = useState("studio-demo");
  const [query, setQuery] = useState("which GST return do we file now");
  const [historyOn, setHistoryOn] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [retrieved, setRetrieved] = useState<Record<string, unknown> | null>(null);
  const [retrieveBusy, setRetrieveBusy] = useState(false);
  const [compareBusy, setCompareBusy] = useState(false);
  const [err, setErr] = useState("");

  const hits = (retrieved?.hits as Hit[] | undefined) ?? [];
  const freshness = retrieved?.freshness as Freshness | undefined;
  const packed = retrieved?.packed as Packed | undefined;
  const packedText = typeof packed?.text === "string" ? packed.text : JSON.stringify(packed ?? {}, null, 2);

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
          disabled={retrieveBusy}
          onClick={async () => {
            setErr("");
            setRetrieveBusy(true);
            try {
              const [hits, packed] = await Promise.all([
                api.search(user, query),
                api.context(user, query, historyOn),
              ]);
              setRetrieved({ hits: hits.hits, freshness: hits.freshness, debug: hits.debug, packed });
            } catch (error) {
              setErr(error instanceof Error ? error.message : "failed");
            } finally {
              setRetrieveBusy(false);
            }
          }}
        >
          {retrieveBusy ? "Retrieving…" : "Retrieve"}
        </button>
        <button
          className="primary"
          type="button"
          disabled={compareBusy}
          onClick={async () => {
            setErr("");
            setCompareBusy(true);
            try {
              setResult(await api.compare(user, query, historyOn));
            } catch (error) {
              setErr(error instanceof Error ? error.message : "failed");
            } finally {
              setCompareBusy(false);
            }
          }}
        >
          {compareBusy ? "Comparing…" : "Compare"}
        </button>
      </div>
      {err ? <p className="err">{err}</p> : null}
      {retrieved ? (
        <div className="card" style={{ marginTop: "1rem" }}>
          <strong>Retrieval tester</strong>
          {freshness ? (
            <p className="lead" style={{ marginTop: "0.5rem" }}>
              Freshness: as_of_seq={freshness.as_of_seq ?? "—"}, latest_seq={freshness.latest_seq ?? "—"}, pending=
              {freshness.pending ?? "—"}, failed={freshness.failed ?? "—"}, is_current=
              {freshness.is_current ? "yes" : "no"}
            </p>
          ) : null}
          {hits.length > 0 ? (
            <table className="mono" style={{ width: "100%", marginTop: "0.75rem", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "0.25rem" }}>Kind</th>
                  <th style={{ textAlign: "left", padding: "0.25rem" }}>ID</th>
                  <th style={{ textAlign: "left", padding: "0.25rem" }}>Text</th>
                  <th style={{ textAlign: "right", padding: "0.25rem" }}>Score</th>
                  <th style={{ textAlign: "left", padding: "0.25rem" }}>Status</th>
                  <th style={{ textAlign: "left", padding: "0.25rem" }}>Predicate</th>
                </tr>
              </thead>
              <tbody>
                {hits.map((hit, index) => (
                  <tr key={hit.id ?? index} style={{ borderTop: "1px solid #ddd" }}>
                    <td style={{ padding: "0.25rem" }}>{hit.kind ?? "—"}</td>
                    <td style={{ padding: "0.25rem" }}>{hit.id ?? "—"}</td>
                    <td style={{ padding: "0.25rem", maxWidth: "40ch", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {hit.text ?? "—"}
                    </td>
                    <td style={{ padding: "0.25rem", textAlign: "right" }}>{hit.score?.toFixed(3) ?? "—"}</td>
                    <td style={{ padding: "0.25rem" }}>{hit.status ?? "—"}</td>
                    <td style={{ padding: "0.25rem" }}>{hit.predicate ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>No hits.</p>
          )}
          <div style={{ marginTop: "1rem" }}>
            <strong>Packed context</strong>
            <pre className="mono" style={{ marginTop: "0.25rem", whiteSpace: "pre-wrap" }}>
              {packedText}
            </pre>
          </div>
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
