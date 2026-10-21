from unittest.mock import MagicMock, patch
import pytest

from server.proxmox import ProxmoxClient, ProxmoxError


def test_proxmox_client_initialization_and_token_headers():
    client = ProxmoxClient(
        host="192.168.1.100",
        port=8006,
        user="root@pam",
        token_id="test-token",
        token_secret="12345678-abcd-1234-abcd-1234567890ab",
        verify_ssl=False,
    )
    headers = client._get_headers()
    assert "Authorization" in headers
    assert "PVEAPIToken=root@pam!test-token=12345678-abcd-1234-abcd-1234567890ab" in headers["Authorization"]
    assert client.base_url == "https://192.168.1.100:8006"


@patch("requests.Session.request")
def test_proxmox_test_connection_success(mock_request):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "version": "8.2.4",
            "release": "8.2",
            "repoid": "xyz",
        }
    }
    mock_request.return_value = mock_resp

    client = ProxmoxClient(
        host="192.168.1.100",
        token_id="user!token",
        token_secret="secret",
    )
    res = client.test_connection()
    assert res["status"] == "ok"
    assert res["connected"] is True
    assert res["version"] == "8.2.4"


@patch("requests.Session.request")
def test_proxmox_restore_clean_state_workflow(mock_request):
    mock_resp_rollback = MagicMock()
    mock_resp_rollback.status_code = 200
    mock_resp_rollback.json.return_value = {"data": "UPID:pve:00001:rollback"}

    mock_resp_start = MagicMock()
    mock_resp_start.status_code = 200
    mock_resp_start.json.return_value = {"data": "UPID:pve:00002:start"}

    mock_request.side_effect = [mock_resp_rollback, mock_resp_start]

    client = ProxmoxClient(
        host="192.168.1.100",
        token_id="user!token",
        token_secret="secret",
        default_node="pve",
        default_snapshot="estado_limpio",
    )

    result = client.restore_clean_state(vmid=101, snapshot_name="estado_limpio")
    assert result["status"] == "success"
    assert result["vmid"] == 101
    assert result["snapshot"] == "estado_limpio"
    assert result["rollback_task"] == "UPID:pve:00001:rollback"
    assert result["start_task"] == "UPID:pve:00002:start"
