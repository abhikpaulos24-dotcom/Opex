"""The Incident Room: three Gemini agents with one job each, reviewing every serious issue
before a person decides.

  Diagnostician   - weighs the sensor evidence, past incidents and data quality -> root cause
  Planner         - explains the priced options and the trade-off in manager language
  Safety officer  - pulls the SOP steps that must happen before anyone touches the machine

Agents only see facts OpEx has already computed (machine report, priced options, retrieved SOP
text) and are told never to invent numbers. If Gemini is not configured, each agent falls back
to a rule-based version so the room still works offline. A human always makes the final call.
"""

import json
import logging

from app.knowledge.search import get_index

from . import gemini

log = logging.getLogger(__name__)

LANGUAGES = {"en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "mr": "Marathi"}
GROUNDING = (
    "Use ONLY the facts in the JSON you are given. Never invent numbers, part names or history. "
    "If something is uncertain, say so. Write for a busy shop-floor team."
)


def _style(language: str, simple: bool) -> str:
    style = f"Answer in {LANGUAGES.get(language, 'English')}."
    if simple:
        style += " Use very simple words and short sentences (reading age 12). Avoid jargon."
    return style


def _facts(report: dict) -> dict:
    p = report["prediction"]
    return {
        "machine": report["machine"],
        "state": report["state"],
        "anomalies": [a["sentence"] for a in report["anomalies"][:5]],
        "chain_of_impact": [c["text"] for c in report["root_cause"]["chain"]],
        "cause_candidates": [{"cause": c["name"], "match": c["match"]} for c in report["root_cause"]["candidates"]],
        "similar_incidents": report["root_cause"]["memory"].get("sentence"),
        "past_technician_notes": [m["technician_note"] for m in report["root_cause"]["memory"].get("matches", [])[:4]],
        "prediction": {k: p[k] for k in ("p_fail_8h", "window", "severity", "confidence", "focus_component")},
        "data_health": {
            "score": report["data_health"]["score"],
            "issues": [i["text"] for i in report["data_health"]["issues"]],
        },
        "quality": report["quality"]["sentence"] if report.get("quality") else None,
    }


DIAGNOSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string"},
        "certainty": {"type": "string", "enum": ["high", "medium", "low"]},
        "evidence_for": {"type": "array", "items": {"type": "string"}},
        "evidence_against": {"type": "array", "items": {"type": "string"}},
        "check_first": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["root_cause", "certainty", "evidence_for", "check_first"],
}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "why": {"type": "string"},
        "trade_offs": {"type": "array", "items": {"type": "string"}},
        "if_we_do_nothing": {"type": "string"},
    },
    "required": ["headline", "why", "trade_offs", "if_we_do_nothing"],
}
SAFETY_SCHEMA = {
    "type": "object",
    "properties": {
        "before_starting": {"type": "array", "items": {"type": "string"}},
        "sop_references": {"type": "array", "items": {"type": "string"}},
        "concerns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["before_starting", "sop_references"],
}


def diagnostician(report: dict, language: str = "en", simple: bool = False) -> dict:
    facts = _facts(report)
    result = gemini.generate(
        f"Diagnose this machine issue. Facts:\n{json.dumps(facts, default=str)}",
        system="You are the Diagnostician in a CNC plant's incident room: a senior reliability engineer. "
        "Connect the signals into ONE most likely root cause, list evidence for and against "
        "(including data-quality doubts) and what a technician should check first. "
        + GROUNDING
        + " "
        + _style(language, simple),
        json_schema=DIAGNOSIS_SCHEMA,
    )
    if result:
        return {"agent": "Diagnostician", "source": "gemini", **result}
    top = report["root_cause"]["top"]
    memory = report["root_cause"]["memory"]
    return {
        "agent": "Diagnostician",
        "source": "rules",
        "root_cause": top["name"] if top else "No clear fault pattern",
        "certainty": "high" if top and top["match"] > 0.8 else "medium",
        "evidence_for": facts["anomalies"][:3] + ([memory["sentence"]] if memory.get("count") else []),
        "evidence_against": facts["data_health"]["issues"],
        "check_first": [
            "Confirm the reading with a portable instrument",
            "Check lubrication / coolant / belt as relevant",
        ],
    }


def planner(recommendation: dict, language: str = "en", simple: bool = False) -> dict:
    options = [
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
                "confidence",
                "safety_blocked",
            )
        }
        for o in recommendation["options"]
    ]
    facts = {
        "recommended": recommendation["recommendation"],
        "options": options,
        "priorities": recommendation["weights"],
        "hours_to_maintenance_window": recommendation["hours_to_window"],
        "hours_to_shift_change": recommendation["hours_to_shift"],
        "cause": recommendation["cause"]["name"],
    }
    result = gemini.generate(
        f"Explain this decision to the plant manager. Facts:\n{json.dumps(facts, default=str)}",
        system="You are the Planner in a CNC plant's incident room. OpEx's decision engine has already priced every "
        "option in rupees and ranked them with the plant's priorities. Explain why the recommended option wins, "
        "the main trade-offs, and what happens if nobody acts. Quote rupee amounts exactly as given "
        "(use lakh/K formatting is fine). " + GROUNDING + " " + _style(language, simple),
        json_schema=PLAN_SCHEMA,
    )
    if result:
        return {"agent": "Planner", "source": "gemini", **result}
    rec = recommendation["recommendation"]
    best, worst = recommendation["options"][0], max(recommendation["options"], key=lambda o: o["total_inr"])
    return {
        "agent": "Planner",
        "source": "rules",
        "headline": rec["headline"],
        "why": " ".join(rec["why"]),
        "trade_offs": [
            f"{o['title']}: ₹{o['total_inr']:,.0f} expected, {o['p_fail']:.0%} chance of failure"
            for o in recommendation["options"][:3]
        ],
        "if_we_do_nothing": f"Worst option costs about ₹{worst['total_inr']:,.0f} versus ₹{best['total_inr']:,.0f}.",
    }


