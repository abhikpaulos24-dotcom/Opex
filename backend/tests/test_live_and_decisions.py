from fastapi.testclient import TestClient

from app.analytics.machine_report import machine_report
from app.main import app
from app.plant.live import get_plant

PASSWORD = "OpEx-demo-2026"


def login(client, who):
    response = client.post("/api/auth/login", json={"email": f"{who}@opex.demo", "password": PASSWORD})
    assert response.status_code == 200
    return response.json()


def test_scripted_morning_flags_the_failing_bearing():
    with TestClient(app):
        m17 = machine_report("M-17")
        assert m17["prediction"]["focus_component"] == "bearing"
        assert m17["prediction"]["p_fail_8h"] > 0.5
        assert m17["root_cause"]["top"]["component"] == "bearing"
        m21 = machine_report("M-21")
        assert m21["root_cause"]["top"]["key"] == "sensor_drift"
        assert m21["prediction"]["confidence"] < m21["prediction"]["confidence_before_data_check"]


def test_wrong_password_is_rejected():
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"email": "manager@opex.demo", "password": "nope"})
        assert response.status_code == 401


def test_operator_cannot_approve_a_repair_but_engineer_can():
    with TestClient(app) as client:
        login(client, "operator")
        rec = client.post("/api/machines/M-17/recommendation", json={}).json()
        assert rec["needed"]
        denied = client.post(f"/api/recommendations/{rec['id']}/decision", json={"decision": "approved"})
        assert denied.status_code == 403

        client.post("/api/auth/logout")
        login(client, "engineer")
        ok = client.post(f"/api/recommendations/{rec['id']}/decision", json={"decision": "approved", "note": "test"})
        assert ok.status_code == 200
        log = client.get("/api/decisions").json()
        assert any(d["machine_id"] == "M-17" and d["source"] == "live" for d in log["decisions"])


def test_viewer_is_read_only():
    with TestClient(app) as client:
        login(client, "viewer")
        assert client.get("/api/overview").status_code == 200
        assert client.put("/api/settings/priorities", json={"preset": "balanced"}).status_code == 403
        assert client.post("/api/admin/demo/reset").status_code == 403


def test_a_short_stop_does_not_hide_a_failing_part():
    """M-17 gets a routine tool change soon after start; its bearing is just as worn while the tool is swapped."""
    with TestClient(app):
        plant = get_plant()
        for _ in range(60):
            plant.fast_forward(1)
            if plant.machine_state("M-17")["state"] == "maintenance":
                break
        else:
            raise AssertionError("expected a routine tool change on M-17 within an hour")
        report = machine_report("M-17")
        assert report["prediction"]["focus_component"] == "bearing"
        assert report["prediction"]["severity"] in ("critical", "high")
        assert report["root_cause"]["top"]["component"] == "bearing"
        plant.reset()
