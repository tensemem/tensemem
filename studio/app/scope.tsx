"use client";

import { useEffect, useState } from "react";
import { api, getToken, getUser, setToken, setUser } from "@/lib/api";

export function ScopeBar({ onUser }: { onUser: (user: string) => void }) {
  const [user, setLocal] = useState("studio-demo");
  const [token, setTok] = useState("");
  const [scopes, setScopes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    const current = getUser();
    setLocal(current);
    setTok(getToken());
    onUser(current);
    api
      .scopes()
      .then((data) => setScopes([...new Set(data.scopes.map((row) => row.user_id))]))
      .catch((error: Error) => setErr(error.message));
  }, [onUser]);

  return (
    <div className="card row">
      <label>
        User{" "}
        <input
          list="users"
          value={user}
          onChange={(event) => {
            setLocal(event.target.value);
            setUser(event.target.value);
            onUser(event.target.value);
          }}
        />
        <datalist id="users">
          {scopes.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </label>
      <label>
        Token{" "}
        <input
          value={token}
          onChange={(event) => {
            setTok(event.target.value);
            setToken(event.target.value);
          }}
          placeholder="optional bearer"
        />
      </label>
      <button
        className="primary"
        type="button"
        disabled={busy}
        onClick={async () => {
          setErr("");
          setBusy(true);
          try {
            await api.sample();
            setLocal("studio-demo");
            setUser("studio-demo");
            onUser("studio-demo");
          } catch (error) {
            setErr(error instanceof Error ? error.message : "sample failed");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Loading…" : "Load sample workspace"}
      </button>
      {err ? <span className="err">{err}</span> : null}
    </div>
  );
}