def safety_officer(recommendation: dict, language: str = "en", simple: bool = False) -> dict:
    action = recommendation["options"][0]["title"]
    component = recommendation["cause"]["component"] or ""
    sources = get_index().search(
        f"lockout safety {component} {recommendation['cause']['name']} {action}", limit=4, kinds=("sop", "manual")
    )
    facts = {
        "action": action,
        "machine": recommendation["machine_id"],
        "cause": recommendation["cause"]["name"],
        "procedures": [{"doc": s["title"], "section": s["section"], "text": s["text"][:1200]} for s in sources],
    }
    result = gemini.generate(
        f"List the safety steps for this job. Facts:\n{json.dumps(facts)}",
        system="You are the Safety officer in a CNC plant's incident room. From the procedures given, list what must "
        "happen before anyone starts this job (lockout-tagout, cooling, PPE), cite the SOP numbers, and flag "
        "any concern. Never make up a procedure that is not in the text. " + _style(language, simple),
        json_schema=SAFETY_SCHEMA,
        fast=True,
    )
    if result:
        return {"agent": "Safety officer", "source": "gemini", "documents": [s["title"] for s in sources], **result}
    return {
        "agent": "Safety officer",
        "source": "rules",
        "documents": [s["title"] for s in sources],
        "before_starting": [
            "Apply Lockout-Tagout before opening guards or panels (SOP-MNT-009)",
            "Wait for the spindle to stop and cool; wear gloves and glasses",
        ],
        "sop_references": sorted({s["title"].split(" ")[0] for s in sources}),
        "concerns": [],
    }


def incident_room(report: dict, recommendation: dict, language: str = "en", simple: bool = False) -> list[dict]:
    return [
        diagnostician(report, language, simple),
        planner(recommendation, language, simple),
        safety_officer(recommendation, language, simple),
    ]


