"""Servidor de aplicaciones SingletonProxyObserverTPFI."""

import argparse
import logging
import socket
import sys
import threading
import uuid
from typing import Any

from tpfi.common import actualizaciones_corporativas, configurar_registro
from tpfi.jsonio import codificar_json, leer_mensaje_json
from tpfi.observer import ObservadorSocket, SujetoObservable
from tpfi.service import (
    ContextoSolicitud,
    ProxyCorporativo,
    RegistroAuditoria,
    ServicioCorporativo,
    ServicioCorporativoReal,
)

TIEMPO_ESPERA_SOLICITUD = 30.0


class ErrorInicioServidor(RuntimeError):
    """El servidor no pudo abrir su puerto (por ejemplo, ya está en uso)."""


class ServidorTPFI:
    """Acepta conexiones TCP y despacha get, set, list y subscribe."""

    def __init__(
        self,
        host: str = "0.0.0.0",  # nosec B104  # noqa: S104
        port: int = 8080,
        service: ServicioCorporativo | None = None,
        audit: RegistroAuditoria | None = None,
        sujeto: SujetoObservable | None = None,
    ) -> None:
        """Configura el servidor; las dependencias se crean al arrancar."""
        self.host = host
        self.port = port
        self.ready = threading.Event()
        self._service = service
        self._audit = audit
        self.sujeto = sujeto if sujeto is not None else SujetoObservable()
        self._listener: socket.socket | None = None
        self._running = False

    def servir_permanentemente(self) -> None:
        """Abre el puerto y atiende conexiones (un hilo por conexión)."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)  # solo Windows
        if exclusive is not None:
            listener.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((self.host, self.port))
        except OSError as exc:
            listener.close()
            raise ErrorInicioServidor(
                f"Cannot bind {self.host}:{self.port} ({exc})"
            ) from exc
        self.port = int(listener.getsockname()[1])
        # El acceso a AWS se prepara después del bind para fallar primero por puerto.
        self._audit = self._audit or RegistroAuditoria()
        self._service = self._service or ProxyCorporativo(
            ServicioCorporativoReal(), self._audit
        )
        listener.listen()
        self._listener = listener
        self._running = True
        self.ready.set()
        logging.info("Servidor escuchando en %s:%d", self.host, self.port)
        while self._running:
            try:
                conn, addr = listener.accept()
            except OSError:
                break
            threading.Thread(
                target=self._gestionar_conexion, args=(conn, addr), daemon=True
            ).start()

    def cerrar_servidor(self) -> None:
        """Detiene el servidor cerrando el socket de escucha."""
        self._running = False
        if self._listener is not None:
            self._listener.close()

    def _gestionar_conexion(self, conn: socket.socket, addr: Any) -> None:
        """Atiende una conexión: lee el pedido, lo despacha y la cierra."""
        session_id = str(uuid.uuid4())
        logging.debug("Conexión de %s, sesión %s", addr, session_id)
        try:
            conn.settimeout(TIEMPO_ESPERA_SOLICITUD)
            request = leer_mensaje_json(conn)
            conn.settimeout(None)
            self._despachar_solicitud(conn, request, session_id)
        except ValueError as exc:
            self._responder(conn, {"Error": str(exc)})
        except OSError as exc:
            logging.debug("Error de red: %s", exc)
        except Exception:
            logging.exception("Error interno")
            self._responder(conn, {"Error": "Internal server error"})
        finally:
            conn.close()

    def _despachar_solicitud(
        self, conn: socket.socket, request: Any, session_id: str
    ) -> None:
        """Valida el pedido y ejecuta la acción solicitada."""
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object")
        client_uuid = request.get("UUID")
        if not client_uuid:
            raise ValueError("UUID is required")
        ctx = ContextoSolicitud(uuid=str(client_uuid), session_id=session_id)
        action = request.get("ACTION")
        record_id = str(request.get("ID") or "")
        service, audit = self._service, self._audit
        if service is None or audit is None:
            raise RuntimeError("Server not started")
        logging.debug("Pedido %s de %s (ID=%r)", action, ctx.uuid, record_id)

        if action == "subscribe":
            self._gestionar_suscripcion(conn, ctx, audit)
        elif action == "get":
            record = service.get(ctx, record_id)
            logging.info(
                "GET id=%s: %s",
                record_id,
                "registro encontrado" if record is not None else "no encontrado",
            )
            self._responder(
                conn,
                record if record is not None else {"Error": f"Not found: {record_id}"},
            )
        elif action == "list":
            records = service.list(ctx)
            logging.info("LIST: %d registros", len(records))
            self._responder(conn, records)
        elif action == "set":
            result = service.set(ctx, record_id, actualizaciones_corporativas(request))
            logging.info("SET id=%s: registro actualizado en DynamoDB", record_id)
            self._responder(conn, result)
            self.sujeto.notificar(
                {"UUID": ctx.uuid, "ID": record_id, "ACTION": "change", "Data": result}
            )
        else:
            raise ValueError(f"Unknown ACTION: {action}")

    def _gestionar_suscripcion(
        self, conn: socket.socket, ctx: ContextoSolicitud, audit: RegistroAuditoria
    ) -> None:
        """Audita, registra el socket como observador y espera su desconexión."""
        audit.registrar(ctx, "subscribe")
        observer = ObservadorSocket(conn, ctx.uuid)
        self.sujeto.attach(observer)
        try:
            while conn.recv(4096):
                pass
        except OSError as exc:
            logging.debug("Suscriptor desconectado: %s", exc)
        finally:
            self.sujeto.detach(observer)

    @staticmethod
    def _responder(conn: socket.socket, payload: Any) -> None:
        """Envía la respuesta; ignora clientes que ya cerraron."""
        try:
            conn.sendall(codificar_json(payload))
        except OSError as exc:
            logging.debug("No se pudo responder: %s", exc)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: ``singletonproxyobserver.py {-p=port} {-v}``."""
    parser = argparse.ArgumentParser(description="SingletonProxyObserverTPFI")
    parser.add_argument("-p", "--port", type=int, default=8080, help="puerto TCP")
    parser.add_argument("-v", "--verbose", action="store_true", help="mensajes debug")
    args = parser.parse_args(argv)
    configurar_registro(args.verbose)
    server = ServidorTPFI(port=args.port)
    try:
        server.servir_permanentemente()
    except ErrorInicioServidor as exc:
        logging.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        server.cerrar_servidor()
    return 0


if __name__ == "__main__":
    sys.exit(main())
