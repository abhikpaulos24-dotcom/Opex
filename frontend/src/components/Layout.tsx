import { Bell, BookOpenCheck, Brain, Database, Factory, ListChecks, LogOut, Menu, MessageCircle, Pause, Play, Settings as SettingsIcon, Type, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useLive } from "../lib/live";
import { useOverview } from "../lib/queries";
import { useSession } from "../lib/session";
import type { Alert } from "../lib/types";
import { AccessibilityPanel } from "./AccessibilityPanel";

const NAV = [
  { to: "/", label: "Overview", icon: Factory },
  { to: "/actions", label: "Actions", icon: ListChecks },
  { to: "/copilot", label: "Ask OpEx", icon: MessageCircle },
  { to: "/simulation", label: "5-year simulation", icon: Brain },
  { to: "/learning", label: "Learning log", icon: BookOpenCheck },
  { to: "/data", label: "Data & models", icon: Database },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export function Layout({ children }: { children: ReactNode }) {
  const { user, signOut, prefs } = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const [a11yOpen, setA11yOpen] = useState(false);
  const [toasts, setToasts] = useState<Alert[]>([]);
  const seen = useRef<Set<string> | null>(null);
  const location = useLocation();
  const overview = useOverview();
  const data = overview.data;

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  // New critical alerts pop up once (and are announced by screen readers).
  useEffect(() => {
    if (!data?.alerts) return;
    const ids = new Set(data.alerts.map((a) => a.id));
    if (seen.current === null) {
      seen.current = ids;
      return;
    }
    const fresh = data.alerts.filter((a) => !seen.current!.has(a.id) && ["critical", "high"].includes(a.severity));
    seen.current = ids;
    // Toasts stay until dismissed (no time limit to read them); at most 3 on screen.
    if (fresh.length) setToasts((t) => [...t, ...fresh].slice(-3));
  }, [data]);

  const riskCount = data?.risks.filter((r) => ["critical", "high"].includes(r.severity)).length ?? 0;

  return (
    <div className={`shell ${prefs.focus ? "focus-mode" : ""}`}>
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="topbar">
        <button className="btn icon-btn ghost menu-button" aria-label="Open menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
          <Menu aria-hidden />
        </button>
        <Link to="/" className="brand" aria-label="OpEx home">
          <img src="/opex-mark.png" alt="" />
          <span><strong>OpEx</strong><small>Team OpEx · Operations copilot</small></span>
        </Link>
        <span className="spacer" />
        <LiveStatus updatedAt={overview.dataUpdatedAt} failed={overview.isError} />
        {data && (
          <div className="clock" aria-label={`Plant time ${data.plant_time.replace("T", " ")}, ${data.shift}`}>
            <b>{data.plant_time.slice(11, 16)} · {data.shift}</b>
            <span>Sahyadri Precision · Unit 2 (demo)</span>
          </div>
        )}
        <Link to="/actions" className="btn icon-btn ghost" aria-label={`${data?.open_alert_count ?? 0} open alerts`}>
          <Bell aria-hidden />
          {!!data?.open_alert_count && <span className="badge sev-high">{data.open_alert_count}</span>}
        </Link>
        <button className="btn icon-btn ghost" onClick={() => setA11yOpen(true)} aria-label="Display and accessibility settings" title="Display and accessibility">
          <Type aria-hidden />
        </button>
        <div className="row" style={{ gap: 6 }}>
          <span className="small muted user-name" style={{ textAlign: "right", lineHeight: 1.2 }}>
            {user?.full_name}<br />{user?.role_label}
          </span>
          <button className="btn icon-btn ghost top-sign-out" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut aria-hidden /></button>
        </div>
      </header>

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <nav aria-label="Main">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
              <Icon size={20} aria-hidden /> {label}
              {to === "/actions" && riskCount > 0 && <span className="badge sev-critical count" aria-label={`${riskCount} urgent`}>{riskCount}</span>}
            </NavLink>
          ))}
          <button className="nav-link menu-sign-out" onClick={signOut}><LogOut size={20} aria-hidden /> Sign out</button>
        </nav>
      </aside>

      <main id="main" className="main" tabIndex={-1}>{children}</main>

      <div className="toasts" aria-live="assertive" role="status">
        {toasts.map((t) => (
          <div key={t.id} className="toast" style={{ borderColor: `var(--${t.severity})` }}>
            <div className="row between">
              <strong className={`badge sev-${t.severity}`}>{t.severity === "critical" ? "Critical" : "High"}</strong>
              <button className="btn icon-btn ghost" style={{ minHeight: 36, minWidth: 36 }} aria-label="Dismiss"
                onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}><X size={18} aria-hidden /></button>
            </div>
            <p style={{ margin: "6px 0 2px", fontWeight: 700 }}>{t.title}</p>
            <p className="small muted" style={{ margin: 0 }}>{t.message}</p>
            <Link className="btn small" style={{ marginTop: 8 }} to={`/machines/${t.machine_id}`}
              onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}>Open {t.machine_id}</Link>
          </div>
        ))}
      </div>
      <AccessibilityPanel open={a11yOpen} onClose={() => setA11yOpen(false)} />
    </div>
  );
}

/** "Live · updated 4 s ago", a clear warning when the feed stops, and a pause button (WCAG 2.2.2). */
function LiveStatus({ updatedAt, failed }: { updatedAt: number; failed: boolean }) {
  const { paused, setPaused } = useLive();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  if (!updatedAt) return null;
  const seconds = Math.max(0, Math.round((now - updatedAt) / 1000));
  const stale = !paused && (failed || seconds > 30);
  const time = new Date(updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const text = paused ? `Paused · ${time}` : stale ? `Connection lost · data from ${time}` : `Live · ${seconds} s ago`;
  return (
    <span className={`live ${stale ? "stale" : ""} ${paused ? "paused" : ""}`} title={text}>
      <span className="dot" aria-hidden />
      <span className="live-text">{text}</span>
      <button className="btn small ghost live-btn" onClick={() => setPaused(!paused)} aria-pressed={paused}
        aria-label={paused ? "Resume live updates" : "Pause live updates"} title={paused ? "Resume live updates" : "Pause live updates"}>
        {paused ? <Play size={16} aria-hidden /> : <Pause size={16} aria-hidden />}
        <span className="live-btn-text">{paused ? "Resume" : "Pause"}</span>
      </button>
    </span>
  );
}
