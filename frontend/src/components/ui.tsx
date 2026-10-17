import { AlertCircle, AlertTriangle, CheckCircle2, HelpCircle, Loader2, OctagonAlert, OctagonX, Pause, Play, Square, Volume2, Wrench } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { canSpeak, speak } from "../lib/speech";
import { useSession } from "../lib/session";
import { GLOSSARY } from "../lib/words";

export const SEVERITY: Record<string, { label: string; plain: string; icon: typeof AlertCircle }> = {
  critical: { label: "Critical", plain: "Act now", icon: OctagonAlert },
  high: { label: "High", plain: "Act today", icon: AlertTriangle },
  medium: { label: "Medium", plain: "Plan it", icon: AlertCircle },
  low: { label: "OK", plain: "No action", icon: CheckCircle2 },
};

export function SeverityBadge({ level }: { level: string }) {
  const s = SEVERITY[level] ?? SEVERITY.low;
  const Icon = s.icon;
  return (
    <span className={`badge sev-${level}`}>
      <Icon size={15} aria-hidden /> {s.label} · {s.plain}
    </span>
  );
}

const STATES: Record<string, { label: string; icon: typeof Play; cls: string }> = {
  running: { label: "Running", icon: Play, cls: "sev-ok" },
  idle: { label: "Idle", icon: Pause, cls: "sev-medium" },
  maintenance: { label: "In maintenance", icon: Wrench, cls: "sev-info" },
  breakdown: { label: "Broken down", icon: OctagonX, cls: "sev-critical" },
  stopped: { label: "Stopped", icon: Square, cls: "sev-info" },
};

export function StateBadge({ state }: { state: string }) {
  const s = STATES[state] ?? STATES.running;
  const Icon = s.icon;
  return <span className={`badge ${s.cls}`}><Icon size={14} aria-hidden /> {s.label}</span>;
}

export function Card({ title, sub, icon, actions, children, className = "", id }: {
  title?: ReactNode; sub?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section id={id} className={`card ${className}`} aria-labelledby={id ? `${id}-title` : undefined}>
      {(title || actions) && (
        <div className="row between" style={{ marginBottom: sub ? 2 : 10 }}>
          {title && <h2 id={id ? `${id}-title` : undefined}>{icon}{title}</h2>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {sub && <p className="sub">{sub}</p>}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, big }: { label: ReactNode; value: ReactNode; hint?: ReactNode; big?: boolean }) {
  return (
    <div className={`stat ${big ? "big" : ""}`}>
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="row muted" style={{ padding: 20 }}>
      <Loader2 className="spin" size={20} aria-hidden /> {label}…
    </div>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return <div role="alert" className="banner sev-critical"><OctagonAlert aria-hidden /><span className="text">{message}</span></div>;
}

export function ReadAloud({ text, label = "Read aloud" }: { text: string; label?: string }) {
  const { prefs } = useSession();
  if (!canSpeak()) return null;
  return (
    <button className="btn small ghost" onClick={() => speak(text, prefs.language, prefs.voiceRate)} aria-label={label} title={label}>
      <Volume2 size={18} aria-hidden /> <span className="small">Listen</span>
    </button>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Dialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} aria-labelledby={titleId}>
      <div className="dialog-body">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h2 id={titleId}>{title}</h2>
          <button className="btn small" onClick={onClose}>Close</button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

export function Bar({ value, label, color }: { value: number; label: string; color?: string }) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <div className="bar" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(clamped * 100)} aria-label={label}>
      <span style={{ width: `${clamped * 100}%`, background: color }} />
    </div>
  );
}

/** Placeholder blocks shaped like the page that is loading, so the layout doesn't jump. */
export function PageSkeleton({ label, blocks = 3 }: { label: string; blocks?: number }) {
  return (
    <div className="stack" role="status" aria-label={`${label}…`}>
      <div className="skeleton" style={{ minHeight: 56, maxWidth: 420 }} />
      {Array.from({ length: blocks }, (_, i) => <div key={i} className="skeleton" />)}
    </div>
  );
}

/** A word from the glossary with a "?" that explains it in plain language. */
export function Term({ name }: { name: keyof typeof GLOSSARY }) {
  const { prefs } = useSession();
  const [open, setOpen] = useState(false);
  const id = useId();
  const entry = GLOSSARY[name];
  return (
    <span className="term">
      {prefs.simple ? entry.simple : entry.term}
      <button type="button" className="term-btn" aria-expanded={open} aria-controls={id}
        aria-label={`What does ${entry.term} mean?`} onClick={() => setOpen(!open)}>
        <HelpCircle size={15} aria-hidden />
      </button>
      {open && <span id={id} role="note" className="term-note">{entry.explain}</span>}
    </span>
  );
}

/** Where a reading sits compared with its normal band (recognition instead of remembering numbers). */
export function RangeBar({ value, low, high, label }: { value: number; low: number; high: number; label: string }) {
  const span = high - low || 1;
  const min = Math.min(low - span * 0.5, value - span * 0.15);
  const max = Math.max(high + span * 0.5, value + span * 0.15);
  const at = (v: number) => `${((v - min) / (max - min)) * 100}%`;
  const outside = value < low || value > high;
  return (
    <div className="range" role="img" aria-label={`${label}: ${value.toFixed(2)}, normal ${low.toFixed(2)} to ${high.toFixed(2)}`}>
      <span className="band" style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})` }} />
      <span className={`marker ${outside ? "out" : ""}`} style={{ left: at(value) }} />
    </div>
  );
}

/** Second step for actions that stop or slow a machine: say exactly what will happen first. */
export function ConfirmDialog({ open, title, children, confirmLabel, busy, onConfirm, onCancel }: {
  open: boolean; title: string; children: ReactNode; confirmLabel: string; busy?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Dialog open={open} onClose={onCancel} title={title}>
      {children}
      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn primary" onClick={onConfirm} disabled={busy}>{busy ? "Saving…" : confirmLabel}</button>
        <button className="btn" onClick={onCancel}>Go back</button>
      </div>
    </Dialog>
  );
}
