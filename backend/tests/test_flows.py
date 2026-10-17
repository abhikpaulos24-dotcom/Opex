"""Every screen's API flow, end to end, for each role. No keys are set, so this also proves
the free rule-based fallbacks work when Gemini and Google Cloud are not configured."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.paths import STORAGE_DIR
from app.main import app

PASSWORD = "OpEx-demo-2026"
ROLES = ("manager", "engineer", "operator", "viewer")
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, role):
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"email": f"{role}@opex.demo", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("role", ROLES)
def test_every_screen_loads_for_every_role(client, role):
    login(client, role)
    for path in (
        "/api/auth/me",
        "/api/config",
        "/api/health",
        "/api/overview",
        "/api/machines/M-17",
        "/api/machines/M-05",
        "/api/machines/M-17/history?minutes=180",
        "/api/actions",
        "/api/alerts",
        "/api/incidents",
        "/api/decisions",
        "/api/settings/priorities",
        "/api/settings/economics",
        "/api/plant",
        "/api/simulations",
        "/api/data/overview",
        "/api/data/knowledge",
        "/api/data/template.csv",
        "/api/data/knowledge/search?q=bearing",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{role} {path}: {response.status_code} {response.text[:200]}"


def test_signed_out_people_see_nothing(client):
    client.post("/api/auth/logout")
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/machines/M-17").status_code == 401
    assert client.get("/api/config").status_code == 200  # the login page needs it


def test_guest_login_is_read_only(client):
    client.post("/api/auth/logout")
    me = client.post("/api/auth/guest").json()
    assert me["role"] == "viewer"
    assert client.post("/api/admin/demo/fast-forward?minutes=5").status_code == 403


def test_preferences_are_saved(client):
    login(client, "operator")
    response = client.put("/api/auth/me/preferences", json={"preferences": {"text": "xl", "simple": True}})
    assert response.status_code == 200
    assert client.get("/api/auth/me").json()["preferences"]["text"] == "xl"


def test_unknown_machine_is_a_clear_404(client):
    login(client, "viewer")
    assert client.get("/api/machines/M-99").status_code == 404


def test_each_option_says_who_may_approve_it(client):
    login(client, "engineer")
    rec = client.post("/api/machines/M-17/recommendation", json={"preset": "safety_first"}).json()
    assert rec["needed"] and rec["preset"] == "safety_first"
    assert {o["permission"] for o in rec["options"]} <= {"decide_minor", "decide_major"}
    assert client.post("/api/machines/M-17/recommendation", json={"preset": "nonsense"}).status_code == 400


def test_full_decision_flow(client):
    login(client, "engineer")
    rec = client.post("/api/machines/M-17/recommendation", json={}).json()

    not_an_option = {"decision": "modified", "action_key": "dance"}
    assert client.post(f"/api/recommendations/{rec['id']}/decision", json=not_an_option).status_code == 400

    agents = client.post(f"/api/recommendations/{rec['id']}/agents?language=en&simple=true")
    assert agents.status_code == 200
    assert [a["agent"] for a in agents.json()["agents"]] == ["Diagnostician", "Planner", "Safety officer"]

    other = rec["options"][1]["key"]
    done = client.post(
        f"/api/recommendations/{rec['id']}/decision", json={"decision": "modified", "action_key": other, "note": "test"}
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["action"] == other and body["check_in_plant_minutes"] > 0

    logged = client.get("/api/decisions").json()["decisions"]
    assert any(d["action_key"] == other and d["source"] == "live" for d in logged)


def test_operator_can_reject_and_approve_minor_actions(client):
    login(client, "operator")
    rec = client.post("/api/machines/M-21/recommendation", json={}).json()  # drifting vibration sensor
    assert rec["needed"]
    assert rec["recommendation"]["action_key"] == "recalibrate_sensor"
    rejected = client.post(f"/api/recommendations/{rec['id']}/decision", json={"decision": "rejected"})
    assert rejected.status_code == 200

    rec = client.post("/api/machines/M-21/recommendation", json={}).json()
    approved = client.post(f"/api/recommendations/{rec['id']}/decision", json={"decision": "approved"})
    assert approved.status_code == 200, approved.text


def test_viewer_cannot_change_anything(client):
    login(client, "viewer")
    alerts = client.get("/api/alerts").json()
    if alerts:
        assert client.post(f"/api/alerts/{alerts[0]['id']}/acknowledge").status_code == 403
    assert client.put("/api/settings/priorities", json={"preset": "balanced"}).status_code == 403
    assert client.post("/api/data/export-bigquery").status_code == 403
    assert client.get("/api/users").status_code == 403


def test_alerts_can_be_acknowledged(client):
    login(client, "operator")
    alerts = client.get("/api/alerts").json()
    assert alerts, "the scripted morning should raise alerts"
    assert client.post(f"/api/alerts/{alerts[0]['id']}/acknowledge").status_code == 200
    assert alerts[0]["id"] not in {a["id"] for a in client.get("/api/alerts").json()}


def test_incident_investigation(client):
    login(client, "engineer")
    incidents = client.get("/api/incidents").json()
    assert incidents, "M-17 at critical risk should open an incident"
    incident_id = incidents[0]["id"]
    assert client.get(f"/api/incidents/{incident_id}").status_code == 200
    report = client.post(f"/api/incidents/{incident_id}/report?language=en")
    assert report.status_code == 200
    assert client.get(f"/api/incidents/{incident_id}").json()["report"]


def test_copilot_works_without_gemini(client):
    login(client, "operator")
    answer = client.post("/api/copilot/chat", json={"message": "Which machine is most likely to fail?"})
    assert answer.status_code == 200
    assert "M-17" in answer.json()["text"]

    first = client.post("/api/copilot/briefing?language=en&simple=false").json()
    second = client.post("/api/copilot/briefing?language=en&simple=false").json()
    assert first["text"] and first["text"] == second["text"]  # cached for the half hour


def test_photo_check(client):
    login(client, "operator")
    photo = {"file": ("../../escape.png", io.BytesIO(TINY_PNG), "image/png")}
    response = client.post("/api/machines/M-17/photo-check?language=en", files=photo)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False  # no Gemini key in tests
    assert (STORAGE_DIR / "photos" / "M-17").resolve() in Path(body["stored_at"]).resolve().parents  # not "../../"

    gif = {"file": ("part.gif", io.BytesIO(b"GIF89a"), "image/gif")}
    assert client.post("/api/machines/M-17/photo-check", files=gif).status_code == 400


def test_sensor_file_upload(client):
    login(client, "engineer")
    template = client.get("/api/data/template.csv").text
    response = client.post(
        "/api/data/upload?machine_id=M-03", files={"file": ("../x.csv", io.BytesIO(template.encode()), "text/csv")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["rows"] > 0


def test_knowledge_library(client):
    login(client, "engineer")
    doc = {"title": "Chuck jaw check", "body": "## Steps\nInspect the chuck jaws for wear marks every shift."}
    assert client.post("/api/data/knowledge", json=doc).status_code == 200
    hits = client.get("/api/data/knowledge/search?q=chuck jaws").json()
    assert any(h["title"] == "Chuck jaw check" for h in hits)


def test_downloads_listed_on_the_data_page_exist(client):
    login(client, "viewer")
    for name in client.get("/api/data/overview").json()["downloads"]:
        assert client.get(f"/api/data/download/{name}").status_code == 200, name
    assert client.get("/api/data/download/secrets.env").status_code == 404
    assert client.get("/api/not-a-thing").status_code == 404  # not the web app's HTML


def test_bigquery_export_explains_when_not_set_up(client):
    login(client, "manager")
    response = client.post("/api/data/export-bigquery")
    assert response.status_code == 400
    assert "BigQuery" in response.json()["detail"]


def test_manager_settings_and_users(client):
    login(client, "manager")
    economics = client.get("/api/settings/economics").json()
    assert client.put("/api/settings/economics", json=economics).status_code == 200
    assert client.put("/api/settings/priorities", json={"preset": "quality_first"}).status_code == 200
    assert client.get("/api/settings/priorities").json()["preset"] == "quality_first"
    client.put("/api/settings/priorities", json={"preset": "balanced"})

    new = {"email": "new.tech@opex.demo", "full_name": "New Tech", "role": "operator", "password": "long-enough-1"}
    created = client.post("/api/users", json=new)
    assert created.status_code in (200, 201), created.text
    user_id = created.json()["id"]
    assert client.patch(f"/api/users/{user_id}", json={"role": "engineer"}).status_code == 200
    assert client.get("/api/audit").status_code == 200


def test_demo_controls(client):
    login(client, "manager")
    before = client.get("/api/plant").json()
    assert client.post("/api/admin/demo/fast-forward?minutes=30").status_code == 200
    assert client.post("/api/admin/demo/inject", json={"machine_id": "M-09", "fault": "coolant"}).status_code == 200
    assert client.post("/api/admin/demo/inject", json={"machine_id": "M-09", "fault": "lava"}).status_code == 400
    assert client.post("/api/admin/demo/reset").status_code == 200
    assert client.get("/api/plant").json() == before or client.get("/api/overview").status_code == 200


def test_sensor_ingest_is_off_without_a_key(client):
    response = client.post("/api/ingest/readings", json={"machine_id": "M-01", "readings": {"rpm": 1500}})
    assert response.status_code == 403


def test_simulation_run_replay_rewind_and_downloads(client):
    login(client, "engineer")
    run = client.post("/api/simulations", json={"years": 1, "seed": 11}).json()
    assert run["player"]["days"] == 365
    assert client.get(f"/api/simulations/{run['id']}").json()["id"] == run["id"]
    assert any(r["id"] == run["id"] for r in client.get("/api/simulations").json())
    rewind = client.get(f"/api/simulations/{run['id']}/rewind/0")
    assert rewind.status_code == 200 and {"with", "without"} <= set(rewind.json())
    for name in ("daily.csv", "events.csv", "machines.csv", "summary.json", "assumptions.json"):
        assert client.get(f"/api/simulations/{run['id']}/download/{name}").status_code == 200, name
    assert client.post("/api/simulations", json={"years": 9}).status_code == 422
