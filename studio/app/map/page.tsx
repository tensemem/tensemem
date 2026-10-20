"use client";

import { useCallback, useState } from "react";
import { api, type Fact } from "@/lib/api";
import { ScopeBar } from "../scope";

export default function MapPage() {
  const [user, setUser] = useState("studio-demo");
  const [facts, setFacts] = useState<Fact[]>([]);
  const [graph, setGraph] = useState<{ nodes: Array<Record<string, string>>; edges: Array<Record<string, string>> }>({
    nodes: [],
    edges: [],
  });
  const [err, setErr] = useState("");

  const load = useCallback(async (who: string) => {
    const [history, drawn] = await Promise.all([api.history(who), api.graph(who)]);
    setFacts(history.facts);
    setGraph(drawn);
  }, []);

  const handleUser = useCallback(
    (who: string) => {
      setUser(who);
      void load(who).catch((error: Error) => setErr(error.message));
    },
    [load],
  );

  const lanes = new Map<string, Fact[]>();
  for (const fact of facts) {
    const bucket = lanes.get(fact.predicate) ?? [];
    bucket.push(fact);
    lanes.set(fact.predicate, bucket);
  }

  return (
    <>
      <h1>Tense lanes + fact graph</h1>
      <p className="lead">One current value per ONE slot. Was vs is, plus SUPERSEDES edges.</p>
      <ScopeBar onUser={handleUser} />
      {err ? <p className="err">{err}</p> : null}
      <h2>Lanes</h2>
      {[...lanes.entries()].map(([predicate, rows]) => (
        <div className="lane" key={predicate}>
          <div>{predicate}</div>
          <div>
            {rows.map((fact) => (
              <span key={fact.id} style={{ marginRight: "0.8rem" }}>
                <span className={`dot ${fact.status === "ACTIVE" ? "now" : "was"}`} />
                {fact.object}{" "}
                <span className={`badge ${fact.status === "ACTIVE" ? "act" : "was"}`}>{fact.status}</span>
              </span>
            ))}
          </div>
        </div>
      ))}
      <h2>Graph</h2>
      <svg viewBox="0 0 900 420" width="100%" height="420" style={{ background: "#101218", borderRadius: 10 }}>
        {graph.edges.map((edge, index) => {
          const from = graph.nodes.findIndex((node) => node.id === edge.source);
          const to = graph.nodes.findIndex((node) => node.id === edge.target);
          if (from < 0 || to < 0) return null;
          const x1 = 80 + (from % 6) * 140;
          const y1 = 50 + Math.floor(from / 6) * 90;
          const x2 = 80 + (to % 6) * 140;
          const y2 = 50 + Math.floor(to / 6) * 90;
          return (
            <line
              key={`${edge.source}-${edge.target}-${index}`}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={edge.kind === "SUPERSEDES" ? "#d4a574" : "#2a2d36"}
              strokeWidth={edge.kind === "SUPERSEDES" ? 2 : 1}
            />
          );
        })}
        {graph.nodes.map((node, index) => {
          const x = 80 + (index % 6) * 140;
          const y = 50 + Math.floor(index / 6) * 90;
          const fill = node.kind === "fact" ? "#2a3344" : node.kind === "subject" ? "#243024" : "#322618";
          return (
            <g key={node.id}>
              <circle cx={x} cy={y} r={18} fill={fill} stroke="#8b8678" />
              <text x={x} y={y + 32} textAnchor="middle" fill="#e8e4d9" fontSize="11">
                {(node.label ?? node.id).slice(0, 18)}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="lead">{graph.edges.filter((edge) => edge.kind === "SUPERSEDES").length} SUPERSEDES edges</p>
    </>
  );
}
