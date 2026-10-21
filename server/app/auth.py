from flask import Blueprint, jsonify, request
from flask_login import current_user, login_user, logout_user

from server.app import db
from server.app.models import Event, User

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error="invalid_credentials"), 400
    user = User.query.filter_by(username=username.strip(), active=True).first()
    if user is None or not user.check_password(password):
        return jsonify(error="invalid_credentials"), 401
    login_user(user)
    db.session.add(Event(user_id=user.id, event_type="admin.login", details={}))
    db.session.commit()
    return jsonify(user={"id": user.id, "username": user.username, "role": user.role})


@auth_bp.post("/logout")
def logout():
    if not current_user.is_authenticated:
        return jsonify(error="authentication_required"), 401
    user_id = current_user.id
    db.session.add(Event(user_id=user_id, event_type="admin.logout", details={}))
    db.session.commit()
    logout_user()
    return jsonify(status="ok")

