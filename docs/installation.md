# Guía de Instalación, Configuración y Despliegue

Sistema centralizado de control de aula, supervisión de pantallas en vivo (estilo Veyon) y recuperación de máquinas virtuales mediante la API REST de Proxmox VE.

---

## 1. Arquitectura del Sistema

```
+-------------------------------------------------------------+
|   Máquina Física 1 (Red Local)                              |
|   Proxmox VE 8.x (IP: ej. 192.168.1.50:8006)                 |
|   - VM 101: Ubuntu Desktop 24.04 (Snapshot: estado_limpio)  |
|   - VM 102: Ubuntu Desktop 24.04 (Snapshot: estado_limpio)  |
+-------------------------------------------------------------+
                              ^
                              | (API REST HTTPS / PVEAPIToken)
+-----------------------------+-------------------------------+
|   Servidor Central (Docente)                                |
|   Python 3 + Flask + SQLite (IP: ej. 192.168.1.10:5000)     |
|   - Panel Web Docente (HTML/CSS/JS - Cuadrícula en vivo)     |
|   - Módulo Proxmox (Rollback instantáneo a estado_limpio)   |
|   - API de Control (Bloqueo, Mensajes, Métricas psutil)     |
+-------------------------------------------------------------+
           ^                                     ^
           | (HTTP Heartbeat / Capturas)         |
+----------+------------------+     +------------+--------------------+
| Estudiante 01 (Ubuntu VM)   |     | Estudiante 02 (Ubuntu VM)       |
| - Agente Python (systemd)   |     | - Agente Python (systemd)       |
| - Bloqueador Tkinter modal  |     | - Bloqueador Tkinter modal      |
| - Capturas de pantalla      |     | - Capturas de pantalla          |
| - Métricas psutil (CPU/RAM) |     | - Métricas psutil (CPU/RAM)     |
+-----------------------------+     +---------------------------------+
```

---

## 2. Preparación del Servidor (Docente)

### Requisitos previos
- Ubuntu Server 24.04 LTS (o cualquier sistema con Python 3.10+).
- SQLite3 (incluido en la biblioteca estándar de Python).

### Pasos de instalación

1. **Crear y activar el entorno virtual:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   pip install -r requirements-server.txt
   ```

2. **Configurar variables de entorno:**
   Copiar `.env.example` a `.env`:
   ```bash
   cp .env.example .env
   ```
   Editar `.env` con los datos de tu red y Proxmox:
   ```ini
   FLASK_APP=server.wsgi:app
   SECRET_KEY=clave-secreta-docente-segura
   DATABASE_URL=sqlite:///control_equipos.sqlite3
   AGENT_ENROLLMENT_TOKEN=token-de-enrolamiento-aula-2026
   HEARTBEAT_TIMEOUT_SECONDS=30

   # Conexión con Proxmox VE (Servidor físico)
   PROXMOX_HOST=192.168.1.50
   PROXMOX_USER=root@pam
   PROXMOX_TOKEN_ID=control-aula
   PROXMOX_TOKEN_SECRET=tu-token-secret-de-proxmox
   PROXMOX_NODE=pve
   PROXMOX_SNAPSHOT=estado_limpio
   PROXMOX_VERIFY_SSL=false
   ```

3. **Inicializar la base de datos SQLite:**
   ```bash
   flask db upgrade
   ```

4. **Crear la cuenta del docente administrador:**
   ```bash
   flask create-admin
   ```
   *Ingresa el nombre de usuario (ej. `docente`) y contraseña (mínimo 12 caracteres).*

5. **Probar la conectividad con Proxmox desde la terminal:**
   ```bash
   flask proxmox-test
   ```

6. **Iniciar el servidor web:**
   ```bash
   flask run --host 0.0.0.0 --port 5000
   ```
   Accede desde el navegador del docente a: `http://localhost:5000` (o la IP de la máquina docente).

---

## 3. Preparación de Proxmox VE

Para habilitar la **Recuperación Estrella**:

1. **Crear el Snapshot Limpio en cada VM de estudiante:**
   - En la consola web de Proxmox (`https://192.168.1.50:8006`), selecciona la VM de Ubuntu Desktop (ej. VM 101).
   - Con la máquina configurada y limpia, ve a **Snapshots** -> **Take Snapshot**.
   - Nombre del snapshot: **`estado_limpio`** (exactamente ese nombre).
   - Descripción: "Instalación base limpia para rollback de aula".

2. **Crear un API Token en Proxmox:**
   - Ve a **Datacenter** -> **Permissions** -> **API Tokens** -> **Add**.
   - User: `root@pam` (o usuario dedicado).
   - Token ID: `control-aula`.
   - Desmarcar "Privilege Separation" (para que herede permisos).
   - Copia el **Secret** generado y colócalo en el `.env` del servidor (`PROXMOX_TOKEN_SECRET`).

---

## 4. Preparación de las Máquinas Estudiantes (Ubuntu Desktop 24.04)

### Requisitos en Ubuntu Desktop:
Instalar paquetes base del sistema:
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-tk
```

### Instalación del Agente:

1. **Crear directorio e instalar dependencias:**
   ```bash
   sudo mkdir -p /opt/control-agent
   sudo chown -R $USER:$USER /opt/control-agent
   cd /opt/control-agent

   # Copiar la carpeta 'agent/' del proyecto a /opt/control-agent/agent/
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements-agent.txt
   ```

2. **Configurar el agente (`config.json`):**
   Crear `/opt/control-agent/config.json`:
   ```json
   {
     "server_url": "http://192.168.1.10:5000",
     "agent_id": "00000000-0000-4000-8000-000000000001",
     "device_name": "PC-Estudiante-01",
     "enrollment_token": "token-de-enrolamiento-aula-2026"
   }
   ```
   *(Nota: Cada PC debe tener un `agent_id` único en formato UUID).*

3. **Probar el agente manualmente:**
   ```bash
   python3 -m agent.client --config /opt/control-agent/config.json --interval 5
   ```
   *En el primer inicio se enrolará, guardará su credencial individual y comenzará a enviar métricas y capturas.*

4. **Instalar como servicio `systemd` para arranque automático:**
   ```bash
   sudo cp agent/control-agent.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now control-agent.service
   ```
   Verificar estado:
   ```bash
   sudo systemctl status control-agent.service
   ```

---

## 5. Pruebas Automatizadas

Para validar que todo el código, API y módulo Proxmox funcionan correctamente:

```bash
python -m pytest -v
```

Resultado esperado: **16/16 pruebas pasando exitosamente**.
