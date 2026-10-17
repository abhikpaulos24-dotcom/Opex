// The four questions every machine page answers, in order (Detect → Diagnose → Predict → Decide).
export const STEPS = [
  { id: "detect", title: "What we detected" },
  { id: "why", title: "Why it is happening" },
  { id: "next", title: "What happens next" },
  { id: "decide", title: "What should we do?" },
] as const;

type StepId = (typeof STEPS)[number]["id"];

export function StepTitle({ step }: { step: StepId }) {
  const index = STEPS.findIndex((s) => s.id === step);
  return <span className="step-title"><span className="step-num" aria-hidden>{index + 1}</span><span><span className="sr-only">Step {index + 1}: </span>{STEPS[index].title}</span></span>;
}

export function StepNav() {
  return (
    <nav className="steps-nav" aria-label="Sections of this page">
      {STEPS.map((s, i) => <a key={s.id} href={`#${s.id}`}><span className="n" aria-hidden>{i + 1}</span>{s.title}</a>)}
      <a href="#photo">Photo check</a>
      <a href="#sensors">Sensor history</a>
    </nav>
  );
}
