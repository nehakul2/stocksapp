"use client";
import { useState } from "react";
import { useWatchlist } from "@/lib/watchlist";

type Mode = "none" | "new" | "rename";

// Pick which watchlist to look at, and create, rename or delete them. Only shown when signed in.
export default function ListSwitcher() {
  const { lists, activeId, signedIn, setActive, createList, renameList, deleteList } = useWatchlist();
  const [mode, setMode] = useState<Mode>("none");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (!signedIn) return null;
  const active = lists.find((l) => l.id === activeId);

  const open = (m: Mode) => { setMode(m); setErr(""); setConfirmDelete(false); setName(m === "rename" ? active?.name ?? "" : ""); };
  const close = () => { setMode("none"); setErr(""); };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const msg = mode === "new" ? await createList(name) : activeId != null ? await renameList(activeId, name) : null;
    if (msg) setErr(msg); else close();
  }

  async function remove() {
    if (activeId == null) return;
    const msg = await deleteList(activeId);
    setConfirmDelete(false);
    if (msg) setErr(msg);
  }

  return (
    <div className="lists">
      <label className="lists-pick">
        <span className="muted">Watchlist</span>
        <select value={activeId ?? ""} onChange={(e) => { setActive(Number(e.target.value)); close(); setConfirmDelete(false); }}>
          {lists.map((l) => <option key={l.id} value={l.id}>{l.name} ({l.tickers.length})</option>)}
        </select>
      </label>
      {mode === "none" ? (
        <div className="lists-actions">
          <button className="linkish" onClick={() => open("new")}>New list</button>
          <button className="linkish" onClick={() => open("rename")}>Rename</button>
          {lists.length > 1 && (confirmDelete ? (
            <span>Delete &ldquo;{active?.name}&rdquo; and its alerts?{" "}
              <button className="linkish danger" onClick={remove}>Yes, delete</button>{" "}
              <button className="linkish" onClick={() => setConfirmDelete(false)}>Cancel</button></span>
          ) : (
            <button className="linkish" onClick={() => { setConfirmDelete(true); setErr(""); }}>Delete</button>
          ))}
        </div>
      ) : (
        <form className="lists-form" onSubmit={submit}>
          <input aria-label={mode === "new" ? "New watchlist name" : "New name for this watchlist"} value={name} maxLength={40} autoFocus
            placeholder="Name, for example Tech" onChange={(e) => setName(e.target.value)} />
          <button type="submit" className="go" disabled={!name.trim()}>{mode === "new" ? "Create" : "Save"}</button>
          <button type="button" className="linkish" onClick={close}>Cancel</button>
        </form>
      )}
      {err && <p className="msg err" role="alert" style={{ flexBasis: "100%", margin: 0 }}>{err}</p>}
    </div>
  );
}
