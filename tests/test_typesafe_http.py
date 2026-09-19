import json
from pathlib import Path

from historical_engine.ai.jev import JevDecisionProvider
from historical_engine.ai.questions import DecisionQuestion, DecisionRequest
from historical_engine.ai.typesafe_config import TypeSafeConfig
from historical_engine.ai.typesafe_http import TypeSafeHttpTransport


class FakeHttpResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_typesafe_transport_uses_documented_systemone_contract() -> None:
    captured = {}

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeHttpResponse(
            {
                "model": "jev-latest",
                "answers": {
                    "decision": {
                        "type": "choice",
                        "choice": "same",
                        "probabilities": {
                            "same": 0.91,
                            "different": 0.04,
                            "unknown": 0.05,
                        },
                        "confidence": 0.86,
                    }
                },
                "usage": {"input_tokens": 42, "output_tokens": 8},
            }
        )

    config = TypeSafeConfig(
        api_key="secret-test-key",
        api_url="https://api.typesafe.ai/v1/systemone",
        auth_header="Authorization",
        auth_prefix="Bearer",
        model="jev-latest",
    )
    transport = TypeSafeHttpTransport(config=config, opener=opener, timeout_s=12.0)
    request = DecisionRequest(
        question=DecisionQuestion.SAME_ENTITY,
        subject_id="entity:1",
        object_id="entity:2",
        collection_id="wikileaks",
        evidence_ids=["cable:1", "cable:2"],
        context={
            "subject_name": "U.S. Embassy Cairo",
            "object_name": "US Embassy Cairo",
            "candidate_score": 0.95,
        },
    )

    result = transport.ask(request)

    assert captured["url"] == "https://api.typesafe.ai/v1/systemone"
    assert captured["timeout"] == 12.0
    assert captured["headers"]["Authorization"] == "Bearer secret-test-key"
    assert captured["headers"]["Content-type"] == "application/json"

    body = captured["body"]
    assert body["model"] == "jev-latest"
    assert body["questions"]["decision"]["type"] == "choice"
    assert set(body["questions"]["decision"]["criteria"]) == {"same", "different", "unknown"}

    state = json.loads(body["state"])
    assert state["subject_id"] == "entity:1"
    assert state["object_id"] == "entity:2"
    assert state["context"]["candidate_score"] == 0.95

    assert result["answer"] == "same"
    assert result["confidence"] == 0.86
    assert result["model"] == "jev-latest"
    assert result["probabilities"]["same"] == 0.91
    assert "secret-test-key" not in result["rationale"]


def test_jev_provider_from_transport_returns_validated_decision() -> None:
    def opener(request, timeout):
        return FakeHttpResponse(
            {
                "model": "jev-latest",
                "answers": {
                    "decision": {
                        "type": "choice",
                        "choice": "different",
                        "probabilities": {
                            "same": 0.02,
                            "different": 0.95,
                            "unknown": 0.03,
                        },
                        "confidence": 0.90,
                    }
                },
                "usage": {"input_tokens": 20, "output_tokens": 6},
            }
        )

    provider = JevDecisionProvider(
        transport=TypeSafeHttpTransport(
            config=TypeSafeConfig(
                api_key="secret",
                api_url="https://api.typesafe.ai/v1/systemone",
                auth_header="Authorization",
                auth_prefix="Bearer",
                model="jev-latest",
            ),
            opener=opener,
        ),
        model="jev-latest",
    )
    request = DecisionRequest(
        question=DecisionQuestion.SAME_EVENT,
        subject_id="event:1",
        object_id="event:2",
        evidence_ids=["warlog:1", "warlog:2"],
        context={"time_delta_hours": 11.0},
    )

    response = provider.decide(request)

    assert response.answer == "different"
    assert response.confidence == 0.90
    assert response.provider == "jev"
    assert response.model == "jev-latest"


def test_from_env_uses_documented_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_URL", raising=False)
    monkeypatch.delenv("TYPESAFE_MODEL", raising=False)
    monkeypatch.delenv("TYPESAFE_API_AUTH_HEADER", raising=False)
    monkeypatch.delenv("TYPESAFE_API_AUTH_PREFIX", raising=False)

    dotenv = tmp_path / ".env"
    dotenv.write_text("TYPESAFE_API_KEY=abc123\n", encoding="utf-8")

    provider = JevDecisionProvider.from_env(dotenv_path=str(dotenv))

    transport = provider.transport
    assert isinstance(transport, TypeSafeHttpTransport)
    assert transport.config.api_url == "https://api.typesafe.ai/v1/systemone"
    assert transport.config.model == "jev-latest"
    assert transport.config.auth_header == "Authorization"
    assert transport.config.auth_prefix == "Bearer"
    assert provider.model == "jev-latest"
