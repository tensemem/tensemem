"use client";

import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { matchesRecent, rememberRecent } from "@/lib/recent";
import { JobNotice } from "../notice";
import { ScopeBar } from "../scope";

export default function PlaygroundPage() {
  const [user, setUser] = useState("studio-demo");
  const [message, setMessage] = useState("");
  const [question, setQuestion] = useState("");
  const [historyOn, setHistoryOn] = useState(false);
  const [steps, setSteps] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(false);
  const [showHints, setShowHints] = useState(false);
  const [err, setErr] = useState("");

  const messageHints = useMemo(() => matchesRecent("playground-message", message), [message, notice, busy]);
  const questionHints = useMemo(() => matchesRecent("playground-question", question), [question, notice, busy]);

  return (
    <>
      <h1>Process playground</h1>
      <p className="lead">One message, then one question. The engine decides — you see why.</p>
      <ScopeBar onUser={setUser} />
      {notice ? <JobNotice onClose={() => setNotice(false)} /> : null}
      <div className="card" style={{ marginTop: "1rem" }}>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onFocus={() => setShowHints(true)}
          rows={3}
          style={{ width: "100%" }}
          placeholder="Message to remember"
        />
        {showHints && messageHints.length ? (
          <div className="hints">
            {messageHints.map((item) => (
              <button
                key={item}
                type="button"
                onMouseDown={(event) => {
                  event.preventDefault();
                  setMessage(item);
                  setShowHints(false);
                }}
              >
                {item}
              </button>
            ))}
          </div>
        ) : null}
        <div className="row" style={{ marginTop: "0.6rem" }}>
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            style={{ flex: 1 }}
            placeholder="Question to recall"
            list="playground-questions"
          />
          <datalist id="playground-questions">
            {questionHints.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <label>
            <input type="checkbox" checked={historyOn} onChange={(event) => setHistoryOn(event.target.checked)} />{" "}
            include history
          </label>
          <button
            className="primary"
            type="button"
            disabled={!message.trim() || !question.trim() || busy}
            onClick={async () => {
              setErr("");
              setNotice(false);
              setBusy(true);
              try {
                const before = await api.state(user);
                const added = await api.add(user, message);
                rememberRecent("playground-message", message);
                rememberRecent("playground-question", question);
                setNotice(true);
                setBusy(false);
                const after = await api.state(user);
                const searched = await api.search(user, question);
                const packed = await api.context(user, question, historyOn);
                setSteps([
                  { title: "1. Episode", body: added },
                  { title: "2. State before", body: before.values },
                  { title: "3. State after resolve", body: after.values },
                  { title: "4. Freshness", body: after.freshness },
                  { title: "5. Search items", body: searched.hits },
                  { title: "6. Packed context", body: packed },
                ]);
              } catch (error) {
                setErr(error instanceof Error ? error.message : "failed");
                setBusy(false);
              }
            }}
          >
            {busy ? "Running…" : "Run path"}
          </button>
        </div>
      </div>
      {err ? <p className="err">{err}</p> : null}
      {steps.map((step) => (
        <div className="step" key={String(step.title)}>
          <strong>{String(step.title)}</strong>
          <pre className="mono">{JSON.stringify(step.body, null, 2)}</pre>
        </div>
      ))}
    </>
  );
}
