"""Fact graph for Studio: subjects, objects, and SUPERSEDES edges."""

from __future__ import annotations

import sqlite3


def load_graph(conn: sqlite3.Connection, scope_id: int) -> dict[str, object]:
    """Nodes for subjects/objects/facts; edges for predicates and SUPERSEDES."""
    facts = conn.execute(
        """
        SELECT f.public_id, f.object_text, f.status, p.name AS predicate,
               e.canonical_name AS subject
        FROM facts f
        JOIN predicates p ON p.id = f.predicate_id
        JOIN entities e ON e.id = f.subject_id
        WHERE f.scope_id = ? AND f.status <> 'DELETED'
        ORDER BY p.name, f.recorded_seq
        """,
        (scope_id,),
    ).fetchall()
    nodes: dict[str, dict[str, object]] = {}
    edges: list[dict[str, object]] = []
    for row in facts:
        subject = str(row["subject"])
        obj = str(row["object_text"])
        fact_id = str(row["public_id"])
        nodes.setdefault(
            f"s:{subject}",
            {"id": f"s:{subject}", "kind": "subject", "label": subject},
        )
        nodes.setdefault(f"o:{obj}", {"id": f"o:{obj}", "kind": "object", "label": obj})
        nodes[f"f:{fact_id}"] = {
            "id": f"f:{fact_id}",
            "kind": "fact",
            "label": f"{row['predicate']}={obj}",
            "status": str(row["status"]),
            "fact_id": fact_id,
        }
        edges.append(
            {
                "source": f"s:{subject}",
                "target": f"o:{obj}",
                "kind": str(row["predicate"]),
                "status": str(row["status"]),
                "fact_id": fact_id,
            }
        )
    for row in conn.execute(
        """
        SELECT src.public_id AS src_id, dst.public_id AS dst_id, fe.kind
        FROM fact_edges fe
        JOIN facts src ON src.id = fe.src_fact_id
        JOIN facts dst ON dst.id = fe.dst_id
        WHERE src.scope_id = ? AND fe.kind = 'SUPERSEDES'
        """,
        (scope_id,),
    ).fetchall():
        edges.append(
            {
                "source": f"f:{row['src_id']}",
                "target": f"f:{row['dst_id']}",
                "kind": "SUPERSEDES",
                "status": "SUPERSEDED",
            }
        )
    return {"nodes": list(nodes.values()), "edges": edges}
