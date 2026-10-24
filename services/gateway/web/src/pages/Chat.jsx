import { useState } from "react";
import { api } from "../api.js";

export default function Chat() {
  const [items, setItems] = useState([]); // {role, content, calls}
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(e) {
    e.preventDefault();
    const content = text.trim();
    if (!content || busy) return;
    const next = [...items, { role: "user", content }];
    setItems(next);
    setText("");
    setBusy(true);
    setError("");
    try {
      // the browser sends only role and content; the server enforces what is allowed
      const messages = next.slice(-19).map(({ role, content }) => ({ role, content }));
      const data = await api("/chat", { method: "POST", body: { messages } });
      setItems([...next, { role: "assistant", content: data.reply, calls: data.tool_calls }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Chat</h2>
      <p className="muted small">The assistant acts as you. Every tool it calls goes through the gateway and appears in the audit log under your name.</p>
      <div className="chatlog">
        {items.length === 0 && (
          <div>
            <p className="muted">Try one of these:</p>
            <div className="suggestions">
              {[
                "List the products in the store.",
                "What orders came in today?",
                "What is the total of today's orders in rupees?",
              ].map((s) => (
                <button key={s} type="button" onClick={() => setText(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {items.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content}
            {m.calls?.length > 0 && (
              <details>
                <summary>{m.calls.length} tool call{m.calls.length > 1 ? "s" : ""}</summary>
                {m.calls.map((c, j) => (
                  <div key={j} className="small">
                    <code>{c.tool}</code> <span className={`badge ${c.is_error ? "error" : "success"}`}>{c.is_error ? "error" : "ok"}</span>
                    <div className="muted">args: {JSON.stringify(c.arguments)}</div>
                    <div className="muted">result: {c.output}</div>
                  </div>
                ))}
              </details>
            )}
          </div>
        ))}
        {busy && <p className="muted">Thinking…</p>}
      </div>
      {error && <p className="error">{error}</p>}
      <form className="row" onSubmit={send}>
        <input style={{ flex: 1 }} placeholder="Ask about products or orders…" value={text} onChange={(e) => setText(e.target.value)} />
        <button disabled={busy}>Send</button>
      </form>
    </section>
  );
}