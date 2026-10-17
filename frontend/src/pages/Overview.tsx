import { useMutation } from "@tanstack/react-query";
import { ArrowRight, Factory, Gauge, Lightbulb, ListChecks, Sparkles, Wrench } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import { Bar, Card, ErrorBox, PageSkeleton, ReadAloud, SEVERITY, SeverityBadge, Stat, StateBadge, Term } from "../components/ui";
import { api } from "../lib/api";
import { num, pct } from "../lib/format";
import { useMachine, useOverview } from "../lib/queries";
import { useSession } from "../lib/session";
import type { MachineTile } from "../lib/types";

const HEALTH_LABELS: Record<string, string> = {
  machine: "Machine health", production: "Production", quality: "Quality", energy: "Energy", data: "Data quality",
};

export default function Overview() {
  const { data, error } = useOverview();
  if (error) return <ErrorBox error={error} />;
  if (!data) return <PageSkeleton label="Reading the factory" blocks={4} />;

  const k = data.kpis;
  const top = data.risks[0];
  const urgent = data.risks.filter((r) => ["critical", "high"].includes(r.severity));
  const summary = urgent.length
    ? `${urgent.length} machine${urgent.length > 1 ? "s need" : " needs"} action. Most urgent: ${top.id} - ${top.headline}.`
    : "All machines are within normal limits. Nothing needs action right now.";

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Factory health</h1>
          <p>Live view of all 24 machines. Plant time {data.plant_time.replace("T", " ")} · {data.shift}.</p>
        </div>
        <ReadAloud text={`${summary} Plant OEE this shift is ${Math.round(k.oee * 100)} percent.`} />
      </div>

      <div className={`banner sev-${urgent.length ? top.severity : "low"}`} role="status">
        <SeverityBadge level={urgent.length ? top.severity : "low"} />
        <div className="text" style={{ flex: 1 }}>
          <strong>{summary}</strong>
          {urgent.length > 0 && <p className="small muted" style={{ margin: 0 }}>Chance of failure in the next 8 hours: {pct(top.p_fail_8h)}.</p>}
        </div>
        {urgent.length > 0 && <Link className="btn primary" to={`/machines/${top.id}`}>Review {top.id} <ArrowRight size={18} aria-hidden /></Link>}
      </div>

      <HowToUse />
      <ShiftBriefing />

      <div className="card">
        <div className="grid grid-stats">
          <Stat label={<><Term name="oee" /> this shift</>} value={pct(k.oee)} hint={`${pct(k.availability)} avail. × ${pct(k.performance)} speed × ${pct(k.quality, 1)} quality`} />
          <Stat label="Machines running" value={`${k.running}/${k.machines}`} hint={k.down_now.length ? `Down: ${k.down_now.join(", ")}` : "None broken down"} />
          <Stat label="Breakdown time this shift" value={`${num(k.downtime_min)} min`} hint={`${num(k.maintenance_min)} min planned maintenance`} />
          <Stat label="Defect rate" value={pct(k.defect_rate, 1)} hint={`${num(k.good_parts)} good parts so far`} />
          <Stat label="Energy per good part" value={`${k.energy_kwh_per_part.toFixed(2)} kWh`} hint={`${num(k.energy_kwh)} kWh this shift`} />
          <Stat label="Active anomalies" value={k.anomalies} hint={`${data.open_alert_count} open alerts`} />
        </div>
      </div>

      <div className="grid grid-2">
        <Card title="What should I worry about first?" icon={<ListChecks aria-hidden />} id="risks"
          sub="Ranked by chance of failure × cost if it fails × how soon. The few that matter, not 50 alarms.">
          {data.risks.length === 0 && <p className="muted">Nothing needs attention.</p>}
          <ol style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
            {data.risks.slice(0, 3).map((r, i) => (
              <li key={r.id} className="row between" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 10 }}>
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div className="row"><b>{i + 1}. {r.id}</b><SeverityBadge level={r.severity} /></div>
                  <span className="small muted">{r.headline}</span>
                </div>
                <Link className="btn small" to={`/machines/${r.id}`} aria-label={`Review ${r.id}`}>Review</Link>
              </li>
            ))}
          </ol>
          {data.risks.length > 3 && (
            <Link to="/actions" className="btn small" style={{ marginTop: 10 }}>See all {data.risks.length} on the Actions page <ArrowRight size={16} aria-hidden /></Link>
          )}
        </Card>

        <Card title="Health scores" icon={<Gauge aria-hidden />} id="health" sub="0-100. Each score says how close that part of the plant is to its best.">
          <div className="stack">
            {Object.entries(data.health).map(([key, value]) => (
              <div key={key}>
                <div className="row between"><span>{HEALTH_LABELS[key]}</span><b className="mono">{value}</b></div>
                <Bar value={value / 100} label={HEALTH_LABELS[key]} color={value >= 80 ? "var(--muted)" : value >= 60 ? "var(--medium)" : "var(--critical)"} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Factory floor" icon={<Factory aria-hidden />} id="floor" sub="Select a machine to see what is happening and what to do. Border colour, icon and words all show the same status.">
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
                  return (
                    <Link key={m.id} to={`/machines/${m.id}`} className={`tile sev-${m.severity}`}
                      aria-label={`${m.id}, ${m.state}, ${SEVERITY[m.severity].label}. ${m.headline}`}>
                      <span className="id">{Icon && <Icon size={15} aria-hidden style={{ color: `var(--${m.severity === "low" ? "ok" : m.severity})` }} />}{m.id}</span>
                      <span className="small muted">{m.state === "running" ? (m.health_pct !== null ? `${m.health_pct}% health` : "running") : m.state}</span>
                      {m.speed_pct < 100 && m.state === "running" && <span className="small">Speed {m.speed_pct}%</span>}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-3 optional">
        <Card title="Recent events" id="events">
          {data.events.length === 0 && <p className="muted small">No events yet this shift.</p>}
          <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
            {data.events.slice(0, 7).map((e, i) => (
              <li key={i}><b>{e.time.slice(11)}</b> {e.machine_id}: {e.message}</li>
            ))}
          </ul>
        </Card>
        <Card title="Maintenance coming up" icon={<Wrench aria-hidden />} id="maint">
          {data.maintenance.due_soon.length === 0 && <p className="muted small">Nothing due in the next 3 weeks.</p>}
          <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
            {data.maintenance.due_soon.map((p, i) => (
              <li key={i}><b>{p.machine}</b> {p.component_name}: {p.when} (needed within {p.needed_within})</li>
            ))}
          </ul>
          <p className="small muted" style={{ marginTop: 8 }}>Next Sunday maintenance window in {data.window_in_h} h.</p>
        </Card>
        <Card title="Lines this shift" id="lines">
          <table>
            <thead><tr><th>Line</th><th>OEE</th><th>Weakest</th></tr></thead>
            <tbody>
              {data.lines.map((l) => (
                <tr key={l.id}><td>{l.id}</td><td>{pct(l.oee)}</td><td><Link to={`/machines/${l.worst_machine}`}>{l.worst_machine}</Link></td></tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <TechTip machines={data.risks} />
    </div>
  );
}

function TechTip({ machines }: { machines: MachineTile[] }) {
  const first = machines.find((m) => m.severity !== "low");
  const { data } = useMachine(first?.id);
  if (!data?.tech_tip) return null;
  return (
    <div className="card optional row" style={{ alignItems: "flex-start" }}>
      <Lightbulb aria-hidden style={{ color: "var(--brand)" }} />
      <div>
        <b>Technology worth a look: {data.tech_tip.title}</b>
        <p className="small muted" style={{ margin: 0 }}>{data.tech_tip.text} (Suggested because of {data.machine.id}.)</p>
      </div>
      <StateBadge state={data.state} />
    </div>
  );
}

function ShiftBriefing() {
  const { prefs } = useSession();
  const brief = useMutation({ mutationFn: () => api(`/api/copilot/briefing?language=${prefs.language}&simple=${prefs.simple}`, { method: "POST" }) });
  const r = brief.data as { text: string; source: string } | undefined;
  return (
    <div className="card row" style={{ alignItems: "flex-start" }}>
      <Sparkles aria-hidden style={{ color: "var(--brand)", flex: "none" }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row between">
          <b>Shift briefing</b>
          <div className="row">
            {r && <ReadAloud text={r.text} />}
            <button className="btn small" onClick={() => brief.mutate()} disabled={brief.isPending}>
              {brief.isPending ? "Writing…" : r ? "Refresh" : "Brief me"}
            </button>
          </div>
        </div>
        {!r && !brief.isPending && <p className="small muted" style={{ margin: 0 }}>The handover note for this shift, written by AI from live plant data, in your language.</p>}
        {r && <div className="small" aria-live="polite"><ReactMarkdown>{r.text}</ReactMarkdown>
          <span className="muted">{r.source === "gemini" ? "Written by Gemini from live plant data" : "Rule-based summary (add a Gemini key for a written briefing)"}</span></div>}
      </div>
    </div>
  );
}

const HOW_TO_KEY = "opex-how-to-seen";

/** Shown until the person dismisses it once. */
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
      /* private mode: it will show again next time */
    }
  };
  return (
    <div className="card how-to">
      <div className="row between"><b>How to use OpEx</b><button className="btn small" onClick={dismiss}>Got it</button></div>
      <ol className="small">
        <li><b>Look at the coloured banner.</b> It names the one machine that needs you most. Grey means normal.</li>
        <li><b>Open that machine.</b> Its page answers four questions in order: what we detected, why, what happens next, and what to do.</li>
        <li><b>Approve, reject or pick another option.</b> OpEx never changes a machine by itself, and checks later whether your decision worked.</li>
        <li>Stuck? <Link to="/copilot">Ask OpEx</Link> in your own words. The <Link to="/simulation">5-year simulation</Link> shows what this is worth.</li>
      </ol>
    </div>
  );
}
