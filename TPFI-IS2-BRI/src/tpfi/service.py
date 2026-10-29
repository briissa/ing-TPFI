"""Servicio de datos corporativos y su Proxy de auditoría (patrón Proxy)."""

import datetime
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from tpfi.common import CAMPOS_CORPORATIVOS
from tpfi.storage import Registro, TablaDatosCorporativos, TablaRegistroCorporativo


@dataclass(frozen=True)
class ContextoSolicitud:
    """Identifica quién solicita: CPU del cliente y sesión de la conexión."""

    uuid: str
    session_id: str


class ServicioCorporativo(ABC):
    """Interfaz común del sujeto real y de su proxy."""

    @abstractmethod
    def get(self, ctx: ContextoSolicitud, record_id: str) -> Registro | None:
        """Recupera un registro, o ``None`` si no existe."""

    @abstractmethod
    def set(self, ctx: ContextoSolicitud, record_id: str, fields: Registro) -> Registro:
        """Crea o modifica un registro y devuelve el resultado."""

    @abstractmethod
    def list(self, ctx: ContextoSolicitud) -> list[Registro]:
        """Devuelve todos los registros."""


class RegistroAuditoria:
    """Escribe la pista de auditoría en la tabla CorporateLog."""

    def __init__(self, table: TablaRegistroCorporativo | None = None) -> None:
        """Usa el Singleton de CorporateLog salvo que se inyecte otra tabla."""
        self._table = table if table is not None else TablaRegistroCorporativo()

    def registrar(
        self, ctx: ContextoSolicitud, action: str, record_id: str | None = None
    ) -> None:
        """Registra UUID, sesión, acción, ID (si aplica) y timestamp."""
        entry: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "CPUid": ctx.uuid,
            "sessionid": ctx.session_id,
            "accion": action,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        }
        if record_id is not None:
            entry["idsolicitado"] = record_id
        self._table.put_item(entry)


class ServicioCorporativoReal(ServicioCorporativo):
    """Sujeto real: opera sobre el Singleton de CorporateData."""

    def __init__(self, table: TablaDatosCorporativos | None = None) -> None:
        """Usa el Singleton de CorporateData salvo que se inyecte otra tabla."""
        self._table = table if table is not None else TablaDatosCorporativos()

    def get(self, ctx: ContextoSolicitud, record_id: str) -> Registro | None:
        """Lee el registro pedido."""
        return self._table.get_item(record_id)

    def set(self, ctx: ContextoSolicitud, record_id: str, fields: Registro) -> Registro:
        """Mezcla los campos informados con el registro existente (o uno vacío)."""
        merged: Registro = {name: "" for name in CAMPOS_CORPORATIVOS}
        merged["id"] = record_id
        existing = self._table.get_item(record_id)
        if existing:
            merged.update(existing)
        merged.update({k: v for k, v in fields.items() if k in CAMPOS_CORPORATIVOS})
        self._table.put_item(merged)
        return merged

    def list(self, ctx: ContextoSolicitud) -> list[Registro]:
        """Lee todos los registros de la tabla."""
        return list(self._table.scan())


class ProxyCorporativo(ServicioCorporativo):
    """Proxy: valida y audita cada pedido antes de delegar en el sujeto real."""

    def __init__(self, real: ServicioCorporativo, audit: RegistroAuditoria) -> None:
        """Recibe el sujeto real y la pista de auditoría."""
        self._real = real
        self._audit = audit

    def get(self, ctx: ContextoSolicitud, record_id: str) -> Registro | None:
        """Valida el ID, audita y delega."""
        if not record_id:
            raise ValueError("get requires ID")
        self._audit.registrar(ctx, "get", record_id)
        return self._real.get(ctx, record_id)

    def set(self, ctx: ContextoSolicitud, record_id: str, fields: Registro) -> Registro:
        """Valida ID y campos, audita y delega."""
        if not record_id:
            raise ValueError("set requires ID")
        if not any(k in CAMPOS_CORPORATIVOS for k in fields):
            raise ValueError("set requires at least one CorporateData field")
        self._audit.registrar(ctx, "set", record_id)
        return self._real.set(ctx, record_id, fields)

    def list(self, ctx: ContextoSolicitud) -> list[Registro]:
        """Audita y delega."""
        self._audit.registrar(ctx, "list")
        return self._real.list(ctx)
