"""Alerts and incidents, kept in step with the live machine reports.

One open alert per machine and kind (no alarm floods); alerts clear themselves when the
condition goes away. A critical risk or a breakdown opens an incident with a snapshot of
everything the AI saw at that moment, for the investigation later.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert, Incident
from app.integrations import pubsub
from app.plant.factory import COMPONENTS

log = logging.getLogger(__name__)
_last_synced_minute = -1


def _wanted_alerts(a: dict) -> dict[str, tuple[str, str, str]]:
    """kind -> (severity, title, message) for one machine report."""
    wanted = {}
    mid, p = a["machine"]["id"], a["prediction"]
    if a["state"] == "breakdown":
        wanted["breakdown"] = (
            "critical",
            f"{mid} has broken down",
            "Repair in progress. Production on this machine has stopped.",
        )
    elif p["severity"] in ("critical", "high"):
        what = COMPONENTS[p["focus_component"]].name if p["focus_component"] else "Operating overload"
        window = f" Expected failure window: {p['window']}." if p["window"] else ""
        wanted["failure_risk"] = (
            p["severity"],
            f"{mid}: {what} - chance of failure {p['p_fail_8h']:.0%}",
            f"{a['root_cause']['top']['name'] if a['root_cause']['top'] else what}.{window}",
        )
    quality = a.get("quality")
    if quality and quality["defect_rate_later"] > 0.04:
        wanted["quality"] = ("high", f"{mid}: defects rising", quality["sentence"])
    if a["energy"]["idle_waste"]:
        wanted["energy"] = (
            "medium",
            f"{mid}: energy wasted while idle",
            f"Drawing {a['energy']['idle_power_kw'] or 0:.1f} kW with no parts being made.",
        )
    if a["data_health"]["score"] < 70:
        wanted["data_health"] = (
            "medium",
            f"{mid}: sensor data unreliable",
            "; ".join(i["text"] for i in a["data_health"]["issues"][:2]),
        )
    return wanted


def sync(db: Session, reports: list[dict], plant_minute: int, plant_time: str) -> None:
    global _last_synced_minute
    if plant_minute == _last_synced_minute:
        return
    _last_synced_minute = plant_minute

    open_alerts = {(a.machine_id, a.kind): a for a in db.scalars(select(Alert).where(Alert.status != "resolved"))}
    open_incidents = {i.machine_id: i for i in db.scalars(select(Incident).where(Incident.status == "open"))}
    for a in reports:
        mid = a["machine"]["id"]
        wanted = _wanted_alerts(a)
        for kind, (severity, title, message) in wanted.items():
            existing = open_alerts.get((mid, kind))
            if existing:
                existing.severity, existing.title, existing.message = severity, title, message
                continue
            alert = Alert(
                machine_id=mid, kind=kind, severity=severity, title=title, message=message, plant_time=plant_time
            )
            db.add(alert)
            if severity == "critical":
                pubsub.publish_alert(
                    {
                        "machine_id": mid,
                        "kind": kind,
                        "severity": severity,
                        "title": title,
                        "message": message,
                        "plant_time": plant_time,
                    }
                )
        for (machine_id, kind), alert in open_alerts.items():
            if machine_id == mid and kind not in wanted:
                alert.status = "resolved"

        critical = a["state"] == "breakdown" or a["prediction"]["severity"] == "critical"
        incident = open_incidents.get(mid)
        if critical and incident is None:
            top = a["root_cause"]["top"]
            db.add(
                Incident(
                    machine_id=mid,
                    severity="critical",
                    status="open",
                    title=f"{mid}: "
                    + ("breakdown" if a["state"] == "breakdown" else f"{top['name'] if top else 'chance of failure'}"),
                    component=a["prediction"]["focus_component"],
                    root_cause=top["name"] if top else None,
                    started_plant_time=plant_time,
                    snapshot={
                        k: a[k] for k in ("prediction", "anomalies", "root_cause", "data_health", "impact", "latest")
                    },
                )
            )
            log.info("incident opened on %s", mid)
        elif incident and not critical and a["state"] == "running" and a["prediction"]["severity"] in ("low", "medium"):
            incident.status, incident.resolved_plant_time = "resolved", plant_time
    db.commit()
