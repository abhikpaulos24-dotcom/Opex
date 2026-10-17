import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Bot, CheckCircle2, ShieldCheck, Stethoscope, TriangleAlert, XCircle } from "lucide-react";
import { useState } from "react";
import { Card, ConfirmDialog, ErrorBox, Loading, Segmented, Term } from "../../components/ui";
import { api } from "../../lib/api";
import { hours, inr, num, pct, titleCase } from "../../lib/format";
import { useRecommendation } from "../../lib/queries";
import { useSession } from "../../lib/session";
import type { DecisionResult, Option, Recommendation, Severity } from "../../lib/types";
import { IncidentRoom } from "./IncidentRoom";
import { StepTitle } from "./steps";

const PRESETS = [
  { value: "balanced", label: "Balanced" },
  { value: "production_first", label: "Production first" },
  { value: "quality_first", label: "Quality first" },
  { value: "energy_saver", label: "Energy saver" },
  { value: "safety_first", label: "Safety first" },
];
const SHOWN_FIRST = 3; // Hick's law: compare a few options; the rest is one click away

/** Shortcut at the top of the machine page to the recommended action. */
export function RecommendationStrip({ machineId }: { machineId: string }) {
  const { data } = useRecommendation(machineId, null);
  if (!data?.needed) return null;
  const s = data.recommendation;
  return (
    <a href="#decide" className="banner sev-info" style={{ textDecoration: "none", alignItems: "center" }}>
      <Bot aria-hidden />
      <span className="text" style={{ flex: 1 }}>
        <b>Recommended: {s.headline}</b> · {inr(s.value_protected_inr)} saved · chance of failure {pct(s.p_fail_before)} → {pct(s.p_fail_after)}
      </span>
      <span className="btn small primary">Review and decide <ArrowRight size={16} aria-hidden /></span>
    </a>
  );
}

export function DecideStep({ machineId, severity }: { machineId: string; severity: Severity }) {
  const [preset, setPreset] = useState<string | null>(null);
  const [done, setDone] = useState<DecisionResult | null>(null);
  const rec = useRecommendation(machineId, preset);

  return (
    <Card title={<StepTitle step="decide" />} id="decide"
      sub="Every option is priced in rupees: repair + downtime + lost production + scrap + energy, plus the chance it still breaks down.">
      {done && (
        <>
          <DecisionDone result={done} />
          <button className="btn" onClick={() => setDone(null)}>Review the options again</button>
        </>
      )}
      {rec.error ? <ErrorBox error={rec.error} /> : null}
      {!done && !rec.data && !rec.error && <Loading label="Pricing the options" />}
      {!done && rec.data && !rec.data.needed && <p className="row"><CheckCircle2 color="var(--ok)" aria-hidden /> {rec.data.message}</p>}
      {!done && rec.data?.needed && (
        <>
          <div style={{ marginBottom: 12 }}>
            <p className="small" style={{ fontWeight: 700, marginBottom: 6 }}>What matters most right now?</p>
            <Segmented label="Priorities" value={preset ?? rec.data.preset} options={PRESETS} onChange={setPreset} />
          </div>
          <Recommended rec={rec.data} />
          <OptionsTable options={rec.data.options} />
          <hr className="divider" />
          <DecisionForm rec={rec.data} onDone={setDone} />
          {severity === "critical" && (
            <p className="small muted" style={{ marginTop: 8 }}><ShieldCheck size={14} aria-hidden /> Follow Lockout-Tagout (SOP-MNT-009) before opening guards.</p>
          )}
        </>
      )}
    </Card>
  );
}

function Recommended({ rec }: { rec: Recommendation }) {
  const s = rec.recommendation;
  return (
    <div className="banner sev-info" style={{ marginBottom: 12 }}>
      <Bot aria-hidden />
      <div className="text">
        <p style={{ fontWeight: 700, fontSize: "1.1rem", margin: 0 }}>Recommended: {s.headline}</p>
        <div className="row" style={{ margin: "6px 0" }}>
          <span><b>{inr(s.value_protected_inr)}</b> <Term name="value_protected" /></span>
          <span>Chance of failure <b>{pct(s.p_fail_before)} → {pct(s.p_fail_after)}</b></span>
          <span>Planned downtime <b>{hours(s.added_downtime_h)}</b></span>
          <span><Term name="confidence" /> <b>{pct(s.confidence)}</b></span>
        </div>
        <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{s.why.map((w) => <li key={w}>{w}</li>)}</ul>
      </div>
    </div>
  );
}

