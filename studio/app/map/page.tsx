"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { api, type Fact, type Graph } from "@/lib/api";
import { ScopeBar } from "../scope";
import { FactGraph } from "./graph";

function badgeClass(status: string): string {
  if (status === "ACTIVE") return "act";
  if (status === "REJECTED") return "stop";
  return "was";
}

function when(value: string | null): string {
  if (!value) return "—";
  return value.replace("T", " ").replace(/\.\d+.*/, "").replace("Z", "");
}

export default function MapPage() {
  const [user, setUser] = useState("studio-demo");
  const [facts, setFacts] = useState<Fact[]>([]);
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState("");

  const current = useRef("");
  const load = useCallback(async (who: string) => {
    current.current = who;
    const [history, drawn] = await Promise.all([api.history(who), api.graph(who)]);
    if (current.current !== who) {
      return;
    }
    setFacts(history.facts);
    setGraph(drawn);
  }, []);

  const handleUser = useCallback(
    (who: string) => {
      setUser(who);
      setSelected(null);
      void load(who).catch((error: Error) => setErr(error.message));
    },
    [load],
  );

  const rows = useMemo(() => {
    const rank = (status: string) => (status === "ACTIVE" ? 0 : status === "SUPERSEDED" ? 1 : 2);
    return [...facts].sort((a, b) => {
      const lane = a.predicate.localeCompare(b.predicate);
      if (lane) return lane;
      const status = rank(a.status) - rank(b.status);
      if (status) return status;
      return a.recorded_at.localeCompare(b.recorded_at);
    });
  }, [facts]);

  const lanes = new Set(rows.map((fact) => fact.predicate)).size;
  const supersedes = graph.edges.filter((edge) => edge.kind === "SUPERSEDES").length;

  return (
    <>
      <h1>Map</h1>
      <p className="lead">
        Every lane in one table. The graph is subject → fact → object, with dashed SUPERSEDES when a newer value
        replaced an older one.
      </p>
      <ScopeBar onUser={handleUser} />
      {err ? <p className="err">{err}</p> : null}

      <h2>Lanes</h2>
      <p className="lead">
        {rows.length} facts across {lanes} {lanes === 1 ? "lane" : "lanes"}. Click a row to focus that fact on the
        graph.
      </p>
      {rows.length ? (
        <div className="table-wrap table-wrap-lanes">
          <table className="facts">
            <thead>
              <tr>
                <th className="col-predicate">Lane</th>
                <th className="col-subject">Subject</th>
                <th className="col-object">Object</th>
                <th className="col-status">Status</th>
                <th className="col-when">Valid from</th>
                <th className="col-when">Recorded</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((fact) => {
                const nodeId = `f:${fact.id}`;
                return (
                  <tr
                    key={fact.id}
                    className={selected === nodeId ? "is-selected" : undefined}
                    onClick={() => setSelected(nodeId)}
                  >
                    <td className="col-predicate">{fact.predicate}</td>
                    <td className="col-subject">{fact.subject}</td>
                    <td className="col-object">{fact.object}</td>
                    <td className="col-status">
                      <span className="status">
                        <span className={`dot ${fact.status === "ACTIVE" ? "now" : "was"}`} />
                        <span className={`badge ${badgeClass(fact.status)}`}>{fact.status}</span>
                      </span>
                    </td>
                    <td className="col-when">{when(fact.valid_from)}</td>
                    <td className="col-when">{when(fact.recorded_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="lead">No facts in this scope yet.</p>
      )}

      <h2>Graph</h2>
      <p className="lead">{supersedes} SUPERSEDES {supersedes === 1 ? "edge" : "edges"}.</p>
      {graph.nodes.length ? (
        <FactGraph nodes={graph.nodes} edges={graph.edges} selectedId={selected} onSelect={setSelected} />
      ) : (
        <p className="lead">Nothing to draw until this scope has facts.</p>
      )}
    </>
  );
}
