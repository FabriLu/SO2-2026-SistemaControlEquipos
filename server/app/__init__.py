import os
from flask import Flask, jsonify
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect, generate_csrf

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///control_equipos.sqlite3"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AGENT_ENROLLMENT_TOKEN=os.getenv("AGENT_ENROLLMENT_TOKEN", ""),
        HEARTBEAT_TIMEOUT_SECONDS=int(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "90")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        WTF_CSRF_CHECK_DEFAULT=True,
        WTF_CSRF_TIME_LIMIT=None,
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from server.app import models  # noqa: F401
    from server.app.api.agent import agent_bp
    from server.app.api.admin import admin_bp
    from server.app.auth import auth_bp
    from server.app.web import web_bp

    app.register_blueprint(web_bp, url_prefix="")
    app.register_blueprint(agent_bp, url_prefix="/api/agent")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    csrf.exempt(agent_bp)

    @login_manager.user_loader
    def load_user(user_id):
        from server.app.models import User

        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import redirect, request, url_for
        if request.path.startswith("/api/"):
            return jsonify(error="authentication_required"), 401
        return redirect(url_for("web.login"))

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/admin/csrf")
    def csrf_token():
        return jsonify(csrf_token=generate_csrf())

    return app

