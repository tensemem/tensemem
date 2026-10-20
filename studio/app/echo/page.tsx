"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ScopeBar } from "../scope";

export default function EchoPage() {
  const [user, setUser] = useState("studio-demo");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");

  return (
    <>
      <h1>Echo lab</h1>
      <p className="lead">Feed recalled context back in. Fact count and confidence should stay flat.</p>
      <ScopeBar onUser={setUser} />
      <div className="card" style={{ marginTop: "1rem" }}>
        <button
          className="primary"
          onClick={async () => {
            setErr("");
            try {
              setResult(await api.echo(user, 8));
            } catch (error) {
              setErr(error instanceof Error ? error.message : "failed");
            }
          }}
        >
          Run 8 echo turns
        </button>
      </div>
      {err ? <p className="err">{err}</p> : null}
      {result ? (
        <div className="card" style={{ marginTop: "1rem" }}>
          <span className={`badge ${result.flat ? "act" : "stop"}`}>{result.flat ? "fence held" : "contaminated"}</span>
          <pre className="mono">{JSON.stringify(result.series, null, 2)}</pre>
        </div>
      ) : null}
    </>
  );
}
