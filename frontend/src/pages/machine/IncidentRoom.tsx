import { useQuery } from "@tanstack/react-query";
import { Dialog, ErrorBox, Loading } from "../../components/ui";
import { api } from "../../lib/api";

type AgentView = {
  agent: "Diagnostician" | "Planner" | "Safety officer";
  source: "gemini" | "rules";
  root_cause?: string; certainty?: string; evidence_for?: string[]; evidence_against?: string[]; check_first?: string[];
  headline?: string; why?: string; trade_offs?: string[]; if_we_do_nothing?: string;
  before_starting?: string[]; sop_references?: string[]; concerns?: string[]; documents?: string[];
};

/** Three Gemini agents review the case before a person decides. */
export function IncidentRoom({ open, onClose, recommendationId, language, simple }: {
  open: boolean; onClose: () => void; recommendationId: string; language: string; simple: boolean;
}) {
  const q = useQuery({
    queryKey: ["agents", recommendationId, language, simple],
    queryFn: () => api<{ agents: AgentView[] }>(`/api/recommendations/${recommendationId}/agents?language=${language}&simple=${simple}`, { method: "POST" }),
    enabled: open,
    staleTime: Infinity,
  });
  return (
    <Dialog open={open} onClose={onClose} title="Second opinion: AI incident room">
      <p className="muted small measure">Three AI agents look at the case from different angles before you decide. They only use facts OpEx has measured and priced, and they can be wrong: treat this as a second opinion, not an order.</p>
      {q.isLoading && <Loading label="Three agents are reviewing the evidence" />}
      {q.error ? <ErrorBox error={q.error} /> : null}
      <div className="stack">
        {q.data?.agents.map((ag) => (
          <div key={ag.agent} className="card">
            <div className="row between">
              <h3>{ag.agent}</h3>
              <span className="badge sev-info">{ag.source === "gemini" ? "Gemini" : "Rule-based (add a Gemini key for full reasoning)"}</span>
            </div>
            {ag.agent === "Diagnostician" && <>
              <p><b>{ag.root_cause}</b> ({ag.certainty} certainty)</p>
              <List title="Evidence" items={ag.evidence_for} />
              <List title="Doubts" items={ag.evidence_against} />
              <List title="Check first" items={ag.check_first} />
            </>}
            {ag.agent === "Planner" && <>
              <p><b>{ag.headline}</b></p>
              <p>{ag.why}</p>
              <List title="Trade-offs" items={ag.trade_offs} />
              <p className="small"><b>If we do nothing:</b> {ag.if_we_do_nothing}</p>
            </>}
            {ag.agent === "Safety officer" && <>
              <List title="Before anyone starts" items={ag.before_starting} />
              <List title="Procedures" items={ag.sop_references} />
              <List title="Concerns" items={ag.concerns} />
              {!!ag.documents?.length && <p className="small muted">Read from: {ag.documents.join("; ")}</p>}
            </>}
          </div>
        ))}
      </div>
    </Dialog>
  );
}

function List({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) return null;
  return (
    <>
      <p className="small" style={{ fontWeight: 700, margin: "8px 0 2px" }}>{title}</p>
      <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{items.map((i) => <li key={i}>{i}</li>)}</ul>
    </>
  );
}
