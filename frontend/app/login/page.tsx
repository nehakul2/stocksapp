"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { signIn, signUp } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const creating = mode === "signup";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await (creating ? signUp : signIn)(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <h1>{creating ? "Create your account" : "Sign in"}</h1>
      <p className="muted">
        {creating
          ? "Your watchlist is saved to your account, so it follows you to any device."
          : "Sign in to see your saved watchlist."}
      </p>
      <form onSubmit={submit}>
        <label>Email
          <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>Password
          <input
            type="password" required minLength={8} value={password}
            autoComplete={creating ? "new-password" : "current-password"}
            onChange={(e) => setPassword(e.target.value)}
          />
          {creating && <span className="hint">At least 8 characters.</span>}
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy}>
          {busy ? "One moment…" : creating ? "Create account" : "Sign in"}
        </button>
      </form>
      <p className="switch">
        {creating ? "Already have an account? " : "New here? "}
        <button type="button" className="linkish" onClick={() => { setMode(creating ? "signin" : "signup"); setError(null); }}>
          {creating ? "Sign in" : "Create an account"}
        </button>
      </p>
      <p className="muted"><Link href="/">Continue without an account</Link> — your watchlist then stays in this browser.</p>
    </div>
  );
}
