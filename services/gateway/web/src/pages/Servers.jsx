import { useEffect, useState } from "react";
import { api } from "../api.js";

const EMPTY = { slug: "", name: "", url: "", auth_type: "none", header_name: "", credential: "" };

function ServerForm({ initial, editing, onSave, onCancel }) {
  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      await onSave(form);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h3>{editing ? `Edit ${initial.slug}` : "Add an MCP server"}</h3>
      {!editing && <input placeholder="Slug, e.g. weather" value={form.slug} onChange={set("slug")} />}
      <input placeholder="Display name" value={form.name} onChange={set("name")} />
      <input placeholder="Streamable HTTP URL, e.g. http://host:8000/mcp" value={form.url} onChange={set("url")} />
      <select value={form.auth_type} onChange={set("auth_type")}>
        <option value="none">No credential</option>
        <option value="bearer">Bearer token</option>
        <option value="header">Custom header</option>
      </select>
      {form.auth_type === "header" && (
        <input placeholder="Header name" value={form.header_name || ""} onChange={set("header_name")} />
      )}
      {form.auth_type !== "none" && (
        <input
          type="password"
          autoComplete="off"
          placeholder={editing ? "New credential (empty keeps the current one)" : "Credential"}
          value={form.credential}
          onChange={set("credential")}
        />
      )}
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button>Save</button>
        <button type="button" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

export default function Servers({ isAdmin }) {
  const [servers, setServers] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState(null); // null, {mode: "add"} or {mode: "edit", server}

  async function load() {
    try {
      setServers(await api("/servers"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000); // status refreshes itself every 10 seconds
    return () => clearInterval(timer);
  }, []);

  async function run(action) {
    try {
      await action();
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function save(data) {
    if (form.mode === "add") {
      await api("/servers", {
        method: "POST",
        body: {
          slug: data.slug.trim(),
          name: data.name.trim(),
          url: data.url.trim(),
          auth_type: data.auth_type,
          header_name: data.auth_type === "header" ? data.header_name : null,
          credential: data.auth_type === "none" ? null : data.credential,
        },
      });
    } else {
      const body = {
        name: data.name.trim(),
        url: data.url.trim(),
        auth_type: data.auth_type,
        header_name: data.auth_type === "header" ? data.header_name : null,
      };
      if (data.auth_type === "none") body.credential = "";
      else if (data.credential) body.credential = data.credential; // empty means: keep the current one
      await api(`/servers/${form.server.id}`, { method: "PATCH", body });
    }
    setForm(null);
    await load();
  }

  const remove = (s) =>
    run(async () => {
      if (confirm(`Remove ${s.name}? Its tools will disappear for everyone.`)) {
        await api(`/servers/${s.id}`, { method: "DELETE" });
      }
    });

    if (!servers) return <p className="muted">{error || "Loading…"}</p>;

  const connected = servers.filter((s) => s.status === "connected").length;
  const toolCount = servers.reduce((n, s) => n + s.tools.length, 0);

  return (
    <section>
      <div className="page-head">
        <div>
          <h2>MCP servers</h2>
          <p className="muted">Everything your team can use through a single endpoint.</p>
        </div>
        {isAdmin && !form && <button className="primary" onClick={() => setForm({ mode: "add" })}>+ Add server</button>}
      </div>
      <div className="stats">
        <div className="stat"><span>Servers</span><strong>{servers.length}</strong></div>
        <div className="stat"><span>Connected</span><strong>{connected}</strong></div>
        <div className="stat"><span>Tools available</span><strong>{toolCount}</strong></div>
      </div>
      {error && <p className="error">{error}</p>}
      {form && (
        <ServerForm
          key={form.mode + (form.server?.id ?? "")}
          initial={form.mode === "add" ? EMPTY : { ...EMPTY, ...form.server, credential: "" }}
          editing={form.mode === "edit"}
          onSave={save}
          onCancel={() => setForm(null)}
        />
      )}
      {servers.map((s) => (
        <div className="card" key={s.id}>
          <div className="row between">
            <div className="title">
              <strong>{s.name}</strong> <code>{s.slug}</code>
              <span className={`badge ${s.status}`}>{s.status}</span>
            </div>
            {isAdmin && (
              <div className="row">
                <button onClick={() => setForm({ mode: "edit", server: s })}>Edit</button>
                <button onClick={() => run(() => api(`/servers/${s.id}`, { method: "PATCH", body: { enabled: !s.enabled } }))}>
                  {s.enabled ? "Disable" : "Enable"}
                </button>
                <button className="danger" onClick={() => remove(s)}>Remove</button>
              </div>
            )}
          </div>
          <div className="muted small">
            {s.url} · auth: {s.auth_type}{s.has_credential ? " · credential stored, never shown" : ""}
          </div>
          {s.error && <div className="error small">{s.error}</div>}
          <details>
            <summary>{s.tools.length} tools</summary>
            <ul className="toollist">
              {s.tools.map((t) => (
                <li key={t.name}><code>{t.name}</code><span className="muted">{t.description}</span></li>
              ))}
            </ul>
          </details>
        </div>
      ))}
    </section>
  );
}