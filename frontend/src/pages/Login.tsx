import { Check, LogIn } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ErrorBox } from "../components/ui";
import { api } from "../lib/api";
import { loadGoogle } from "../lib/google";
import { useSession, type User } from "../lib/session";

const ROLE_NAME: Record<string, string> = { manager: "Plant manager", engineer: "Maintenance engineer" };
const ROLE_TEXT: Record<string, string> = {
  manager: "Plant manager: everything, including people and settings",
  engineer: "Maintenance engineer: approves actions, acknowledges alerts",
};

export default function Login() {
  const { signIn, config } = useSession();
  const [error, setError] = useState<unknown>(null);

  async function withGoogle(credential: string) {
    setError(null);
    try {
      signIn(await api<User>("/api/auth/google", { body: { credential } }));
    } catch (e) {
      setError(e);
    }
  }

  return (
    <main className="login-wrap" id="main">
      <aside className="login-side">
        <img className="logo" src="/opex-logo.png" alt="OpEx" />
        <h2>Catch trouble before it stops the line.</h2>
        <p className="lead">Your calm copilot for the shop floor.</p>
        <ul className="login-points">
          <li><span className="dot"><Check size={18} aria-hidden /></span> Spots machine problems hours early.</li>
          <li><span className="dot"><Check size={18} aria-hidden /></span> Prices every fix in rupees.</li>
          <li><span className="dot"><Check size={18} aria-hidden /></span> You decide. OpEx never touches a machine.</li>
        </ul>
      </aside>
      <div className="login-main">
        <div className="login-card">
          <h1>Welcome back</h1>
          <p className="lead">Sign in to see how your plant is doing.</p>
          <div className="stack" style={{ alignItems: "center" }}>
            {config?.google_client_id
              ? <GoogleButton clientId={config.google_client_id} onCredential={withGoogle} onError={setError} />
              : <p className="banner sev-medium small" role="note"><span className="text">
                  Google sign-in isn't set up yet. The plant manager adds a Google client ID (AUDIT.md, step 2b).
                  {config?.demo_mode && " Meanwhile, use the demo account below."}</span></p>}
            <p className="muted" style={{ textAlign: "center", margin: 0 }}>
              Use the Google account your plant manager added. No extra password to remember.
            </p>
            {error ? <ErrorBox error={error} /> : null}
          </div>
          {config?.demo_mode && <DemoSignIn onSignedIn={signIn} setError={setError} />}
        </div>
      </div>
    </main>
  );
}

function GoogleButton({ clientId, onCredential, onError }: {
  clientId: string; onCredential: (credential: string) => void; onError: (error: unknown) => void;
}) {
  const holder = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false;
    loadGoogle()
      .then((google) => {
        if (cancelled || !holder.current) return;
        google.accounts.id.initialize({ client_id: clientId, callback: (r) => onCredential(r.credential) });
        google.accounts.id.renderButton(holder.current, { theme: "outline", size: "large", text: "signin_with", width: 280 });
      })
      .catch(onError);
    return () => { cancelled = true; };
    // the button is created once; callbacks only report back
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);
  return <div ref={holder} style={{ minHeight: 44 }} aria-label="Sign in with Google" />;
}

/** Demo mode only: pick one of the demo accounts and log in. No email or password to type. */
function DemoSignIn({ onSignedIn, setError }: { onSignedIn: (user: User) => void; setError: (e: unknown) => void }) {
  const { config } = useSession();
  const accounts = config?.demo_accounts ?? [];
  const [email, setEmail] = useState("");
  const [working, setWorking] = useState(false);
  const chosen = email || accounts[0]?.email || "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    setWorking(true);
    setError(null);
    try {
      onSignedIn(await api<User>("/api/auth/login", { body: { email: chosen, password: config?.demo_password ?? "" } }));
    } catch (e) {
      setError(e);
    } finally {
      setWorking(false);
    }
  }

  return (
    <>
      <div className="or" aria-hidden><span>or</span></div>
      <form onSubmit={submit} className="stack">
        <label className="field">Choose an account
          <select value={chosen} onChange={(e) => setEmail(e.target.value)}>
            {accounts.map((a) => <option key={a.email} value={a.email}>{a.full_name} · {ROLE_NAME[a.role] ?? a.role}</option>)}
          </select>
        </label>
        <p className="muted small" style={{ margin: 0, textAlign: "left" }}>{ROLE_TEXT[accounts.find((a) => a.email === chosen)?.role ?? ""]}</p>
        <button className="btn primary" disabled={working || !chosen}><LogIn size={18} aria-hidden /> {working ? "Logging in…" : "Log in"}</button>
      </form>
    </>
  );
}
