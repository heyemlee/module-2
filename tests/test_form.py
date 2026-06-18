"""The factory construction-rules web form: served HTML + accepted submission."""

import os
import tempfile

from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_construction_form_is_served():
    r = client.get("/api/module2/construction-form")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "构造规则" in body            # it's the form
    assert 'name="back_inset_mm"' in body  # has the pending-rule inputs
    assert "generate()" in body          # has the JS that builds the JSON


def test_submission_is_accepted_and_saved(monkeypatch):
    monkeypatch.chdir(tempfile.mkdtemp())  # keep the data/ file out of the repo
    payload = {
        "contract_version": "module2.v1",
        "submitted_by": "GuangChao",
        "construction": {"back_inset_mm": "30", "adj_shelf_setback_mm": "20"},
        "board_sizes": [{"material": "Cleaf", "width": "2065", "length": "2800"}],
    }
    r = client.post("/api/module2/construction-rules", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "received"
    assert body["data"]["saved"] is True
    assert os.path.exists(os.path.join("data", "construction_submissions.jsonl"))
