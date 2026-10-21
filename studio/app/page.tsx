"use client";

import { useCallback, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ScopeBar } from "./scope";

export default function BoardPage() {
  const [user, setUser] = useState("studio-demo");
  const [risk, setRisk] = useState<Record<string, unknown> | null>(null);
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]);
  const [err, setErr] = useState("");

  const current = useRef("");
  const load = useCallback(async (who: string) => {
    current.current = who;
    setErr("");
    try {
      const [nextRisk, nextJobs] = await Promise.all([api.actRisk(who), api.jobs(who)]);
      if (current.current !== who) {
        return;
      }
      setRisk(nextRisk);
      setJobs(nextJobs.jobs);
    } catch (error) {
      if (current.current !== who) {
        return;
      }
      setRisk(null);
      setJobs([]);
      setErr(error instanceof Error ? error.message : "unavailable");
    }
  }, []);

  const handleUser = useCallback(
    (who: string) => {
      setUser(who);
      void load(who);
    },
    [load],
  );

  const verdict = String(risk?.verdict ?? "wait");
  const freshness = (risk?.freshness ?? {}) as Record<string, unknown>;
  const values = (risk?.values ?? {}) as Record<string, unknown>;

  return (
    <>
      <h1>Safe to act?</h1>
      <p className="lead">
        Freshness, dead extract, hedges, and corrections — not a list of similar snippets.
      </p>
      <ScopeBar onUser={handleUser} />
      {err ? <p className="err">{err}. Start `tensemem serve` on :8080.</p> : null}
      {risk ? (
        <div className="grid" style={{ marginTop: "1rem" }}>
          <div className="card">
            <span className={`badge ${verdict === "act" ? "act" : verdict === "wait" ? "wait" : "stop"}`}>
              {verdict.replaceAll("_", " ")}
            </span>
            <p>
              current={String(freshness.is_current)} pending={String(freshness.pending)} failed=
              {String(freshness.failed)}
            </p>
            <p>
              dead jobs {String(risk.dead_jobs)} · hedges {String(risk.hedges)} · rejected{" "}
              {String(risk.rejected_claims)}
            </p>
          </div>
          <div className="card">
            <strong>Current card</strong>
            <pre className="mono">{JSON.stringify(values, null, 2)}</pre>
          </div>
        </div>
      ) : null}
      {jobs.filter((job) => job.status !== "DONE").length ? (
        <>
          <h2>Jobs</h2>
          {jobs
            .filter((job) => job.status !== "DONE")
            .map((job) => (
            <div className="lane" key={String(job.id)}>
              <div>{String(job.kind)}</div>
              <div>
                <span className={`badge ${job.status === "DEAD" ? "stop" : "wait"}`}>{String(job.status)}</span>
                {job.last_error ? <span> {String(job.last_error)}</span> : null}
                <button
                  style={{ marginLeft: "0.5rem" }}
                  onClick={async () => {
                    await api.retryJob(String(job.id));
                    await load(user);
                  }}
                >
                  Retry
                </button>
                <button
                  style={{ marginLeft: "0.4rem" }}
                  onClick={async () => {
                    await api.dismissJob(String(job.id));
                    await load(user);
                  }}
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </>
      ) : null}
    </>
  );
}
