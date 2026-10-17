import { MessageCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { ErrorBox, PageSkeleton, ReadAloud, SeverityBadge, StateBadge } from "../../components/ui";
import { useMachine } from "../../lib/queries";
import { useSession } from "../../lib/session";
import type { MachineReport } from "../../lib/types";
import { DecideStep, RecommendationStrip } from "./DecideStep";
import { DetectStep } from "./DetectStep";
import { MaintenancePlan, NextStep } from "./NextStep";
import { PhotoCheck } from "./PhotoCheck";
import { SensorChart } from "./SensorChart";
import { StepNav } from "./steps";
import { WhyStep } from "./WhyStep";

export default function Machine() {
  const { id = "" } = useParams();
  const { data: report, error } = useMachine(id);
  const { prefs } = useSession();
  if (error) return <ErrorBox error={error} />;
  if (!report) return <PageSkeleton label={`Diagnosing ${id}`} blocks={4} />;

  const m = report.machine;
  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <p className="small"><Link to="/">Overview</Link> / {m.id}</p>
          <h1>{m.id} · {m.name}</h1>
          <div className="row">
            <StateBadge state={report.state} />
            <SeverityBadge level={report.prediction.severity} />
            <span className="muted small">{m.product} · Line {m.line_id.slice(1)} · plant time {report.plant_time.slice(11)}</span>
          </div>
        </div>
        <div className="row">
          <ReadAloud text={spokenSummary(report, prefs.simple)} />
          <Link className="btn" to={`/copilot?q=${encodeURIComponent(`What is wrong with ${m.id} and what should I do?`)}`}>
            <MessageCircle size={18} aria-hidden /> Ask OpEx about {m.id}
          </Link>
        </div>
      </div>

      <RecommendationStrip machineId={m.id} />
      <StepNav />
      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <DetectStep report={report} />
        <WhyStep report={report} />
      </div>
      <div className="grid grid-2" style={{ alignItems: "start" }}>
        <NextStep report={report} />
        <MaintenancePlan report={report} />
      </div>
      <DecideStep machineId={m.id} severity={report.prediction.severity} />
      <PhotoCheck machineId={m.id} />
      <SensorChart machineId={m.id} ranges={report.ranges} />
    </div>
  );
}

function spokenSummary(report: MachineReport, simple: boolean): string {
  const p = report.prediction;
  const top = report.root_cause.top;
  return [
    `${report.machine.id}. ${p.severity} risk.`,
    ...report.anomalies.map((x) => (simple ? x.plain_sentence : x.sentence)),
    top ? `Likely cause: ${top.name}.` : "",
    p.window ? `Breakdown expected in ${p.window}.` : "",
  ].join(" ");
}
