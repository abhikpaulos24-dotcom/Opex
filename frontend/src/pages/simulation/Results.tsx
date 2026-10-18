import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download } from "lucide-react";
import { useState } from "react";
import { Card, Loading, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { inr, num, pct } from "../../lib/format";
import type { SimRun } from "./types";

type Rewind = {
  without: { when?: string; text: string }[];
  with: { when?: string; text: string }[];
  caught: boolean;
  warning_days: number;
  value_protected_inr: number;
  reason: string;
  detection_odds: number;
};

export function Results({ run }: { run: SimRun }) {
  const s = run.summary;
  const dl = s.delta;
  const years = run.params.years;
  const [rewindIndex, setRewindIndex] = useState<number | null>(null);
  const rewind = useQuery({
    queryKey: ["rewind", run.id, rewindIndex],
    queryFn: () => api<Rewind>(`/api/simulations/${run.id}/rewind/${rewindIndex}`),
    enabled: rewindIndex !== null,
  });
  return (
    <>
      <div className="banner sev-ok" role="status">
        <CheckCircle2 aria-hidden />
        <div className="text">
          <b>In short, over {years} year{years > 1 ? "s" : ""} with OpEx:</b>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            <li>{num(dl.failures_avoided)} fewer breakdowns ({pct(dl.breakdowns_reduction)} fewer) and {num(dl.downtime_avoided_h)} machine-hours of downtime avoided.</li>
            <li>OEE goes from {pct(s.kpis.without.oee, 1)} to {pct(s.kpis.with.oee, 1)}, with {num(dl.good_parts_gained)} extra good parts.</li>
            <li>{inr(dl.net_benefit_inr)} net benefit after paying for OpEx: {dl.roi_multiple.toFixed(1)}× the money back{dl.payback_months ? `, paid back in month ${dl.payback_months}` : ""}.</li>
          </ul>
        </div>
      </div>
      <Card title={`Results after ${years} year${years > 1 ? "s" : ""}`} id="results" sub="Net of everything OpEx costs: sensors, setup, cloud and support.">
        <div className="grid grid-stats">
          <Stat big label="Net benefit" value={inr(dl.net_benefit_inr)} hint={`after ${inr(dl.opex_cost_inr)} cost of OpEx`} />
          <Stat big label="Return on investment" value={`${dl.roi_multiple.toFixed(1)}×`} hint={dl.payback_months ? `pays back in month ${dl.payback_months}` : "does not pay back"} />
          <Stat label="Breakdowns avoided" value={num(dl.failures_avoided)} hint={`${pct(dl.breakdowns_reduction)} fewer`} />
          <Stat label="Breakdown hours avoided" value={num(dl.downtime_avoided_h)} hint="machine-hours" />
          <Stat label="Extra good parts" value={num(dl.good_parts_gained)} hint={inr(dl.production_protected_inr)} />
          <Stat label="Maintenance saved" value={inr(dl.maintenance_savings_inr)} hint={`${pct(dl.maintenance_cost_reduction)} lower`} />
          <Stat label="Scrap avoided" value={num(dl.defects_avoided)} hint={inr(dl.scrap_savings_inr)} />
          <Stat label="Energy saved" value={`${num(dl.energy_saved_mwh)} MWh`} hint={`${num(dl.co2_avoided_t)} t CO₂ · ${inr(dl.energy_savings_inr)}`} />
          <Stat label="OEE (with OpEx)" value={pct(s.kpis.with.oee, 1)} hint={`was ${pct(s.kpis.without.oee, 1)} · +${dl.oee_points.toFixed(1)} points`} />
        </div>
        <h3 style={{ marginTop: 16 }}>Sanity check against published benchmarks</h3>
        <p className="small muted">US Department of Energy O&amp;M Best Practices Guide (Release 3.0), predictive vs reactive maintenance.</p>
        <table><thead><tr><th>Measure</th><th>This simulation</th><th>DOE published range</th></tr></thead>
          <tbody>
            <tr><td>Fewer breakdowns</td><td>{pct(s.benchmarks.breakdowns_reduction.ours)}</td><td>70–75%</td></tr>
            <tr><td>Lower maintenance cost</td><td>{pct(s.benchmarks.maintenance_cost_reduction.ours)}</td><td>25–30%</td></tr>
            <tr><td>Less equipment downtime*</td><td>{pct(s.benchmarks.downtime_reduction.ours)}</td><td>35–45%</td></tr>
          </tbody></table>
        <p className="small muted">*Ours counts equipment stops only; material, set-up and other stops (17.5% of planned time, from the Zenodo line data) are identical in both factories.</p>
      </Card>

      <div className="grid grid-2">
        <Card title="How we calculated this" id="calc">
          <ul className="small stack" style={{ paddingLeft: 18, margin: 0, gap: 8 }}>
            {s.calculations.map((c) => <li key={c.label}><b>{c.label}:</b> {c.formula}.<br /><span className="mono">{c.value}</span></li>)}
          </ul>
        </Card>
        <Card title="Year by year" id="years">
          <div className="table-wrap"><table>
            <thead><tr><th>Year</th><th>OEE without → with</th><th>Breakdowns</th><th>Downtime h</th></tr></thead>
            <tbody>{s.yearly.map((y) => (
              <tr key={y.year}><td>{y.year}</td><td>{pct(y.without.oee, 1)} → {pct(y.with.oee, 1)}</td>
                <td>{y.without.failures} → {y.with.failures}</td><td>{num(y.without.downtime_h)} → {num(y.with.downtime_h)}</td></tr>
            ))}</tbody>
          </table></div>
          <p className="small muted">OpEx cost: sensor kits {inr(s.costs.sensor_kits_inr)} + setup {inr(s.costs.implementation_inr)} once, then {inr(s.costs.yearly_inr)} a year.</p>
        </Card>
      </div>

      <Card title="Rewind the factory" id="rewind" sub="Pick one of the costliest breakdowns from the 'without AI' history and replay the same wear with OpEx watching.">
        <div className="chips">
          {run.rewind.map((e, i) => (
            <button key={i} className="chip" aria-pressed={rewindIndex === i} onClick={() => setRewindIndex(i)}>
              Day {e.day + 1} · {e.machine} {e.component} · {inr(e.total_inr)}
            </button>
          ))}
        </div>
        {rewind.isLoading && <Loading label="Replaying that breakdown with OpEx watching" />}
        {rewind.data && (
          <div className="grid grid-2" style={{ marginTop: 12 }}>
            <Timeline title="Without AI" color="var(--without)" steps={rewind.data.without} />
            <Timeline title="With OpEx" color="var(--with)" steps={rewind.data.with}
              footer={rewind.data.caught ? `Warned ${rewind.data.warning_days} production days ahead. Value protected: ${inr(rewind.data.value_protected_inr)}.`
                : `Honest result: this one would have been missed - ${rewind.data.reason}. (OpEx catches about ${pct(rewind.data.detection_odds)} of failures like this.)`} />
          </div>
        )}
      </Card>

      <Card title="Download the datasets" icon={<Download aria-hidden />} id="downloads" sub="Use them in Excel, BigQuery or Looker Studio.">
        <div className="row">
          {["daily.csv", "events.csv", "machines.csv", "summary.json", "assumptions.json"].map((f) => (
            <a key={f} className="btn" href={`/api/simulations/${run.id}/download/${f}`} download><Download size={16} aria-hidden /> {f}</a>
          ))}
        </div>
      </Card>
    </>
  );
}

function Timeline({ title, color, steps, footer }: { title: string; color: string; steps: Rewind["with"]; footer?: string }) {
  return (
    <div className="card" style={{ borderColor: color }}>
      <h3 style={{ color }}>{title}</h3>
      <ol style={{ margin: 0, paddingLeft: 20 }} className="stack">
        {steps.map((s, i) => <li key={i}>{s.when && <span className="small muted">{s.when} · </span>}{s.text}</li>)}
      </ol>
      {footer && <p className="small" style={{ marginTop: 10, fontWeight: 700 }}>{footer}</p>}
    </div>
  );
}
