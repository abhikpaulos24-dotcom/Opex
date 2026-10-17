import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Scale } from "lucide-react";
import { Card, ErrorBox, PageSkeleton, Stat } from "../components/ui";
import { api } from "../lib/api";
import { useRefresh } from "../lib/live";
import { pct, share, titleCase } from "../lib/format";

const CAUSE_NAMES: Record<string, string> = {
  bearing_degradation: "Bearing degradation", lubrication_starvation: "Lubrication starvation", drive_slip: "Drive belt slip",
  coolant_failure: "Coolant problem", power_module: "Power module fault", tool_overstrain: "Tool overstrain",
  idle_waste: "Idle energy waste", sensor_drift: "Sensor drift",
};

export default function Learning() {
  const { data, error } = useQuery({ queryKey: ["decisions"], queryFn: () => api("/api/decisions"), refetchInterval: useRefresh(15000) });
  if (error) return <ErrorBox error={error} />;
  if (!data) return <PageSkeleton label="Loading the learning log" />;
  const live = data.decisions.filter((d: any) => d.source === "live");
  const evaluated = data.decisions.filter((d: any) => d.outcome_status !== "pending");
  const successes = evaluated.filter((d: any) => d.outcome_status === "success").length;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Learning log</h1>
          <p>Prediction → recommendation → human decision → what actually happened. Every outcome updates how much OpEx trusts each action next time.</p>
        </div>
      </div>
      <div className="card">
        <div className="grid grid-stats">
          <Stat label="Decisions recorded" value={data.decisions.length} hint={`${live.length} live, the rest from the 90-day pilot (demo data)`} />
          <Stat label="Checked outcomes" value={evaluated.length} hint={`${share(successes, evaluated.length)} worked`} />
          <Stat label="Followed the AI" value={share(data.agreement.followed_ai, live.length)} hint="live decisions that approved the recommendation" />
          <Stat label="Waiting for outcome" value={data.totals.pending ?? 0} hint="checked 2 plant hours after the decision" />
        </div>
      </div>

      <Card title="What has worked here" icon={<Scale aria-hidden />} id="learned"
        sub="Success counts per problem and action. The decision engine uses these (with a cautious prior) to rank options.">
        <div className="table-wrap"><table>
          <thead><tr><th>Problem</th><th>Action</th><th>Worked</th><th>Success rate</th></tr></thead>
          <tbody>{data.learned.map((l: any) => (
            <tr key={`${l.cause}-${l.action}`}><td>{CAUSE_NAMES[l.cause] ?? l.cause}</td><td>{titleCase(l.action)}</td>
              <td>{l.successes} of {l.trials}</td><td>{pct(l.success_rate)}</td></tr>
          ))}</tbody>
        </table></div>
      </Card>

      <Card title="Decisions and outcomes" icon={<RefreshCw aria-hidden />} id="log" sub="Before and after: the machine's last hour before the decision versus 2 plant hours later.">
        <div className="table-wrap"><table>
          <thead><tr><th>When</th><th>Machine</th><th>AI suggested</th><th>Decision</th><th>By</th><th>Outcome</th><th>Before → after</th></tr></thead>
          <tbody>{data.decisions.slice(0, 40).map((d: any) => (
            <tr key={d.id}>
              <td className="small">{d.plant_time ? d.plant_time.replace("T", " ") : new Date(d.decided_at).toLocaleDateString()}</td>
              <td>{d.machine_id}</td>
              <td>{titleCase(d.recommended_action ?? "-")}</td>
              <td>{titleCase(d.decision)}{d.decision === "modified" ? `: ${titleCase(d.action_key)}` : ""}{d.note && <div className="small muted">“{d.note}”</div>}</td>
              <td className="small">{d.decided_by}</td>
              <td><span className={`badge sev-${d.outcome_status === "success" ? "ok" : d.outcome_status === "failure" ? "critical" : "info"}`}>{titleCase(d.outcome_status)}</span>
                {d.outcome?.summary && <div className="small muted">{d.outcome.summary}</div>}</td>
              <td className="small">{d.before?.oee !== undefined && d.after?.oee !== undefined
                ? <>OEE {pct(d.before.oee)} → {pct(d.after.oee)}<br />Vibration {d.before.vibration_mm_s} → {d.after.vibration_mm_s} mm/s<br />Defects {pct(d.before.defect_rate, 1)} → {pct(d.after.defect_rate, 1)}</>
                : d.before?.oee !== undefined ? <>OEE before {pct(d.before.oee)}</> : "–"}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </Card>
    </div>
  );
}
