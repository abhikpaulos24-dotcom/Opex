import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { Bar, Card } from "../../components/ui";
import { hours, pct } from "../../lib/format";
import type { MachineReport } from "../../lib/types";
import { StepTitle } from "./steps";

export function WhyStep({ report }: { report: MachineReport }) {
  const { top, candidates, chain, memory } = report.root_cause;
  return (
    <Card title={<StepTitle step="why" />} id="why" className="step">
      {top ? (
        <>
          <p><b>Most likely: {top.name}</b> <span className="muted">({pct(top.match)} pattern match)</span></p>
          <div className="stack" style={{ gap: 6 }}>
            {candidates.slice(0, 3).map((c) => (
              <div key={c.key}>
                <div className="row between small"><span>{c.name}</span><span className="mono">{pct(c.probability)}</span></div>
                <Bar value={c.probability} label={`${c.name} likelihood`} />
              </div>
            ))}
          </div>
        </>
      ) : <p className="muted" style={{ margin: 0 }}>No fault pattern matches. The machine looks healthy.</p>}

      {chain.length > 1 && (
        <>
          <h3 style={{ marginTop: 14 }}>Chain of impact</h3>
          <p className="small muted">Signals in the order they went abnormal. The first is closest to the cause.</p>
          <div className="chain" aria-label="Chain of impact">
            {chain.map((c, i) => (
              <span key={c.signal} className="row" style={{ gap: 6 }}>
                {i > 0 && <ArrowRight size={16} className="arrow" aria-hidden />}
                <span className="step">{c.text}</span>
              </span>
            ))}
          </div>
        </>
      )}
      <Memory memory={memory} />
    </Card>
  );
}

function Memory({ memory }: { memory: MachineReport["root_cause"]["memory"] }) {
  const [open, setOpen] = useState(false);
  const matches = memory.matches ?? [];
  return (
    <div style={{ marginTop: 14 }}>
      <h3>Have we seen this before?</h3>
      <p>{memory.sentence}</p>
      {matches.length > 0 && (
        <>
          <button className="btn small ghost" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide the" : "Show the"} {matches.length} similar incident{matches.length === 1 ? "" : "s"}</button>
          {open && (
            <div className="table-wrap"><table>
              <thead><tr><th>Date</th><th>Machine</th><th>Confirmed cause</th><th>Technician note</th><th>Downtime</th></tr></thead>
              <tbody>{matches.map((m) => (
                <tr key={m.id}><td>{m.date.slice(0, 10)}</td><td>{m.machine_id}</td><td>{m.root_cause}</td><td className="small">{m.technician_note}</td><td>{hours(m.downtime_h)}</td></tr>
              ))}</tbody>
            </table></div>
          )}
        </>
      )}
    </div>
  );
}
