import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ClipboardList, FileText, Package, Wrench } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import { Card, Dialog, ErrorBox, Loading, PageSkeleton, SeverityBadge } from "../components/ui";
import { api } from "../lib/api";
import { inr, pct } from "../lib/format";
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

  if (queue.error) return <ErrorBox error={queue.error} />;
  if (!queue.data) return <PageSkeleton label="Loading the action list" />;
  const q = queue.data;
  const parts = partsToStock(q.maintenance_due);

  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Actions</h1><p>Everything that needs a decision, a repair or a look. Most urgent first.</p></div>
      </div>

      <Card title="Priority list" icon={<ClipboardList aria-hidden />} id="queue" sub="Priority = chance of failure × cost if it breaks down × how soon it could happen.">
        {q.risks.length === 0 ? <p className="muted">Nothing needs a decision right now.</p> : (
          <div className="table-wrap"><table>
            <thead><tr><th>#</th><th>Machine</th><th>Status</th><th>What is happening</th><th>Chance of failure (8 h)</th><th><span className="sr-only">Open</span></th></tr></thead>
            <tbody>
              {q.risks.map((r, i) => (
                <tr key={r.id}>
                  <td>{i + 1}</td><td><b>{r.id}</b></td><td><SeverityBadge level={r.severity} /></td>
                  <td>{r.headline}</td><td>{pct(r.p_fail_8h)}</td>
                  <td><Link className="btn small" to={`/machines/${r.id}`}>Decide<span className="sr-only"> for {r.id}</span></Link></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>

      <div className="grid grid-2">
        <OpenAlerts canAcknowledge={can("acknowledge_alert")} />
        <Card title="Incidents" icon={<FileText aria-hidden />} id="incidents" sub="Every critical risk or breakdown is logged with what the AI saw at that moment.">
          {incidents.data?.length === 0 && <p className="muted">No incidents yet.</p>}
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
            {incidents.data?.map((i) => (
              <li key={i.id} className="row between" style={{ borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
                <div><b>{i.title}</b><div className="small muted">{i.status === "open" ? "Open" : "Resolved"} · started {i.started_plant_time.replace("T", " ")}</div></div>
                <button className="btn small" onClick={() => setReportFor(i)}>Investigation</button>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid grid-2">
        <Card title="Maintenance plan (next 3 weeks)" icon={<Wrench aria-hidden />} id="plan"
          sub={`Next shift change in ${q.shift_change_in_h} h · Sunday maintenance window in ${q.window_in_h} h.`}>
          {q.maintenance_due.length === 0 ? <p className="muted">Nothing due.</p> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Machine</th><th>Job</th><th>When</th><th>Needed within</th></tr></thead>
              <tbody>{q.maintenance_due.map((m) => (
                <tr key={`${m.machine}-${m.component}`}>
                  <td>{m.machine}</td>
                  <td>{m.component_name}<div className="small muted">{m.inspect} · {m.repair_h} h</div></td>
                  <td>{m.emergency ? <span className="badge sev-critical">Now</span> : m.when}</td>
                  <td>{m.needed_within}</td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </Card>
        <Card title="Spare parts to have ready" icon={<Package aria-hidden />} id="parts" sub="So a planned swap never waits for a part.">
          {parts.length === 0 ? <p className="muted">No parts needed in the next 3 weeks.</p> : (
            <table>
              <thead><tr><th>Part</th><th>Quantity</th><th>First needed</th><th>Value</th></tr></thead>
              <tbody>{parts.map((p) => <tr key={p.name}><td>{p.name}</td><td>{p.qty}</td><td>{p.first}</td><td>{inr(p.value)}</td></tr>)}</tbody>
            </table>
          )}
        </Card>
      </div>
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
    <Card title="Open alerts" icon={<Bell aria-hidden />} id="alerts" sub="Grouped by machine. Alerts clear themselves when the problem goes away.">
      {alerts.isLoading && <Loading />}
      {alerts.data?.length === 0 && <p className="muted">No open alerts.</p>}
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }} className="stack">
        {shown.map((g) => (
          <li key={g.machine} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
            <div className="row between">
              <span className="row"><b>{g.machine}</b><SeverityBadge level={g.worst} /></span>
              <span className="small muted">{g.alerts.length} alert{g.alerts.length > 1 ? "s" : ""}</span>
            </div>
            <ul className="small" style={{ margin: "4px 0", paddingLeft: 18 }}>
              {g.alerts.map((a) => <li key={a.id}><b>{a.title}</b> <span className="muted">({a.plant_time.slice(11)})</span> {a.message}</li>)}
            </ul>
            <div className="row">
              <Link className="btn small" to={`/machines/${g.machine}`}>Open {g.machine}</Link>
              {canAcknowledge && (
                <button className="btn small" disabled={ack.isPending} onClick={() => ack.mutate(g.alerts.map((a) => a.id))}>
                  Acknowledge{g.alerts.length > 1 ? " all" : ""}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {groups.length > SHOWN_FIRST && (
        <button className="btn small" style={{ marginTop: 8 }} aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show the top 3 only" : `Show all ${groups.length} machines with alerts`}
        </button>
      )}
      {ack.error ? <ErrorBox error={ack.error} /> : null}
    </Card>
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
      {detail.isLoading && <Loading />}
      {report ? <div className="prose"><ReactMarkdown>{report}</ReactMarkdown></div> : (
        <p className="muted">No write-up yet. The AI writes it from the recorded evidence: what happened, when, what changed, root cause, impact, options, action taken and whether it worked.</p>
      )}
      {canWrite && (
        <button className="btn primary" onClick={() => write.mutate()} disabled={write.isPending}>
          {write.isPending ? "Writing…" : report ? "Rewrite with latest outcome" : "Write investigation"}
        </button>
      )}
      {write.error ? <ErrorBox error={write.error} /> : null}
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
