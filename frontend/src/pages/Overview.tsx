import { useMutation } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Lightbulb, Sparkles, Wrench } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import { AiTag, Bar, Card, EmptyState, ErrorBox, More, PageSkeleton, ReadAloud, SEVERITY, Section, SeverityBadge, Stat, Term } from "../components/ui";
import { api } from "../lib/api";
import { num, pct, spanOf } from "../lib/format";
import { useMachine, useOverview } from "../lib/queries";
import { useSession } from "../lib/session";
import type { MachineTile } from "../lib/types";

const HEALTH_LABELS: Record<string, string> = {
  machine: "Machine health", production: "Production", quality: "Quality", energy: "Energy", data: "Data quality",
};

export default function Overview() {
  const { data, error, refetch } = useOverview();
  const { user } = useSession();
  if (error) return <ErrorBox error={error} retry={() => refetch()} />;
  if (!data) return <PageSkeleton label="Reading the floor" blocks={4} />;

  const k = data.kpis;
  const top = data.risks[0];
  const urgent = data.risks.filter((r) => ["critical", "high"].includes(r.severity));
  const firstName = user?.full_name?.split(" ")[0];
  const headline = urgent.length
    ? `${urgent.length} machine${urgent.length > 1 ? "s need" : " needs"} a decision. Start with ${top.id}.`
    : "Every machine is inside its normal range.";
  const detail = urgent.length ? top.headline : "Nothing needs a decision right now.";
  const summary = `${headline} ${detail}${/[.!?]$/.test(detail) ? "" : "."}`;

  return (
    <div className="stack-lg">
      <div className="page-head">
        <div>
          <p className="eyebrow">{data.shift} · plant time {data.plant_time.slice(11, 16)}</p>
          <h1>{firstName ? `${greeting(data.plant_time)}, ${firstName}` : "Factory health"}</h1>
          <p>All 24 machines on 4 lines, live. Start with the one thing below.</p>
        </div>
        <ReadAloud text={`${summary} Plant OEE this shift is ${Math.round(k.oee * 100)} percent.`} />
      </div>

      {/* The one thing: what needs you most, and the single button that takes you there. */}
      <section className="hero" role="status" style={{ "--hero-color": `var(--${urgent.length ? top.severity : "ok"})` } as React.CSSProperties} aria-label="What needs attention">
        <div>
          <SeverityBadge level={urgent.length ? top.severity : "low"} />
          <h2>{headline}</h2>
          <p className="measure" style={{ margin: "0 0 8px" }}>{detail}</p>
          {urgent.length > 0 ? (
            <div className="facts">
              <span>Chance of failure in 8 h <b>{pct(top.p_fail_8h)}</b></span>
              {top.health_pct !== null && <span>Health <b>{top.health_pct}%</b></span>}
              {urgent.length > 1 && <span>Also waiting: <b>{urgent.slice(1, 4).map((r) => r.id).join(", ")}</b></span>}
            </div>
          ) : (
            <div className="facts"><span>Plant OEE <b>{pct(k.oee)}</b></span><span>Running <b>{k.running} of {k.machines}</b></span></div>
          )}
        </div>
        {urgent.length > 0
          ? <Link className="btn primary big" to={`/machines/${top.id}`}>Review {top.id} <ArrowRight size={20} aria-hidden /></Link>
          : <Link className="btn" to="/actions">See the full list</Link>}
      </section>

      <HowToUse />

      <div className="kpi-strip" aria-label="This shift in numbers">
        <Stat label={<><Term name="oee" /> this shift</>} value={pct(k.oee)} hint={`${pct(k.availability)} available × ${pct(k.performance)} speed × ${pct(k.quality, 1)} quality`} />
        <Stat label="Machines running" value={`${k.running} of ${k.machines}`} hint={k.down_now.length ? `Down: ${k.down_now.join(", ")}` : "None broken down"} />
        <Stat label="Breakdown time" value={`${num(k.downtime_min)} min`} hint={`${num(k.maintenance_min)} min planned maintenance`} />
        <Stat label="Defect rate" value={pct(k.defect_rate, 1)} hint={`${num(k.good_parts)} good parts so far`} />
        <Stat label="Energy per good part" value={`${k.energy_kwh_per_part.toFixed(2)} kWh`} hint={`${num(k.energy_kwh)} kWh this shift`} />
        <Stat label="Signals out of range" value={k.anomalies} hint={`${data.open_alert_count} open alert${data.open_alert_count === 1 ? "" : "s"}`} />
      </div>

      <Section title="Factory floor" id="floor" sub="Grey is normal. A coloured border, an icon and a word all say the same thing when something is off. Select a machine to see what is happening and what to do.">
        <div className="floor">
          {data.lines.map((line) => (
            <div className="floor-line" key={line.id}>
              <div>
                <b>{line.name}</b>
                <div className="small muted">OEE {pct(line.oee)} · {num(line.good_parts)} good parts</div>
              </div>
              <div className="machines">
                {data.machines.filter((m) => m.line_id === line.id).map((m) => {
                  const Icon = SEVERITY[m.severity]?.icon;
                  const off = m.severity !== "low";
                  return (
                    <Link key={m.id} to={`/machines/${m.id}`} className={`tile sev-${m.severity}`}
                      aria-label={`${m.id}, ${m.state}, ${SEVERITY[m.severity].label}. ${m.headline}`}>
                      <span className="id">{off && Icon && <Icon size={15} aria-hidden style={{ color: `var(--${m.severity})` }} />}{m.id}</span>
                      <span className="small muted">{m.state === "running" ? (m.health_pct !== null ? `${m.health_pct}% health` : "running") : m.state}</span>
                      {m.speed_pct < 100 && m.state === "running" && <span className="small">Speed {m.speed_pct}%</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <div className="grid grid-2 start">
        <Card title="What should I worry about first?" id="risks" sub="Ranked by chance of failure × cost if it fails × how soon. A short list, not 50 alarms.">
          {data.risks.length === 0 && <EmptyState icon={<CheckCircle2 size={20} />} title="Nothing to worry about" hint="No machine is drifting towards a failure. OpEx keeps watching and will tell you first." />}
          <ol style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
            {data.risks.slice(0, 3).map((r, i) => (
              <li key={r.id} className="row between" style={{ borderBottom: i < Math.min(3, data.risks.length) - 1 ? "1px solid var(--border)" : undefined, paddingBottom: 12 }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div className="row" style={{ gap: 8 }}><b>{i + 1}. {r.id}</b><SeverityBadge level={r.severity} short /></div>
                  <span className="small muted">{r.headline}</span>
                </div>
                <Link className={`btn small ${i === 0 ? "primary" : ""}`} to={`/machines/${r.id}`} aria-label={`Review ${r.id}`}>Review</Link>
              </li>
            ))}
          </ol>
          {data.risks.length > 3 && (
            <Link to="/actions" className="btn small ghost" style={{ marginTop: 10 }}>All {data.risks.length} on the Actions page <ArrowRight size={16} aria-hidden /></Link>
          )}
        </Card>
        <ShiftBriefing />
      </div>

      <More label="More about this shift" hint="health scores, recent events, maintenance coming up, lines" id="more">
        <div className="grid grid-2 start" style={{ marginTop: 8 }}>
          <Section title="Health scores" id="health" sub="0 to 100. How close each part of the plant is to its best.">
            <div className="stack" style={{ gap: 10 }}>
              {Object.entries(data.health).map(([key, value]) => (
                <div key={key}>
                  <div className="row between"><span>{HEALTH_LABELS[key]}</span><b className="mono">{value}</b></div>
                  <Bar value={value / 100} label={HEALTH_LABELS[key]} color={value >= 80 ? "var(--muted)" : value >= 60 ? "var(--medium)" : "var(--critical)"} />
                </div>
              ))}
            </div>
          </Section>
          <Section title="Maintenance coming up" icon={<Wrench size={20} aria-hidden />} id="maint" sub={`Next Sunday maintenance window in ${spanOf(data.window_in_h)}.`}>
            {data.maintenance.due_soon.length === 0 && <p className="muted small">Nothing due in the next 3 weeks.</p>}
            <ul className="small" style={{ margin: 0 }}>
              {data.maintenance.due_soon.map((p, i) => (
                <li key={i}><b>{p.machine}</b> {p.component_name}: {p.when} (needed within {p.needed_within})</li>
              ))}
            </ul>
          </Section>
          <Section title="Recent events" id="events">
            {data.events.length === 0 && <p className="muted small">Quiet so far this shift.</p>}
            <ul className="small" style={{ margin: 0 }}>
              {data.events.slice(0, 7).map((e, i) => (
                <li key={i}><b className="mono">{e.time.slice(11, 16)}</b> {e.machine_id}: {e.message}</li>
              ))}
            </ul>
          </Section>
          <Section title="Lines this shift" id="lines">
            <table>
              <thead><tr><th>Line</th><th>OEE</th><th>Weakest machine</th></tr></thead>
              <tbody>
                {data.lines.map((l) => (
                  <tr key={l.id}><td>{l.id}</td><td>{pct(l.oee)}</td><td><Link to={`/machines/${l.worst_machine}`}>{l.worst_machine}</Link></td></tr>
                ))}
              </tbody>
            </table>
          </Section>
        </div>
        <TechTip machines={data.risks} />
      </More>
    </div>
  );
}

function greeting(plantTime: string): string {
  const hour = Number(plantTime.slice(11, 13));
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function TechTip({ machines }: { machines: MachineTile[] }) {
  const first = machines.find((m) => m.severity !== "low");
  const { data } = useMachine(first?.id);
  if (!data?.tech_tip) return null;
  return (
    <div className="card quiet tight row start optional" style={{ marginTop: 16 }}>
      <Lightbulb aria-hidden style={{ color: "var(--warm)", flex: "none" }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <b>Worth a look: {data.tech_tip.title}</b>
        <p className="small muted" style={{ margin: 0 }}>{data.tech_tip.text} Suggested because of {data.machine.id}.</p>
      </div>
    </div>
  );
}

function ShiftBriefing() {
  const { prefs } = useSession();
  const brief = useMutation({ mutationFn: () => api(`/api/copilot/briefing?language=${prefs.language}&simple=${prefs.simple}`, { method: "POST" }) });
  const r = brief.data as { text: string; source: string } | undefined;
  return (
    <Card title="Shift briefing" icon={<Sparkles size={20} aria-hidden style={{ color: "var(--ai)" }} />} id="briefing"
      actions={<>{r && <ReadAloud text={r.text} />}
        <button className={`btn small ${r ? "" : "primary"}`} onClick={() => brief.mutate()} disabled={brief.isPending}>
          {brief.isPending ? "Writing…" : r ? "Refresh" : "Write it for me"}
        </button></>}>
      {!r && !brief.isPending && (
        <p className="small muted measure" style={{ margin: 0 }}>
          The handover note for this shift, written from live plant data in your language. Takes a few seconds.
        </p>
      )}
      {brief.isPending && <p className="small muted" role="status" style={{ margin: 0 }}>Reading 24 machines and today's events…</p>}
      {brief.error ? <ErrorBox error={brief.error} retry={() => brief.mutate()} /> : null}
      {r && (
        <div className="small fade-in" aria-live="polite">
          <div className="prose"><ReactMarkdown>{r.text}</ReactMarkdown></div>
          <AiTag source={r.source} />
        </div>
      )}
    </Card>
  );
}

const HOW_TO_KEY = "opex-how-to-seen";

function HowToUse() {
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(HOW_TO_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (hidden) return null;
  const dismiss = () => {
    setHidden(true);
    try {
      localStorage.setItem(HOW_TO_KEY, "1");
    } catch {
    }
  };
  return (
    <div className="card quiet how-to">
      <div className="row between"><b>New here? Three things to know</b><button className="btn small" onClick={dismiss}>Got it</button></div>
      <ol className="small">
        <li><b>The box above names the one machine that needs you most.</b> Green means all is well.</li>
        <li><b>Open it.</b> Its page answers four questions in order: what we noticed, why, what happens next, and what to do.</li>
        <li><b>You decide.</b> OpEx never changes a machine by itself, and later checks whether your decision worked.</li>
      </ol>
      <p className="small muted" style={{ margin: "6px 0 0" }}>Stuck? <Link to="/copilot">Ask OpEx</Link> in your own words.</p>
    </div>
  );
}
