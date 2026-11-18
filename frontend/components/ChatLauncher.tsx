"use client";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Chat from "@/components/Chat";

// The floating Chat button, bottom right on every page, and the panel it opens.
// On a stock page the chat is about that stock; elsewhere it is about your watchlists.
export default function ChatLauncher() {
  const path = usePathname() ?? "";
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);

  const match = path.match(/^\/stock\/([^/]+)/);
  const ticker = match ? decodeURIComponent(match[1]).toUpperCase() : undefined;

  // When the panel closes, put keyboard focus back on the Chat button (it is visible again by then).
  useEffect(() => {
    if (wasOpen.current && !open) button.current?.focus();
    wasOpen.current = open;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    // Move focus into the panel so keyboard users land on the question box.
    panel.current?.querySelector<HTMLInputElement>(".ask input")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (path.startsWith("/login")) return null;

  return (
    <>
      <div
        ref={panel} className="chatpanel" role="dialog" aria-label={ticker ? `Chat about ${ticker}` : "Chat about your watchlists"}
        hidden={!open}
      >
        <div className="chathead">
          <b>{ticker ? `Ask about ${ticker}` : "Ask about your watchlists"}</b>
          <button className="chatclose" aria-label="Close chat" onClick={() => setOpen(false)}>{"✕"}</button>
        </div>
        <div className="chatbody">
          <Chat ticker={ticker} active={open} />
        </div>
      </div>
      <button ref={button} className="chatfab" aria-expanded={open} aria-label={open ? "Close chat" : "Open chat"} hidden={open}
        onClick={() => setOpen(true)}>
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        Chat
      </button>
    </>
  );
}
