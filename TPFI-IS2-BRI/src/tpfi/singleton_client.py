"""SingletonClient: cliente de operaciones get, set y list."""

import argparse
import json
import logging
import socket
from pathlib import Path
from typing import Any

from tpfi.common import (
    PUERTO_PREDETERMINADO,
    SERVIDOR_PREDETERMINADO,
    actualizaciones_corporativas,
    configurar_registro,
    uuid_cpu,
)
from tpfi.jsonio import codificar_json


class ClienteSingleton:
    """Envía un pedido al servidor y devuelve su respuesta."""

    def __init__(
        self, host: str = SERVIDOR_PREDETERMINADO, port: int = PUERTO_PREDETERMINADO
    ) -> None:
        """Define el servidor destino."""
        self.host = host
        self.port = port

    @staticmethod
    def construir_solicitud(data: Any) -> dict[str, Any]:
        """Valida el pedido y le agrega el UUID de la CPU.

        Raises:
            ValueError: si falta la acción, el ID o los datos mínimos.
        """
        if not isinstance(data, dict):
            raise ValueError("Input must be a JSON object")
        action = data.get("ACTION")
        if action not in ("get", "set", "list"):
            raise ValueError("ACTION must be 'get', 'set' or 'list'")
        request = dict(data)
        if action == "list":
            request.pop("ID", None)
        elif not request.get("ID"):
            raise ValueError(f"ACTION '{action}' requires an ID")
        if action == "set" and not actualizaciones_corporativas(request):
            raise ValueError("ACTION 'set' requires at least one CorporateData field")
        request.setdefault("UUID", uuid_cpu())
        return request

    def enviar_solicitud(self, request: dict[str, Any]) -> Any:
        """Envía el pedido por TCP y devuelve la respuesta JSON.

        Raises:
            ConnectionError: si no se puede contactar al servidor.
            ValueError: si la respuesta está vacía o no es JSON.
        """
        try:
            with socket.create_connection((self.host, self.port), timeout=10) as sock:
                sock.sendall(codificar_json(request))
                answer = b""
                while chunk := sock.recv(4096):
                    answer += chunk
        except OSError as exc:
            raise ConnectionError(
                f"Could not connect to server {self.host}:{self.port}"
            ) from exc
        if not answer.strip():
            raise ValueError("Empty response from server")
        try:
            return json.loads(answer.decode("utf-8"))
        except ValueError as exc:
            raise ValueError("Invalid JSON response from server") from exc


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: ``singletonclient.py -i=input.json {-o=output.json} {-v}``."""
    parser = argparse.ArgumentParser(description="SingletonClient")
    parser.add_argument("-i", "--input", required=True, help="JSON de entrada")
    parser.add_argument("-o", "--output", help="JSON de salida (opcional)")
    parser.add_argument("-s", "--server", default=SERVIDOR_PREDETERMINADO, help="host")
    parser.add_argument(
        "-p", "--port", type=int, default=PUERTO_PREDETERMINADO, help="puerto"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="mensajes debug")
    args = parser.parse_args(argv)
    configurar_registro(args.verbose)
    try:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        client = ClienteSingleton(args.server, args.port)
        request = client.construir_solicitud(data)
        logging.debug("Enviando: %s", request)
        response = client.enviar_solicitud(request)
    except (OSError, ValueError) as exc:
        logging.error("%s", exc)
        return 1
    text = json.dumps(response, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


def _main_command(action: str, argv: list[str] | None = None) -> int:
    """Ejecuta una operación CLI sin requerir un archivo JSON."""
    parser = argparse.ArgumentParser(description=f"SingletonClient {action}")
    if action in ("get", "set"):
        parser.add_argument("--id", required=True, help="ID del registro")
    field_options = {
        "cp": "--cp",
        "CUIT": "--cuit",
        "domicilio": "--domicilio",
        "idreq": "--idreq",
        "idSeq": "--id-seq",
        "localidad": "--localidad",
        "provincia": "--provincia",
        "sede": "--sede",
        "seqID": "--seq-id",
        "telefono": "--telefono",
        "web": "--web",
    }
    if action == "set":
        for field, option in field_options.items():
            parser.add_argument(option, dest=field, help=f"Valor de {field}")
    parser.add_argument("-s", "--server", default=SERVIDOR_PREDETERMINADO, help="host")
    parser.add_argument(
        "-p", "--port", type=int, default=PUERTO_PREDETERMINADO, help="puerto"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="mensajes debug")
    args = parser.parse_args(argv)
    configurar_registro(args.verbose)

    request: dict[str, Any] = {"ACTION": action}
    if action in ("get", "set"):
        request["ID"] = args.id
    if action == "set":
        request.update(
            {
                field: value
                for field in field_options
                if (value := getattr(args, field)) is not None
            }
        )

    try:
        client = ClienteSingleton(args.server, args.port)
        response = client.enviar_solicitud(
            ClienteSingleton.construir_solicitud(request)
        )
    except (OSError, ValueError) as exc:
        logging.error("%s", exc)
        return 1

    print(json.dumps(response, indent=2, ensure_ascii=False))
    return 0


def main_set(argv: list[str] | None = None) -> int:
    """Ejecuta ``singleton-set --id ID --campo valor``."""
    return _main_command("set", argv)


def main_get(argv: list[str] | None = None) -> int:
    """Ejecuta ``singleton-get --id ID``."""
    return _main_command("get", argv)


def main_list(argv: list[str] | None = None) -> int:
    """Ejecuta ``singleton-list``."""
    return _main_command("list", argv)
