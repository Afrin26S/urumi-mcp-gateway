import { useEffect, useState } from "react";
import { api } from "./api.js";
import Servers from "./pages/Servers.jsx";
import Keys from "./pages/Keys.jsx";
import Users from "./pages/Users.jsx";
import Audit from "./pages/Audit.jsx";
import Chat from "./pages/Chat.jsx";

// small line icons (24x24, stroke style), so no icon package is needed
const ICONS = {
  servers: (<><rect x="2" y="2" width="20" height="8" rx="2" ry="2" /><rect x="2" y="14" width="20" height="8" rx="2" ry="2" /><line x1="6" y1="6" x2="6.01" y2="6" /><line x1="6" y1="18" x2="6.01" y2="18" /></>),
  chat: <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />,
  keys: <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />,
  users: (<><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></>),
  audit: (<><line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" /></>),
  logout: (<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></>),
};

function Icon({ name }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {ICONS[name]}
    </svg>
  );
}

function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      onLogin(await api("/auth/login", { method: "POST", body: { email, password } }));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="login-page">
      <form className="card login" onSubmit={submit}>
        <div className="logo">M</div>
        <h1>MCP Gateway</h1>
        <p className="muted small">Sign in to manage servers and use your team's tools.</p>
        <input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="error small">{error}</p>}
        <button>Sign in</button>
      </form>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(undefined); // undefined: checking, null: signed out
  const [tab, setTab] = useState("servers");

  useEffect(() => {
    api("/me").then(setUser).catch(() => setUser(null));
  }, []);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    setUser(null);
  }

  if (user === undefined) return <p className="muted" style={{ padding: 24 }}>Loading…</p>;
  if (user === null) return <Login onLogin={setUser} />;

  const isAdmin = user.role === "admin";
  const tabs = [
    ["servers", "Servers", "servers"],
    ["chat", "Chat", "chat"],
    ["keys", "API keys", "keys"],
    ...(isAdmin ? [["users", "Users", "users"], ["audit", "Audit log", "audit"]] : []),
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">M</div>
          <div><strong>MCP Gateway</strong><span>One endpoint for every tool</span></div>
        </div>
        <nav>
          {tabs.map(([id, label, icon]) => (
            <button key={id} className={`nav-item ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>
              <Icon name={icon} />{label}
            </button>
          ))}
        </nav>
        <div className="spacer" />
        <div className="me">
          <div className="avatar">{user.email[0].toUpperCase()}</div>
          <div><div className="who">{user.email}</div><div className="role">{user.role}</div></div>
        </div>
        <button className="nav-item" onClick={logout}><Icon name="logout" />Sign out</button>
      </aside>
      <main className="content">
        {tab === "servers" && <Servers isAdmin={isAdmin} />}
        {tab === "chat" && <Chat />}
        {tab === "keys" && <Keys user={user} />}
        {tab === "users" && isAdmin && <Users />}
        {tab === "audit" && isAdmin && <Audit />}
      </main>
    </div>
  );
}