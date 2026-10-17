import { useMutation } from "@tanstack/react-query";
import { ImagePlus, Mic, MicOff, Send, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { useSearchParams } from "react-router-dom";
import { LANGUAGES } from "../components/AccessibilityPanel";
import { ErrorBox } from "../components/ui";
import { api } from "../lib/api";
import { canListen, canSpeak, listen, speak } from "../lib/speech";
import { useSession } from "../lib/session";

type Message = { role: "user" | "assistant"; text: string; source?: string; image?: string };

const STARTERS = [
  "Which machine is most likely to fail?", "What should I fix first?", "Why is Line 3 underperforming?",
  "What happens if I shut down Machine 17?", "How do I inspect a spindle bearing?", "Prioritise production over energy for M-17",
];

export default function Copilot() {
  const { prefs, setPref, config } = useSession();
  const [params] = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [image, setImage] = useState<{ data: string; type: string } | null>(null);
  const [listening, setListening] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(STARTERS);
  const endRef = useRef<HTMLDivElement>(null);
  const asked = useRef(false);

  const chat = useMutation({
    mutationFn: (body: any) => api("/api/copilot/chat", { body }),
    onSuccess: (r: any) => {
      setMessages((m) => [...m, { role: "assistant", text: r.text, source: r.source }]);
      setSuggestions(r.suggestions);
    },
  });

  function send(text: string) {
    if (!text.trim() || chat.isPending) return;
    const history = messages.map((m) => ({ role: m.role, text: m.text }));
    setMessages((m) => [...m, { role: "user", text, image: image?.data }]);
    chat.mutate({ message: text, history, language: prefs.language, simple: prefs.simple,
      image_base64: image?.data, image_type: image?.type });
    setInput("");
    setImage(null);
  }

  useEffect(() => {
    const q = params.get("q");
    if (q && !asked.current) {
      asked.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, which must not reach React as a cleanup.
    endRef.current?.scrollIntoView({ behavior: prefs.motion === "reduce" ? "auto" : "smooth" });
  }, [messages, prefs.motion]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    send(input);
  }

  function onPhoto(file: File | undefined) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setImage({ data: String(reader.result), type: file.type });
    reader.readAsDataURL(file);
  }

  function toggleVoice() {
    if (listening) return;
    setListening(true);
    listen(prefs.language, (text) => setInput(text), () => setListening(false));
  }

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1>Ask OpEx</h1>
          <p>Ask in your own words - by typing or speaking. Answers come from live plant data, priced options and your SOPs.
            {!config?.gemini && " (Running without Gemini: common questions only. See AUDIT.md to add a key.)"}</p>
        </div>
        <label className="field" style={{ minWidth: 180 }}>Answer language
          <select value={prefs.language} onChange={(e) => setPref("language", e.target.value)}>
            {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </label>
      </div>

      <div className="card">
        <div className="chat" aria-live="polite" aria-relevant="additions">
          {messages.length === 0 && <p className="muted">Try one of these, or ask anything about the plant:</p>}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <span className="sr-only">{m.role === "user" ? "You said:" : "OpEx answered:"}</span>
              {m.image && <img src={m.image} alt="Photo you attached" style={{ maxWidth: 200, borderRadius: 8, display: "block", marginBottom: 6 }} />}
              <ReactMarkdown>{m.text}</ReactMarkdown>
              {m.role === "assistant" && (
                <div className="row" style={{ marginTop: 6 }}>
                  {canSpeak() && <button className="btn small ghost" onClick={() => speak(m.text, prefs.language, prefs.voiceRate)}><Volume2 size={16} aria-hidden /> Listen</button>}
                  <span className="small muted">{m.source === "gemini" ? "Gemini · grounded on plant tools" : "Rule-based answer"}</span>
                </div>
              )}
            </div>
          ))}
          {chat.isPending && <div className="msg" role="status">Thinking…</div>}
          {chat.error ? <ErrorBox error={chat.error} /> : null}
          <div ref={endRef} />
        </div>
        <div className="chips" style={{ margin: "14px 0" }}>
          {suggestions.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
        </div>
        <form onSubmit={onSubmit} className="row" style={{ alignItems: "flex-end" }}>
          <label className="field" style={{ flex: 1, minWidth: 220 }}>
            <span className="sr-only">Your question</span>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. What caused today's production loss?" />
          </label>
          {canListen() && (
            <button type="button" className="btn icon-btn" onClick={toggleVoice} aria-pressed={listening} aria-label={listening ? "Listening" : "Speak your question"}>
              {listening ? <MicOff aria-hidden /> : <Mic aria-hidden />}
            </button>
          )}
          <label className="btn icon-btn" aria-label="Attach a photo of a part">
            <ImagePlus aria-hidden />
            <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => onPhoto(e.target.files?.[0])} />
          </label>
          <button className="btn primary" disabled={chat.isPending || !input.trim()}><Send size={18} aria-hidden /> Ask</button>
        </form>
        {image && (
          <div className="row small" style={{ marginTop: 8 }}>
            <img src={image.data} alt="Selected photo" style={{ height: 48, borderRadius: 6 }} /> Photo attached
            <button className="btn small ghost" onClick={() => setImage(null)} aria-label="Remove photo"><X size={16} aria-hidden /></button>
          </div>
        )}
      </div>
    </div>
  );
}
