import { Bell, BookOpenCheck, ChevronDown, Factory, LineChart, ListChecks, LogOut, Menu, MessageCircle, Pause, Play, Settings as SettingsIcon, Type, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useLive } from "../lib/live";
import { useOverview } from "../lib/queries";
import { useSession } from "../lib/session";
import type { Alert } from "../lib/types";
import { AccessibilityPanel } from "./AccessibilityPanel";

// Shallow navigation, grouped by what a person is doing: running today's shift, or understanding the system.
const NAV: { group: string; items: { to: string; label: string; icon: typeof Factory }[] }[] = [
  { group: "Today", items: [
    { to: "/", label: "Overview", icon: Factory },
    { to: "/actions", label: "Actions", icon: ListChecks },
    { to: "/copilot", label: "Ask OpEx", icon: MessageCircle },
  ] },
  { group: "Understand", items: [
    { to: "/simulation", label: "5-year simulation", icon: LineChart },
    { to: "/learning", label: "Learning log", icon: BookOpenCheck },
  ] },
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
    // Toasts stay until dismissed (no time limit to read them); at most 3 on screen, one per machine and title.
    if (fresh.length) {
      setToasts((t) => {
        const merged = [...t];
        for (const a of fresh) if (!merged.some((x) => x.machine_id === a.machine_id && x.title === a.title)) merged.push(a);
        return merged.slice(-3);
      });
    }
  }, [data]);

  const riskCount = data?.risks.filter((r) => ["critical", "high"].includes(r.severity)).length ?? 0;
  const dismiss = (id: string) => setToasts((all) => all.filter((x) => x.id !== id));

  return (
    <div className={`shell ${prefs.focus ? "focus-mode" : ""}`}>
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="topbar">
        <button className="btn icon-btn ghost menu-button" aria-label={menuOpen ? "Close menu" : "Open menu"} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? <X aria-hidden /> : <Menu aria-hidden />}
        </button>
        <Link to="/" className="brand" aria-label="OpEx home">
          <img src="/opex-mark.png" alt="" />
          <strong>OpEx</strong>
        </Link>
        <span className="spacer" />
        <LiveStatus updatedAt={overview.dataUpdatedAt} failed={overview.isError} />
        {data && (
          <div className="plant" aria-label={`Plant time ${data.plant_time.replace("T", " ")}, ${data.shift}`}>
            <b>{data.plant_time.slice(11, 16)} · {data.shift}</b>
            <span>Sahyadri Precision · Unit 2 (demo)</span>
          </div>
        )}
        <Link to="/actions" className="btn icon-btn ghost" aria-label={`${data?.open_alert_count ?? 0} open alerts`} title="Open alerts">
          <Bell aria-hidden />
          {!!data?.open_alert_count && <span className="badge sev-high">{data.open_alert_count}</span>}
        </Link>
        <button className="btn icon-btn ghost a11y-btn" onClick={() => setA11yOpen(true)} aria-label="Display and reading settings" title="Display and reading">
          <Type aria-hidden />
        </button>
        <UserMenu name={user?.full_name ?? ""} role={user?.role_label ?? ""} onDisplay={() => setA11yOpen(true)} onSignOut={signOut} />
      </header>

      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <nav aria-label="Main">
          {NAV.map((g) => (
            <div key={g.group} style={{ display: "contents" }}>
              <div className="nav-group" aria-hidden>{g.group}</div>
              {g.items.map(({ to, label, icon: Icon }) => (
                <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                  <Icon size={20} aria-hidden /> {label}
                  {to === "/actions" && riskCount > 0 && <span className="badge sev-critical count" aria-label={`${riskCount} urgent`}>{riskCount}</span>}
                </NavLink>
              ))}
            </div>
          ))}
          <div className="nav-group" aria-hidden>You</div>
          <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><SettingsIcon size={20} aria-hidden /> Settings</NavLink>
          <button className="nav-link" style={{ border: 0, background: "none", font: "inherit", cursor: "pointer", width: "100%" }} onClick={signOut}><LogOut size={20} aria-hidden /> Sign out</button>
        </nav>
      </aside>

      <main id="main" className="main" tabIndex={-1}>{children}</main>

      <div className="toasts" aria-live="assertive" role="status">
        {toasts.map((t) => (
          <div key={t.id} className="toast" style={{ "--toast-color": `var(--${t.severity})` } as React.CSSProperties}>
            <div className="row between">
              <strong className={`badge sev-${t.severity}`}>{t.severity === "critical" ? "Critical · act now" : "High · act today"}</strong>
              <button className="btn icon-btn ghost" style={{ minHeight: 36, minWidth: 36 }} aria-label="Dismiss" onClick={() => dismiss(t.id)}><X size={18} aria-hidden /></button>
            </div>
            <p style={{ margin: "6px 0 2px", fontWeight: 700 }}>{t.title}</p>
            <p className="small muted" style={{ margin: 0 }}>{t.message}</p>
            <Link className="btn small primary" style={{ marginTop: 10 }} to={`/machines/${t.machine_id}`} onClick={() => dismiss(t.id)}>Open {t.machine_id}</Link>
          </div>
        ))}
      </div>
      <AccessibilityPanel open={a11yOpen} onClose={() => setA11yOpen(false)} />
    </div>
  );
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
}

/** Who is signed in, and the two things people look for under their name. */
function UserMenu({ name, role, onDisplay, onSignOut }: { name: string; role: string; onDisplay: () => void; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);
  return (
    <div className="menu" ref={ref}>
      <button className="btn ghost" style={{ padding: "6px 8px", gap: 6 }} aria-haspopup="menu" aria-expanded={open} aria-label={`Account: ${name}, ${role}`} onClick={() => setOpen(!open)}>
        <span aria-hidden style={{ width: 32, height: 32, borderRadius: "50%", background: "var(--brand-soft)", color: "var(--brand-strong)", display: "grid", placeItems: "center", fontWeight: 700, fontSize: "0.85rem" }}>{initials(name)}</span>
        <ChevronDown size={16} aria-hidden />
      </button>
      {open && (
        <div className="menu-panel" role="menu">
          <div className="who"><b>{name}</b>{role}</div>
          <button className="menu-item" role="menuitem" onClick={() => { setOpen(false); onDisplay(); }}><Type size={18} aria-hidden /> Display and reading</button>
          <Link className="menu-item" role="menuitem" to="/settings" onClick={() => setOpen(false)}><SettingsIcon size={18} aria-hidden /> Settings</Link>
          <button className="menu-item" role="menuitem" onClick={onSignOut}><LogOut size={18} aria-hidden /> Sign out</button>
        </div>
      )}
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
