# Sistema de Control, Monitoreo y Recuperación de Equipos

Aplicación para administrar equipos de un aula desde un servidor central. El servidor ofrece un panel web y una API; cada equipo estudiante ejecuta un agente que reporta su estado y recibe órdenes. El proyecto está en desarrollo.

## Funciones implementadas

- Inicio de sesión para el administrador y creación inicial de la cuenta mediante un comando Flask.
- Registro de agentes con token de enrolamiento y credencial individual.
- Panel web con estado de conexión, métricas y capturas de pantalla recientes.
- Órdenes individuales y grupales para bloquear, desbloquear, mostrar mensajes, reiniciar y apagar equipos.
- Registro de eventos, órdenes y sus confirmaciones.
- Integración con Proxmox VE: consulta de estado y máquinas virtuales, asociación de un equipo con una VM y restauración de una o todas las VM asociadas al snapshot configurado.
- Endpoint de salud del servidor en `/health`.

Las órdenes para los agentes se entregan en el siguiente heartbeat. La restauración en Proxmox depende de que la VM tenga el snapshot configurado y de que el servidor tenga credenciales y permisos válidos.

## Tecnologías

- Python, Flask, Flask-SQLAlchemy y Flask-Migrate.
- SQLite por defecto; la configuración también admite otros motores SQLAlchemy.
- HTML, CSS y JavaScript para el panel web.
- Agente Python con `requests`, `psutil`, `mss` y Pillow.
- API REST de Proxmox VE para la recuperación de máquinas virtuales.
- `systemd` como opción para ejecutar el agente en Ubuntu.

Las dependencias se encuentran separadas entre [`requirements-server.txt`](requirements-server.txt) y [`requirements-agent.txt`](requirements-agent.txt).

## Inicio rápido del servidor

Requiere Python 3.10 o posterior.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-server.txt
```

Copia `.env.example` a `.env` y configura al menos `SECRET_KEY` y `AGENT_ENROLLMENT_TOKEN`. Para usar Proxmox, configura también las variables `PROXMOX_*`. Después ejecuta:

```bash
flask --app server.wsgi:app db upgrade
flask --app server.wsgi:app create-admin
flask --app server.wsgi:app run --host 0.0.0.0 --port 5000
```

Abre `http://localhost:5000` en el navegador. `create-admin` solicita nombre de usuario y contraseña; exige una contraseña de al menos 12 caracteres.

## Instalar un agente

Consulta la [guía de instalación y despliegue](docs/installation.md) para configurar el agente, preparar Proxmox y registrar el servicio `systemd`. La plantilla de configuración del agente está en [`config/agent.example.json`](config/agent.example.json); cada equipo necesita un `agent_id` UUID único y un token de enrolamiento válido. Al enrolarse, el agente reemplaza el token por su credencial individual.

## Pruebas

La suite automatizada está en `tests/` y se ejecuta con:

```bash
python -m pytest -v
```

## Estructura

```text
agent/       Agente de los equipos estudiante
config/      Plantillas de configuración
docs/        Guía de instalación y despliegue
migrations/  Migraciones de la base de datos
server/      Aplicación Flask, API, panel y cliente Proxmox
tests/       Pruebas automatizadas
```

## Datos del proyecto

- Responsable: Fabrizio Hernán Magne Luizaga
- Rol: Scrum master y desarrollador
