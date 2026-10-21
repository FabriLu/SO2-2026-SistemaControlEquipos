"""Agente de monitoreo, control y reporte para computadoras de estudiantes (Ubuntu Desktop 24.04)."""

import argparse
import json
import logging
import os
import platform
import socket
import subprocess
import time
import uuid
from pathlib import Path

import requests

from agent.locker import locker
from agent.screen import capture_screen_base64

logger = logging.getLogger("control-agent")


def get_local_ip():
    """Detecta la dirección IP de la interfaz de red activa."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        # No envía tráfico real, solo determina la ruta hacia el gateway
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_hardware_metrics():
    """Obtiene el consumo de CPU, RAM y disco mediante psutil si está disponible."""
    metrics = {
        "cpu_percent": 0.0,
        "ram_percent": 0.0,
        "disk_percent": 0.0,
    }
    try:
        import psutil

        metrics["cpu_percent"] = float(psutil.cpu_percent(interval=None))
        metrics["ram_percent"] = float(psutil.virtual_memory().percent)
        # Partición raíz en Linux
        path = "/" if os.name != "nt" else "C:\\"
        metrics["disk_percent"] = float(psutil.disk_usage(path).percent)
    except Exception as exc:
        logger.debug("psutil no disponible o error al leer métricas: %s", exc)
    return metrics


def load_config(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        config = json.load(stream)
    required = {"server_url", "agent_id", "device_name"}
    missing = required - config.keys()
    if missing:
        raise ValueError("Faltan claves de configuración: " + ", ".join(sorted(missing)))
    if not config.get("credential") and not config.get("enrollment_token"):
        raise ValueError("Se requiere credential o enrollment_token para este agente")
    try:
        config["agent_id"] = str(uuid.UUID(config["agent_id"]))
    except ValueError as exc:
        raise ValueError("agent_id debe ser un UUID válido") from exc
    config["server_url"] = config["server_url"].rstrip("/")
    config["_config_path"] = str(Path(path).resolve())
    return config


def _save_config(config):
    config_path = Path(config["_config_path"])
    saved = {key: value for key, value in config.items() if not key.startswith("_")}
    temp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass
    temp_path.replace(config_path)


def register(session, config):
    ip = get_local_ip()
    response = session.post(
        f"{config['server_url']}/api/agent/register",
        headers={"X-Enrollment-Token": config["enrollment_token"]},
        json={
            "agent_id": config["agent_id"],
            "name": config["device_name"],
            "hostname": socket.gethostname(),
            "ip_address": ip,
            "os_version": platform.platform(),
            "agent_version": "0.2.0",
        },
        timeout=10,
    )
    response.raise_for_status()
    config["credential"] = response.json()["credential"]
    config.pop("enrollment_token", None)
    _save_config(config)
    return config


def acknowledge_command(session, config, command_id, result_code="success", message=""):
    """Envía al servidor la confirmación de ejecución de una orden."""
    try:
        session.post(
            f"{config['server_url']}/api/agent/commands/{command_id}/ack",
            headers={"Authorization": f"Bearer {config['credential']}"},
            json={"result_code": result_code, "result_message": message},
            timeout=5,
        )
    except Exception as exc:
        logger.warning("No se pudo enviar ACK para orden %s: %s", command_id, exc)


def handle_commands(session, config, commands):
    """Procesa las órdenes pendientes enviadas por el servidor docente."""
    if not commands or not isinstance(commands, list):
        return

    for cmd in commands:
        cmd_id = cmd.get("id")
        cmd_type = cmd.get("type", "").lower()
        payload = cmd.get("payload") or {}

        logger.info("Procesando orden del servidor: %s (%s)", cmd_type, cmd_id)

        if cmd_type == "lock":
            msg = payload.get("message")
            locker.lock(message=msg)
            acknowledge_command(session, config, cmd_id, "success", "Pantalla bloqueada")

        elif cmd_type == "unlock":
            locker.unlock()
            acknowledge_command(session, config, cmd_id, "success", "Pantalla desbloqueada")

        elif cmd_type == "message":
            msg = payload.get("message", "Aviso del profesor")
            locker.show_message(msg)
            acknowledge_command(session, config, cmd_id, "success", "Mensaje desplegado")

        elif cmd_type == "reboot":
            acknowledge_command(session, config, cmd_id, "success", "Reiniciando equipo")
            # Ejecutar reinicio del sistema
            try:
                subprocess.Popen(["systemctl", "reboot"])
            except Exception:
                try:
                    subprocess.Popen(["reboot"])
                except Exception as e:
                    logger.error("Error al reiniciar: %s", e)

        elif cmd_type in ("poweroff", "shutdown"):
            acknowledge_command(session, config, cmd_id, "success", "Apagando equipo")
            # Ejecutar apagado del sistema
            try:
                subprocess.Popen(["systemctl", "poweroff"])
            except Exception:
                try:
                    subprocess.Popen(["shutdown", "-h", "now"])
                except Exception as e:
                    logger.error("Error al apagar: %s", e)


def send_heartbeat(session, config, include_screenshot=True):
    metrics = get_hardware_metrics()
    lock_state = "locked" if locker.is_locked() else "unlocked"

    payload = {
        "name": config["device_name"],
        "hostname": socket.gethostname(),
        "ip_address": get_local_ip(),
        "os_version": platform.platform(),
        "agent_version": "0.2.0",
        "lock_status": lock_state,
        "cpu_percent": metrics["cpu_percent"],
        "ram_percent": metrics["ram_percent"],
        "disk_percent": metrics["disk_percent"],
    }

    if include_screenshot:
        screenshot_b64 = capture_screen_base64()
        if screenshot_b64:
            payload["screenshot"] = screenshot_b64

    response = session.post(
        f"{config['server_url']}/api/agent/heartbeat",
        headers={"Authorization": f"Bearer {config['credential']}"},
        json=payload,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    # Si el servidor devolvió órdenes para ejecutar, procesarlas
    if "commands" in data and data["commands"]:
        handle_commands(session, config, data["commands"])

    return data


def run(config_path, interval):
    config = load_config(config_path)
    session = requests.Session()

    # Iniciar el hilo del bloqueador visual
    locker.start()

    if not config.get("credential"):
        logger.info("Enrolando agente con el servidor central...")
        config = register(session, config)
        logger.info("Agente enrolado con éxito. Credencial guardada.")

    logger.info("Agente en ejecución. Enviando señales cada %s segundos.", interval)
    while True:
        try:
            send_heartbeat(session, config, include_screenshot=True)
        except requests.RequestException as exc:
            logger.warning("Fallo al contactar servidor: %s", exc)
        time.sleep(interval)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="agent/config.json")
    parser.add_argument("--interval", type=int, default=5, help="Intervalo de reporte en segundos (por defecto 5s)")
    args = parser.parse_args()
    if args.interval < 2:
        parser.error("--interval debe ser de al menos 2 segundos")
    run(args.config, args.interval)


if __name__ == "__main__":
    main()
