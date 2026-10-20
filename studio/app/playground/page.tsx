"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { ScopeBar } from "../scope";

const SAMPLES = [
  "This month we file GSTR-3B from Maharashtra. Books stay in Tally.",
  "I might move the biometrics to Chennai if Mumbai gets cancelled.",
];

const QUESTIONS = [
  "which GST return do we file now",
  "what was the hotel before",
  "what currency do we bill Contoso",
];

export default function PlaygroundPage() {
  const [user, setUser] = useState("studio-demo");
  const [message, setMessage] = useState(SAMPLES[0]);
  const [question, setQuestion] = useState(QUESTIONS[0]);
  const [historyOn, setHistoryOn] = useState(false);
  const [steps, setSteps] = useState<Array<Record<string, unknown>>>([]);
  const [err, setErr] = useState("");

  return (
    <>
      <h1>Process playground</h1>
      <p className="lead">One message, then one question. The engine decides — you see why.</p>
      <ScopeBar onUser={setUser} />
      <div className="card" style={{ marginTop: "1rem" }}>
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={3} style={{ width: "100%" }} />
        <div className="row" style={{ marginTop: "0.6rem" }}>
          {SAMPLES.map((sample) => (
            <button key={sample} onClick={() => setMessage(sample)}>
              {sample.slice(0, 32)}…
            </button>
          ))}
        </div>
        <div className="row" style={{ marginTop: "0.6rem" }}>
          <input value={question} onChange={(event) => setQuestion(event.target.value)} style={{ flex: 1 }} />
          <label>
            <input type="checkbox" checked={historyOn} onChange={(event) => setHistoryOn(event.target.checked)} />{" "}
            include history
          </label>
          <button
            className="primary"
            onClick={async () => {
              setErr("");
              try {
                const before = await api.state(user);
                const added = await api.add(user, message);
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
              }
            }}
          >
            Run path
          </button>
        </div>
        <div className="row" style={{ marginTop: "0.5rem" }}>
          {QUESTIONS.map((item) => (
            <button key={item} onClick={() => setQuestion(item)}>
              {item}
            </button>
          ))}
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
