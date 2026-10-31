import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db

init_db()
client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app_name"] == "SmartFollow AI"

def test_dashboard_stats():
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_tracked" in data
    assert "awaiting_followup" in data
    assert "followups_due_today" in data
    assert "followup_response_rate" in data

def test_tracked_threads_list():
    response = client.get("/api/email-management/threads")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

def test_settings_retrieval_and_update():
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "followup_delay_hours" in data
    assert "test_mode" in data

    update_res = client.put("/api/settings", json={"test_mode": True, "followup_delay_hours": 72})
    assert update_res.status_code == 200

def test_seed_demo_and_verify_flow():
    seed_res = client.post("/api/automation/seed-demo")
    assert seed_res.status_code == 200

    list_res = client.get("/api/email-management/threads")
    assert list_res.status_code == 200
    threads = list_res.json()["items"]
    assert len(threads) >= 4

def test_account_deliverability_endpoint():
    # Ensure at least 1 account exists by seeding
    seed_res = client.post("/api/automation/seed-demo")
    assert seed_res.status_code == 200

    accounts_res = client.get("/api/accounts")
    assert accounts_res.status_code == 200
    accounts = accounts_res.json()
    assert len(accounts) >= 1

    first_account = accounts[0]
    deliv_res = client.get(f"/api/accounts/{first_account['id']}/deliverability")
    assert deliv_res.status_code == 200
    data = deliv_res.json()
    assert "domain" in data
    assert "overall_status" in data
    assert "score" in data
    assert "checks" in data
    assert "spf" in data["checks"]
    assert "dkim" in data["checks"]
    assert "dmarc" in data["checks"]
    assert "mx" in data["checks"]
