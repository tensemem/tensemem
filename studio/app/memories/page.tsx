"use client";

import { useCallback, useState } from "react";
import { api, type Fact } from "@/lib/api";
import { ScopeBar } from "../scope";

export default function MemoriesPage() {
  const [user, setUser] = useState("studio-demo");
  const [query, setQuery] = useState("");
  const [text, setText] = useState("");
  const [replacement, setReplacement] = useState("");
  const [facts, setFacts] = useState<Fact[]>([]);
  const [hits, setHits] = useState<Array<Record<string, unknown>>>([]);
  const [explain, setExplain] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async (who: string) => {
    const history = await api.history(who);
    setFacts(history.facts);
  }, []);

  const handleUser = useCallback(
    (who: string) => {
      setUser(who);
      void load(who).catch((error: Error) => setErr(error.message));
    },
    [load],
  );

  return (
    <>
      <h1>Memories</h1>
      <p className="lead">Browse, search, add, correct, or forget a scope. Edit is deny / restore — not a rewrite.</p>
      <ScopeBar onUser={handleUser} />
      {err ? <p className="err">{err}</p> : null}
      <div className="card" style={{ marginTop: "1rem" }}>
        <div className="row">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="search" />
          <button
            onClick={async () => {
              const found = await api.search(user, query);
              setHits(found.hits);
            }}
          >
            Search
          </button>
        </div>
        <div className="row" style={{ marginTop: "0.7rem" }}>
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={2} style={{ flex: 1 }} />
          <button
            className="primary"
            onClick={async () => {
              await api.add(user, text);
              setText("");
              await load(user);
            }}
          >
            Add
          </button>
          <button
            onClick={async () => {
              if (confirm(`Forget ${user}?`)) {
                await api.forget(user);
                await load(user);
              }
            }}
          >
            Forget scope
          </button>
        </div>
      </div>
      <h2>Facts</h2>
      {facts.map((fact) => (
        <div className="lane" key={fact.id}>
          <div>
            <span className={`dot ${fact.status === "ACTIVE" ? "now" : "was"}`} />
            {fact.predicate}
          </div>
          <div>
            <strong>{fact.object}</strong>{" "}
            <span className={`badge ${fact.status === "ACTIVE" ? "act" : "was"}`}>{fact.status}</span>
            <button
              style={{ marginLeft: "0.5rem" }}
              onClick={async () => setExplain(await api.explain(fact.id))}
            >
              Timeline
            </button>
            {fact.status === "ACTIVE" ? (
              <>
                <input
                  value={replacement}
                  onChange={(event) => setReplacement(event.target.value)}
                  placeholder="replacement (optional)"
                  style={{ marginLeft: "0.4rem", width: "12rem" }}
                />
                <button
                  style={{ marginLeft: "0.4rem" }}
                  onClick={async () => {
                    await api.correct(fact.id, replacement || undefined);
                    setReplacement("");
                    await load(user);
                  }}
                >
                  Correct
                </button>
              </>
            ) : null}
          </div>
        </div>
      ))}
      {hits.length ? (
        <>
          <h2>Search hits</h2>
          <pre className="mono">{JSON.stringify(hits, null, 2)}</pre>
        </>
      ) : null}
      {explain ? (
        <>
          <h2>Change timeline</h2>
          <pre className="mono">{JSON.stringify(explain, null, 2)}</pre>
        </>
      ) : null}
    </>
  );
}
