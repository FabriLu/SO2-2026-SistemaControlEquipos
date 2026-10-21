import pytest

from server.app import create_app, db
from server.app.cli import register_cli
from server.app.models import User


@pytest.fixture
def app(tmp_path):
    database_file = tmp_path / "test.sqlite3"
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_file.as_posix()}",
        "AGENT_ENROLLMENT_TOKEN": "test-enrollment-token",
        "HEARTBEAT_TIMEOUT_SECONDS": 90,
    })
    register_cli(app)
    with app.app_context():
        db.create_all()
        user = User(username="teacher")
        user.set_password("a-long-test-password")
        db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()

