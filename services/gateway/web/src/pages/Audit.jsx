import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Audit() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      setRows(await api("/audit?limit=200"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  return (
    <section>
      <div className="row between"><h2>Audit log</h2><button onClick={load}>Refresh</button></div>
      {error && <p className="error">{error}</p>}
      <table>
        <thead>
          <tr><th>Time</th><th>User</th><th>Via</th><th>Server</th><th>Tool</th><th>ms</th><th>Outcome</th><th>Detail</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{new Date(r.ts).toLocaleString()}</td>
              <td>{r.user_email}</td>
              <td>{r.source}</td>
              <td>{r.server_slug}</td>
              <td>{r.tool}</td>
              <td>{r.duration_ms}</td>
              <td><span className={`badge ${r.outcome}`}>{r.outcome}</span></td>
              <td className="muted">{r.error}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}