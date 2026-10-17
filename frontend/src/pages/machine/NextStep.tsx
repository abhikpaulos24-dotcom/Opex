import { Bar, Card, Term } from "../../components/ui";
import { inr, num, pct } from "../../lib/format";
import type { MachineReport } from "../../lib/types";
import { StepTitle } from "./steps";

const METHOD = { trend: "From the live damage trend", model: "From the NASA-trained life model" };

export function NextStep({ report }: { report: MachineReport }) {
  const { prediction: p, components, quality, impact } = report;
  return (
    <Card title={<StepTitle step="next" />} id="next">
      <div className="grid grid-3">
        <div className="stat big">
          <span className="label"><Term name="p_fail" /> in 8 h</span>
          <span className="value" style={{ color: p.p_fail_8h > 0.5 ? "var(--critical)" : undefined }}>{pct(p.p_fail_8h)}</span>
        </div>
        <div className="stat">
          <span className="label"><Term name="window" /></span>
          <span className="value" style={{ fontSize: "1.4rem" }}>{p.window ?? "Not within 3 weeks"}</span>
          {p.method && <span className="hint">{METHOD[p.method]}</span>}
        </div>
        <div className="stat">
          <span className="label"><Term name="confidence" /></span>
          <span className="value" style={{ fontSize: "1.4rem" }}>{pct(p.confidence)}</span>
          <span className="hint">Cost if it breaks down: {inr(p.failure_cost_inr)}</span>
        </div>
      </div>

      {Object.keys(components).length > 0 && (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <caption className="sr-only">Component health</caption>
            <thead><tr><th>Component</th><th>Health</th><th>Life left (10–90%)</th></tr></thead>
            <tbody>
              {Object.values(components).map((c) => (
                <tr key={c.component}>
                  <td>{c.component_name}</td>
                  <td style={{ minWidth: 120 }}>
                    <div className="row" style={{ gap: 8 }}>
                      <Bar value={c.health_pct / 100} label={`${c.component_name} health`}
                        color={c.health_pct < 30 ? "var(--critical)" : c.health_pct < 60 ? "var(--medium)" : "var(--muted)"} />
                      <span className="mono small">{c.health_pct}%</span>
                    </div>
                  </td>
                  <td>{c.window}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {quality && <p style={{ marginTop: 10 }}>{quality.sentence}</p>}
      {impact.inr_per_hour > 0 && (
        <p className="small">
          Right now this costs about <b>{inr(impact.inr_per_hour)} per hour</b> ({num(impact.lost_parts_per_h, 1)} fewer parts/h,{" "}
          {num(impact.extra_defects_per_h, 1)} extra defects/h
          {(impact.energy_per_part_change_pct ?? 0) > 2 ? `, energy per part +${impact.energy_per_part_change_pct}%` : ""}).
        </p>
      )}
    </Card>
  );
}

export function MaintenancePlan({ report }: { report: MachineReport }) {
  if (report.maintenance_plan.length === 0) return null;
  return (
    <Card title="Maintenance plan and parts" id="plan">
      <ul style={{ paddingLeft: 18, margin: 0 }} className="stack">
        {report.maintenance_plan.map((m) => (
          <li key={m.component}>
            <b>{m.component_name}</b>{" "}
            {m.emergency ? <span className="badge sev-critical">Emergency</span> : <span className="badge sev-info">Scheduled</span>} {m.when}.
            <br />
            <span className="small">
              Inspect: {m.inspect}. Parts: {m.parts.join(", ")} ({inr(m.part_cost_inr)}). Job: about {m.repair_h} h. Needed within {m.needed_within}.
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
