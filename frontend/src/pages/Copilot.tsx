import { useMutation } from "@tanstack/react-query";
import { ArrowRight, ImagePlus, MessageSquareWarning, Mic, MicOff, Send, Sparkles, Volume2, X } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useSearchParams } from "react-router-dom";
import { LANGUAGES } from "../components/AccessibilityPanel";
import { AiTag, ErrorBox, More } from "../components/ui";
import { api } from "../lib/api";
import { canListen, canSpeak, listen, speak } from "../lib/speech";
import { useSession } from "../lib/session";

type Message = { role: "user" | "assistant"; text: string; source?: string; image?: string };

// Starting points grouped by what a person wants to get done, not by feature (and no need to type).
const STARTERS: { goal: string; prompts: string[] }[] = [
  { goal: "Find the problem", prompts: ["Which machine is most likely to fail?", "What should I fix first?", "Why is Line 3 underperforming?"] },
  { goal: "Weigh a decision", prompts: ["What happens if I shut down Machine 17?", "Prioritise production over energy for M-17"] },
  { goal: "Do the job", prompts: ["How do I inspect a spindle bearing?"] },
];
const ALL_STARTERS = STARTERS.flatMap((s) => s.prompts);
const MACHINE_ID = /\bM-\d{2}\b/g;

export default function Copilot() {
  const { prefs, setPref, config } = useSession();
  const [params] = useSearchParams();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [image, setImage] = useState<{ data: string; type: string } | null>(null);
  const [listening, setListening] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(ALL_STARTERS);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const asked = useRef(false);

  const chat = useMutation({
    mutationFn: (body: any) => api("/api/copilot/chat", { body }),
    onSuccess: (r: any) => {
      setMessages((m) => [...m, { role: "assistant", text: r.text, source: r.source }]);
      setSuggestions(r.suggestions?.length ? r.suggestions : ALL_STARTERS);
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

  /** "That's wrong" leads somewhere: a follow-up that says what is different, with the input ready to type into. */
  function correct() {
    setInput("That's not right. What actually happened is: ");
    inputRef.current?.focus();
  }

  const empty = messages.length === 0 && !chat.isPending;

  return (
    <div className="stack-lg">
      <div className="page-head">
        <div>
          <h1>Ask OpEx</h1>
          <p>In your own words, typed or spoken. Answers use live plant data, priced options and your SOPs, and always say which.</p>
        </div>
        <label className="field" style={{ minWidth: 180 }}>Answer language
          <select value={prefs.language} onChange={(e) => setPref("language", e.target.value)}>
            {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </label>
      </div>

      {!config?.gemini && (
        <p className="banner sev-medium small" role="note"><span className="text">Running without a Gemini key, so OpEx can answer common questions only. AUDIT.md explains how to add one.</span></p>
      )}

      <div className="stack">
        <div className="chat" aria-live="polite" aria-relevant="additions">
          {empty && (
            <div className="card quiet">
              <p style={{ fontWeight: 700, margin: 0 }}>Where would you like to start?</p>
              <p className="small muted" style={{ margin: "2px 0 12px" }}>Pick one, or type your own question below.</p>
              <div className="stack" style={{ gap: 12 }}>
                {STARTERS.map((g) => (
                  <div key={g.goal}>
                    <p className="eyebrow">{g.goal}</p>
                    <div className="chips">{g.prompts.map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role} fade-in`}>
              <span className="sr-only">{m.role === "user" ? "You said:" : "OpEx answered:"}</span>
              {m.image && <img src={m.image} alt="Photo you attached" style={{ maxWidth: 200, borderRadius: 8, display: "block", marginBottom: 6 }} />}
              <ReactMarkdown>{m.text}</ReactMarkdown>
              {m.role === "assistant" && <AnswerActions message={m} onCorrect={correct} onSpeak={() => speak(m.text, prefs.language, prefs.voiceRate)} />}
            </div>
          ))}
          {chat.isPending && <div className="msg assistant" role="status"><span className="loading" style={{ padding: 0 }}><Sparkles size={16} className="spin" aria-hidden /> Checking live plant data…</span></div>}
          {chat.error ? <ErrorBox error={chat.error} retry={() => { const last = [...messages].reverse().find((m) => m.role === "user"); if (last) send(last.text); }} /> : null}
          <div ref={endRef} />
        </div>

        {!empty && (
          <div className="chips" aria-label="Suggested follow-ups">
            {suggestions.slice(0, 4).map((s) => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}
          </div>
        )}

        <form onSubmit={onSubmit} className="composer">
          <label style={{ flex: 1, display: "flex" }}>
            <span className="sr-only">Your question</span>
            <input ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask anything about the plant, e.g. why did Line 3 drop today?" />
          </label>
          {canListen() && (
            <button type="button" className="btn icon-btn ghost" onClick={toggleVoice} aria-pressed={listening} aria-label={listening ? "Listening" : "Speak your question"} title="Speak">
              {listening ? <MicOff aria-hidden /> : <Mic aria-hidden />}
            </button>
          )}
          <label className="btn icon-btn ghost" aria-label="Attach a photo of a part" title="Attach a photo">
            <ImagePlus aria-hidden />
            <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={(e) => onPhoto(e.target.files?.[0])} />
          </label>
          <button className="btn primary" disabled={chat.isPending || !input.trim()}><Send size={18} aria-hidden /> Ask</button>
        </form>
        {image && (
          <div className="row small">
            <img src={image.data} alt="Selected photo" style={{ height: 48, borderRadius: 6 }} /> Photo attached. It goes with your next question.
            <button className="btn small ghost" onClick={() => setImage(null)} aria-label="Remove photo"><X size={16} aria-hidden /> Remove</button>
          </div>
        )}

        <More label="What OpEx can and can't answer">
          <div className="grid grid-2 small">
            <div>
              <p className="eyebrow">Can</p>
              <ul style={{ margin: 0 }}>
                <li>Say which machine is at risk, why, and what each option costs in rupees.</li>
                <li>Explain OEE, downtime and defects for a line or shift from live data.</li>
                <li>Look up your SOPs and past technician notes.</li>
                <li>Look at a photo of a part for visible defects.</li>
              </ul>
            </div>
            <div>
              <p className="eyebrow">Can't</p>
              <ul style={{ margin: 0 }}>
                <li>Change a machine. Decisions are made by a person on the machine page.</li>
                <li>Be certain. Predictions come with a chance and a confidence, never a promise.</li>
                <li>Know what it has not measured. If a sensor is missing, it says so.</li>
                <li>Remember you between visits beyond your saved preferences.</li>
              </ul>
            </div>
          </div>
        </More>
      </div>
    </div>
  );
}

/** Every answer leads somewhere: listen, open the machines it mentions, or say it is wrong. */
function AnswerActions({ message, onCorrect, onSpeak }: { message: Message; onCorrect: () => void; onSpeak: () => void }) {
  const machines = [...new Set(message.text.match(MACHINE_ID) ?? [])].slice(0, 3);
  return (
    <div className="meta">
      <AiTag source={message.source} />
      {machines.map((id) => (
        <Link key={id} className="btn small" to={`/machines/${id}`}>Open {id} <ArrowRight size={14} aria-hidden /></Link>
      ))}
      {canSpeak() && <button className="btn small ghost" onClick={onSpeak}><Volume2 size={16} aria-hidden /> Listen</button>}
      <button className="btn small ghost" onClick={onCorrect} title="Tell OpEx what is different"><MessageSquareWarning size={16} aria-hidden /> Not right?</button>
    </div>
  );
}
