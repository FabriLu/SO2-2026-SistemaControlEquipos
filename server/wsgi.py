from server.app import create_app
from server.app.cli import register_cli

app = create_app()
register_cli(app)

