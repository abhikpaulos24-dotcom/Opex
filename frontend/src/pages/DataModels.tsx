import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen, CloudCog, CloudUpload, Database, Download, FlaskConical, Search, Upload } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Card, ErrorBox, PageSkeleton } from "../components/ui";
import { api } from "../lib/api";
import { num, pct } from "../lib/format";
import { useSession } from "../lib/session";

const PIPELINE = [
  { step: "Collect", text: "4 public industrial datasets (AI4I 2020, NASA C-MAPSS, Azure PdM, Zenodo line OEE) + live sensor feed" },
  { step: "Clean", text: "Unit fixes, label repair, duplicate & spike removal, 1-minute resampling, quality report" },
  { step: "Learn", text: "3 models: failure modes (AI4I), remaining life (C-MAPSS), component precursors (Azure)" },
  { step: "Calibrate", text: "Failure rates, wear curves, repair times and line losses become simulator inputs" },
  { step: "Serve", text: "Live diagnosis, priced options, Gemini agents, 5-year simulation" },
];

export default function DataModels() {
  const { config, can } = useSession();
  const { data, error } = useQuery({ queryKey: ["data-overview"], queryFn: () => api("/api/data/overview") });
  if (error) return <ErrorBox error={error} />;
  if (!data) return <PageSkeleton label="Loading data and model results" />;
  const fm = data.models.failure_mode;
  const rul = data.models.remaining_life;
  const pre = data.models.precursor;

  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Data & models</h1><p>Where every number comes from: the data, what we did to it, and how well each model does on data it never saw.</p></div>
      </div>

      <Card title="Data pipeline" icon={<Database aria-hidden />} id="pipeline">
        <ol className="grid grid-3" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {PIPELINE.map((p, i) => (
            <li key={p.step} className="card" style={{ boxShadow: "none" }}>
              <span className="step-title"><span className="step-num">{i + 1}</span><b>{p.step}</b></span>
              <p className="small" style={{ marginTop: 6 }}>{p.text}</p>
            </li>
          ))}
        </ol>
        <p className="small muted" style={{ marginTop: 10 }}>Re-run it any time: <code>cd backend && python -m pipeline.run_all</code></p>
      </Card>

      <Card title="Models, tested on held-out data" icon={<FlaskConical aria-hidden />} id="models">
        <div className="grid grid-3">
          <ModelCard title="Failure-mode classifier" data="AI4I 2020 · 10,000 records" rows={[
            ["ROC AUC (any failure)", fm.roc_auc_any_failure?.toFixed(3)], ["Precision / recall", `${pct(fm.precision_at_threshold)} / ${pct(fm.recall_at_threshold)}`],
            ["Correct failure mode", pct(fm.mode_accuracy_on_failures)], ["Tool-wear failures caught", pct(fm.per_mode?.TWF?.recall)],
          ]} note="Tool-wear failures in AI4I are close to random, so OpEx also watches tool wear directly." />
          <ModelCard title="Remaining-life model" data="NASA C-MAPSS FD001 · 100 test engines" rows={[
            ["Test RMSE", `${rul.test_rmse_cycles?.toFixed(1)} cycles`], ["NASA score", num(rul.nasa_score)],
            ["10–90% band coverage", pct(rul.p10_p90_coverage)], ["Warned ≥10 cycles early", pct(rul.warning_recall)],
          ]} note="Uses health-index features only, so it transfers to any machine that has a health index." />
          <ModelCard title="Component precursor model" data={pre.dataset ?? "Azure PdM"} rows={
            Object.entries(pre.components ?? {}).map(([k, v]: [string, any]) => [`${k}: caught / false alarms per yr`, `${pct(v.event_recall)} / ${v.false_alarms_per_machine_year.toFixed(1)}`])
          } note="Azure PdM is a synthetic benchmark, so the simulator discounts these rates for real sensors (sensor coverage)." />
        </div>
      </Card>

      <Card title="Datasets and cleaning steps" id="datasets">
        <div className="grid grid-2">
          {data.datasets.map((d: any) => (
            <div key={d.name} className="card" style={{ boxShadow: "none" }}>
              <b>{d.name}</b><div className="small muted">{d.source}</div>
              <p className="small" style={{ margin: "6px 0" }}>{num(d.rows_in)} rows in{d.rows_out !== undefined ? ` · ${num(d.rows_out)} out` : ""} · {num(d.missing_cells)} missing cells · {num(d.duplicate_rows)} duplicates</p>
              <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>{d.steps.map((s: string) => <li key={s}>{s}</li>)}</ul>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Simulator calibration" id="calibration" sub="Every input of the 5-year simulation, with its source and method.">
        <div className="table-wrap"><table>
          <thead><tr><th>Parameter</th><th>Value</th><th>Source</th><th>How</th></tr></thead>
          <tbody>
            {Object.entries(data.calibration ?? {}).flatMap(([group, params]: [string, any]) =>
              Object.entries(params).flatMap(([key, p]: [string, any]) =>
                "value" in p ? [<CalRow key={`${group}.${key}`} name={key} p={p} />]
                  : Object.entries(p).map(([sub, q]: [string, any]) => <CalRow key={`${group}.${key}.${sub}`} name={`${key} · ${sub}`} p={q} />)))}
          </tbody>
        </table></div>
      </Card>

      <div className="grid grid-2">
        <UploadCard />
        <Card title="Google Cloud services" icon={<CloudCog aria-hidden />} id="cloud">
          <ul className="small stack" style={{ paddingLeft: 18, margin: 0, gap: 6 }}>
            <li><b>Gemini</b> ({config?.gemini_model ?? "not configured"}): copilot, incident-room agents, investigations, photo checks - {config?.gemini ? "on" : "off (rule-based fallback)"}</li>
            <li><b>Gemini embeddings</b>: semantic search in factory memory - {config?.gemini ? "on" : "off (keyword search)"}</li>
            <li><b>Cloud Run</b>: one service serves this app and the API</li>
            <li><b>BigQuery</b> (free sandbox): simulation days, decisions, incidents and alerts for analysis in Looker Studio - {config?.bigquery ? "on" : "off"}</li>
            <li><b>Cloud Storage</b>: uploaded files - {config?.cloud_storage ? "on" : "off (local folder)"}</li>
            <li><b>Pub/Sub</b>: critical alerts to other systems, sensor ingest push - {config?.pubsub ? "on" : "off"}</li>
            <li><b>Database</b>: {config?.database === "supabase" ? "Supabase Postgres" : "local SQLite (set DATABASE_URL for Supabase)"}</li>
          </ul>
          <hr className="divider" />
          <p className="small"><b>Downloads</b></p>
          <div className="row">{data.downloads.map((f: string) => <a key={f} className="btn small" href={`/api/data/download/${f}`} download><Download size={14} aria-hidden /> {f}</a>)}</div>
          {can("edit_settings") && <BigQueryExport enabled={!!config?.bigquery} />}
        </Card>
      </div>
      <Knowledge canAdd={can("manage_knowledge")} />
    </div>
  );
}

function BigQueryExport({ enabled }: { enabled: boolean }) {
  const exportNow = useMutation({
    mutationFn: () => api<{ tables: Record<string, number>; open_in_console: string }>("/api/data/export-bigquery", { method: "POST" }),
  });
  const r = exportNow.data;
  return (
    <>
      <hr className="divider" />
      <p className="small"><b>Send to BigQuery</b></p>
      {!enabled ? (
        <p className="small muted">Off. Set GOOGLE_CLOUD_PROJECT and BIGQUERY_DATASET in .env to use the free BigQuery sandbox (AUDIT.md explains how).</p>
      ) : (
        <>
          <p className="small muted">Replaces the decisions, incidents, alerts and latest simulation tables with a fresh copy.</p>
          <button className="btn small" onClick={() => exportNow.mutate()} disabled={exportNow.isPending}>
            <CloudUpload size={16} aria-hidden /> {exportNow.isPending ? "Sending…" : "Send a snapshot now"}
          </button>
        </>
      )}
      {exportNow.error ? <ErrorBox error={exportNow.error} /> : null}
      {r && (
        <p role="status" className="small" style={{ marginTop: 8 }}>
          Sent {Object.entries(r.tables).map(([table, rows]) => `${table} (${num(rows)} rows)`).join(", ")}.{" "}
          <a href={r.open_in_console} target="_blank" rel="noreferrer">Open in BigQuery</a>
        </p>
      )}
    </>
  );
}

function CalRow({ name, p }: { name: string; p: any }) {
  const value = typeof p.value === "object" ? Object.entries(p.value).map(([k, v]: [string, any]) => `${k} ${Number(v).toFixed(2)}`).join(", ")
    : typeof p.value === "number" ? (Math.abs(p.value) < 10 ? p.value.toFixed(3) : num(p.value, 1)) : String(p.value);
  return <tr><td>{name.replace(/_/g, " ")}</td><td className="mono small">{value} <span className="muted">{p.unit}</span></td><td className="small">{p.source}</td><td className="small muted">{p.method}</td></tr>;
}

function ModelCard({ title, data, rows, note }: { title: string; data: string; rows: [string, any][]; note: string }) {
  return (
    <div className="card" style={{ boxShadow: "none" }}>
      <b>{title}</b><div className="small muted">{data}</div>
      <table style={{ marginTop: 6 }}><tbody>{rows.map(([k, v]) => <tr key={k}><td className="small">{k}</td><td className="mono"><b>{v ?? "–"}</b></td></tr>)}</tbody></table>
      <p className="small muted" style={{ marginTop: 6 }}>{note}</p>
    </div>
  );
}

function UploadCard() {
  const [machine, setMachine] = useState("M-01");
  const [file, setFile] = useState<File | null>(null);
  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file!);
      return api(`/api/data/upload?machine_id=${machine}`, { form });
    },
  });
  const r: any = upload.data;
  return (
    <Card title="Check your own sensor file" icon={<Upload aria-hidden />} id="upload" sub="Upload a CSV: OpEx cleans it, scores the data quality and looks for anomalies against the machine's normal ranges.">
      <form className="stack" onSubmit={(e: FormEvent) => { e.preventDefault(); if (file) upload.mutate(); }}>
        <div className="row">
          <label className="field">Machine
            <select value={machine} onChange={(e) => setMachine(e.target.value)}>
              {Array.from({ length: 24 }, (_, i) => `M-${String(i + 1).padStart(2, "0")}`).map((m) => <option key={m}>{m}</option>)}
            </select>
          </label>
          <label className="field" style={{ flex: 1 }}>CSV file
            <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
        </div>
        <div className="row">
          <button className="btn primary" disabled={!file || upload.isPending}>{upload.isPending ? "Checking…" : "Check file"}</button>
          <a className="btn" href="/api/data/template.csv" download>Download template</a>
        </div>
      </form>
      {upload.error ? <ErrorBox error={upload.error} /> : null}
      {r && (
        <div style={{ marginTop: 12 }}>
          <p><b>{num(r.rows)} minutes of data · data health {r.data_health.score}/100</b></p>
          <ul className="small" style={{ paddingLeft: 18 }}>{r.steps.map((s: string) => <li key={s}>{s}</li>)}</ul>
          {r.data_health.issues.map((i: any) => <p key={i.text} className="small">⚠️ {i.text}</p>)}
          {r.anomalies.length === 0 ? <p className="small">No anomalies found.</p> :
            <ul className="small" style={{ paddingLeft: 18 }}>{r.anomalies.map((a: any) => <li key={a.signal}>{a.sentence}</li>)}</ul>}
        </div>
      )}
    </Card>
  );
}

