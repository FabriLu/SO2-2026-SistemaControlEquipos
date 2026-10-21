"""Cliente de la API REST de Proxmox VE para recuperación y control de máquinas virtuales."""

import logging
import os
import urllib3
import requests

logger = logging.getLogger(__name__)


class ProxmoxError(Exception):
    """Excepción para errores de comunicación u operaciones en Proxmox VE."""
    pass


class ProxmoxClient:
    """Cliente HTTP para interactuar con la API REST de Proxmox VE.
    
    Permite listar VMs, consultar snapshots, realizar rollback a 'estado_limpio'
    y encender/reiniciar máquinas virtuales de estudiantes en el hipervisor físico.
    """

    def __init__(
        self,
        host=None,
        port=8006,
        user=None,
        password=None,
        token_id=None,
        token_secret=None,
        default_node=None,
        default_snapshot=None,
        verify_ssl=None,
    ):
        raw_host = host or os.getenv("PROXMOX_HOST", "127.0.0.1")
        if raw_host.startswith("http://") or raw_host.startswith("https://"):
            self.base_url = raw_host.rstrip("/")
        else:
            self.base_url = f"https://{raw_host}:{port or 8006}"

        self.user = user or os.getenv("PROXMOX_USER", "root@pam")
        self.password = password or os.getenv("PROXMOX_PASSWORD", "")
        self.token_id = token_id or os.getenv("PROXMOX_TOKEN_ID", "")
        self.token_secret = token_secret or os.getenv("PROXMOX_TOKEN_SECRET", "")
        self.default_node = default_node or os.getenv("PROXMOX_NODE", "pve")
        self.default_snapshot = default_snapshot or os.getenv("PROXMOX_SNAPSHOT", "estado_limpio")

        if verify_ssl is None:
            verify_env = os.getenv("PROXMOX_VERIFY_SSL", "false").lower()
            self.verify_ssl = verify_env in ("true", "1", "yes")
        else:
            self.verify_ssl = bool(verify_ssl)

        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        self._ticket = None
        self._csrf_token = None

    @classmethod
    def from_env(cls):
        """Crea una instancia leyendo las variables de entorno disponibles."""
        return cls()

    def _get_headers(self):
        """Construye los encabezados de autenticación (API Token o Ticket de sesión)."""
        headers = {"Accept": "application/json"}
        # 1. Autenticación preferida: API Token (sin estado, seguro y directo)
        if self.token_id and self.token_secret:
            # Formato: USER@REALM!TOKENID=SECRET
            if "!" in self.token_id:
                token_str = f"{self.token_id}={self.token_secret}"
            else:
                token_str = f"{self.user}!{self.token_id}={self.token_secret}"
            headers["Authorization"] = f"PVEAPIToken={token_str}"
            return headers

        # 2. Autenticación por Ticket (Usuario y Contraseña)
        if self._ticket and self._csrf_token:
            headers["CSRFPreventionToken"] = self._csrf_token
        return headers

    def _ensure_auth(self):
        """Garantiza autenticación por ticket si se usa usuario y contraseña."""
        if self.token_id and self.token_secret:
            return  # Tokens no requieren llamada previa a /access/ticket

        if self._ticket and self._csrf_token:
            return

        if not self.password:
            raise ProxmoxError(
                "No se han configurado credenciales de Proxmox (se requiere API Token o Usuario+Contraseña)."
            )

        url = f"{self.base_url}/api2/json/access/ticket"
        try:
            resp = self.session.post(
                url,
                data={"username": self.user, "password": self.password},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            self._ticket = data.get("ticket")
            self._csrf_token = data.get("CSRFPreventionToken")
            self.session.cookies.set("PVEAuthCookie", self._ticket)
        except requests.RequestException as exc:
            logger.error("Error autenticando con Proxmox: %s", exc)
            raise ProxmoxError(f"Error de autenticación con Proxmox: {exc}") from exc

    def request(self, method, endpoint, params=None, data=None):
        """Ejecuta una petición HTTP a la API de Proxmox con reintento de autenticación."""
        self._ensure_auth()
        url = f"{self.base_url}/api2/json/{endpoint.lstrip('/')}"
        headers = self._get_headers()

        try:
            resp = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                headers=headers,
                timeout=15,
            )

            # Si venció el ticket (401), reintentar una vez
            if resp.status_code == 401 and not (self.token_id and self.token_secret):
                self._ticket = None
                self._csrf_token = None
                self._ensure_auth()
                headers = self._get_headers()
                resp = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    headers=headers,
                    timeout=15,
                )

            resp.raise_for_status()
            payload = resp.json()
            return payload.get("data")
        except requests.RequestException as exc:
            msg = f"Fallo en petición a Proxmox [{method} {endpoint}]: {exc}"
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    err_json = exc.response.json()
                    msg += f" - Detalle: {err_json.get('errors', exc.response.text)}"
                except Exception:
                    msg += f" - Status: {exc.response.status_code}"
            logger.error(msg)
            raise ProxmoxError(msg) from exc

    def test_connection(self):
        """Verifica la conectividad y devuelve la versión del servidor Proxmox."""
        try:
            version_data = self.request("GET", "/version")
            return {
                "status": "ok",
                "connected": True,
                "version": version_data.get("version"),
                "release": version_data.get("release"),
                "repoid": version_data.get("repoid"),
                "host": self.base_url,
            }
        except Exception as exc:
            return {
                "status": "error",
                "connected": False,
                "error": str(exc),
                "host": self.base_url,
            }

    def get_nodes(self):
        """Obtiene la lista de nodos disponibles en el cluster o host Proxmox."""
        nodes = self.request("GET", "/nodes")
        return nodes or []

    def get_vms(self, node=None):
        """Lista todas las máquinas virtuales QEMU del nodo indicado (o de todos los nodos)."""
        target_node = node or self.default_node
        try:
            vms = self.request("GET", f"/nodes/{target_node}/qemu")
            return vms or []
        except ProxmoxError:
            # Si el nodo configurado falló, intentar descubrir nodos online
            nodes = self.get_nodes()
            all_vms = []
            for n in nodes:
                n_name = n.get("node")
                if n_name and n.get("status") == "online":
                    try:
                        vms_node = self.request("GET", f"/nodes/{n_name}/qemu")
                        for vm in (vms_node or []):
                            vm["node"] = n_name
                            all_vms.append(vm)
                    except Exception:
                        continue
            return all_vms

    def get_vm_status(self, vmid, node=None):
        """Obtiene el estado actual de una máquina virtual (running, stopped, cpu, mem)."""
        target_node = node or self.default_node
        return self.request("GET", f"/nodes/{target_node}/qemu/{vmid}/status/current")

    def get_snapshots(self, vmid, node=None):
        """Devuelve la lista de snapshots existentes para una máquina virtual."""
        target_node = node or self.default_node
        return self.request("GET", f"/nodes/{target_node}/qemu/{vmid}/snapshot")

    def rollback_snapshot(self, vmid, snapshot_name=None, node=None):
        """Restaura la máquina virtual al snapshot indicado (por defecto 'estado_limpio').
        
        Retorna el UPID de la tarea de Proxmox.
        """
        target_node = node or self.default_node
        target_snapshot = snapshot_name or self.default_snapshot
        endpoint = f"/nodes/{target_node}/qemu/{vmid}/snapshot/{target_snapshot}/rollback"
        logger.info("Iniciando rollback de VM %s a snapshot '%s' en nodo %s", vmid, target_snapshot, target_node)
        return self.request("POST", endpoint)

    def start_vm(self, vmid, node=None):
        """Inicia (enciende) la máquina virtual en Proxmox."""
        target_node = node or self.default_node
        endpoint = f"/nodes/{target_node}/qemu/{vmid}/status/start"
        logger.info("Encendiendo VM %s en nodo %s", vmid, target_node)
        return self.request("POST", endpoint)

    def stop_vm(self, vmid, node=None):
        """Detiene (apaga) la máquina virtual en Proxmox."""
        target_node = node or self.default_node
        endpoint = f"/nodes/{target_node}/qemu/{vmid}/status/stop"
        logger.info("Deteniendo VM %s en nodo %s", vmid, target_node)
        return self.request("POST", endpoint)

    def reboot_vm(self, vmid, node=None):
        """Reinicia la máquina virtual en Proxmox."""
        target_node = node or self.default_node
        endpoint = f"/nodes/{target_node}/qemu/{vmid}/status/reboot"
        logger.info("Reiniciando VM %s en nodo %s", vmid, target_node)
        return self.request("POST", endpoint)

    def restore_clean_state(self, vmid, snapshot_name=None, node=None, auto_start=True):
        """Procedimiento completo de recuperación:
        1. Ejecuta rollback al snapshot 'estado_limpio'.
        2. Si auto_start es True, asegura que la VM quede encendida.
        """
        target_snapshot = snapshot_name or self.default_snapshot
        target_node = node or self.default_node

        rollback_task = self.rollback_snapshot(vmid, snapshot_name=target_snapshot, node=target_node)

        # Si auto_start está activado, enviamos la orden de start (Proxmox la encola o ejecuta tras el rollback)
        start_task = None
        if auto_start:
            try:
                start_task = self.start_vm(vmid, node=target_node)
            except Exception as exc:
                logger.warning("Aviso al encender VM tras rollback (puede estar ya iniciando): %s", exc)

        return {
            "status": "success",
            "vmid": vmid,
            "node": target_node,
            "snapshot": target_snapshot,
            "rollback_task": rollback_task,
            "start_task": start_task,
            "message": f"VM {vmid} restaurada con éxito al snapshot '{target_snapshot}'",
        }
