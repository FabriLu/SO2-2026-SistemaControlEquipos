"""Módulo de captura de pantalla para el agente de monitoreo (Ubuntu Desktop 24.04)."""

import base64
import io
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def capture_screen_base64(max_width=800, max_height=450, quality=65):
    """Captura la pantalla actual, la redimensiona y la comprime a JPEG en base64.
    
    Implementa fallbacks sucesivos:
    1. mss (alta velocidad y compatibilidad nativa)
    2. PIL.ImageGrab (Pillow)
    3. Herramientas de sistema en Linux (grim en Wayland, scrot o gnome-screenshot en X11)
    """
    # 1. Intento con mss + PIL
    try:
        import mss
        from PIL import Image

        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as exc:
        logger.debug("mss no disponible o falló: %s", exc)

    # 2. Intento directo con PIL.ImageGrab
    try:
        from PIL import ImageGrab

        img = ImageGrab.grab()
        img.thumbnail((max_width, max_height))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as exc:
        logger.debug("ImageGrab no disponible o falló: %s", exc)

    # 3. Intento con utilidades nativas de Linux (Ubuntu 24.04 Wayland / X11)
    for cmd in (["grim"], ["gnome-screenshot", "-f"], ["scrot"]):
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name

            exec_cmd = cmd + [tmp_path]
            res = subprocess.run(exec_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
            if res.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                try:
                    from PIL import Image
                    with Image.open(tmp_path) as img:
                        img.thumbnail((max_width, max_height))
                        buffer = io.BytesIO()
                        img.convert("RGB").save(buffer, format="JPEG", quality=quality)
                        return base64.b64encode(buffer.getvalue()).decode("utf-8")
                except ImportError:
                    # Si no hay PIL, leer archivo directo
                    with open(tmp_path, "rb") as f:
                        return base64.b64encode(f.read()).decode("utf-8")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
        except Exception:
            continue

    return None