function Knowledge({ canAdd }: { canAdd: boolean }) {
  const [q, setQ] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const docs = useQuery({ queryKey: ["knowledge"], queryFn: () => api("/api/data/knowledge") });
  const search = useMutation({ mutationFn: () => api(`/api/data/knowledge/search?q=${encodeURIComponent(q)}`) });
  const add = useMutation({ mutationFn: () => api("/api/data/knowledge", { body: { title, body, kind: "sop" } }), onSuccess: () => { setTitle(""); setBody(""); docs.refetch(); } });
  return (
    <Card title="Factory memory" icon={<BookOpen aria-hidden />} id="knowledge" sub={`SOPs, manuals and ${docs.data ? num(docs.data.chunks) : "…"} searchable passages including past technician notes.`}>
      <form className="row" onSubmit={(e) => { e.preventDefault(); if (q.trim()) search.mutate(); }}>
        <label className="field" style={{ flex: 1 }}><span className="sr-only">Search</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. coolant pressure low, LOTO, bearing preload" /></label>
        <button className="btn"><Search size={18} aria-hidden /> Search</button>
      </form>
      {search.data && (search.data as any[]).length === 0 && <p className="small muted">No matches. Try other words.</p>}
      {(search.data as any[])?.map((h: any, i: number) => (
        <div key={i} style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
          <b>{h.title}</b> <span className="small muted">· {h.section} · {h.kind.replace("_", " ")} · {h.method}</span>
          <p className="small" style={{ margin: 0 }}>{h.text.slice(0, 280)}{h.text.length > 280 ? "…" : ""}</p>
        </div>
      ))}
      <details style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>Library ({docs.data?.documents.length ?? 0} documents)</summary>
        <ul className="small">{docs.data?.documents.map((d: any) => <li key={d.id}>{d.title} <span className="muted">({d.kind}, {d.source})</span></li>)}</ul>
      </details>
      {canAdd && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer", fontWeight: 600 }}>Add a document</summary>
          <form className="stack" style={{ marginTop: 8 }} onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
            <label className="field">Title<input value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3} /></label>
            <label className="field">Text (use "## Heading" lines to split sections)<textarea value={body} onChange={(e) => setBody(e.target.value)} required minLength={20} rows={6} /></label>
            <button className="btn primary" disabled={add.isPending}>Add to memory</button>
            {add.error ? <ErrorBox error={add.error} /> : null}
          </form>
        </details>
      )}
    </Card>
  );
}
