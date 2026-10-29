"""ObserverClient: cliente suscripto a los cambios de CorporateData."""

import argparse
import json
import logging
import socket
import threading
from pathlib import Path

from tpfi.common import (
    PUERTO_PREDETERMINADO,
    SERVIDOR_PREDETERMINADO,
    configurar_registro,
    uuid_cpu,
)
from tpfi.jsonio import codificar_json


class ClienteObservador:
    """Mantiene la conexión abierta, reconecta y re-suscribe si se interrumpe."""

    def __init__(
        self,
        host: str = SERVIDOR_PREDETERMINADO,
        port: int = PUERTO_PREDETERMINADO,
        output_file: str | None = None,
        retry_interval: float = 30.0,
    ) -> None:
        """Define el servidor, el archivo de salida y el intervalo de reintento."""
        self.host = host
        self.port = port
        self.output_file = output_file
        self.retry_interval = retry_interval
        self.sock: socket.socket | None = None
        self._stop = threading.Event()

    def connect(self) -> bool:
        """Abre la conexión TCP; devuelve ``False`` si falla."""
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=10)
            self.sock.settimeout(None)
        except OSError as exc:
            logging.error("No se pudo conectar a %s:%d (%s)", self.host, self.port, exc)
            self.sock = None
            return False
        return True

    def disconnect(self) -> None:
        """Cierra la conexión si está abierta."""
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def subscribe(self) -> bool:
        """Envía la acción de suscripción; devuelve ``False`` si falla."""
        if self.sock is None:
            return False
        try:
            self.sock.sendall(
                codificar_json({"UUID": uuid_cpu(), "ACTION": "subscribe"})
            )
        except OSError as exc:
            logging.error("No se pudo suscribir: %s", exc)
            return False
        logging.debug("Suscripción enviada")
        return True

    def notificar(self, message: object) -> None:
        """Muestra una notificación por salida estándar y en el archivo (si hay)."""
        text = json.dumps(message, ensure_ascii=False)
        print(text, flush=True)
        if self.output_file:
            with Path(self.output_file).open("a", encoding="utf-8") as handle:
                handle.write(text + "\n")

    def listen(self) -> bool:
        """Recibe notificaciones hasta que el servidor cierre; ``False`` al cortar."""
        sock = self.sock
        if sock is None:
            return False
        buffer = b""
        try:
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    logging.warning("El servidor cerró la conexión")
                    return False
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        self.notificar(json.loads(line.decode("utf-8")))
                    except ValueError:
                        logging.warning("Mensaje descartado (JSON inválido)")
        except OSError as exc:
            logging.warning("Conexión interrumpida: %s", exc)
            return False

    def run(self) -> None:
        """Bucle principal: conecta, suscribe, escucha y reintenta al caer."""
        while not self._stop.is_set():
            if self.connect() and self.subscribe():
                self.listen()
            self.disconnect()
            if not self._stop.is_set():
                logging.info("Reintentando en %s segundos...", self.retry_interval)
                self._stop.wait(self.retry_interval)

    def stop(self) -> None:
        """Detiene el bucle principal."""
        self._stop.set()
        self.disconnect()


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: ``observerclient.py {-s=host} {-p=port} {-o=file} {-v}``."""
    parser = argparse.ArgumentParser(description="ObserverClient")
    parser.add_argument("-s", "--server", default=SERVIDOR_PREDETERMINADO, help="host")
    parser.add_argument(
        "-p", "--port", type=int, default=PUERTO_PREDETERMINADO, help="puerto"
    )
    parser.add_argument("-o", "--output", help="archivo JSON de salida (opcional)")
    parser.add_argument("--retry-interval", type=float, default=30.0, help="segundos")
    parser.add_argument("-v", "--verbose", action="store_true", help="mensajes debug")
    args = parser.parse_args(argv)
    configurar_registro(args.verbose)
    client = ClienteObservador(args.server, args.port, args.output, args.retry_interval)
    try:
        client.run()
    except KeyboardInterrupt:
        client.stop()
    return 0
