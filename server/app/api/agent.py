import base64
import hashlib
import hmac
import os
import secrets
import uuid

from flask import Blueprint, current_app, jsonify, request

from server.app import db
from server.app.models import AgentCredential, Command, Device, Event, utcnow

agent_bp = Blueprint("agent", __name__)
LOCK_STATES = {"unknown", "unlocked", "locked", "error"}


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _device_from_bearer():
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    credential = AgentCredential.query.filter_by(token_hash=token_hash, revoked_at=None).first()
    if credential is None:
        return None
    credential.last_used_at = utcnow()
    return credential.device


def _save_screenshot(agent_id, base64_data):
    """Guarda la imagen de captura de pantalla en el directorio de instancia."""
    if not base64_data or not isinstance(base64_data, str):
        return False
    try:
        # Remover prefijo data:image/jpeg;base64, si estuviese presente
        if "," in base64_data:
            _, _, base64_data = base64_data.partition(",")
        img_bytes = base64.b64decode(base64_data)
        if len(img_bytes) < 10:
            return False

        screenshots_dir = os.path.join(current_app.instance_path, "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        target_path = os.path.join(screenshots_dir, f"{agent_id}.jpg")
        temp_path = os.path.join(screenshots_dir, f"{agent_id}.tmp")

        with open(temp_path, "wb") as f:
            f.write(img_bytes)
        os.replace(temp_path, target_path)
        return True
    except Exception as exc:
        current_app.logger.warning("No se pudo guardar captura de %s: %s", agent_id, exc)
        return False


@agent_bp.post("/register")
def register():
    data = _json_object()
    if data is None:
        return jsonify(error="json_object_required"), 400
    enrollment = current_app.config.get("AGENT_ENROLLMENT_TOKEN", "")
    provided = request.headers.get("X-Enrollment-Token", "")
    if not enrollment or not hmac.compare_digest(enrollment, provided):
        return jsonify(error="invalid_enrollment_token"), 401

    agent_id = data.get("agent_id")
    name = data.get("name")
    hostname = data.get("hostname")
    if not all(isinstance(value, str) and value.strip() for value in (agent_id, name, hostname)):
        return jsonify(error="agent_id_name_hostname_required"), 400
    try:
        agent_id = str(uuid.UUID(agent_id))
    except ValueError:
        return jsonify(error="agent_id_must_be_uuid"), 400
    if len(name) > 120 or len(hostname) > 255:
        return jsonify(error="field_too_long"), 400
    if Device.query.filter_by(agent_id=agent_id).first():
        return jsonify(error="agent_already_registered"), 409

    optional = {}
    for key, limit in (("os_version", 120), ("agent_version", 40), ("ip_address", 45)):
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            return jsonify(error=f"invalid_{key}"), 400
        optional[key] = value.strip() if isinstance(value, str) else None

    # Si no se pasó IP, usar la IP del request
    if not optional.get("ip_address"):
        optional["ip_address"] = request.remote_addr

    device = Device(
        agent_id=agent_id,
        name=name.strip(),
        hostname=hostname.strip(),
        **optional,
        lock_status="unknown",
    )
    token = secrets.token_urlsafe(32)
    db.session.add(device)
    db.session.flush()
    db.session.add(AgentCredential(device_id=device.id, token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest()))
    db.session.add(Event(device_id=device.id, event_type="device.registered", details={"hostname": hostname.strip()}))
    db.session.commit()
    return jsonify(device_id=device.id, agent_id=device.agent_id, credential=token), 201


@agent_bp.post("/heartbeat")
def heartbeat():
    device = _device_from_bearer()
    if device is None:
        return jsonify(error="invalid_agent_credential"), 401
    data = _json_object()
    if data is None:
        return jsonify(error="json_object_required"), 400

    lock_status = data.get("lock_status", device.lock_status)
    if not isinstance(lock_status, str) or lock_status not in LOCK_STATES:
        return jsonify(error="invalid_lock_status"), 400

    values = {}
    for key, limit in (("name", 120), ("hostname", 255), ("os_version", 120), ("agent_version", 40), ("ip_address", 45)):
        value = data.get(key)
        if value is not None:
            if not isinstance(value, str) or len(value) > limit:
                return jsonify(error=f"invalid_{key}"), 400
            if key in {"name", "hostname"} and not value.strip():
                return jsonify(error=f"invalid_{key}"), 400
            values[key] = value.strip()

    # Métricas de hardware
    for metric in ("cpu_percent", "ram_percent", "disk_percent"):
        if metric in data and data[metric] is not None:
            try:
                values[metric] = float(data[metric])
            except (ValueError, TypeError):
                pass

    if "ip_address" not in values and not device.ip_address:
        values["ip_address"] = request.remote_addr

    # Captura de pantalla enviada en el heartbeat (si viene incluida)
    raw_screenshot = data.get("screenshot")
    if raw_screenshot:
        if _save_screenshot(device.agent_id, raw_screenshot):
            device.last_screenshot_at = utcnow()

    was_connected = device.connection_status(current_app.config["HEARTBEAT_TIMEOUT_SECONDS"]) == "connected"
    if device.last_seen is not None and not was_connected:
        db.session.add(Event(device_id=device.id, event_type="device.disconnected", details={"detected_on": "heartbeat"}))

    device.last_seen = utcnow()
    device.lock_status = lock_status
    for key, value in values.items():
        setattr(device, key, value)

    if not was_connected:
        db.session.add(Event(device_id=device.id, event_type="device.connected", details={}))

    # Obtener órdenes pendientes para entregar al agente
    pending_commands = (
        Command.query.filter_by(device_id=device.id, status="pending")
        .order_by(Command.created_at.asc())
        .all()
    )
    dispatched = []
    for cmd in pending_commands:
        cmd.status = "delivered"
        cmd.delivered_at = utcnow()
        dispatched.append(cmd.to_dict())

    db.session.commit()
    return jsonify(
        status="ok",
        server_time=device.last_seen.isoformat(),
        device_id=device.id,
        commands=dispatched,
    )


@agent_bp.post("/screenshot")
def upload_screenshot():
    """Endpoint dedicado para subir captura de pantalla periódica."""
    device = _device_from_bearer()
    if device is None:
        return jsonify(error="invalid_agent_credential"), 401

    data = _json_object()
    if not data or "screenshot" not in data:
        return jsonify(error="screenshot_field_required"), 400

    if _save_screenshot(device.agent_id, data["screenshot"]):
        device.last_screenshot_at = utcnow()
        db.session.commit()
        return jsonify(status="ok", last_screenshot_at=device.last_screenshot_at.isoformat())
    return jsonify(error="failed_to_save_screenshot"), 400


@agent_bp.post("/commands/<string:command_id>/ack")
def acknowledge_command(command_id):
    """Confirmación del agente tras intentar ejecutar una orden (éxito o fallo)."""
    device = _device_from_bearer()
    if device is None:
        return jsonify(error="invalid_agent_credential"), 401

    cmd = Command.query.filter_by(id=command_id, device_id=device.id).first()
    if cmd is None:
        return jsonify(error="command_not_found"), 404

    data = _json_object() or {}
    result_code = data.get("result_code", "completed")
    result_message = data.get("result_message", "")

    cmd.finished_at = utcnow()
    cmd.result_code = str(result_code)[:80]
    cmd.result_message = str(result_message)
    cmd.status = "completed" if result_code in ("success", "completed", "ok") else "failed"

    # Actualizar estado de bloqueo si la orden fue de lock o unlock
    if cmd.type == "lock" and cmd.status == "completed":
        device.lock_status = "locked"
    elif cmd.type == "unlock" and cmd.status == "completed":
        device.lock_status = "unlocked"

    db.session.add(
        Event(
            device_id=device.id,
            command_id=cmd.id,
            event_type=f"command.{cmd.status}",
            details={"type": cmd.type, "result_code": cmd.result_code, "message": cmd.result_message},
        )
    )
    db.session.commit()
    return jsonify(status="ok", command=cmd.to_dict())
