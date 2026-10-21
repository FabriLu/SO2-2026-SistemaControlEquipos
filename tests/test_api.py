import uuid


def register_device(client, agent_id=None):
    return client.post(
        "/api/agent/register",
        headers={"X-Enrollment-Token": "test-enrollment-token"},
        json={
            "agent_id": agent_id or str(uuid.uuid4()),
            "name": "PC Aula 1",
            "hostname": "pc-aula-1",
            "os_version": "Ubuntu test",
            "agent_version": "0.1.0",
        },
    )


def login(client):
    return client.post("/api/auth/login", json={"username": "teacher", "password": "a-long-test-password"})


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_agent_registration_requires_enrollment_token(client):
    response = client.post("/api/agent/register", json={"agent_id": str(uuid.uuid4())})
    assert response.status_code == 401


def test_registration_returns_credential_and_duplicate_is_rejected(client):
    agent_id = str(uuid.uuid4())
    response = register_device(client, agent_id)
    assert response.status_code == 201
    assert response.json["credential"]
    duplicate = register_device(client, agent_id)
    assert duplicate.status_code == 409


def test_heartbeat_and_admin_device_listing(client):
    registered = register_device(client)
    token = registered.json["credential"]
    response = client.post(
        "/api/agent/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
        json={"lock_status": "unlocked", "hostname": "pc-aula-1"},
    )
    assert response.status_code == 200
    assert login(client).status_code == 200
    listing = client.get("/api/admin/devices")
    assert listing.status_code == 200
    device = listing.json["devices"][0]
    assert device["connection_status"] == "connected"
    assert device["lock_status"] == "unlocked"


def test_invalid_agent_credential_is_rejected(client):
    response = client.post(
        "/api/agent/heartbeat",
        headers={"Authorization": "Bearer not-a-valid-token"},
        json={"lock_status": "unknown"},
    )
    assert response.status_code == 401


def test_admin_api_requires_login(client):
    response = client.get("/api/admin/devices")
    assert response.status_code == 401


def test_heartbeat_rejects_invalid_state(client):
    registered = register_device(client)
    response = client.post(
        "/api/agent/heartbeat",
        headers={"Authorization": f"Bearer {registered.json['credential']}"},
        json={"lock_status": "arbitrary"},
    )
    assert response.status_code == 400


def test_event_log_is_admin_only_and_contains_registration(client):
    assert register_device(client).status_code == 201
    assert client.get("/api/admin/events").status_code == 401
    assert login(client).status_code == 200
    response = client.get("/api/admin/events")
    assert response.status_code == 200
    event_types = {event["event_type"] for event in response.json["events"]}
    assert "device.registered" in event_types
    assert "admin.login" in event_types


def test_login_requires_csrf_when_enabled(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    denied = client.post("/api/auth/login", json={"username": "teacher", "password": "a-long-test-password"})
    assert denied.status_code == 400
    token = client.get("/api/admin/csrf").json["csrf_token"]
    accepted = client.post(
        "/api/auth/login",
        headers={"X-CSRFToken": token},
        json={"username": "teacher", "password": "a-long-test-password"},
    )
    assert accepted.status_code == 200


def test_command_dispatch_heartbeat_delivery_and_ack(client):
    reg = register_device(client).json
    device_id = reg["device_id"]
    token = reg["credential"]

    assert login(client).status_code == 200

    # 1. Admin envía orden de bloqueo
    cmd_resp = client.post(
        f"/api/admin/devices/{device_id}/command",
        json={"type": "lock", "payload": {"message": "Atención clase"}},
    )
    assert cmd_resp.status_code == 201
    cmd_id = cmd_resp.json["command"]["id"]

    # 2. Agente envía heartbeat y recibe la orden pendiente
    hb_resp = client.post(
        "/api/agent/heartbeat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "lock_status": "unlocked",
            "cpu_percent": 15.5,
            "ram_percent": 42.0,
            "disk_percent": 30.0,
        },
    )
    assert hb_resp.status_code == 200
    delivered = hb_resp.json["commands"]
    assert len(delivered) == 1
    assert delivered[0]["id"] == cmd_id
    assert delivered[0]["type"] == "lock"

    # 3. Agente confirma ejecución de la orden
    ack_resp = client.post(
        f"/api/agent/commands/{cmd_id}/ack",
        headers={"Authorization": f"Bearer {token}"},
        json={"result_code": "success", "result_message": "Pantalla bloqueada con éxito"},
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json["command"]["status"] == "completed"

    # 4. Verificar que el estado del equipo se actualizó en la API de administración
    detail = client.get(f"/api/admin/devices/{device_id}").json["device"]
    assert detail["lock_status"] == "locked"
    assert detail["cpu_percent"] == 15.5


def test_assign_proxmox_vmid(client):
    reg = register_device(client).json
    device_id = reg["device_id"]

    assert login(client).status_code == 200
    assign = client.post(
        f"/api/admin/devices/{device_id}/assign-proxmox",
        json={"proxmox_vmid": 102, "proxmox_node": "pve"},
    )
    assert assign.status_code == 200
    assert assign.json["device"]["proxmox_vmid"] == 102
    assert assign.json["device"]["proxmox_node"] == "pve"


def test_web_routes_and_protection(client):
    # Sin autenticación, / redirige a /login
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    # /login responde 200 HTML
    login_page = client.get("/login")
    assert login_page.status_code == 200
    assert b"Control de Equipos" in login_page.data

    # Tras iniciar sesión, / carga el dashboard
    assert login(client).status_code == 200
    dash = client.get("/")
    assert dash.status_code == 200
    assert b"Recuperaci" in dash.data


