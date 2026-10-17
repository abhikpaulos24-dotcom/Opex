import { FastForward, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, Segmented } from "../../components/ui";
import { inr, num, pct } from "../../lib/format";
import { useSession } from "../../lib/session";
import { Results } from "./Results";
import { type SimRun, WORLD_LABEL } from "./types";

const STATE_INFO = [
  { label: "Healthy", mark: "" }, { label: "Wearing", mark: "~" }, { label: "At risk", mark: "!" },
  { label: "Slowed down", mark: "↓" }, { label: "Planned maintenance", mark: "PM" }, { label: "Broken down", mark: "✕" },
];
const CO2_T_PER_MWH = 0.675; // India grid emission factor (CEA)

function cumulative(values: number[]): number[] {
  let total = 0;
  return values.map((v) => (total += v));
}

export function Player({ run, durationS }: { run: SimRun; durationS: number }) {
  const { prefs } = useSession();
  const days = run.player.days;
  const [day, setDay] = useState(0);
  const [playing, setPlaying] = useState(prefs.motion !== "reduce"); // no auto-play for people who asked for less motion
  const [speed, setSpeed] = useState("1");
  const last = useRef<number | null>(null);
  const finished = day >= days - 1;

  const series = useMemo(() => {
    const totals = (w: "without" | "with") => {
      const s = run.player.worlds[w];
      return {
        failures: cumulative(s.failures), downtime: cumulative(s.downtime_h), good: cumulative(s.good),
        defects: cumulative(s.defects), energy: cumulative(s.energy_kwh), cost: cumulative(s.cost_inr),
      };
    };
    const out = { without: totals("without"), with: totals("with") };
    const weekly = [];
    for (let d = 6; d < days; d += 7) {
      weekly.push({ day: d, label: `Y${Math.floor(d / 365) + 1}`, without: Math.round(out.without.downtime[d]), with: Math.round(out.with.downtime[d]) });
    }
    return { ...out, weekly };
  }, [run, days]);

  useEffect(() => {
    if (!playing || finished) {
      last.current = null;
      return;
    }
    let frame = 0;
    const tick = (now: number) => {
      if (last.current !== null) {
        const dt = (now - last.current) / 1000;
        setDay((d) => Math.min(days - 1, d + (days / durationS) * dt * Number(speed)));
      }
      last.current = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, finished, days, durationS, speed]);

  const d = Math.floor(day);
  const date = new Date(new Date(run.player.start_date).getTime() + d * 86400000);
  const month = Math.min(Math.floor((d * 12) / 365), run.summary.monthly.oee_with.length - 1);
  const value = series.without.cost[d] - series.with.cost[d];
  const grid = run.summary.kpis;
  const rows = [
    { label: "Breakdowns", w: series.without.failures[d], o: series.with.failures[d], fmt: (v: number) => num(v), better: "lower" },
    { label: "Breakdown downtime", w: series.without.downtime[d], o: series.with.downtime[d], fmt: (v: number) => `${num(v)} h`, better: "lower" },
    { label: "Good parts made", w: series.without.good[d], o: series.with.good[d], fmt: (v: number) => num(v), better: "higher" },
    { label: "Defective parts", w: series.without.defects[d], o: series.with.defects[d], fmt: (v: number) => num(v), better: "lower" },
    { label: "Energy used", w: series.without.energy[d] / 1000, o: series.with.energy[d] / 1000, fmt: (v: number) => `${num(v)} MWh`, better: "lower" },
    { label: "CO₂ from electricity", w: (series.without.energy[d] / 1000) * CO2_T_PER_MWH, o: (series.with.energy[d] / 1000) * CO2_T_PER_MWH, fmt: (v: number) => `${num(v)} t`, better: "lower" },
  ];
  const ticker = useMemo(() => run.ticker.filter((e) => e.day <= d).slice(-6).reverse(), [run.ticker, d]);
  const monthlyOee = run.summary.monthly.oee_without.slice(0, month + 1).map((v, i) => ({
    month: i + 1, without: Math.round(v * 1000) / 10, with: Math.round(run.summary.monthly.oee_with[i] * 1000) / 10,
  }));
  const announce = `Month ${month + 1}: without AI ${num(series.without.failures[d])} breakdowns, with OpEx ${num(series.with.failures[d])}. Value created ${inr(value)}.`;

  return (
    <>
      <Card title={<span className="row">Replay <span className="badge simulated">Simulated</span></span>} id="player">
        <div className="row between">
          <div>
            <p style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>Year {Math.floor(d / 365) + 1} · {date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</p>
            <span className="small muted">Day {num(d + 1)} of {num(days)}</span>
          </div>
          <div className="row">
            <button className="btn" onClick={() => setPlaying(!playing)} disabled={finished} aria-label={playing ? "Pause" : "Play"}>
              {playing && !finished ? <><Pause size={18} aria-hidden /> Pause</> : <><Play size={18} aria-hidden /> Play</>}
            </button>
            <button className="btn" onClick={() => { setDay(0); setPlaying(true); }}><RotateCcw size={18} aria-hidden /> Restart</button>
            <button className="btn" onClick={() => setDay(days - 1)}><FastForward size={18} aria-hidden /> Skip to results</button>
            <Segmented label="Playback speed" value={speed} onChange={setSpeed} options={[{ value: "0.5", label: "½×" }, { value: "1", label: "1×" }, { value: "2", label: "2×" }, { value: "4", label: "4×" }]} />
          </div>
        </div>
        <input type="range" min={0} max={days - 1} value={d} onChange={(e) => { setDay(Number(e.target.value)); setPlaying(false); }}
          aria-label="Simulation day" aria-valuetext={`Day ${d + 1}`} style={{ width: "100%", marginTop: 10 }} />
        <p className="sr-only" aria-live="polite">{month % 3 === 0 ? announce : ""}</p>

        <div className="grid grid-2" style={{ marginTop: 12 }}>
          <div>
            <div className="stat big"><span className="label">Value created by OpEx so far</span>
              <span className="value" style={{ color: value >= 0 ? "var(--ok)" : "var(--critical)" }}>{inr(value)}</span>
              <span className="hint">Extra production + avoided repairs, scrap and energy (before the cost of OpEx)</span></div>
            <div className="table-wrap" style={{ marginTop: 10 }}><table>
              <thead><tr><th>So far</th><th style={{ color: "var(--without)" }}>Without AI</th><th style={{ color: "var(--with)" }}>With OpEx</th><th>Difference</th></tr></thead>
              <tbody>{rows.map((r) => {
                const diff = r.o - r.w;
                const good = r.better === "lower" ? diff <= 0 : diff >= 0;
                return <tr key={r.label}><td>{r.label}</td><td className="mono">{r.fmt(r.w)}</td><td className="mono">{r.fmt(r.o)}</td>
                  <td className="mono" style={{ color: good ? "var(--ok)" : "var(--critical)" }}>{diff > 0 ? "+" : ""}{r.fmt(diff)}</td></tr>;
              })}</tbody>
            </table></div>
          </div>
          <div className="stack">
            {(["without", "with"] as const).map((w) => {
              const states = run.player.worlds[w].states[d];
              const counts = [0, 0, 0, 0, 0, 0];
              for (const ch of states) counts[Number(ch)] += 1;
              return (
                <div key={w}>
                  <p style={{ fontWeight: 700, margin: "0 0 6px", color: `var(--${w})` }}>{WORLD_LABEL[w]} · today</p>
                  <div className="mini-floor" role="img" aria-label={`${WORLD_LABEL[w]}: ${counts[5]} broken down, ${counts[4]} in planned maintenance, ${counts[2]} at risk`}>
                    {[...states].map((ch, i) => (
                      <div key={i} className={`mini-tile st-${ch}`} title={`${run.player.machines[i]}: ${STATE_INFO[Number(ch)].label}`}>
                        {STATE_INFO[Number(ch)].mark || run.player.machines[i].slice(2)}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
            <div className="row small">
              {STATE_INFO.map((s, i) => <span key={s.label} className="row" style={{ gap: 4 }}><span className={`mini-tile st-${i}`} style={{ width: 26, aspectRatio: "1.4" }}>{s.mark}</span>{s.label}</span>)}
            </div>
          </div>
        </div>

        <div className="grid grid-2" style={{ marginTop: 16 }}>
          <div>
            <h3>Breakdown hours, running total</h3>
            <div style={{ height: 220 }} role="img" aria-label={`Breakdown hours so far: without AI ${num(series.without.downtime[d])}, with OpEx ${num(series.with.downtime[d])}`}>
              <ResponsiveContainer>
                <LineChart data={series.weekly.filter((p) => p.day <= d)} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: "var(--muted)", fontSize: 12 }} interval={51} />
                  <YAxis tick={{ fill: "var(--muted)", fontSize: 12 }} width={56} />
                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
                  <Legend />
                  <Line dataKey="without" name="Without AI" stroke="var(--without)" dot={false} strokeWidth={2.5} isAnimationActive={false} />
                  <Line dataKey="with" name="With OpEx" stroke="var(--with)" dot={false} strokeWidth={2.5} strokeDasharray="6 3" isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div>
            <h3>OEE by month</h3>
            <div style={{ height: 220 }} role="img" aria-label="OEE by month for both factories">
              <ResponsiveContainer>
                <LineChart data={monthlyOee} margin={{ top: 6, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="month" tick={{ fill: "var(--muted)", fontSize: 12 }} />
                  <YAxis tick={{ fill: "var(--muted)", fontSize: 12 }} domain={["auto", "auto"]} unit="%" width={56} />
                  <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)" }} />
                  <Legend />
                  <Line dataKey="without" name="Without AI" stroke="var(--without)" dot={false} strokeWidth={2.5} isAnimationActive={false} />
                  <Line dataKey="with" name="With OpEx" stroke="var(--with)" dot={false} strokeWidth={2.5} strokeDasharray="6 3" isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        <h3 style={{ marginTop: 12 }}>What just happened</h3>
        <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
          {ticker.map((e, i) => (
            <li key={i}><b>Day {e.day + 1}</b> · <span style={{ color: `var(--${e.world})` }}>{WORLD_LABEL[e.world]}</span> · {e.machine} {e.component}:{" "}
              {e.kind === "failure" ? `broke down (${e.detail}), ${e.downtime_h} h lost` : `planned swap (${e.detail})`}</li>
          ))}
        </ul>
      </Card>
      {finished ? <Results run={run} /> : <p className="muted small" style={{ textAlign: "center" }}>Full results, the incident rewind and downloads appear when the replay ends (or press "Skip to results"). Overall OEE so far: {pct(grid.without.oee, 1)} vs {pct(grid.with.oee, 1)} over the full run.</p>}
    </>
  );
}
