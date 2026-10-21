import os
from flask import Blueprint, current_app, jsonify, request, send_file, Response, abort
from flask_login import current_user, login_required

from server.app import db
from server.app.models import Device, Command, Event, utcnow
from server.proxmox import ProxmoxClient, ProxmoxError

admin_bp = Blueprint("admin", __name__)
ALLOWED_COMMANDS = {"lock", "unlock", "message", "reboot", "poweroff", "shutdown"}


def _get_device_or_404(device_id):
    dev = db.session.get(Device, device_id)
    if dev is None:
        abort(404)
    return dev


@admin_bp.before_request
def require_admin():
    if not current_user.is_authenticated:
        return jsonify(error="authentication_required"), 401
    if not current_user.active or current_user.role != "admin":
        return jsonify(error="admin_required"), 403


@admin_bp.get("/devices")
@login_required
def devices():
    timeout = current_app.config["HEARTBEAT_TIMEOUT_SECONDS"]
    items = Device.query.order_by(Device.name.asc()).all()
    return jsonify(devices=[device.to_dict(timeout) for device in items])


@admin_bp.get("/devices/<int:device_id>")
@login_required
def device_detail(device_id):
    device = _get_device_or_404(device_id)
    return jsonify(device=device.to_dict(current_app.config["HEARTBEAT_TIMEOUT_SECONDS"]))


@admin_bp.post("/devices/<int:device_id>/command")
@login_required
def send_command(device_id):
    device = _get_device_or_404(device_id)
    data = request.get_json(silent=True) or {}
    cmd_type = data.get("type", "").strip().lower()
    if cmd_type not in ALLOWED_COMMANDS:
        return jsonify(error="invalid_command_type", allowed=sorted(list(ALLOWED_COMMANDS))), 400

    payload = data.get("payload") or {}
    cmd = Command(
        device_id=device.id,
        requested_by=current_user.id,
        type=cmd_type,
        payload=payload,
        status="pending",
    )
    db.session.add(cmd)
    db.session.add(
        Event(
            device_id=device.id,
            user_id=current_user.id,
            command_id=cmd.id,
            event_type=f"command.{cmd_type}",
            details={"requested_by": current_user.username, "payload": payload},
        )
    )
    db.session.commit()
    return jsonify(command=cmd.to_dict()), 201


@admin_bp.post("/devices/command-all")
@login_required
def send_command_all():
    data = request.get_json(silent=True) or {}
    cmd_type = data.get("type", "").strip().lower()
    if cmd_type not in ALLOWED_COMMANDS:
        return jsonify(error="invalid_command_type", allowed=sorted(list(ALLOWED_COMMANDS))), 400

    payload = data.get("payload") or {}
    devices_list = Device.query.all()
    created = []
    for device in devices_list:
        cmd = Command(
            device_id=device.id,
            requested_by=current_user.id,
            type=cmd_type,
            payload=payload,
            status="pending",
        )
        db.session.add(cmd)
        created.append(cmd)

    db.session.add(
        Event(
            user_id=current_user.id,
            event_type=f"command_all.{cmd_type}",
            details={
                "requested_by": current_user.username,
                "target_count": len(created),
                "payload": payload,
            },
        )
    )
    db.session.commit()
    return jsonify(status="ok", commands_dispatched=len(created)), 201


@admin_bp.post("/devices/<int:device_id>/assign-proxmox")
@login_required
def assign_proxmox(device_id):
    device = _get_device_or_404(device_id)
    data = request.get_json(silent=True) or {}
    vmid = data.get("proxmox_vmid")
    node = data.get("proxmox_node", "pve")

    if vmid is not None:
        try:
            vmid = int(vmid)
        except (ValueError, TypeError):
            return jsonify(error="vmid_must_be_integer"), 400

    device.proxmox_vmid = vmid
    device.proxmox_node = str(node).strip() if node else "pve"
    db.session.commit()
    return jsonify(status="ok", device=device.to_dict(current_app.config["HEARTBEAT_TIMEOUT_SECONDS"]))


