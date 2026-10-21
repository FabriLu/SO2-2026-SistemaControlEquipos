import os
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from server.app import db
from server.app.models import Device, Event, User
from server.proxmox import ProxmoxClient

web_bp = Blueprint("web", __name__, template_folder="templates", static_folder="static")


@web_bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.dashboard"))
    return render_template("login.html")


@web_bp.post("/login")
def login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    user = User.query.filter_by(username=username, active=True).first()
    if user is None or not user.check_password(password):
        flash("Credenciales incorrectas o usuario no activo.", "danger")
        return render_template("login.html", username=username)

    login_user(user)
    db.session.add(Event(user_id=user.id, event_type="admin.login", details={"source": "web_panel"}))
    db.session.commit()
    return redirect(url_for("web.dashboard"))


@web_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    user_id = current_user.id
    db.session.add(Event(user_id=user_id, event_type="admin.logout", details={"source": "web_panel"}))
    db.session.commit()
    logout_user()
    return redirect(url_for("web.login"))


@web_bp.get("/")
@web_bp.get("/dashboard")
@login_required
def dashboard():
    timeout = current_app.config["HEARTBEAT_TIMEOUT_SECONDS"]
    devices = Device.query.order_by(Device.name.asc()).all()

    # Probar conexión con Proxmox para indicador de estado superior
    proxmox = ProxmoxClient.from_env()
    proxmox_info = {
        "host": proxmox.base_url,
        "default_node": proxmox.default_node,
        "default_snapshot": proxmox.default_snapshot,
    }

    return render_template(
        "dashboard.html",
        user=current_user,
        devices=[d.to_dict(timeout) for d in devices],
        proxmox_info=proxmox_info,
        timeout_seconds=timeout,
    )
