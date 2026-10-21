"use client";

import { useCallback, useRef, useState } from "react";
import { api, type Fact } from "@/lib/api";
import { JobNotice } from "../notice";
import { ScopeBar } from "../scope";

export default function MemoriesPage() {
  const [user, setUser] = useState("studio-demo");
  const [query, setQuery] = useState("");
  const [text, setText] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [facts, setFacts] = useState<Fact[]>([]);
  const [hits, setHits] = useState<Array<Record<string, unknown>>>([]);
  const [explain, setExplain] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState(false);
  const [err, setErr] = useState("");

  const current = useRef("");
  const load = useCallback(async (who: string) => {
    current.current = who;
    const history = await api.history(who);
    if (current.current !== who) {
      return;
    }
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
      <p className="lead">Browse, search, add, replace, or forget a scope. Replace needs a new value.</p>
      <ScopeBar onUser={handleUser} />
      {err ? <p className="err">{err}</p> : null}
      {notice ? <JobNotice onClose={() => setNotice(false)} /> : null}
      <div className="card" style={{ marginTop: "1rem" }}>
        <div className="row">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="search" />
          <button
            type="button"
            disabled={busy === "search"}
            onClick={async () => {
              setBusy("search");
              setErr("");
              try {
                const found = await api.search(user, query);
                setHits(found.hits);
              } catch (error) {
                setErr(error instanceof Error ? error.message : "search failed");
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === "search" ? "Searching…" : "Search"}
          </button>
        </div>
        <div className="row" style={{ marginTop: "0.7rem" }}>
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={2} style={{ flex: 1 }} />
          <button
            className="primary"
            type="button"
            disabled={!text.trim() || busy === "add"}
            onClick={async () => {
              setErr("");
              setNotice(false);
              setBusy("add");
              try {
                await api.add(user, text);
                setText("");
                setNotice(true);
                setBusy(null);
                void load(user).catch((error: Error) => setErr(error.message));
              } catch (error) {
                setErr(error instanceof Error ? error.message : "add failed");
                setBusy(null);
              }
            }}
          >
            {busy === "add" ? "Adding…" : "Add"}
          </button>
          <button
            type="button"
            disabled={busy === "forget"}
            onClick={async () => {
              if (!confirm(`Forget ${user}?`)) {
                return;
              }
              setBusy("forget");
              setErr("");
              try {
                await api.forget(user);
                await load(user);
              } catch (error) {
                setErr(error instanceof Error ? error.message : "forget failed");
              } finally {
                setBusy(null);
              }
            }}
          >
            {busy === "forget" ? "Forgetting…" : "Forget scope"}
          </button>
        </div>
      </div>
      <h2>Facts</h2>
      {facts.length ? (
        <div className="table-wrap">
          <table className="facts">
            <thead>
              <tr>
                <th className="col-subject">Subject</th>
                <th className="col-predicate">Predicate</th>
                <th className="col-object">Object</th>
                <th className="col-status">Status</th>
                <th className="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {facts.map((fact) => (
                <tr key={fact.id}>
                  <td className="col-subject">{fact.subject}</td>
                  <td className="col-predicate">{fact.predicate}</td>
                  <td className="col-object">{fact.object}</td>
                  <td className="col-status">
                    <span className="status">
                      <span className={`dot ${fact.status === "ACTIVE" ? "now" : "was"}`} />
                      <span className={`badge ${fact.status === "ACTIVE" ? "act" : "was"}`}>{fact.status}</span>
                    </span>
                  </td>
                  <td className="col-actions">
                    <div className="actions">
                      <button
                        type="button"
                        disabled={busy === `explain:${fact.id}`}
                        onClick={async () => {
                          setBusy(`explain:${fact.id}`);
                          try {
                            setExplain(await api.explain(fact.id));
                          } finally {
                            setBusy(null);
                          }
                        }}
                      >
                        {busy === `explain:${fact.id}` ? "Loading…" : "Timeline"}
                      </button>
                      {fact.status === "ACTIVE" ? (
                        <>
                          <input
                            value={drafts[fact.id] ?? ""}
                            onChange={(event) =>
                              setDrafts((currentDrafts) => ({ ...currentDrafts, [fact.id]: event.target.value }))
                            }
                            placeholder="replacement"
                          />
                          <button
                            type="button"
                            disabled={!(drafts[fact.id] ?? "").trim() || busy === `replace:${fact.id}`}
                            onClick={async () => {
                              const replacement = (drafts[fact.id] ?? "").trim();
                              if (!replacement) {
                                return;
                              }
                              setBusy(`replace:${fact.id}`);
                              try {
                                await api.correct(fact.id, replacement);
                                setDrafts((currentDrafts) => {
                                  const next = { ...currentDrafts };
                                  delete next[fact.id];
                                  return next;
                                });
                                await load(user);
                              } finally {
                                setBusy(null);
                              }
                            }}
                          >
                            {busy === `replace:${fact.id}` ? "Replacing…" : "Replace"}
                          </button>
                        </>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="lead">No facts in this scope yet.</p>
      )}
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
