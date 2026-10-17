import { useSession, type Prefs } from "../lib/session";
import { Dialog, Segmented } from "./ui";

export const LANGUAGES = [
  { value: "en", label: "English" }, { value: "hi", label: "हिन्दी" }, { value: "te", label: "తెలుగు" },
  { value: "ta", label: "தமிழ்" }, { value: "kn", label: "ಕನ್ನಡ" }, { value: "mr", label: "मराठी" },
];

export function AccessibilitySettings() {
  const { prefs, setPref } = useSession();
  return (
    <div className="stack">
      <Field label="Colours">
        <Segmented<Prefs["theme"]> label="Colours" value={prefs.theme} onChange={(v) => setPref("theme", v)}
          options={[{ value: "system", label: "Match device" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }, { value: "contrast", label: "High contrast" }]} />
      </Field>
      <Field label="Text size">
        <Segmented<Prefs["text"]> label="Text size" value={prefs.text} onChange={(v) => setPref("text", v)}
          options={[{ value: "m", label: "Normal" }, { value: "l", label: "Large" }, { value: "xl", label: "Extra large" }]} />
      </Field>
      <Field label="Reading font" hint="Atkinson Hyperlegible is designed for low vision; Lexend can help with dyslexia.">
        <Segmented<Prefs["font"]> label="Reading font" value={prefs.font} onChange={(v) => setPref("font", v)}
          options={[{ value: "atkinson", label: "Atkinson Hyperlegible" }, { value: "lexend", label: "Lexend" }]} />
      </Field>
      <Field label="Letter and line spacing">
        <Segmented<Prefs["spacing"]> label="Spacing" value={prefs.spacing} onChange={(v) => setPref("spacing", v)}
          options={[{ value: "normal", label: "Normal" }, { value: "wide", label: "Wide" }]} />
      </Field>
      <Field label="Motion">
        <Segmented<Prefs["motion"]> label="Motion" value={prefs.motion} onChange={(v) => setPref("motion", v)}
          options={[{ value: "full", label: "Animations on" }, { value: "reduce", label: "Reduce motion" }]} />
      </Field>
      <label className="row"><input type="checkbox" checked={prefs.simple} onChange={(e) => setPref("simple", e.target.checked)} />
        <span><b>Simple words</b><br /><span className="small muted">Shorter AI explanations in everyday language.</span></span></label>
      <label className="row"><input type="checkbox" checked={prefs.focus} onChange={(e) => setPref("focus", e.target.checked)} />
        <span><b>Focus mode</b><br /><span className="small muted">Hide extra panels; show only what needs attention.</span></span></label>
      <label className="field">Language for AI answers and read-aloud
        <select value={prefs.language} onChange={(e) => setPref("language", e.target.value)}>
          {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
        </select>
      </label>
      <label className="field">Read-aloud speed: {prefs.voiceRate.toFixed(1)}×
        <input type="range" min={0.6} max={1.4} step={0.1} value={prefs.voiceRate} onChange={(e) => setPref("voiceRate", Number(e.target.value))} />
      </label>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <p style={{ fontWeight: 700, marginBottom: 6 }}>{label}</p>
      {children}
      {hint && <p className="small muted" style={{ marginTop: 6 }}>{hint}</p>}
    </div>
  );
}

export function AccessibilityPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Display and accessibility">
      <p className="muted">Changes apply instantly and are saved to your account.</p>
      <AccessibilitySettings />
    </Dialog>
  );
}
