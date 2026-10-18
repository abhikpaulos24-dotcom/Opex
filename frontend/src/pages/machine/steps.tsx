import { useEffect, useState } from "react";

// The four questions every machine page answers, in order (Detect → Diagnose → Predict → Decide).
export const STEPS = [
  { id: "detect", title: "What we noticed" },
  { id: "why", title: "Why" },
  { id: "next", title: "What happens next" },
  { id: "decide", title: "What to do" },
] as const;

type StepId = (typeof STEPS)[number]["id"];

export function StepTitle({ step }: { step: StepId }) {
  const index = STEPS.findIndex((s) => s.id === step);
  return <span className="step-title"><span className="step-num" aria-hidden>{index + 1}</span><span><span className="sr-only">Step {index + 1}: </span>{STEPS[index].title}</span></span>;
}

const EXTRA = [{ id: "photo", title: "Photo check" }, { id: "sensors", title: "Sensor history" }];

/** Jump links that also show where you are on the page. */
export function StepNav() {
  const [current, setCurrent] = useState<string>("detect");
  useEffect(() => {
    const ids = [...STEPS.map((s) => s.id), ...EXTRA.map((e) => e.id)];
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]) setCurrent(visible[0].target.id);
    }, { rootMargin: "-120px 0px -60% 0px" });
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);
  return (
    <nav className="steps-nav" aria-label="Sections of this page">
      {STEPS.map((s, i) => (
        <a key={s.id} href={`#${s.id}`} className={current === s.id ? "current" : ""} aria-current={current === s.id ? "location" : undefined}>
          <span className="n" aria-hidden>{i + 1}</span>{s.title}
        </a>
      ))}
      {EXTRA.map((e) => <a key={e.id} href={`#${e.id}`} className={current === e.id ? "current" : ""}>{e.title}</a>)}
    </nav>
  );
}
