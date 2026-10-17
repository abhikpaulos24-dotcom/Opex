"""Ask OpEx: a natural-language factory copilot.

Gemini answers by calling OpEx's own tools (live status, machine diagnosis, priced what-if
options, factory memory search, line performance, the 5-year simulation), so every number in
an answer comes from the plant's data. Supports any of six Indian languages, voice in/out
(handled in the browser) and photos of parts for a visual check.

Without Gemini, a small intent router answers the common questions from the same tools.
"""

import logging
import re

from sqlalchemy.orm import Session

from app.analytics.factory_report import factory_report
from app.analytics.machine_report import machine_report
from app.decisions.ranking import WEIGHT_PRESETS
from app.decisions.service import build_recommendation
from app.knowledge.search import get_index
from app.plant.factory import MACHINES_BY_ID

from . import gemini
from .agents import LANGUAGES

log = logging.getLogger(__name__)

SYSTEM = """You are OpEx, the AI operations copilot of a CNC automotive-component plant in India.
You help operators, maintenance engineers and the plant manager.
Rules:
- Always call a tool to get facts. Never guess machine numbers, risks, costs or history.
- Lead with the answer in one sentence, then 2-5 short bullet points. Use ₹ and lakh/K for money.
- When recommending an action, say it needs human approval in the Actions page.
- If a photo is attached, describe visible defects (burrs, chatter marks, burns, cracks, wear) and link them to
  likely machine causes, then suggest the relevant SOP. Say clearly that a photo is not a measurement.
- Safety first: anything involving opening guards or panels needs Lockout-Tagout (SOP-MNT-009).
- Machine IDs look like M-17. Lines are L1-L4."""


def _tools(db: Session) -> list:
    def get_factory_status() -> dict:
        """Live plant status: OEE, health scores, machines down, and the ranked list of risks."""
        o = factory_report()
        return {
            "plant_time": o["plant_time"],
            "shift": o["shift"],
            "kpis": o["kpis"],
            "health": o["health"],
            "risk_level": o["risk_level"],
            "top_risks": [{k: r[k] for k in ("id", "severity", "p_fail_8h", "headline", "state")} for r in o["risks"]],
            "maintenance_due": o["maintenance"]["due_soon"],
        }

    def get_machine_details(machine_id: str) -> dict:
        """Full diagnosis of one machine (e.g. 'M-17'): anomalies, root cause, failure prediction, data health."""
        a = machine_report(_normalise(machine_id))
        return {
            "machine": a["machine"],
            "state": a["state"],
            "anomalies": [x["sentence"] for x in a["anomalies"]],
            "root_cause": a["root_cause"]["top"],
            "chain": [c["text"] for c in a["root_cause"]["chain"]],
            "similar_incidents": a["root_cause"]["memory"].get("sentence"),
            "prediction": a["prediction"],
            "data_health": a["data_health"],
            "quality": a["quality"],
            "impact": a["impact"],
            "maintenance_plan": a["maintenance_plan"],
        }

    def compare_actions(machine_id: str, priority: str = "balanced") -> dict:
        """Priced intervention options for a machine and the best one. priority: balanced, production_first,
        quality_first, energy_saver or safety_first."""
        preset = priority if priority in WEIGHT_PRESETS else "balanced"
        r = build_recommendation(db, _normalise(machine_id), preset=preset, save=False)
        if not r["needed"]:
            return {"message": r["message"]}
        return {
            "recommendation": r["recommendation"],
            "priority": preset,
            "options": [
                {
                    k: o[k]
                    for k in (
                        "title",
                        "downtime_h",
                        "p_fail",
                        "total_inr",
                        "production_loss_inr",
                        "maintenance_cost_inr",
                        "energy_change_pct",
                    )
                }
                for o in r["options"]
            ],
        }

    def search_factory_memory(query: str) -> list:
        """Search SOPs, manuals and past maintenance notes. Use for 'how do I...' and 'have we seen this before'."""
        return [{k: h[k] for k in ("title", "section", "kind", "text")} for h in get_index().search(query, limit=5)]

    def line_performance(line_id: str) -> dict:
        """OEE, availability, performance, quality and the worst machine for a line (L1, L2, L3 or L4)."""
        line_id = line_id.upper().replace("LINE", "L").replace(" ", "")
        o = factory_report()
        line = next((x for x in o["lines"] if x["id"] == line_id), None)
        if line is None:
            return {"error": f"Unknown line {line_id}"}
        worst = machine_report(line["worst_machine"])
        return {
            **line,
            "worst_machine_root_cause": worst["root_cause"]["top"],
            "worst_machine_state": worst["state"],
            "worst_machine_anomalies": [x["sentence"] for x in worst["anomalies"][:3]],
        }

    def latest_simulation_summary() -> dict:
        """Results of the most recent 5-year with/without-OpEx simulation, if one has been run."""
        from sqlalchemy import select

        from app.db.models import SimulationRun

        run = db.scalars(select(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(1)).first()
        return run.summary["delta"] if run else {"message": "No simulation has been run yet."}

    return [
        get_factory_status,
        get_machine_details,
        compare_actions,
        search_factory_memory,
        line_performance,
        latest_simulation_summary,
    ]


def _normalise(machine_id: str) -> str:
    digits = re.findall(r"\d+", machine_id)
    candidate = f"M-{int(digits[0]):02d}" if digits else machine_id
    if candidate not in MACHINES_BY_ID:
        raise ValueError(f"No machine called {machine_id}")
    return candidate


def answer(
    db: Session,
    message: str,
    history: list[dict],
    language: str = "en",
    simple: bool = False,
    image: tuple[bytes, str] | None = None,
) -> dict:
    if gemini.enabled():
        from google.genai import types

        contents = []
        for turn in history[-8:]:
            role = "model" if turn.get("role") == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=turn.get("text", ""))]))
        parts = [types.Part.from_text(text=message)]
        if image:
            parts.append(types.Part.from_bytes(data=image[0], mime_type=image[1]))
        contents.append(types.Content(role="user", parts=parts))
        style = f"Reply in {LANGUAGES.get(language, 'English')}." + (
            " Use very simple words and short sentences." if simple else ""
        )
        text = gemini.generate(contents, SYSTEM + "\n" + style, tools=_tools(db), temperature=0.2)
        if text:
            return {"text": text, "source": "gemini", "suggestions": _suggestions(message)}
    text = _fallback(db, message)
    if image:
        text += "\n\n_Photo checks need Gemini - add a key in .env (see AUDIT.md)._"
    return {"text": text, "source": "rules", "suggestions": _suggestions(message)}


