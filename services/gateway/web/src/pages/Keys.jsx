import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Keys({ user }) {
  const isAdmin = user.role === "admin";
  const [keys, setKeys] = useState([]);
  const [users, setUsers] = useState([]);
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("");
  const [created, setCreated] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setKeys(await api("/keys"));
      if (isAdmin) setUsers(await api("/users"));
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      const body = { name };
      if (isAdmin && owner) body.user_id = Number(owner);
      setCreated(await api("/keys", { method: "POST", body }));
      setName("");
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function revoke(id) {
    if (!confirm("Revoke this key? Clients using it are rejected immediately.")) return;
    try {
      await api(`/keys/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <h2>API keys</h2>
      <div className="card">
        <div>Connect any MCP client to <code>{location.origin}/mcp</code> with the header <code>Authorization: Bearer &lt;your key&gt;</code>.</div>
        <div className="muted small">You never need the credentials of the upstream servers.</div>
      </div>
      <form className="card row" onSubmit={create}>
        <input placeholder="Key name, e.g. laptop" value={name} onChange={(e) => setName(e.target.value)} />
        {isAdmin && (
          <select value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">for me</option>
            {users.map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
          </select>
        )}
        <button>Create key</button>
      </form>
      {error && <p className="error">{error}</p>}
      {created && (
        <div className="card notice">
          <strong>Copy this key now. It is shown only once.</strong>
          <code className="key">{created.key}</code>
          <button onClick={() => setCreated(null)}>I have saved it</button>
        </div>
      )}
      <table>
        <thead>
          <tr><th>Name</th><th>Prefix</th>{isAdmin && <th>Owner</th>}<th>Created</th><th>Last used</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k.id}>
              <td>{k.name}</td>
              <td><code>umk_{k.prefix}</code></td>
              {isAdmin && <td>{k.owner}</td>}
              <td>{new Date(k.created_at).toLocaleString()}</td>
              <td>{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "never"}</td>
              <td>{k.revoked_at ? "revoked" : "active"}</td>
              <td>{!k.revoked_at && <button className="danger" onClick={() => revoke(k.id)}>Revoke</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}