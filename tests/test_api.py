"""API tests, fully offline: the agent is replaced via FastAPI dependency overrides.

`TestClient(app)` is created WITHOUT a `with` block on purpose, so the lifespan (model and
DB warm-up) never runs.
"""

import json

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

from finsight.api import main
from finsight.models import AnswerResponse, Citation

client = TestClient(app=main.app)
ASK = {"question": "What was TCS attrition?"}


def fake_response() -> AnswerResponse:
    cit = Citation(company="TCS", fiscal_year="FY2026", page=40, snippet="s", text="full text")
    return AnswerResponse(answer="12% [TCS, FY2026, p.40].", citations=[cit])


def fake_answer(question, companies):  # noqa: ANN001, ANN201
    return fake_response(), {}


def fake_stream(question, companies):  # noqa: ANN001, ANN201
    yield {"type": "step", "step": "classify"}
    yield {"type": "step", "step": "retrieve"}
    yield {"type": "answer", **fake_response().model_dump()}


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Fresh limiter, fake agent, and a small limit for every test."""
    main.limiter.reset()
    monkeypatch.setattr(main.get_settings(), "rate_limit_per_hour", 3)
    main.app.dependency_overrides[main.get_answer_fn] = lambda: fake_answer
    main.app.dependency_overrides[main.get_stream_fn] = lambda: fake_stream
    yield
    main.app.dependency_overrides.clear()
    main.limiter.reset()


def test_ask_happy_path() -> None:
    r = client.post("/api/ask", json=ASK)
    body = r.json()
    assert r.status_code == 200 and body["refused"] is False
    assert body["citations"][0]["text"] == "full text"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "   "},
        {"question": "x" * 501},
        {"question": "ok", "companies": ["Acme"]},
    ],
)
def test_validation_errors(payload: dict) -> None:
    assert client.post("/api/ask", json=payload).status_code == 422


def test_known_company_accepted() -> None:
    assert client.post("/api/ask", json={**ASK, "companies": ["TCS"]}).status_code == 200


def test_rate_limit_429_shared_across_endpoints() -> None:
    assert client.post("/api/ask", json=ASK).status_code == 200
    assert client.post("/api/ask/stream", json=ASK).status_code == 200
    assert client.post("/api/ask", json=ASK).status_code == 200
    r = client.post("/api/ask/stream", json=ASK)
    assert r.status_code == 429
    assert "3 questions per hour" in r.json()["detail"] and "minutes" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) >= 1


def test_rejected_requests_do_not_use_the_budget() -> None:
    for _ in range(5):
        assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json=ASK).status_code == 200


def test_forwarded_for_clients_counted_separately() -> None:
    for _ in range(3):
        assert client.post("/api/ask", json=ASK, headers={"X-Forwarded-For": "1.1.1.1"}).is_success
    assert (
        client.post(
            "/api/ask", json=ASK, headers={"X-Forwarded-For": "1.1.1.1, 9.9.9.9"}
        ).status_code
        == 429
    )
    assert (
        client.post("/api/ask", json=ASK, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
    )


def test_stream_ndjson() -> None:
    r = client.post("/api/ask/stream", json=ASK)
    assert r.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in r.text.splitlines()]
    assert [e["type"] for e in events] == ["step", "step", "answer"]
    assert events[-1]["citations"][0]["page"] == 40


def test_stream_error_becomes_error_event() -> None:
    def boom(question, companies):  # noqa: ANN001, ANN202
        yield {"type": "step", "step": "classify"}
        raise RuntimeError("secret detail")

    main.app.dependency_overrides[main.get_stream_fn] = lambda: boom
    r = client.post("/api/ask/stream", json=ASK)
    events = [json.loads(line) for line in r.text.splitlines()]
    assert [e["type"] for e in events] == ["step", "error"]
    assert "secret" not in r.text


def test_groq_error_returns_503_without_leaking() -> None:
    def fail(question, companies):  # noqa: ANN001, ANN202
        req = httpx.Request("POST", "https://api.groq.com/x")
        raise groq.APIConnectionError(message="secret groq detail", request=req)

    main.app.dependency_overrides[main.get_answer_fn] = lambda: fail
    r = client.post("/api/ask", json=ASK)
    assert r.status_code == 503 and r.json() == {"detail": main.UNAVAILABLE}
    assert "secret" not in r.text


def test_health_ok_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.db, "ping", lambda: True)
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": True}

    def down() -> bool:
        raise RuntimeError("db down")

    monkeypatch.setattr(main.db, "ping", down)
    r = client.get("/api/health")
    assert r.status_code == 503 and r.json() == {"status": "error", "db": False}


def test_companies() -> None:
    assert "TCS" in client.get("/api/companies").json()


def test_index_without_frontend(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)
    assert client.get("/").json() == {"message": "Frontend not built yet"}
