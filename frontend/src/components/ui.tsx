import { AlertCircle, AlertTriangle, CheckCircle2, HelpCircle, Inbox, Loader2, OctagonAlert, OctagonX, Pause, Play, Sparkles, Square, Volume2, Wrench } from "lucide-react";
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

export function SeverityBadge({ level, short }: { level: string; short?: boolean }) {
  const s = SEVERITY[level] ?? SEVERITY.low;
  const Icon = s.icon;
  return (
    <span className={`badge sev-${level}`}>
      <Icon size={15} aria-hidden /> {short ? s.plain : <>{s.label} · {s.plain}</>}
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

/** A boxed block. Use it for things a person acts on; plain sections are calmer for everything else. */
export function Card({ title, sub, icon, actions, children, className = "", id }: {
  title?: ReactNode; sub?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section id={id} className={`card ${className}`} aria-labelledby={id && title ? `${id}-title` : undefined}>
      {(title || actions) && (
        <div className="row between" style={{ marginBottom: sub ? 2 : 12 }}>
          {title && <h2 id={id ? `${id}-title` : undefined}>{icon}{title}</h2>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {sub && <p className="sub">{sub}</p>}
      {children}
    </section>
  );
}

/** A heading and its content with no box around it. Most of a page should be sections, not cards. */
export function Section({ title, sub, icon, actions, children, className = "", id }: {
  title: ReactNode; sub?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string;
}) {
  return (
    <section id={id} className={`section ${className}`} aria-labelledby={id ? `${id}-title` : undefined}>
      <div className="section-head">
        <div>
          <h2 id={id ? `${id}-title` : undefined}>{icon}{title}</h2>
          {sub && <p className="sub">{sub}</p>}
        </div>
        {actions && <div className="row">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** Detail that is one click away. The summary says what is inside and how much. */
export function More({ label, hint, children, open, id }: { label: ReactNode; hint?: ReactNode; children: ReactNode; open?: boolean; id?: string }) {
  return (
    <details className="more" open={open} id={id}>
      <summary>{label}{hint && <span className="hint"> · {hint}</span>}</summary>
      <div className="body">{children}</div>
    </details>
  );
}

/** An empty state that says what would be here and what to do about it. */
export function EmptyState({ icon, title, hint, action }: { icon?: ReactNode; title: ReactNode; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty" role="status">
      <span className="icon" aria-hidden>{icon ?? <Inbox size={20} />}</span>
      <div>
        <b>{title}</b>
        {hint && <p>{hint}</p>}
        {action && <div style={{ marginTop: 10 }}>{action}</div>}
      </div>
    </div>
  );
}

/** Marks text that an AI wrote, so it is never mistaken for a measurement. */
export function AiTag({ source, children }: { source?: string; children?: ReactNode }) {
  const gemini = source === undefined || source === "gemini";
  return (
    <span className="ai-note" title={gemini ? "Written by Gemini from live plant data" : "Rule-based, without Gemini"}>
      <Sparkles size={14} aria-hidden /> {children ?? (gemini ? "Written by AI" : "Rule-based (no Gemini key)")}
    </span>
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

/** Say what is being done, not just "Loading". */
export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="loading">
      <Loader2 className="spin" size={20} aria-hidden /> {label}…
    </div>
  );
}

const FRIENDLY: Record<number, string> = {
  401: "Your session has ended. Sign in again to continue.",
  403: "Your role can't do that. A plant manager can change roles in Settings.",
  404: "We couldn't find that. It may have been removed.",
  429: "OpEx is busy right now. Give it a few seconds and try again.",
};

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const status = (error as { status?: number })?.status;
  const raw = error instanceof Error ? error.message : "";
  const message = (status && FRIENDLY[status]) || (raw && !/^Request failed/.test(raw) ? raw : "That didn't go through. Check the connection and try again.");
  return (
    <div role="alert" className="banner sev-critical">
      <OctagonAlert aria-hidden />
      <span className="text">{message}</span>
      {retry && <button className="btn small" onClick={retry}>Try again</button>}
    </div>
  );
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
      <p className="small muted" style={{ margin: 0 }}>{label}…</p>
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
