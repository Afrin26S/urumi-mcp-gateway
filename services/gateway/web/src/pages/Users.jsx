import { useEffect, useState } from "react";
import { api } from "../api.js";

const EMPTY = { email: "", name: "", role: "member", password: "" };

export default function Users() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function load() {
    try {
      setUsers(await api("/users"));
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      await api("/users", { method: "POST", body: form });
      setForm(EMPTY);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggle(u) {
    try {
      await api(`/users/${u.id}`, { method: "PATCH", body: { disabled: !u.disabled } });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <h2>Team members</h2>
      <form className="card" onSubmit={create}>
        <h3>Invite a member</h3>
        <div className="row">
          <input placeholder="Email" value={form.email} onChange={set("email")} />
          <input placeholder="Name" value={form.name} onChange={set("name")} />
          <select value={form.role} onChange={set("role")}>
            <option value="member">member</option>
            <option value="admin">admin</option>
          </select>
          <input type="password" autoComplete="new-password" placeholder="Temporary password (10+ characters)" value={form.password} onChange={set("password")} />
          <button>Create</button>
        </div>
      </form>
      {error && <p className="error">{error}</p>}
      <table>
        <thead><tr><th>Email</th><th>Name</th><th>Role</th><th>Status</th><th></th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td><td>{u.name}</td><td>{u.role}</td>
              <td>{u.disabled ? "disabled" : "active"}</td>
              <td><button onClick={() => toggle(u)}>{u.disabled ? "Enable" : "Disable"}</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}