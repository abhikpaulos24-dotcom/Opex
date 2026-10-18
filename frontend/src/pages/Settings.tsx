import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FastForward, FlaskRound, RotateCcw, SlidersHorizontal, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { AccessibilitySettings } from "../components/AccessibilityPanel";
import { Card, ConfirmDialog, EmptyState, ErrorBox, Segmented } from "../components/ui";
import { api } from "../lib/api";
import { titleCase } from "../lib/format";
import { useSession } from "../lib/session";

const ECON_LABELS: Record<string, string> = {
  electricity_inr_per_kwh: "Electricity (₹ per kWh)", grid_tco2_per_mwh: "Grid emissions (t CO₂ per MWh)",
  technician_inr_per_h: "Maintenance labour (₹ per hour)", overtime_multiplier: "Overtime multiplier after breakdowns",
  sensor_kit_per_machine_inr: "Sensor kit per machine (₹)", implementation_inr: "One-time setup (₹)",
  annual_cloud_inr: "Cloud cost per year (₹)", annual_support_inr: "Support per year (₹)",
};

export default function Settings() {
  const { can, user } = useSession();
  return (
    <div className="stack">
      <div className="page-head"><div><h1>Settings</h1><p>Signed in as {user?.full_name}, {user?.role_label}. Display settings are yours; the rest apply to the whole plant.</p></div></div>
      <Card title="Display and reading" id="a11y" sub="Font, size, spacing, colours, motion and language. Saved to your account."><AccessibilitySettings /></Card>
      <Priorities editable={can("edit_settings")} />
      {can("edit_settings") && <Economics />}
      {can("demo_controls") && <DemoControls />}
      {can("manage_users") && <UsersCard />}
    </div>
  );
}

function Priorities({ editable }: { editable: boolean }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["priorities"], queryFn: () => api("/api/settings/priorities") });
  const save = useMutation({
    mutationFn: (preset: string) => api("/api/settings/priorities", { method: "PUT", body: { preset } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["priorities"] }); queryClient.invalidateQueries({ queryKey: ["recommendation"] }); },
  });
  if (!data) return null;
  return (
    <Card title="Plant priorities" icon={<SlidersHorizontal aria-hidden />} id="priorities"
      sub="The default trade-off the decision engine uses. People can still switch priorities per decision on the machine page.">
      {editable ? (
        <Segmented label="Default priorities" value={data.preset} onChange={(v) => save.mutate(v)}
          options={Object.keys(data.presets).map((p) => ({ value: p, label: titleCase(p) }))} />
      ) : <p>Current: <b>{titleCase(data.preset)}</b> (a plant manager can change this).</p>}
      <table style={{ marginTop: 10, maxWidth: 420 }}><tbody>
        {Object.entries(data.weights).map(([k, v]: [string, any]) => <tr key={k}><td>{titleCase(k)}</td><td className="mono">{Math.round(v * 100)}%</td></tr>)}
      </tbody></table>
    </Card>
  );
}

function Economics() {
  const { data, refetch } = useQuery({ queryKey: ["economics"], queryFn: () => api("/api/settings/economics") });
  const [values, setValues] = useState<Record<string, number>>({});
  useEffect(() => { if (data) setValues(data); }, [data]);
  const save = useMutation({ mutationFn: () => api("/api/settings/economics", { method: "PUT", body: values }), onSuccess: () => refetch() });
  return (
    <Card title="Factory economics" id="econ" sub="Used for every rupee figure and the 5-year simulation. Defaults are sourced in the README.">
      <form className="grid grid-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {Object.keys(ECON_LABELS).map((k) => (
          <label key={k} className="field">{ECON_LABELS[k]}
            <input type="number" step="any" min={0} value={values[k] ?? ""} onChange={(e) => setValues({ ...values, [k]: Number(e.target.value) })} />
          </label>
        ))}
        <div style={{ alignSelf: "end" }}><button className="btn primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</button>{save.isSuccess && <span className="small" role="status" style={{ marginLeft: 10 }}>Saved. Every rupee figure now uses these.</span>}</div>
      </form>
    </Card>
  );
}

