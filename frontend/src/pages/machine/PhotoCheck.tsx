import { useMutation } from "@tanstack/react-query";
import { Camera, CheckCircle2, OctagonAlert, Ruler } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, ErrorBox, Loading } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/session";

type PhotoResult =
  | { available: false; message: string }
  | {
      available: true;
      verdict: "looks_good" | "check_on_gauge" | "reject";
      summary: string;
      defects: { type: string; where: string; severity: string }[];
      likely_machine_cause: string;
      next_steps: string[];
      stored_at: string;
    };

const VERDICT = {
  looks_good: { label: "Looks good", css: "sev-ok", icon: CheckCircle2 },
  check_on_gauge: { label: "Check it on the gauge", css: "sev-medium", icon: Ruler },
  reject: { label: "Reject this part", css: "sev-critical", icon: OctagonAlert },
};

/** Anyone on the floor takes a photo of a finished part; Gemini looks for visible defects and links them to this machine. */
export function PhotoCheck({ machineId }: { machineId: string }) {
  const { prefs, config } = useSession();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const check = useMutation({
    mutationFn: (photo: File) => {
      const form = new FormData();
      form.append("file", photo);
      return api<PhotoResult>(`/api/machines/${machineId}/photo-check?language=${prefs.language}`, { form });
    },
  });
  const r = check.data;

  return (
    <Card title="Photo check of a part" icon={<Camera aria-hidden />} id="photo"
      sub="Take a photo of a finished part. Gemini looks for burrs, chatter marks, burns and cracks, and links them to this machine's signals.">
      {!config?.gemini && <p className="small muted">Needs a free Gemini key (see AUDIT.md). Without it the photo is saved but not checked.</p>}
      <div className="row" style={{ alignItems: "flex-end" }}>
        <label className="field" style={{ flex: 1, minWidth: 220 }}>Photo (JPG, PNG or WEBP, up to 5 MB)
          <input type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); check.reset(); }} />
        </label>
        <button className="btn primary" disabled={!file || check.isPending} onClick={() => file && check.mutate(file)}>
          {check.isPending ? "Checking…" : "Check this part"}
        </button>
      </div>
      {preview && <img src={preview} alt="The part you selected" style={{ maxWidth: 240, maxHeight: 180, borderRadius: 10, marginTop: 10, objectFit: "cover" }} />}
      {check.isPending && <Loading label="Looking at the photo for burrs, chatter, burns and cracks" />}
      {check.error ? <ErrorBox error={check.error} /> : null}
      {r && !r.available && <p role="status" className="banner sev-info" style={{ marginTop: 10 }}><span className="text">{r.message}</span></p>}
      {r?.available && <Verdict result={r} />}
    </Card>
  );
}

function Verdict({ result }: { result: Extract<PhotoResult, { available: true }> }) {
  const v = VERDICT[result.verdict];
  const Icon = v.icon;
  return (
    <div role="status" style={{ marginTop: 12 }}>
      <span className={`badge ${v.css}`}><Icon size={15} aria-hidden /> {v.label}</span>
      <p style={{ margin: "8px 0" }}>{result.summary}</p>
      {result.defects.length > 0 && (
        <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
          {result.defects.map((d) => <li key={`${d.type}-${d.where}`}><b>{d.type}</b> ({d.severity}) at {d.where}</li>)}
        </ul>
      )}
      {result.likely_machine_cause && <p className="small"><b>Likely machine cause:</b> {result.likely_machine_cause}</p>}
      {result.next_steps.length > 0 && (
        <><p className="small" style={{ fontWeight: 700, margin: "6px 0 2px" }}>Next steps</p>
          <ol className="small" style={{ paddingLeft: 18, margin: 0 }}>{result.next_steps.map((s) => <li key={s}>{s}</li>)}</ol></>
      )}
      <p className="small muted" style={{ marginTop: 6 }}>Photo saved for traceability. AI can miss defects: confirm rejects with a gauge.</p>
    </div>
  );
}
