import { useEffect, useState } from "react";
import { api } from "../api.js";

const WINDOWS = [[1, "Last hour"], [24, "Last 24 hours"], [168, "Last 7 days"]];

export default function Metrics() {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setData(await api(`/metrics?hours=${hours}`));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, [hours]);

  const servers = data?.servers ?? [];
  const calls = servers.reduce((n, s) => n + s.calls, 0);
  const failures = servers.reduce((n, s) => n + s.failures, 0);
  const down = servers.filter((s) => s.status === "unreachable").length;

  return (
    <section>
      <div className="page-head">
        <div>
          <h2>Metrics</h2>
          <p className="muted">Calls, error rate and latency per server, from the audit log.</p>
        </div>
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          {WINDOWS.map(([h, label]) => <option key={h} value={h}>{label}</option>)}
        </select>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="stats">
        <div className="stat"><span>Tool calls</span><strong>{calls}</strong></div>
        <div className="stat"><span>Failed calls</span><strong>{failures}</strong></div>
        <div className="stat"><span>Servers unreachable</span><strong>{down}</strong></div>
      </div>
      <table>
        <thead>
          <tr><th>Server</th><th>Status</th><th>Calls</th><th>OK</th><th>Failed</th><th>Denied</th><th>Error rate</th><th>Avg ms</th><th>p95 ms</th></tr>
        </thead>
        <tbody>
          {servers.map((s) => (
            <tr key={s.slug}>
              <td><strong>{s.name}</strong> <code>{s.slug}</code></td>
              <td>
                <span className={`badge ${s.status}`}>{s.status}</span>
                {s.status_reason && <div className="error small">{s.status_reason}</div>}
              </td>
              <td>{s.calls}</td><td>{s.success}</td><td>{s.failures}</td><td>{s.denied}</td>
              <td>{(s.error_rate * 100).toFixed(1)}%</td><td>{s.avg_ms}</td><td>{s.p95_ms}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}