function DemoControls() {
  const queryClient = useQueryClient();
  const [machine, setMachine] = useState("M-09");
  const [fault, setFault] = useState("bearing");
  const [message, setMessage] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const done = (r: any) => { setMessage(r.message ?? `Plant clock now ${r.plant_time?.replace("T", " ")}`); queryClient.invalidateQueries(); };
  const reset = useMutation({
    mutationFn: () => api("/api/admin/demo/reset", { method: "POST" }),
    onSuccess: (r) => { setConfirmReset(false); done(r); },
  });
  const forward = useMutation({ mutationFn: (m: number) => api(`/api/admin/demo/fast-forward?minutes=${m}`, { method: "POST" }), onSuccess: done });
  const inject = useMutation({ mutationFn: () => api("/api/admin/demo/inject", { body: { machine_id: machine, fault } }), onSuccess: done });
  const error = reset.error || forward.error || inject.error;
  return (
    <Card title="Demo controls" icon={<FlaskRound aria-hidden />} id="demo" sub="For demos and training: move the plant clock or start a problem on purpose and watch OpEx catch it.">
      <div className="row">
        <button className="btn" onClick={() => forward.mutate(30)} disabled={forward.isPending}><FastForward size={18} aria-hidden /> +30 plant minutes</button>
        <button className="btn" onClick={() => forward.mutate(120)} disabled={forward.isPending}><FastForward size={18} aria-hidden /> +2 plant hours</button>
        <button className="btn danger" onClick={() => setConfirmReset(true)}><RotateCcw size={18} aria-hidden /> Reset to the scripted morning</button>
      </div>
      <div className="row" style={{ marginTop: 12, alignItems: "flex-end" }}>
        <label className="field">Machine
          <select value={machine} onChange={(e) => setMachine(e.target.value)}>
            {Array.from({ length: 24 }, (_, i) => `M-${String(i + 1).padStart(2, "0")}`).map((m) => <option key={m}>{m}</option>)}
          </select>
        </label>
        <label className="field">Problem
          <select value={fault} onChange={(e) => setFault(e.target.value)}>
            <option value="bearing">Spindle bearing wearing fast</option><option value="drive">Drive belt slipping</option>
            <option value="coolant">Coolant pump failing</option><option value="electrical">Power module fault</option>
            <option value="tool">Tool worn on a hard batch</option><option value="energy_waste">Idle with spindle on</option>
            <option value="sensor">Faulty vibration sensor</option>
          </select>
        </label>
        <button className="btn primary" onClick={() => inject.mutate()} disabled={inject.isPending}>Start this problem</button>
      </div>
      {message && <p role="status" className="small" style={{ marginTop: 8 }}>{message}</p>}
      {error ? <ErrorBox error={error} /> : null}
      <ConfirmDialog open={confirmReset} title="Reset the plant?" confirmLabel="Yes, reset" busy={reset.isPending}
        onConfirm={() => reset.mutate()} onCancel={() => setConfirmReset(false)}>
        <p>The plant clock and all 24 machines go back to the scripted morning, so any wear or repairs since then are undone. The decision log, alerts and settings are kept.</p>
      </ConfirmDialog>
    </Card>
  );
}

type Person = { id: string; email: string; full_name: string; role: string; role_label: string; is_active: boolean };

const ROLE_HELP: Record<string, string> = {
  manager: "Plant manager: everything an engineer can do, plus people, plant priorities, costs and demo controls.",
  engineer: "Maintenance engineer: approves or rejects any action, acknowledges alerts, writes investigations.",
};

function UsersCard() {
  const { user } = useSession();
  const { data, refetch } = useQuery({ queryKey: ["users"], queryFn: () => api<{ manageable_roles: string[]; people: Person[] }>("/api/users") });
  const roles = data?.manageable_roles ?? [];
  const blank = { email: "", full_name: "", role: roles[0] ?? "engineer" };
  const [form, setForm] = useState(blank);
  const create = useMutation({ mutationFn: () => api("/api/users", { body: { ...form, role: form.role || roles[0] } }), onSuccess: () => { setForm(blank); refetch(); } });
  const update = useMutation({ mutationFn: ({ id, body }: { id: string; body: object }) => api(`/api/users/${id}`, { method: "PATCH", body }), onSuccess: () => refetch() });
  return (
    <Card title="People and roles" icon={<Users aria-hidden />} id="users"
      sub={roles.map((r) => ROLE_HELP[r]).join(" ")}>
      {data?.people.length === 0 && <EmptyState title="Nobody added yet" hint="Add a person below. They sign in with their Google account, so there is no password to share." />}
      {!!data?.people.length && (
        <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th>Google account</th><th>Role</th><th>Active</th></tr></thead>
          <tbody>{data.people.map((u) => (
            <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td>
              <td><select aria-label={`Role for ${u.full_name}`} value={u.role} disabled={u.id === user?.id} onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value } })}>
                {roles.map((r) => <option key={r}>{r}</option>)}</select></td>
              <td><input type="checkbox" aria-label={`${u.full_name} active`} checked={u.is_active} disabled={u.id === user?.id} onChange={(e) => update.mutate({ id: u.id, body: { is_active: e.target.checked } })} /></td></tr>
          ))}</tbody>
        </table></div>
      )}
      <form className="grid grid-3" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <label className="field">Full name<input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required minLength={2} /></label>
        <label className="field">Their Google email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></label>
        <label className="field">Role<select value={form.role || roles[0]} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          {roles.map((r) => <option key={r}>{r}</option>)}</select></label>
        <div style={{ alignSelf: "end" }}><button className="btn primary" disabled={create.isPending || !roles.length}>Add person</button></div>
      </form>
      <p className="small muted">They sign in with that Google account. There are no passwords to share.</p>
      {(create.error || update.error) ? <ErrorBox error={create.error || update.error} /> : null}
    </Card>
  );
}
