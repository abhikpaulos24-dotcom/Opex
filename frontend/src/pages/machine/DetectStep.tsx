import { useState } from "react";
import { Card, RangeBar, Term } from "../../components/ui";
import { pct } from "../../lib/format";
import { useSession } from "../../lib/session";
import type { Anomaly, MachineReport } from "../../lib/types";
import { StepTitle } from "./steps";

const LEVEL: Record<Anomaly["severity"], { css: string; label: string }> = {
  critical: { css: "sev-critical", label: "Critical" },
  warning: { css: "sev-high", label: "Warning" },
  watch: { css: "sev-medium", label: "Watch" },
};
const SHOWN_FIRST = 3; // a short list people can take in at a glance; the rest is one click away

export function DetectStep({ report }: { report: MachineReport }) {
  const { prefs } = useSession();
  const [showAll, setShowAll] = useState(false);
  const { anomalies, state } = report;
  const shown = showAll ? anomalies : anomalies.slice(0, SHOWN_FIRST);

  return (
    <Card title={<StepTitle step="detect" />} id="detect" className="step">
      {state === "breakdown" && <p><b>This machine has broken down</b> and is being repaired.</p>}
      {state === "maintenance" && (
        <p>
          {report.state_detail.replacing
            ? `This machine is stopped while a worn part (${report.state_detail.replacing}) is replaced.`
            : "This machine is stopped for a short routine job, such as a tool change. The forecast uses its last minutes of cutting."}
        </p>
      )}
      {state === "idle" && (
        <p>This machine is idle.{report.state_detail.idle_waste && " Its spindle and coolant are still running while it waits."}</p>
      )}
      {anomalies.length === 0 && state === "running" && <p className="muted" style={{ margin: 0 }}>Every signal is inside its normal range. Nothing to flag.</p>}

      <ul className="stack" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {shown.map((x) => (
          <li key={x.signal}>
            <div className="row between">
              <b>{x.label}</b>
              <span className={`badge ${LEVEL[x.severity].css}`}>{LEVEL[x.severity].label}</span>
            </div>
            <RangeBar value={x.value} low={x.normal_low} high={x.normal_high} label={x.label} />
            <p className="small" style={{ margin: 0 }}>{prefs.simple ? x.plain_sentence : x.sentence}</p>
          </li>
        ))}
      </ul>
      {anomalies.length > SHOWN_FIRST && (
        <button className="btn small ghost" style={{ marginTop: 8 }} aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show the main 3 only" : `Show all ${anomalies.length} signals`}
        </button>
      )}
      {anomalies.length > 0 && <p className="small muted" style={{ margin: "8px 0 0" }}>Green band = normal range. Line = reading now.</p>}

      <DataHealth report={report} />
    </Card>
  );
}

function DataHealth({ report }: { report: MachineReport }) {
  const { data_health: dh, prediction: p } = report;
  const reduced = p.confidence_before_data_check - p.confidence > 0.01;
  return (
    <div style={{ marginTop: 14, padding: 12, borderRadius: 10, background: "var(--surface-2)" }}>
      <div className="row between"><b><Term name="data_health" /> {dh.score}/100</b><span className="small muted">{dh.completeness_pct}% of readings present</span></div>
      {dh.issues.length === 0
        ? <p className="small muted" style={{ margin: 0 }}>The sensors can be trusted.</p>
        : <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>{dh.issues.map((i) => <li key={i.text}>{i.text}</li>)}</ul>}
      {reduced && (
        <p className="small" style={{ margin: "6px 0 0" }}>
          Confidence lowered from <b>{pct(p.confidence_before_data_check)}</b> to <b>{pct(p.confidence)}</b> because of these data problems.
        </p>
      )}
    </div>
  );
}
