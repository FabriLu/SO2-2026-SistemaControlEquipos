import click

from server.app import db
from server.app.models import User


def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def create_admin_command(username, password):
        """Create the initial administrator interactively."""
        if len(password) < 12:
            raise click.ClickException("La contraseña debe tener al menos 12 caracteres.")
        username = username.strip()
        if not username:
            raise click.ClickException("El nombre de usuario no puede estar vacío.")
        if User.query.filter_by(username=username).first():
            raise click.ClickException("Ese usuario ya existe.")
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrador creado: {user.username}")

    @app.cli.command("proxmox-test")
    def proxmox_test_command():
        """Verifica la conectividad y versión de Proxmox VE."""
        from server.proxmox import ProxmoxClient

        client = ProxmoxClient.from_env()
        click.echo(f"Probando conexión con Proxmox en: {client.base_url} ...")
        res = client.test_connection()
        if res.get("connected"):
            click.echo(click.style(f"✓ Conectado exitosamente: PVE {res.get('version')} (release {res.get('release')})", fg="green"))
        else:
            click.echo(click.style(f"✗ Falló la conexión: {res.get('error')}", fg="red"))