function OptionsTable({ options }: { options: Option[] }) {
  const [showAll, setShowAll] = useState(false);
  const shown = showAll ? options : options.slice(0, SHOWN_FIRST);
  return (
    <>
      <div className="table-wrap">
        <table>
          <caption className="sr-only">Options compared side by side, best first</caption>
          <thead><tr><th>Option</th><th>Downtime</th><th>Expected cost</th><th>Chance of failure</th><th>Extra bad parts</th><th>Energy per part</th><th>Worked here before</th></tr></thead>
          <tbody>
            {shown.map((o, i) => (
              <tr key={o.key} className={i === 0 ? "highlight" : ""}>
                <td style={{ minWidth: 240 }}>
                  <b>{o.title}</b>
                  {i === 0 && <span className="badge sev-info" style={{ marginLeft: 6 }}>Best</span>}
                  {o.safety_blocked && <span className="badge sev-critical" style={{ marginLeft: 6 }}>Unsafe: likely breakdown</span>}
                  <div className="small muted">{o.description}</div>
                </td>
                <td>{hours(o.downtime_h)}</td>
                <td>{inr(o.total_inr)}</td>
                <td>{pct(o.p_fail)}</td>
                <td>{num(o.extra_defects)}</td>
                <td>{o.energy_change_pct > 0 ? "+" : ""}{o.energy_change_pct}%</td>
                <td className="small">{o.learned.trials ? `${o.learned.successes} of ${o.learned.trials} times` : "Not tried yet"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {options.length > SHOWN_FIRST && (
        <button className="btn small" style={{ marginTop: 8 }} aria-expanded={showAll} onClick={() => setShowAll(!showAll)}>
          {showAll ? "Show the top 3 only" : `Show all ${options.length} options`}
        </button>
      )}
    </>
  );
}

function DecisionForm({ rec, onDone }: { rec: Recommendation; onDone: (r: DecisionResult) => void }) {
  const { can, prefs } = useSession();
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [other, setOther] = useState("");
  const [confirming, setConfirming] = useState<Option | null>(null);
  const [agentsOpen, setAgentsOpen] = useState(false);

  const best = rec.options[0];
  const decide = useMutation({
    mutationFn: (body: { decision: string; action_key?: string; note: string }) =>
      api<DecisionResult>(`/api/recommendations/${rec.id}/decision`, { body }),
    onSuccess: (result) => {
      setConfirming(null);
      onDone(result);
      queryClient.invalidateQueries();
    },
  });

  const approve = (option: Option) => {
    const body = option.key === best.key
      ? { decision: "approved", note }
      : { decision: "modified", action_key: option.key, note };
    decide.mutate(body);
  };
  // Stopping, slowing or opening a machine gets a second look; quick low-risk actions don't.
  const start = (option: Option) => (option.permission === "decide_major" ? setConfirming(option) : approve(option));
  const otherOption = rec.options.find((o) => o.key === other);

  return (
    <>
      <h3>Your decision</h3>
      <p className="small muted">
        OpEx never acts on machines by itself.{" "}
        {can(best.permission) ? "You can approve this." : "This needs a maintenance engineer or plant manager."}
      </p>
      <label className="field">Note for the log (optional)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. spare bearing confirmed in store" />
      </label>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn good" disabled={!can(best.permission) || decide.isPending} onClick={() => start(best)}>
          <CheckCircle2 size={18} aria-hidden /> Approve: {best.title}
        </button>
        <button className="btn danger" disabled={!can("decide_minor") || decide.isPending}
          onClick={() => decide.mutate({ decision: "rejected", note })}>
          <XCircle size={18} aria-hidden /> Reject
        </button>
        <button className="btn" onClick={() => setAgentsOpen(true)}><Stethoscope size={18} aria-hidden /> Ask the AI incident room</button>
      </div>
      <div className="row" style={{ marginTop: 10, alignItems: "flex-end" }}>
        <label className="field" style={{ flex: 1, minWidth: 220 }}>Or choose a different option
          <select value={other} onChange={(e) => setOther(e.target.value)}>
            <option value="">Choose…</option>
            {rec.options.slice(1).map((o) => <option key={o.key} value={o.key}>{o.title}</option>)}
          </select>
        </label>
        <button className="btn" disabled={!otherOption || !can(otherOption.permission) || decide.isPending}
          onClick={() => otherOption && start(otherOption)}>Approve this instead</button>
      </div>
      {decide.error ? <div style={{ marginTop: 10 }}><ErrorBox error={decide.error} /></div> : null}

      <ConfirmDialog open={!!confirming} title={`${confirming?.title ?? ""} on ${rec.machine_id}?`} confirmLabel="Yes, approve"
        busy={decide.isPending} onConfirm={() => confirming && approve(confirming)} onCancel={() => setConfirming(null)}>
        {confirming && <Consequences option={confirming} />}
      </ConfirmDialog>
      <IncidentRoom open={agentsOpen} onClose={() => setAgentsOpen(false)} recommendationId={rec.id} language={prefs.language} simple={prefs.simple} />
    </>
  );
}

function Consequences({ option }: { option: Option }) {
  return (
    <>
      {option.safety_blocked && (
        <p className="banner sev-critical"><TriangleAlert aria-hidden /><span className="text">OpEx marks this option as unsafe: the machine is likely to break down first.</span></p>
      )}
      <p>What will happen:</p>
      <ul>
        {option.downtime_h > 0 && <li>The machine is stopped for about <b>{hours(option.downtime_h)}</b>.</li>}
        {option.lost_parts > 0 && <li>About <b>{num(option.lost_parts)} fewer parts</b> are made.</li>}
        <li>Expected total cost: <b>{inr(option.total_inr)}</b>.</li>
        <li>Chance it still breaks down: <b>{pct(option.p_fail)}</b>.</li>
      </ul>
      <p className="small muted">The plant twin applies this right away. You can see it in the machine's events.</p>
    </>
  );
}

function DecisionDone({ result }: { result: DecisionResult }) {
  const { config } = useSession();
  const checkHours = result.check_in_plant_minutes / 60;
  const realMinutes = Math.round(result.check_in_plant_minutes / (config?.live_speed || 1));
  return (
    <p role="status" className="banner sev-ok" style={{ marginBottom: 12 }}>
      <CheckCircle2 aria-hidden />
      <span className="text">
        <b>{titleCase(result.decision)}.</b> {/[.!?]$/.test(result.result) ? result.result : `${result.result}.`}{" "}
        {result.decision === "rejected" ? "OpEx will check what happened" : "OpEx will check whether it worked"} in {checkHours} plant hours
        {config?.live_speed && config.live_speed > 1 ? ` (about ${realMinutes} real minutes)` : ""} and add the result to the Learning log.
      </span>
    </p>
  );
}