def _suggestions(message: str) -> list[str]:
    pool = [
        "Which machine is most likely to fail?",
        "What should I fix first?",
        "Why is Line 3 underperforming?",
        "What happens if I shut down Machine 17?",
        "How do I inspect a spindle bearing?",
        "Show me similar incidents for M-17",
        "Prioritise production over energy for M-17",
    ]
    return [p for p in pool if p.lower() != message.lower()][:4]


def _fallback(db: Session, message: str) -> str:
    """Rule-based answers so the copilot still helps without Gemini."""
    tools = {t.__name__: t for t in _tools(db)}
    text = message.lower()
    machine = re.search(r"(?:m-?|machine\s*)(\d{1,2})\b", text)
    line = re.search(r"line\s*(\d)", text)

    if machine and re.search(r"shut|stop|what if|what happens|option|action|prioriti", text):
        priority = (
            "production_first"
            if "production" in text
            else "quality_first"
            if "quality" in text
            else "energy_saver"
            if "energy" in text
            else "balanced"
        )
        r = tools["compare_actions"](machine.group(1), priority)
        if "message" in r:
            return r["message"]
        rec = r["recommendation"]
        rows = "\n".join(
            f"- **{o['title']}**: {o['downtime_h']:.1f} h downtime, {o['p_fail']:.0%} chance of failure, "
            f"₹{o['total_inr']:,.0f} expected impact"
            for o in r["options"][:5]
        )
        return (
            f"**Recommended: {rec['headline']}** (priority: {priority.replace('_', ' ')}). "
            f"Value protected ₹{rec['value_protected_inr']:,.0f}.\n\n{rows}\n\nApprove it on the Actions page."
        )
    if machine and re.search(r"similar|before|history|seen", text):
        d = tools["get_machine_details"](machine.group(1))
        return d["similar_incidents"] or "No similar incidents found."
    if machine:
        d = tools["get_machine_details"](machine.group(1))
        p = d["prediction"]
        lines = [
            f"**{d['machine']['id']}** is {d['state']}. Chance of failure in 8 h: **{p['p_fail_8h']:.0%}**"
            + (f", window {p['window']}" if p["window"] else "")
            + f" (confidence {p['confidence']:.0%})."
        ]
        lines += [f"- {s}" for s in d["anomalies"][:3]]
        if d["root_cause"]:
            lines.append(f"- Likely cause: {d['root_cause']['name']}")
        return "\n".join(lines)
    if line:
        r = tools["line_performance"](f"L{line.group(1)}")
        if "error" in r:
            return r["error"]
        cause = r["worst_machine_root_cause"]
        return (
            f"**{r['name']}** OEE this shift is {r['oee']:.0%} (availability {r['availability']:.0%}, "
            f"performance {r['performance']:.0%}, quality {r['quality']:.1%}). The weakest machine is "
            f"**{r['worst_machine']}**"
            + (f": {cause['name'].lower()}." if cause else ".")
            + "".join(f"\n- {a}" for a in r["worst_machine_anomalies"])
        )
    if re.search(r"how do i|how to|inspect|procedure|sop|steps|replace", text):
        hits = tools["search_factory_memory"](message)
        if not hits:
            return "I could not find a procedure for that."
        top = hits[0]
        return f"From **{top['title']} - {top['section']}**:\n\n{top['text'][:900]}"
    if re.search(r"simulat|5.year|roi|five", text):
        s = tools["latest_simulation_summary"]()
        if "message" in s:
            return s["message"]
        return (
            f"Over the simulated period OpEx avoided **{s['failures_avoided']:.0f} breakdowns** and "
            f"**{s['downtime_avoided_h']:,.0f} h** of downtime, net benefit ₹{s['net_benefit_inr'] / 1e5:,.1f} lakh, "
            f"ROI {s['roi_multiple']:.1f}x."
        )
    status = tools["get_factory_status"]()
    risks = "\n".join(
        f"{i}. **{r['id']}** - {r['severity']} - {r['headline']}" for i, r in enumerate(status["top_risks"][:5], 1)
    )
    return (
        f"Plant OEE this shift is **{status['kpis']['oee']:.0%}**, {status['kpis']['running']}/"
        f"{status['kpis']['machines']} machines running. What to worry about first:\n\n{risks}"
    )
