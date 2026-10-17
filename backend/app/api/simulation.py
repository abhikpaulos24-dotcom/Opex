"""Five-year factory simulation: run, list, replay data, rewind incidents, download datasets."""

import csv
import io
import json
import logging
import time
from dataclasses import asdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.core.jsonsafe import clean
from app.db.models import AuditLog, SimulationRun, User
from app.db.session import get_db
from app.integrations import bigquery
from app.plant.calibration import get_calibration
from app.services import settings_store
from app.simulation.engine import START_DATE, FactorySimulation, SimulationParams
from app.simulation.report import build_report, player_payload
from app.simulation.rewind import rewind, rewind_candidates

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/simulations", tags=["simulation"])


class SimulationIn(BaseModel):
    years: int = Field(5, ge=1, le=5)
    adoption_rate: float = Field(0.85, ge=0.3, le=1.0)
    sensor_coverage: float = Field(0.9, ge=0.3, le=1.0)
    seed: int = Field(2026, ge=1, le=999_999)


@router.post("")
def run_simulation(body: SimulationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    params = SimulationParams(
        years=body.years, adoption_rate=body.adoption_rate, sensor_coverage=body.sensor_coverage, seed=body.seed
    )
    started = time.perf_counter()
    sim = FactorySimulation(params, economics=settings_store.get_economics(db))
    result = sim.run()
    report = build_report(sim, result)
    events = []
    for name, world in result["worlds"].items():
        events.extend({**e, "world": name} for e in world.events)
    events = clean(sorted(events, key=lambda e: (e["day"], e["hour"])))
    run = SimulationRun(
        created_by=user.email,
        params=asdict(params),
        summary=report,
        player=player_payload(sim, result),
        events=events,
        duration_s=round(time.perf_counter() - started, 2),
    )
    db.add(run)
    db.add(AuditLog(user_email=user.email, action="simulation.run", details=asdict(params)))
    db.commit()
    log.info(
        "simulation %s by %s: net benefit ₹%.1f lakh", run.id, user.email, report["delta"]["net_benefit_inr"] / 1e5
    )
    bigquery.append_in_background("simulation_daily", _daily_rows(run))
    return _run_out(run, full=True)


@router.get("")
def list_runs(_: User = Depends(current_user), db: Session = Depends(get_db)):
    runs = db.scalars(select(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(20)).all()
    return [_run_out(r) for r in runs]


@router.get("/{run_id}")
def get_run(run_id: str, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return _run_out(_load(db, run_id), full=True)


@router.get("/{run_id}/rewind/{index}")
def rewind_incident(run_id: str, index: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    run = _load(db, run_id)
    candidates = rewind_candidates(run.events)
    if not 0 <= index < len(candidates):
        raise HTTPException(404, "No such incident.")
    return rewind(SimulationParams(**run.params), candidates[index])


@router.get("/{run_id}/download/{name}")
def download(run_id: str, name: str, _: User = Depends(current_user), db: Session = Depends(get_db)):
    run = _load(db, run_id)
    files = {
        "daily.csv": lambda: _csv(_daily_rows(run)),
        "events.csv": lambda: _csv(run.events),
        "machines.csv": lambda: _csv(
            [
                {
                    "machine": m["machine"],
                    "line": m["line"],
                    **{f"{w}_{k}": v for w in ("without", "with") for k, v in m[w].items()},
                }
                for m in run.summary["machines"]
            ]
        ),
        "summary.json": lambda: json.dumps(run.summary, indent=2, default=str),
        "assumptions.json": lambda: json.dumps(
            {
                "parameters": run.params,
                "economics": asdict(settings_store.get_economics(db)),
                "calibration": get_calibration().raw,
            },
            indent=2,
            default=str,
        ),
    }
    if name not in files:
        raise HTTPException(404, "Unknown file.")
    media = "text/csv" if name.endswith(".csv") else "application/json"
    return Response(
        files[name](),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="opex-simulation-{name}"'},
    )


def _load(db: Session, run_id: str) -> SimulationRun:
    run = db.get(SimulationRun, run_id)
    if not run:
        raise HTTPException(404, "Simulation not found.")
    return run


def _run_out(run: SimulationRun, full: bool = False) -> dict:
    out = {
        "id": run.id,
        "created_at": run.created_at,
        "created_by": run.created_by,
        "params": run.params,
        "duration_s": run.duration_s,
        "headline": {
            k: run.summary["delta"][k] for k in ("net_benefit_inr", "roi_multiple", "downtime_avoided_h", "oee_points")
        },
    }
    if full:
        out.update(
            summary=run.summary,
            player=run.player,
            ticker=[e for e in run.events if e["kind"] in ("failure", "planned_repair")],
            rewind=rewind_candidates(run.events),
        )
    return out


def _daily_rows(run: SimulationRun) -> list[dict]:
    rows = []
    worlds = run.player["worlds"]
    for day in range(run.player["days"]):
        row = {
            "run_id": run.id,
            "date": (START_DATE + timedelta(days=day)).isoformat(),
            "production_day": bool(run.player["production_day"][day]),
        }
        for name, w in worlds.items():
            for metric in ("oee", "downtime_h", "failures", "good", "defects", "energy_kwh", "cost_inr"):
                value = w[metric][day]
                row[f"{name}_{metric}"] = None if metric == "oee" and value < 0 else value
        rows.append(row)
    return rows


def _csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    fields = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
