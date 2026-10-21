"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphEdge, GraphNode } from "@/lib/api";

type Pos = { x: number; y: number };
type View = { x: number; y: number; w: number; h: number };

const NODE_W: Record<string, number> = { subject: 150, fact: 200, object: 170 };
const NODE_H = 44;
const CANVAS_H = 560;

function badgeClass(status: string | undefined): string {
  if (status === "ACTIVE") return "act";
  if (status === "REJECTED") return "stop";
  return "was";
}

function statusColor(status: string | undefined): string {
  if (status === "ACTIVE") return "#7dce9a";
  if (status === "REJECTED") return "#e07a6a";
  return "#d4a574";
}

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function layout(nodes: GraphNode[]): { pos: Map<string, Pos>; width: number; height: number } {
  const subjects = nodes.filter((node) => node.kind === "subject");
  const facts = nodes.filter((node) => node.kind === "fact");
  const objects = nodes.filter((node) => node.kind === "object");
  const other = nodes.filter((node) => !["subject", "fact", "object"].includes(node.kind));
  const groups = new Map<string, GraphNode[]>();
  for (const fact of facts) {
    const lane = (fact.label ?? "").split("=")[0] || "fact";
    const bucket = groups.get(lane) ?? [];
    bucket.push(fact);
    groups.set(lane, bucket);
  }
  const factRows = [...groups.values()].reduce((sum, group) => sum + group.length + 0.6, 0);
  const rows = Math.max(subjects.length, objects.length, factRows, other.length, 1);
  const height = Math.max(420, 80 + rows * 58);
  const width = 1120;
  const pos = new Map<string, Pos>();
  const stack = (list: GraphNode[], x: number) => {
    const gap = (height - 80) / Math.max(list.length, 1);
    list.forEach((node, index) => {
      pos.set(node.id, { x, y: 50 + gap * (index + 0.5) });
    });
  };
  stack(subjects, 140);
  stack(objects, 980);
  let y = 50;
  const factGap = (height - 80) / Math.max(factRows, 1);
  for (const group of groups.values()) {
    y += factGap * 0.3;
    for (const fact of group) {
      pos.set(fact.id, { x: 560, y: y + factGap * 0.5 });
      y += factGap;
    }
  }
  stack(other, 560);
  return { pos, width, height };
}

function links(edges: GraphEdge[]): GraphEdge[] {
  const drawn: GraphEdge[] = [];
  for (const edge of edges) {
    if (edge.kind === "SUPERSEDES") {
      drawn.push(edge);
      continue;
    }
    if (edge.fact_id) {
      drawn.push({ ...edge, target: `f:${edge.fact_id}` });
      drawn.push({ ...edge, source: `f:${edge.fact_id}` });
    } else {
      drawn.push(edge);
    }
  }
  return drawn;
}

function neighbors(id: string, edges: GraphEdge[]): Set<string> {
  const near = new Set<string>([id]);
  for (const edge of edges) {
    if (edge.source === id) near.add(edge.target);
    if (edge.target === id) near.add(edge.source);
  }
  return near;
}

function curve(from: Pos, to: Pos, bend: number): string {
  const mx = (from.x + to.x) / 2 + bend;
  const my = (from.y + to.y) / 2;
  return `M ${from.x} ${from.y} Q ${mx} ${my} ${to.x} ${to.y}`;
}

