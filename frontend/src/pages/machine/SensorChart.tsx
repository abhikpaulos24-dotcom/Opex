import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "../../components/ui";
import { api } from "../../lib/api";
import { useRefresh } from "../../lib/live";

const SIGNALS = [
  { key: "vibration_mm_s", label: "Vibration (mm/s)" }, { key: "process_temp_c", label: "Temperature (°C)" },
  { key: "rpm", label: "Spindle speed (rpm)" }, { key: "torque_nm", label: "Torque (Nm)" },
  { key: "coolant_bar", label: "Coolant (bar)" }, { key: "power_kw", label: "Power (kW)" },
  { key: "cycle_time_s", label: "Cycle time (s)" }, { key: "defect_rate_pct", label: "Defect rate (%)" },
];

type History = { times: string[]; series: Record<string, (number | null)[]> };

export function SensorChart({ machineId, ranges }: { machineId: string; ranges: Record<string, [number, number]> }) {
  const [signal, setSignal] = useState("vibration_mm_s");
  const [asTable, setAsTable] = useState(false);
  const { data } = useQuery({
    queryKey: ["history", machineId],
    queryFn: () => api<History>(`/api/machines/${machineId}/history?minutes=180`),
    refetchInterval: useRefresh(12000),
  });
  const rows = data ? data.times.map((t, i) => ({ t, v: data.series[signal]?.[i] ?? null })) : [];
  const band = ranges[signal];
  const label = SIGNALS.find((s) => s.key === signal)?.label ?? signal;

  return (
    <Card title="Sensor history" sub="The last 3 plant hours. The shaded band is the normal operating range." id="sensors" className="optional"
      actions={<button className="btn small" onClick={() => setAsTable(!asTable)}>{asTable ? "Show chart" : "Show as table"}</button>}>
      <label className="field" style={{ maxWidth: 320, marginBottom: 10 }}>Signal
        <select value={signal} onChange={(e) => setSignal(e.target.value)}>
          {SIGNALS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      </label>
      {band && <p className="small muted">Normal range for this signal: {band[0]} to {band[1]}.</p>}
      {asTable ? (
        <div className="table-wrap" style={{ maxHeight: 320 }}>
          <table>
            <thead><tr><th>Time</th><th>{label}</th></tr></thead>
            <tbody>{rows.filter((_, i) => i % 10 === 0).map((r) => <tr key={r.t}><td>{r.t}</td><td>{r.v ?? "missing"}</td></tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div style={{ height: 260 }} role="img" aria-label={`${label} over the last 3 hours. Use "Show as table" for the numbers.`}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--border)" vertical={false} />
              <XAxis dataKey="t" tick={{ fill: "var(--muted)", fontSize: 12 }} interval={29} />
              <YAxis tick={{ fill: "var(--muted)", fontSize: 12 }} domain={["auto", "auto"]} width={56} />
              {band && <ReferenceArea y1={band[0]} y2={band[1]} fill="var(--ok)" fillOpacity={0.1} />}
              <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
              <Line type="monotone" dataKey="v" name={label} stroke="var(--brand)" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
