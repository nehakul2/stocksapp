"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ChatAction, ChatTurn } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useWatchlist } from "@/lib/watchlist";

type Msg = { role: "user" | "assistant"; content: string; actions?: ChatAction[] };
type Status = "pending" | "done" | "dismissed" | string; // a string that isn't a keyword is an error message

// Minimal types for the browser's speech features (Chrome, Edge and Safari have them; Firefox doesn't).
type Recognition = {
  lang: string; interimResults: boolean; continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
  start: () => void; stop: () => void;
};
type RecognitionCtor = new () => Recognition;
const SPEAK_KEY = "chat.speak";

const STOCK_IDEAS = ["Why is it moving today?", "Is it near its 52-week low?", "How does it compare with similar companies?"];
const HOME_IDEAS = ["Which of my stocks needs a look today?", "Create a watchlist called Energy with XOM and CVX", "What do my watchlists have in common?"];

export default function Chat({ ticker }: { ticker?: string }) {
  const { token } = useAuth();
  const { runAction } = useWatchlist();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [left, setLeft] = useState<string>("");
  const [canListen, setCanListen] = useState(false);
  const [canSpeak, setCanSpeak] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const msgsRef = useRef<Msg[]>([]);
  msgsRef.current = msgs;
  const speakRef = useRef(false);
  speakRef.current = speak;

  useEffect(() => {
    const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
    setCanListen(!!(w.SpeechRecognition || w.webkitSpeechRecognition));
    setCanSpeak("speechSynthesis" in window);
    try { setSpeak(localStorage.getItem(SPEAK_KEY) === "1"); } catch { /* ignore */ }
    return () => { try { window.speechSynthesis?.cancel(); rec.current?.stop(); } catch { /* ignore */ } };
  }, []);

  // A new stock is a new conversation.
  useEffect(() => { setMsgs([]); setStatus({}); setErr(""); stopSpeaking(); }, [ticker]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { end.current?.scrollIntoView?.({ block: "nearest" }); }, [msgs, busy]);

  function stopSpeaking() {
    try { window.speechSynthesis?.cancel(); } catch { /* ignore */ }
    setSpeaking(false);
  }

  function say(answer: string) {
    if (!speakRef.current || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(answer);
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  }

  const send = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || !token || busy) return;
    const history: ChatTurn[] = msgsRef.current.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: q }]);
    setText(""); setErr(""); setBusy(true);
    try {
      const r = await api.chat(token, q, history, ticker);
      setMsgs((m) => [...m, { role: "assistant", content: r.answer, actions: r.actions }]);
      setLeft(`${Math.max(0, r.usage.limit - r.usage.used)} of ${r.usage.limit} AI questions left today`);
      say(r.answer);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }, [token, busy, ticker]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleSpeak(on: boolean) {
    setSpeak(on);
    try { localStorage.setItem(SPEAK_KEY, on ? "1" : "0"); } catch { /* ignore */ }
    if (!on) stopSpeaking();
  }

  function listen() {
    if (listening) { rec.current?.stop(); return; }
    const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) return;
    stopSpeaking();
    const r = new Ctor();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = false;
    let finalText = "";
    r.onresult = (e) => {
      let t = "";
      for (let i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
      finalText = t;
      setText(t);
    };
    r.onerror = (e) => {
      setListening(false);
      setErr(e.error === "not-allowed" ? "Microphone access is blocked. Allow it in your browser's site settings to talk to the chat." : "I couldn't hear that. Try again.");
    };
    r.onend = () => { setListening(false); if (finalText.trim()) send(finalText); };
    rec.current = r;
    setErr(""); setListening(true);
    r.start();
  }

  async function confirm(key: string, a: ChatAction) {
    setStatus((s) => ({ ...s, [key]: "working" }));
    const msg = await runAction(a);
    setStatus((s) => ({ ...s, [key]: msg ?? "done" }));
  }

  if (!token) {
    return <p className="fine" style={{ marginTop: 0 }}><Link href="/login">Sign in</Link> to ask questions about {ticker ?? "your watchlists"}.</p>;
  }

  const ideas = ticker ? STOCK_IDEAS : HOME_IDEAS;

  return (
    <div className="chat">
      {msgs.length === 0 && (
        <div className="ideas">
          {ideas.map((q) => <button key={q} onClick={() => send(q)} disabled={busy}>{q}</button>)}
        </div>
      )}
      <div className="log" role="log" aria-live="polite">
        {msgs.map((m, i) => (
          <div key={i} className={`msg-${m.role}`}>
            <p>{m.content}</p>
            {m.actions?.map((a, j) => {
              const key = `${i}-${j}`;
              const st = status[key] ?? "pending";
              return (
                <div className="act" key={key}>
                  <span>{a.label}</span>
                  {st === "pending" && (<>
                    <button className="go" onClick={() => confirm(key, a)}>Confirm</button>
                    <button className="linkish" onClick={() => setStatus((s) => ({ ...s, [key]: "dismissed" }))}>Dismiss</button>
                  </>)}
                  {st === "working" && <span className="muted">Working&hellip;</span>}
                  {st === "done" && <span className="ok">Done</span>}
                  {st === "dismissed" && <span className="muted">Dismissed</span>}
                  {!["pending", "working", "done", "dismissed"].includes(st) && <span className="bad" role="alert">{st}</span>}
                </div>
              );
            })}
          </div>
        ))}
        {busy && <p className="muted">Thinking&hellip;</p>}
        <div ref={end} />
      </div>
      {err && <p className="msg err" role="alert">{err}</p>}
      <form className="ask" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <input aria-label={ticker ? `Ask about ${ticker}` : "Ask about your watchlists"} value={text} maxLength={400}
          placeholder={listening ? "Listening…" : ticker ? `Ask about ${ticker}` : "Ask about your watchlists, or ask me to change one"}
          onChange={(e) => setText(e.target.value)} />
        {canListen && (
          <button type="button" className={`mic${listening ? " on" : ""}`} aria-pressed={listening} onClick={listen}
            aria-label={listening ? "Stop listening" : "Speak your question"}>{listening ? "Stop" : "Speak"}</button>
        )}
        <button type="submit" className="go" disabled={busy || !text.trim()}>Ask</button>
        {msgs.length > 0 && <button type="button" className="linkish" onClick={() => { setMsgs([]); setStatus({}); setErr(""); stopSpeaking(); }}>Clear</button>}
      </form>
      <div className="chatmeta">
        {canSpeak && (
          <label><input type="checkbox" checked={speak} onChange={(e) => toggleSpeak(e.target.checked)} /> Read answers aloud</label>
        )}
        {speaking && <button className="linkish" onClick={stopSpeaking}>Stop reading</button>}
        {left && <span className="muted">{left}</span>}
      </div>
      <p className="fine">Answers use this page&rsquo;s data and can be wrong. Not financial advice.</p>
    </div>
  );
}
