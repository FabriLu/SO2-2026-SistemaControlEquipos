import json

from agent.client import load_config, register


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"credential": "client-secret"}


class FakeSession:
    def post(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        return FakeResponse()


def test_agent_registration_persists_individual_credential(tmp_path):
    config_path = tmp_path / "agent.json"
    config_path.write_text(json.dumps({
        "server_url": "https://server.local:5000/",
        "agent_id": "00000000-0000-4000-8000-000000000001",
        "device_name": "PC-01",
        "enrollment_token": "bootstrap-secret",
    }), encoding="utf-8")
    config = load_config(config_path)
    session = FakeSession()

    result = register(session, config)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert result["credential"] == "client-secret"
    assert saved["credential"] == "client-secret"
    assert "enrollment_token" not in saved
    assert session.url == "https://server.local:5000/api/agent/register"
