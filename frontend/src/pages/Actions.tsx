import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, FileText, Package, Wrench } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import { AiTag, Card, Dialog, EmptyState, ErrorBox, Loading, More, PageSkeleton, Section, SeverityBadge } from "../components/ui";
import { api } from "../lib/api";
import { hours, inr, pct, spanOf } from "../lib/format";
import { useRefresh } from "../lib/live";
import { useSession } from "../lib/session";
import type { Alert, MachineTile, MaintenanceJob, Severity } from "../lib/types";

type Queue = {
  risks: MachineTile[];
  maintenance_due: (MaintenanceJob & { machine: string })[];
  window_in_h: number;
  shift_change_in_h: number;
};
type Incident = { id: string; title: string; status: string; started_plant_time: string };

const RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const SHOWN_FIRST = 3; // alarm-flood rule: lead with the few that matter

export default function Actions() {
  const { can, prefs } = useSession();
  const queue = useQuery({ queryKey: ["actions"], queryFn: () => api<Queue>("/api/actions"), refetchInterval: useRefresh(8000) });
  const incidents = useQuery({ queryKey: ["incidents"], queryFn: () => api<Incident[]>("/api/incidents"), refetchInterval: useRefresh(15000) });
  const [reportFor, setReportFor] = useState<Incident | null>(null);

  if (queue.error) return <ErrorBox error={queue.error} retry={() => queue.refetch()} />;
  if (!queue.data) return <PageSkeleton label="Sorting what needs a decision" />;
  const q = queue.data;
  const parts = partsToStock(q.maintenance_due);
  const urgent = q.risks.filter((r) => ["critical", "high"].includes(r.severity)).length;

  return (
    <div className="stack-lg">
      <div className="page-head">
        <div>
          <p className="eyebrow">Shift change in {hours(q.shift_change_in_h)} · maintenance window in {spanOf(q.window_in_h)}</p>
          <h1>Actions</h1>
          <p>{urgent ? `${urgent} machine${urgent > 1 ? "s" : ""} need${urgent > 1 ? "" : "s"} a decision today.` : "Nothing urgent right now."} Everything that needs a decision, a repair or a look, most urgent first.</p>
        </div>
      </div>

      <Card title="Decide first" id="queue" sub="Priority = chance of failure × cost if it breaks down × how soon it could happen.">
        {q.risks.length === 0 ? (
          <EmptyState icon={<CheckCircle2 size={20} />} title="No decisions waiting" hint="No machine is drifting towards a failure. New risks appear here the moment OpEx sees them." />
        ) : (
          <div className="table-wrap"><table>
            <thead><tr><th>#</th><th>Machine</th><th>Status</th><th>What is happening</th><th>Chance of failure (8 h)</th><th><span className="sr-only">Open</span></th></tr></thead>
            <tbody>
              {q.risks.map((r, i) => (
                <tr key={r.id} className={i === 0 ? "highlight" : ""}>
                  <td>{i + 1}</td><td><b>{r.id}</b></td><td><SeverityBadge level={r.severity} short /></td>
                  <td>{r.headline}</td><td>{pct(r.p_fail_8h)}</td>
                  <td><Link className={`btn small ${i === 0 ? "primary" : ""}`} to={`/machines/${r.id}`}>Decide<span className="sr-only"> for {r.id}</span></Link></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>

      <div className="grid grid-2 start">
        <OpenAlerts canAcknowledge={can("acknowledge_alert")} />
        <Section title="Incidents" icon={<FileText size={20} aria-hidden />} id="incidents" sub="Every critical risk or breakdown is logged with what OpEx saw at that moment.">
          {incidents.data?.length === 0 && <EmptyState title="No incidents yet" hint="When a machine reaches critical risk or breaks down, the story is written here." />}
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
            {incidents.data?.map((i) => (
              <li key={i.id} className="row between" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 10 }}>
                <div><b>{i.title}</b><div className="small muted">{i.status === "open" ? "Open" : "Resolved"} · started {i.started_plant_time.replace("T", " ").slice(0, 16)}</div></div>
                <button className="btn small" onClick={() => setReportFor(i)}>Read the investigation</button>
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <More label="Maintenance plan and spare parts" hint={`${q.maintenance_due.length} job${q.maintenance_due.length === 1 ? "" : "s"} in the next 3 weeks · ${parts.length} part${parts.length === 1 ? "" : "s"} to have ready`} id="plan-more" open>
        <div className="grid grid-2 start" style={{ marginTop: 8 }}>
          <Section title="Maintenance plan" icon={<Wrench size={20} aria-hidden />} id="plan" sub={`Next 3 weeks. Emergencies are marked; the rest can wait for the Sunday window in ${spanOf(q.window_in_h)}.`}>
            {q.maintenance_due.length === 0 ? <EmptyState title="Nothing due" hint="No component needs a planned swap in the next 3 weeks." /> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Machine</th><th>Job</th><th>When</th><th>Needed within</th></tr></thead>
                <tbody>{q.maintenance_due.map((m) => (
                  <tr key={`${m.machine}-${m.component}`}>
                    <td><Link to={`/machines/${m.machine}`}>{m.machine}</Link></td>
                    <td>{m.component_name}<div className="small muted">{m.inspect} · {m.repair_h} h</div></td>
                    <td>{m.emergency ? <span className="badge sev-critical">Now</span> : m.when}</td>
                    <td>{m.needed_within}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </Section>
          <Section title="Spare parts to have ready" icon={<Package size={20} aria-hidden />} id="parts" sub="So a planned swap never waits for a part.">
            {parts.length === 0 ? <EmptyState title="No parts needed" hint="Nothing in the plan needs a spare in the next 3 weeks." /> : (
              <table>
                <thead><tr><th>Part</th><th>Qty</th><th>First needed</th><th>Value</th></tr></thead>
                <tbody>{parts.map((p) => <tr key={p.name}><td>{p.name}</td><td>{p.qty}</td><td>{p.first}</td><td>{inr(p.value)}</td></tr>)}</tbody>
              </table>
            )}
          </Section>
        </div>
      </More>
      {reportFor && <Investigation incident={reportFor} onClose={() => setReportFor(null)} canWrite={can("write_report")} language={prefs.language} />}
    </div>
  );
}

/** One row per machine (its alerts grouped), worst first; the top 3 shown, the rest on request. */
function OpenAlerts({ canAcknowledge }: { canAcknowledge: boolean }) {
  const queryClient = useQueryClient();
  const [showAll, setShowAll] = useState(false);
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api<Alert[]>("/api/alerts"), refetchInterval: useRefresh(8000) });
  const ack = useMutation({
    mutationFn: (ids: string[]) => Promise.all(ids.map((id) => api(`/api/alerts/${id}/acknowledge`, { method: "POST" }))),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  const groups = groupByMachine(alerts.data ?? []);
  const shown = showAll ? groups : groups.slice(0, SHOWN_FIRST);
  return (
    <Section title="Open alerts" icon={<Bell size={20} aria-hidden />} id="alerts" sub="Grouped by machine. Alerts clear themselves when the problem goes away.">
      {alerts.isLoading && <Loading label="Collecting alerts" />}
      {alerts.data?.length === 0 && <EmptyState icon={<CheckCircle2 size={20} />} title="No open alerts" hint="All quiet. You will see a note in the corner the moment a critical one arrives." />}
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
        {shown.map((g) => (
          <li key={g.machine} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 10 }}>
            <div className="row between">
              <span className="row" style={{ gap: 8 }}><b>{g.machine}</b><SeverityBadge level={g.worst} short /></span>
              <span className="small muted">{g.alerts.length} alert{g.alerts.length > 1 ? "s" : ""}</span>
            </div>
            <ul className="small" style={{ margin: "4px 0" }}>
              {g.alerts.map((a) => <li key={a.id}><b>{a.title}</b> <span className="muted">({a.plant_time.slice(11, 16)})</span> {a.message}</li>)}
            </ul>
            <div className="row">
              <Link className="btn small" to={`/machines/${g.machine}`}>Open {g.machine}</Link>
              {canAcknowledge && (
                <button className="btn small ghost" disabled={ack.isPending} onClick={() => ack.mutate(g.alerts.map((a) => a.id))}>
                  {ack.isPending ? "Saving…" : `Acknowledge${g.alerts.length > 1 ? " all" : ""}`}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {groups.length > SHOWN_FIRST && (
        <button className="btn small ghost" style={{ marginTop: 8 }} aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show the top 3 only" : `Show all ${groups.length} machines with alerts`}
        </button>
      )}
      {ack.error ? <ErrorBox error={ack.error} /> : null}
    </Section>
  );
}

function Investigation({ incident, onClose, canWrite, language }: { incident: Incident; onClose: () => void; canWrite: boolean; language: string }) {
  const detail = useQuery({ queryKey: ["incident", incident.id], queryFn: () => api<{ report: string | null }>(`/api/incidents/${incident.id}`) });
  const write = useMutation({
    mutationFn: () => api(`/api/incidents/${incident.id}/report?language=${language}`, { method: "POST" }),
    onSuccess: () => detail.refetch(),
  });
  const report = detail.data?.report;
  return (
    <Dialog open onClose={onClose} title={`Investigation: ${incident.title}`}>
      {detail.isLoading && <Loading label="Opening the incident file" />}
      {report ? <><div className="prose"><ReactMarkdown>{report}</ReactMarkdown></div><p><AiTag /></p></> : (
        !detail.isLoading && <EmptyState title="No write-up yet" hint="OpEx writes it from the recorded evidence: what happened, when, what changed, the root cause, the impact, the options, the action taken and whether it worked." />
      )}
      {canWrite && (
        <button className="btn primary" style={{ marginTop: 12 }} onClick={() => write.mutate()} disabled={write.isPending}>
          {write.isPending ? "Writing from the evidence…" : report ? "Rewrite with the latest outcome" : "Write the investigation"}
        </button>
      )}
      {write.error ? <ErrorBox error={write.error} retry={() => write.mutate()} /> : null}
    </Dialog>
  );
}

function groupByMachine(alerts: Alert[]) {
  const groups = new Map<string, { machine: string; worst: Severity; alerts: Alert[] }>();
  for (const a of alerts) {
    const g = groups.get(a.machine_id) ?? { machine: a.machine_id, worst: a.severity, alerts: [] };
    g.alerts.push(a);
    if (RANK[a.severity] < RANK[g.worst]) g.worst = a.severity;
    groups.set(a.machine_id, g);
  }
  return [...groups.values()].sort((x, y) => RANK[x.worst] - RANK[y.worst] || y.alerts.length - x.alerts.length);
}

function partsToStock(plan: Queue["maintenance_due"]) {
  const byName = new Map<string, { name: string; qty: number; first: string; value: number }>();
  for (const job of plan) {
    for (const part of job.parts) {
      const entry = byName.get(part) ?? { name: part, qty: 0, first: job.needed_within, value: 0 };
      entry.qty += 1;
      entry.value += job.part_cost_inr / job.parts.length; // the job's part cost is shared by its parts
      byName.set(part, entry);
    }
  }
  return [...byName.values()];
}
