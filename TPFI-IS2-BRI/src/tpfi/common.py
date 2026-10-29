"""Utilidades compartidas por el servidor y los clientes."""

import logging
import sys
import uuid

SERVIDOR_PREDETERMINADO = "localhost"
PUERTO_PREDETERMINADO = 8080

# Campos del tuple CorporateData (Tabla 1 de la consigna), sin la clave "id".
CAMPOS_CORPORATIVOS: frozenset[str] = frozenset(
    {
        "cp",
        "CUIT",
        "domicilio",
        "idreq",
        "idSeq",
        "localidad",
        "provincia",
        "sede",
        "seqID",
        "telefono",
        "web",
    }
)


def uuid_cpu() -> str:
    """Devuelve el identificador único de la CPU (``uuid.getnode()``)."""
    return str(uuid.getnode())


def configurar_registro(verbose: bool) -> None:
    """Configura ``logging`` por salida estándar; DEBUG solo con ``-v``."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
        stream=sys.stdout,
        force=True,
    )


def actualizaciones_corporativas(payload: dict[str, object]) -> dict[str, object]:
    """Extrae del pedido solo los campos válidos del tuple CorporateData."""
    return {k: v for k, v in payload.items() if k in CAMPOS_CORPORATIVOS}