export function FactGraph({
  nodes,
  edges,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const placed = useMemo(() => layout(nodes), [nodes]);
  const [pos, setPos] = useState<Map<string, Pos>>(placed.pos);
  const [view, setView] = useState<View>({ x: 0, y: 0, w: placed.width, h: placed.height });
  const [hover, setHover] = useState<string | null>(null);
  const [showPred, setShowPred] = useState(true);
  const [showSupersede, setShowSupersede] = useState(true);
  const [activeOnly, setActiveOnly] = useState(false);
  const drag = useRef<{ id: string | "pan"; x: number; y: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    setPos(placed.pos);
    setView({ x: 0, y: 0, w: placed.width, h: placed.height });
  }, [placed]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const box = svg.getBoundingClientRect();
      setView((current) => {
        const worldX = current.x + ((event.clientX - box.left) / box.width) * current.w;
        const worldY = current.y + ((event.clientY - box.top) / box.height) * current.h;
        const factor = event.deltaY > 0 ? 1.12 : 0.88;
        const w = Math.min(2400, Math.max(280, current.w * factor));
        const h = (w / current.w) * current.h;
        return {
          x: worldX - ((worldX - current.x) / current.w) * w,
          y: worldY - ((worldY - current.y) / current.h) * h,
          w,
          h,
        };
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  const visibleNodes = useMemo(() => {
    if (!activeOnly) return nodes;
    return nodes.filter((node) => node.kind !== "fact" || node.status === "ACTIVE");
  }, [activeOnly, nodes]);
  const visibleIds = useMemo(() => new Set(visibleNodes.map((node) => node.id)), [visibleNodes]);
  const drawn = useMemo(
    () =>
      links(edges).filter((edge) => {
        if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) return false;
        if (edge.kind === "SUPERSEDES") return showSupersede;
        return showPred;
      }),
    [edges, showPred, showSupersede, visibleIds],
  );
  const focus = hover ?? selectedId;
  const lit = focus ? neighbors(focus, drawn) : null;
  const selected = nodes.find((node) => node.id === selectedId) ?? null;

  const toWorld = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const box = svg.getBoundingClientRect();
    return {
      x: view.x + ((clientX - box.left) / box.width) * view.w,
      y: view.y + ((clientY - box.top) / box.height) * view.h,
    };
  };

  const fit = () => {
    const xs = [...pos.values()].map((point) => point.x);
    const ys = [...pos.values()].map((point) => point.y);
    if (!xs.length) return;
    const minX = Math.min(...xs) - 120;
    const maxX = Math.max(...xs) + 120;
    const minY = Math.min(...ys) - 60;
    const maxY = Math.max(...ys) + 60;
    setView({ x: minX, y: minY, w: Math.max(maxX - minX, 400), h: Math.max(maxY - minY, 300) });
  };

  return (
    <div className="graph-shell">
      <div className="graph-toolbar">
        <button type="button" onClick={fit}>
          Fit
        </button>
        <button type="button" onClick={() => setView({ x: 0, y: 0, w: placed.width, h: placed.height })}>
          Reset
        </button>
        <label>
          <input type="checkbox" checked={showPred} onChange={(event) => setShowPred(event.target.checked)} />
          Predicate links
        </label>
        <label>
          <input
            type="checkbox"
            checked={showSupersede}
            onChange={(event) => setShowSupersede(event.target.checked)}
          />
          SUPERSEDES
        </label>
        <label>
          <input type="checkbox" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} />
          ACTIVE facts only
        </label>
        <span className="graph-hint">Scroll to zoom · drag background to pan · drag a node to move it</span>
      </div>
      <div className="graph-body">
        <svg
          ref={svgRef}
          className="graph-canvas"
          viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
          height={CANVAS_H}
          role="img"
          aria-label="Fact graph"
          onPointerDown={(event) => {
            if (event.target !== event.currentTarget) return;
            const world = toWorld(event.clientX, event.clientY);
            drag.current = { id: "pan", x: world.x, y: world.y };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            const held = drag.current;
            if (!held) return;
            const world = toWorld(event.clientX, event.clientY);
            if (held.id === "pan") {
              setView((current) => ({
                ...current,
                x: current.x - (world.x - held.x),
                y: current.y - (world.y - held.y),
              }));
              return;
            }
            setPos((current) => {
              const next = new Map(current);
              next.set(held.id, { x: world.x, y: world.y });
              return next;
            });
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
        >
          <defs>
            <marker id="arrow-pred" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#6b7280" />
            </marker>
            <marker id="arrow-super" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#d4a574" />
            </marker>
          </defs>
          {drawn.map((edge, index) => {
            const from = pos.get(edge.source);
            const to = pos.get(edge.target);
            if (!from || !to) return null;
            const superEdge = edge.kind === "SUPERSEDES";
            const on = !lit || lit.has(edge.source) || lit.has(edge.target);
            return (
              <g key={`${edge.source}-${edge.target}-${index}`} opacity={on ? 1 : 0.12}>
                <path
                  d={curve(from, to, superEdge ? 80 : 0)}
                  fill="none"
                  stroke={superEdge ? "#d4a574" : "#4b5563"}
                  strokeWidth={superEdge ? 2.4 : 1.6}
                  strokeDasharray={superEdge ? "6 4" : undefined}
                  markerEnd={superEdge ? "url(#arrow-super)" : "url(#arrow-pred)"}
                />
                {on && !superEdge ? (
                  <text
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 8}
                    textAnchor="middle"
                    fill="#8b8678"
                    fontSize="11"
                  >
                    {clip(edge.kind, 22)}
                  </text>
                ) : null}
              </g>
            );
          })}
          {visibleNodes.map((node) => {
            const point = pos.get(node.id);
            if (!point) return null;
            const width = NODE_W[node.kind] ?? 150;
            const on = !lit || lit.has(node.id);
            const picked = selectedId === node.id;
            const stroke = node.kind === "fact" ? statusColor(node.status) : picked ? "#7aa2f7" : "#8b8678";
            return (
              <g
                key={node.id}
                opacity={on ? 1 : 0.18}
                style={{ cursor: "grab" }}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  const world = toWorld(event.clientX, event.clientY);
                  drag.current = { id: node.id, x: world.x, y: world.y };
                  onSelect(node.id);
                  event.currentTarget.setPointerCapture(event.pointerId);
                }}
                onPointerEnter={() => setHover(node.id)}
                onPointerLeave={() => setHover((current) => (current === node.id ? null : current))}
              >
                <rect
                  x={point.x - width / 2}
                  y={point.y - NODE_H / 2}
                  width={width}
                  height={NODE_H}
                  rx={10}
                  fill={picked ? "#1b2433" : "#14161c"}
                  stroke={stroke}
                  strokeWidth={picked ? 2.4 : 1.4}
                />
                <text x={point.x} y={point.y - 4} textAnchor="middle" fill="#e8e4d9" fontSize="12" fontWeight={600}>
                  {clip(node.label || node.id, 24)}
                </text>
                <text x={point.x} y={point.y + 12} textAnchor="middle" fill="#8b8678" fontSize="10">
                  {node.kind}
                  {node.status ? ` · ${node.status}` : ""}
                </text>
                <title>{`${node.kind}: ${node.label}${node.status ? ` (${node.status})` : ""}`}</title>
              </g>
            );
          })}
        </svg>
        <aside className="graph-inspect">
          <h3>Inspector</h3>
          {selected ? (
            <>
              <p className="mono">{selected.label}</p>
              <p>
                <span className="badge was">{selected.kind}</span>{" "}
                {selected.status ? (
                  <span className={`badge ${badgeClass(selected.status)}`}>{selected.status}</span>
                ) : null}
              </p>
              {selected.fact_id ? <p className="lead">Fact {selected.fact_id}</p> : null}
              <p className="lead">
                {drawn.filter((edge) => edge.source === selected.id || edge.target === selected.id).length} connected
                edges. Dimmed nodes are outside this neighborhood.
              </p>
              <button type="button" onClick={() => onSelect(null)}>
                Clear
              </button>
            </>
          ) : (
            <p className="lead">Click a table row or a node to inspect it. Hover a node to light its neighborhood.</p>
          )}
          <div className="graph-legend">
            <span>
              <i className="dot now" /> ACTIVE fact
            </span>
            <span>
              <i className="dot was" /> SUPERSEDED / was
            </span>
            <span className="legend-line">dashed gold = SUPERSEDES</span>
          </div>
        </aside>
      </div>
    </div>
  );
}
