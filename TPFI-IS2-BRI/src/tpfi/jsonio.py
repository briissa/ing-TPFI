"""Lectura y escritura de mensajes JSON sobre sockets TCP."""

import decimal
import json
import socket
from typing import Any

_CHUNK = 4096


def _default(value: object) -> object:
    """Serializa ``Decimal`` (tipo numérico de DynamoDB) a int o float."""
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def codificar_json(payload: Any) -> bytes:
    """Serializa ``payload`` como una línea JSON terminada en salto de línea."""
    text = json.dumps(payload, ensure_ascii=False, default=_default)
    return text.encode("utf-8") + b"\n"


def leer_mensaje_json(sock: socket.socket) -> Any:
    """Lee un mensaje JSON: una línea o un JSON completo hasta el cierre.

    Raises:
        ValueError: si el mensaje está vacío o no es JSON válido.
    """
    buffer = b""
    while True:
        chunk = sock.recv(_CHUNK)
        if not chunk:
            break
        buffer += chunk
        if b"\n" in buffer:
            line = buffer.split(b"\n", 1)[0]
            if line.strip():
                return json.loads(line.decode("utf-8"))
            buffer = b""
    if not buffer.strip():
        raise ValueError("Empty request")
    return json.loads(buffer.decode("utf-8"))
