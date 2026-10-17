import { Eye, LogIn, UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { useSession, type User } from "../lib/session";
import { ErrorBox } from "../components/ui";

const ROLE_TEXT: Record<string, string> = {
  manager: "Plant manager - everything, incl. users and settings",
  engineer: "Maintenance engineer - approves repairs and stops",
  operator: "Machine operator - acknowledges alerts, approves small actions",
  viewer: "Viewer - read-only",
};

export default function Login() {
  const { signIn, config } = useSession();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const dark = document.documentElement.dataset.theme === "dark";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = mode === "signin"
        ? await api<User>("/api/auth/login", { body: { email, password } })
        : await api<User>("/api/auth/signup", { body: { email, password, full_name: name } });
      signIn(user);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function guest() {
    setBusy(true);
    try {
      signIn(await api<User>("/api/auth/guest", { method: "POST" }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-wrap" id="main">
      <div className="card login-card">
        <img className="logo" src={dark ? "/opex-logo-dark.png" : "/opex-logo.png"} alt="OpEx logo" />
        <h1 style={{ textAlign: "center" }}>{mode === "signin" ? "Sign in to OpEx" : "Create an account"}</h1>
        <p className="muted" style={{ textAlign: "center" }}>Catch machine problems early, see what each fix costs, decide with confidence.</p>

        <form onSubmit={submit} className="stack" style={{ marginTop: 16 }}>
          {mode === "signup" && (
            <label className="field">Full name
              <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required minLength={2} />
            </label>
          )}
          <label className="field">Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
          </label>
          <label className="field">Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signin" ? "current-password" : "new-password"} required minLength={mode === "signup" ? 8 : 1} />
          </label>
          {error ? <ErrorBox error={error} /> : null}
          <button className="btn primary" disabled={busy}>
            {mode === "signin" ? <><LogIn size={18} aria-hidden /> Sign in</> : <><UserPlus size={18} aria-hidden /> Create account</>}
          </button>
        </form>

        {config?.demo_mode && (
          <>
            <button className="btn" style={{ width: "100%", marginTop: 10 }} onClick={guest} disabled={busy}>
              <Eye size={18} aria-hidden /> Explore as a guest (read-only)
            </button>
            <hr className="divider" />
            <p className="small"><b>Demo accounts</b> (password <code>{config.demo_password}</code>) - select one to fill the form:</p>
            <ul className="small" style={{ paddingLeft: 18 }}>
              {config.demo_accounts.map((a) => (
                <li key={a.email}>
                  <button className="btn ghost small" style={{ padding: "2px 4px", minHeight: 30 }}
                    onClick={() => { setMode("signin"); setEmail(a.email); setPassword(config.demo_password ?? ""); }}>
                    {a.email}
                  </button>
                  <span className="muted"> {ROLE_TEXT[a.role]}</span>
                </li>
              ))}
            </ul>
          </>
        )}
        {config?.allow_signup && (
          <p className="small" style={{ textAlign: "center", marginTop: 8 }}>
            {mode === "signin" ? "New here? " : "Already have an account? "}
            <button className="btn ghost small" onClick={() => setMode(mode === "signin" ? "signup" : "signin")}>
              {mode === "signin" ? "Create an account" : "Sign in"}
            </button>
          </p>
        )}
      </div>
    </main>
  );
}
