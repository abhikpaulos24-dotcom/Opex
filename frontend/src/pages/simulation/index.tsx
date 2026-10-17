import { useMutation, useQuery } from "@tanstack/react-query";
import { History, Play, Sparkles } from "lucide-react";
import { useState } from "react";
import { Card, ErrorBox, Segmented } from "../../components/ui";
import { api } from "../../lib/api";
import { inr, pct } from "../../lib/format";
import { Player } from "./Player";
import type { RunListItem, SimRun } from "./types";

export default function Simulation() {
  const [durationS, setDurationS] = useState(60);
  const [years, setYears] = useState("5");
  const [adoption, setAdoption] = useState(0.85);
  const [coverage, setCoverage] = useState(0.9);
  const [seed, setSeed] = useState(2026);
  const [run, setRun] = useState<SimRun | null>(null);
  const runs = useQuery({ queryKey: ["sim-runs"], queryFn: () => api<RunListItem[]>("/api/simulations") });

  const start = useMutation({
    mutationFn: () => api<SimRun>("/api/simulations", { body: { years: Number(years), adoption_rate: adoption, sensor_coverage: coverage, seed } }),
    onSuccess: (r) => { setRun(r); runs.refetch(); },
  });
  const load = useMutation({ mutationFn: (id: string) => api<SimRun>(`/api/simulations/${id}`), onSuccess: setRun });

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>5-year factory simulation</h1>
          <p>The same 24-machine plant, the same luck, run twice: once the way most plants run today, once with OpEx.
            Every difference comes from the decisions, nothing else.</p>
        </div>
      </div>
      <p className="banner sev-info small" role="note"><Sparkles aria-hidden /><span className="text">
        <b>Simulated, not a real factory's results.</b> Calibrated on real industrial datasets: failure rates and sensor
        signatures from Azure PdM (761 failures), wear curves and prediction error from NASA C-MAPSS, operating limits from
        AI4I 2020, and line losses from a real production line (Zenodo 17855209). OpEx's own measured miss rate and false alarms are included.</span></p>

      <Card title="Set up the run" id="setup">
        <div className="grid grid-2">
          <label className="field">How long should the replay take? <b>{durationS < 60 ? `${durationS} seconds` : durationS === 60 ? "1 minute" : `${(durationS / 60).toFixed(durationS % 60 ? 1 : 0)} minutes`}</b>
            <input type="range" min={20} max={600} step={10} value={durationS} onChange={(e) => setDurationS(Number(e.target.value))}
              aria-valuetext={`${durationS} seconds`} />
            <span className="small muted">That is about {Math.round((Number(years) * 365) / durationS)} simulated days per second. You can pause, scrub or skip at any time.</span>
          </label>
          <div>
            <p style={{ fontWeight: 600, marginBottom: 6 }}>Years to simulate</p>
            <Segmented label="Years" value={years} onChange={setYears} options={["1", "2", "3", "4", "5"].map((y) => ({ value: y, label: `${y} yr` }))} />
          </div>
        </div>
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>Advanced assumptions</summary>
          <div className="grid grid-3" style={{ marginTop: 10 }}>
            <label className="field">People follow the advice: {pct(adoption)}
              <input type="range" min={0.5} max={1} step={0.05} value={adoption} onChange={(e) => setAdoption(Number(e.target.value))} />
            </label>
            <label className="field">Failures our sensors can see: {pct(coverage)}
              <input type="range" min={0.5} max={1} step={0.05} value={coverage} onChange={(e) => setCoverage(Number(e.target.value))} />
            </label>
            <label className="field">Random seed (same seed = same history)
              <input type="number" value={seed} min={1} onChange={(e) => setSeed(Number(e.target.value))} />
            </label>
          </div>
        </details>
        <div className="row" style={{ marginTop: 14 }}>
          <button className="btn primary" onClick={() => start.mutate()} disabled={start.isPending} style={{ fontSize: "1.05rem" }}>
            <Play size={20} aria-hidden /> {start.isPending ? "Simulating…" : `Simulate ${years} year${years === "1" ? "" : "s"}`}
          </button>
          {start.isPending && <span className="muted" role="status">Simulating {(Number(years) * 8760 * 24 * 2 / 1e6).toFixed(1)} million machine-hours (two factories × 24 machines)…</span>}
        </div>
        {start.error ? <ErrorBox error={start.error} /> : null}
        {load.error ? <ErrorBox error={load.error} /> : null}
      </Card>

      {run && <Player key={run.id} run={run} durationS={durationS} />}

      {!!runs.data?.length && (
        <Card title="Earlier runs" icon={<History aria-hidden />} id="runs" className="optional">
          <div className="table-wrap"><table>
            <thead><tr><th>When</th><th>By</th><th>Years</th><th>Adoption</th><th>Net benefit</th><th>ROI</th><th></th></tr></thead>
            <tbody>{runs.data.map((r) => (
              <tr key={r.id}><td>{new Date(r.created_at).toLocaleString()}</td><td>{r.created_by}</td><td>{r.params.years}</td>
                <td>{pct(r.params.adoption_rate)}</td><td>{inr(r.headline.net_benefit_inr)}</td><td>{r.headline.roi_multiple.toFixed(1)}×</td>
                <td><button className="btn small" onClick={() => load.mutate(r.id)} disabled={load.isPending}>Open</button></td></tr>
            ))}</tbody>
          </table></div>
        </Card>
      )}
    </div>
  );
}
