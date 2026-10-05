"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";

type ModuleKey = "leaves" | "remote_work" | "hr_policy";
type Message = { id: string; role: "user" | "assistant"; content: string; pending?: boolean; route?: ModuleKey };
type Reply = {
  reply?: string;
  content?: string;
  sessionId?: string;
  route?: { module?: ModuleKey } | ModuleKey;
  message?: { content?: string };
  error?: string;
};

const labels: Record<ModuleKey, string> = { leaves: "Άδειες", remote_work: "Τηλεργασία", hr_policy: "Πολιτικές HR" };
const prompts: Record<ModuleKey, string> = {
  leaves: "Θέλω βοήθεια με αίτημα άδειας.",
  remote_work: "Θέλω βοήθεια με αίτημα τηλεργασίας.",
  hr_policy: "Θέλω να ρωτήσω για πολιτική HR."
};

function responseText(data: Reply) {
  return data.reply ?? data.message?.content ?? data.content ?? "Δεν έλαβα απάντηση.";
}
function routeKey(data: Reply): ModuleKey | undefined {
  const key = typeof data.route === "string" ? data.route : data.route?.module;
  return key && key in labels ? key : undefined;
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [appsOpen, setAppsOpen] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  async function sendMessage(raw: string) {
    const content = raw.trim();
    if (!content || busy) return;

    const activeSession = sessionId ?? crypto.randomUUID();
    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
    setSessionId(activeSession);
    setMessages((items) => [...items,
      { id: userId, role: "user", content },
      { id: assistantId, role: "assistant", content: "", pending: true }
    ]);
    setDraft("");
    setAppsOpen(false);
    setBusy(true);
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: "smooth" }));

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: content, sessionId: activeSession })
      });
      const data = (await response.json()) as Reply;
      if (!response.ok) throw new Error(data.error ?? "Η αποστολή απέτυχε. Δοκίμασε ξανά.");
      setSessionId(data.sessionId ?? activeSession);
      setMessages((items) => items.map((item) => item.id === assistantId
        ? { ...item, content: responseText(data), route: routeKey(data), pending: false }
        : item
      ));
    } catch (error) {
      const text = error instanceof Error ? error.message : "Παρουσιάστηκε σφάλμα σύνδεσης.";
      setMessages((items) => items.map((item) => item.id === assistantId
        ? { ...item, content: text, pending: false }
        : item
      ));
    } finally {
      setBusy(false);
      requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: "smooth" }));
      inputRef.current?.focus();
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage(draft);
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage(draft);
    }
  }
  function newChat() {
    setMessages([]);
    setSessionId(null);
    setDraft("");
    setAppsOpen(false);
    inputRef.current?.focus();
  }
  function choose(key: ModuleKey) {
    void sendMessage(prompts[key]);
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">V</span><b>ViLabs</b></div>
        <div className="profile">
          <div className="avatar">HR</div>
          <div className="profile-copy"><strong>HR Assistant</strong><small>Εσωτερική υποστήριξη</small></div>
          <i className="online-dot" />
        </div>
        <button className="new-chat" type="button" onClick={newChat}><span>＋</span> Νέα συνομιλία</button>
        <div className="nav-title">ΕΡΓΑΣΙΕΣ</div>
        <button className="nav-item selected" type="button" onClick={() => inputRef.current?.focus()}><span>▤</span> Κεντρικό chat</button>
        <button className="nav-item" type="button" onClick={() => choose("leaves")}><span>◷</span> Άδειες</button>
        <button className="nav-item" type="button" onClick={() => choose("remote_work")}><span>⌂</span> Τηλεργασία</button>
        <div className="sidebar-foot"><i /> Ο βοηθός HR είναι έτοιμος</div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><div className="crumb">ViLabs <span>/</span> HR Assistant</div><h1>Κεντρικό chat</h1></div>
          <button className="user-avatar" type="button" aria-label="Προφίλ χρήστη">Γ</button>
        </header>

        <section className={"conversation " + (messages.length ? "has-messages" : "empty")}>
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-logo">HR<i /></div>
              <p className="eyebrow">Ο προσωπικός σου HR assistant</p>
              <h2>Πώς μπορώ να σε βοηθήσω;</h2>
              <p className="welcome-copy">Ρώτησέ με για άδειες, τηλεργασία ή οτιδήποτε σχετικό με την εργασία σου.</p>
              <div className="suggestions">
                <button type="button" onClick={() => choose("leaves")}>◷ &nbsp; Θέλω να ζητήσω άδεια</button>
                <button type="button" onClick={() => choose("remote_work")}>⌂ &nbsp; Θέλω τηλεργασία</button>
                <button type="button" onClick={() => choose("hr_policy")}>⌕ &nbsp; Ρώτησε για πολιτική HR</button>
              </div>
            </div>
          ) : (
            <div className="message-list" aria-live="polite">
              {messages.map((message) => (
                <article className={"message-row " + message.role} key={message.id}>
                  {message.role === "assistant" && <div className="message-avatar">HR</div>}
                  <div className="message-content">
                    <div className="message-author">{message.role === "assistant" ? "HR Assistant" : "Εσύ"}</div>
                    <div className={"bubble " + (message.pending ? "pending" : "")}>
                      {message.pending ? <span className="typing"><i /><i /><i /> Σκέφτομαι</span> : message.content}
                    </div>
                    {message.route && !message.pending && (
                      <button className="route-card" type="button" onClick={() => choose(message.route!)}>
                        <span className="route-icon">↗</span>
                        <span><strong>Συνέχεια στις {labels[message.route]}</strong><small>Άνοιξε αυτή τη λειτουργία μέσα από το chat</small></span>
                        <b>→</b>
                      </button>
                    )}
                  </div>
                </article>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </section>

        <div className="composer-area">
          <form className="composer" onSubmit={submit}>
            <button className="attach" type="button" disabled title="Η επισύναψη αρχείων θα συνδεθεί με το backend.">＋</button>
            <textarea ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={keyDown}
              placeholder="Ρώτησε οτιδήποτε για το HR..." rows={1} aria-label="Το μήνυμά σου" />
            <div className="composer-actions">
              <div className="apps-wrap">
                <button className={"apps-button " + (appsOpen ? "selected" : "")} type="button"
                  aria-label="Επιλογή λειτουργίας" aria-expanded={appsOpen} onClick={() => setAppsOpen((open) => !open)}>✣</button>
                {appsOpen && <div className="apps-menu">
                  <p>Τι θέλεις να κάνεις;</p>
                  <button type="button" onClick={() => choose("leaves")}><b>◷</b><span><strong>Άδειες</strong><small>Υπόλοιπο ή νέο αίτημα</small></span></button>
                  <button type="button" onClick={() => choose("remote_work")}><b>⌂</b><span><strong>Τηλεργασία</strong><small>Ημέρες και αιτήματα</small></span></button>
                  <button type="button" onClick={() => choose("hr_policy")}><b>⌕</b><span><strong>Πολιτικές HR</strong><small>Ρώτησε για διαδικασίες</small></span></button>
                </div>}
              </div>
              <button className="send" type="submit" disabled={!draft.trim() || busy} aria-label="Αποστολή">↑</button>
            </div>
          </form>
          <p className="composer-hint">Enter για αποστολή · Shift + Enter για νέα γραμμή</p>
        </div>
      </section>
    </main>
  );
}
