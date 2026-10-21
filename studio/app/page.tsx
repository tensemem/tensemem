"use client";

import { useCallback, useRef, useState } from "react";
import { api } from "@/lib/api";
import { jobBadgeClass, jobStatusLabel } from "@/lib/jobs";
import { ScopeBar } from "./scope";

export default function BoardPage() {
  const [user, setUser] = useState("studio-demo");
  const [risk, setRisk] = useState<Record<string, unknown> | null>(null);
  const [jobs, setJobs] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState<string | null>(null);
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
  const openJobs = jobs.filter((job) => job.status !== "DONE");

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
      <h2>Jobs</h2>
      {openJobs.length ? (
        <div className="table-wrap">
          <table className="facts jobs">
            <thead>
              <tr>
                <th className="col-kind">Kind</th>
                <th className="col-status">Status</th>
                <th className="col-attempts">Tries</th>
                <th className="col-object">Error</th>
                <th className="col-job-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {openJobs.map((job) => {
                const id = String(job.id);
                const failed = job.status === "DEAD";
                return (
                  <tr key={id}>
                    <td className="col-kind">{String(job.kind)}</td>
                    <td className="col-status">
                      <span className="status">
                        <span className={`dot ${job.status === "DEAD" ? "was" : "now"}`} />
                        <span className={`badge ${jobBadgeClass(job.status)}`}>{jobStatusLabel(job.status)}</span>
                      </span>
                    </td>
                    <td className="col-attempts">{String(job.attempts ?? 0)}</td>
                    <td className="col-object">{job.last_error ? String(job.last_error) : "—"}</td>
                    <td className="col-job-actions">
                      <div className="actions">
                        <button
                          type="button"
                          disabled={!failed || busy === `retry:${id}`}
                          onClick={async () => {
                            setBusy(`retry:${id}`);
                            try {
                              await api.retryJob(id);
                              await load(user);
                            } finally {
                              setBusy(null);
                            }
                          }}
                        >
                          {busy === `retry:${id}` ? "Retrying…" : "Retry"}
                        </button>
                        <button
                          type="button"
                          disabled={!failed || busy === `dismiss:${id}`}
                          onClick={async () => {
                            setBusy(`dismiss:${id}`);
                            try {
                              await api.dismissJob(id);
                              await load(user);
                            } finally {
                              setBusy(null);
                            }
                          }}
                        >
                          {busy === `dismiss:${id}` ? "Dismissing…" : "Dismiss"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="lead">No open jobs. Queued and in-progress extract work shows up here.</p>
      )}
    </>
  );
}