@admin_bp.post("/devices/<int:device_id>/proxmox-restore")
@login_required
def proxmox_restore(device_id):
    device = _get_device_or_404(device_id)
    if not device.proxmox_vmid:
        return jsonify(error="device_has_no_proxmox_vmid"), 400

    snapshot_name = request.json.get("snapshot") if request.is_json else None
    client = ProxmoxClient.from_env()

    try:
        result = client.restore_clean_state(
            vmid=device.proxmox_vmid,
            snapshot_name=snapshot_name,
            node=device.proxmox_node or "pve",
            auto_start=True,
        )
        db.session.add(
            Event(
                device_id=device.id,
                user_id=current_user.id,
                event_type="proxmox.restore",
                details={
                    "vmid": device.proxmox_vmid,
                    "snapshot": result.get("snapshot"),
                    "node": device.proxmox_node,
                    "task": result.get("rollback_task"),
                },
            )
        )
        db.session.commit()
        return jsonify(result), 200
    except ProxmoxError as exc:
        return jsonify(error="proxmox_error", message=str(exc)), 502


@admin_bp.post("/devices/proxmox-restore-all")
@login_required
def proxmox_restore_all():
    devices_list = Device.query.filter(Device.proxmox_vmid.isnot(None)).all()
    if not devices_list:
        return jsonify(error="no_devices_with_proxmox_vmid"), 400

    snapshot_name = request.json.get("snapshot") if request.is_json else None
    client = ProxmoxClient.from_env()
    results = []
    errors = []

    for device in devices_list:
        try:
            res = client.restore_clean_state(
                vmid=device.proxmox_vmid,
                snapshot_name=snapshot_name,
                node=device.proxmox_node or "pve",
                auto_start=True,
            )
            results.append({"device_id": device.id, "vmid": device.proxmox_vmid, "status": "restoring"})
        except Exception as exc:
            errors.append({"device_id": device.id, "vmid": device.proxmox_vmid, "error": str(exc)})

    db.session.add(
        Event(
            user_id=current_user.id,
            event_type="proxmox.restore_all",
            details={"restored_count": len(results), "errors_count": len(errors)},
        )
    )
    db.session.commit()
    return jsonify(restored=results, errors=errors), 200


@admin_bp.get("/devices/<int:device_id>/screenshot")
@login_required
def device_screenshot(device_id):
    device = _get_device_or_404(device_id)
    screenshots_dir = os.path.join(current_app.instance_path, "screenshots")
    screenshot_file = os.path.join(screenshots_dir, f"{device.agent_id}.jpg")

    if os.path.isfile(screenshot_file):
        return send_file(screenshot_file, mimetype="image/jpeg", max_age=2)

    # Si no hay imagen real guardada aún, generamos un SVG informativo elegante
    svg_placeholder = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
        <rect width="100%" height="100%" fill="#1a1e29"/>
        <circle cx="320" cy="150" r="48" fill="#2a324b"/>
        <path d="M305 150 L320 135 L335 150 M320 135 L320 170" stroke="#7e8ce0" stroke-width="4" stroke-linecap="round"/>
        <text x="320" y="225" font-family="system-ui, sans-serif" font-size="16" fill="#8f9ebf" text-anchor="middle" font-weight="600">{device.name}</text>
        <text x="320" y="250" font-family="system-ui, sans-serif" font-size="13" fill="#586786" text-anchor="middle">Esperando primera captura de pantalla...</text>
    </svg>"""
    return Response(svg_placeholder, mimetype="image/svg+xml")


@admin_bp.get("/proxmox/status")
@login_required
def proxmox_status():
    client = ProxmoxClient.from_env()
    return jsonify(client.test_connection())


@admin_bp.get("/proxmox/vms")
@login_required
def proxmox_vms():
    client = ProxmoxClient.from_env()
    try:
        vms = client.get_vms()
        return jsonify(vms=vms)
    except Exception as exc:
        return jsonify(error="proxmox_error", message=str(exc)), 502


@admin_bp.get("/events")
@login_required
def events():
    limit = request.args.get("limit", default=100, type=int)
    limit = min(max(limit or 100, 1), 500)
    rows = Event.query.order_by(Event.created_at.desc()).limit(limit).all()
    return jsonify(events=[{
        "id": row.id,
        "device_id": row.device_id,
        "user_id": row.user_id,
        "command_id": row.command_id,
        "event_type": row.event_type,
        "details": row.details,
        "created_at": row.created_at.isoformat(),
    } for row in rows])