def investigation_report(incident: dict, decisions: list[dict], language: str = "en") -> str:
    facts = {"incident": incident, "decisions": decisions}
    text = gemini.generate(
        f"Write the incident investigation. Facts:\n{json.dumps(facts, default=str)}",
        system="You write incident investigations for a CNC plant. Use these Markdown headings exactly: "
        "What happened, When did it start, What changed, Root cause, Impact, Actions that were possible, "
        "Action taken, Did it work. Keep each section to 1-3 sentences. " + GROUNDING + " " + _style(language, False),
        max_tokens=1500,
    )
    if text:
        return text
    snap = incident.get("snapshot", {})
    prediction = snap.get("prediction", {})
    chain = " → ".join(c["text"] for c in snap.get("root_cause", {}).get("chain", []))
    taken = decisions[0] if decisions else None
    changes = [a.get("sentence", "") for a in snap.get("anomalies", [])[:3]]
    return "\n".join(
        [
            f"## What happened\n{incident['title']}.",
            f"## When did it start\nFirst flagged at plant time {incident['started_plant_time']}.",
            "## What changed\n" + ("; ".join(changes) or "No sensor changes recorded."),
            f"## Root cause\n{incident.get('root_cause') or 'Not confirmed'}. Signal chain: {chain or 'n/a'}.",
            f"## Impact\nChance of failure {prediction.get('p_fail_8h', 0):.0%} within 8 h; cost if it failed about "
            f"₹{prediction.get('failure_cost_inr', 0):,.0f}.",
            "## Actions that were possible\nSee the options table recorded with the recommendation.",
            "## Action taken\n"
            + (
                f"{taken['decision']} - {taken['action_key']} by {taken['decided_by']}."
                if taken
                else "No decision recorded yet."
            ),
            "## Did it work\n" + (taken.get("outcome", {}).get("summary", "Being checked.") if taken else "Pending."),
        ]
    )


def shift_briefing(overview: dict, language: str = "en", simple: bool = False) -> dict:
    """The handover note a shift supervisor writes by hand today, written from live plant facts."""
    facts = {
        "plant_time": overview["plant_time"],
        "shift": overview["shift"],
        "kpis": overview["kpis"],
        "health": overview["health"],
        "top_risks": [{k: r[k] for k in ("id", "severity", "p_fail_8h", "headline")} for r in overview["risks"][:5]],
        "maintenance_due": overview["maintenance"]["due_soon"][:4],
        "recent_events": [e["message"] for e in overview["events"][:6]],
        "hours_to_maintenance_window": overview["window_in_h"],
    }
    text = gemini.generate(
        f"Write the shift handover briefing. Facts:\n{json.dumps(facts, default=str)}",
        system="You are OpEx writing the shift handover for a CNC plant. "
        "Start with one sentence on overall status, then "
        "at most 5 bullets in priority order: what needs action, by whom, and by when. End with one line on "
        "what went well. Under 120 words. " + GROUNDING + " " + _style(language, simple),
        fast=True,
        max_tokens=600,
    )
    if text:
        return {"source": "gemini", "text": text}
    k = overview["kpis"]
    urgent = [r for r in overview["risks"] if r["severity"] in ("critical", "high")]
    lines = [
        f"{overview['shift']}: OEE {k['oee']:.0%}, {k['running']}/{k['machines']} machines running, "
        f"defect rate {k['defect_rate']:.1%}."
    ]
    lines += [f"- **{r['id']}** ({r['severity']}): {r['headline']}" for r in urgent[:3]]
    lines += [f"- {m['machine']}: {m['component_name']} - {m['when']}" for m in overview["maintenance"]["due_soon"][:2]]
    if not urgent:
        lines.append("- No machine needs urgent action.")
    return {"source": "rules", "text": "\n".join(lines)}
