"""Acceso físico a las tablas CorporateData y CorporateLog (patrón Singleton).

Cada tabla tiene su propio Singleton. Con ``TPFI_USE_MEMORY=1`` se usa un
almacenamiento en memoria (para pruebas sin AWS); si no, DynamoDB.
"""

import decimal
import os
import threading
from collections.abc import Iterator
from typing import Any, ClassVar

Registro = dict[str, Any]


def use_memory() -> bool:
    """Indica si se debe usar el almacenamiento en memoria."""
    return os.environ.get("TPFI_USE_MEMORY", "").lower() in ("1", "true", "yes")


def from_dynamo(value: Any) -> Any:
    """Convierte recursivamente ``Decimal`` de DynamoDB a int o float."""
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value


def to_dynamo(value: Any) -> Any:
    """Convierte recursivamente float a ``Decimal`` (DynamoDB rechaza float)."""
    if isinstance(value, float):
        return decimal.Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    return value


class MetaclaseSingleton(type):
    """Metaclase que garantiza una única instancia por clase (thread-safe)."""

    _instances: ClassVar[dict[type, Any]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Devuelve la instancia única, creándola con doble chequeo."""
        if cls not in MetaclaseSingleton._instances:
            with MetaclaseSingleton._lock:
                if cls not in MetaclaseSingleton._instances:
                    MetaclaseSingleton._instances[cls] = super().__call__(
                        *args, **kwargs
                    )
        return MetaclaseSingleton._instances[cls]

    @classmethod
    def reset(mcs, target: type | None = None) -> None:
        """Descarta la instancia de ``target`` (o todas); útil en tests."""
        with mcs._lock:
            if target is None:
                mcs._instances.clear()
            else:
                mcs._instances.pop(target, None)


def _dynamo_table(name: str) -> Any:
    """Abre una tabla DynamoDB (boto3 se importa solo si hace falta)."""
    import boto3

    resource: Any = boto3.resource("dynamodb")
    return resource.Table(name)


class IteradorDatosCorporativos:
    """Patrón Iterator: recorre los registros de CorporateData de a uno.

    Oculta si los datos están en un dict en memoria o en una tabla DynamoDB
    paginada (``LastEvaluatedKey``).
    """

    def __init__(self, source: Any) -> None:
        """Crea el iterador sobre un dict o una tabla DynamoDB."""
        self._source = source
        self._page: list[Registro] = []
        self._last_key: Any = None
        self._started = False

    def __iter__(self) -> "IteradorDatosCorporativos":
        """Devuelve el propio iterador."""
        return self

    def __next__(self) -> Registro:
        """Devuelve el siguiente registro o lanza ``StopIteration``."""
        if isinstance(self._source, dict):
            if not self._started:
                self._page = list(self._source.values())
                self._started = True
        elif not self._page:
            if self._started and self._last_key is None:
                raise StopIteration
            kwargs = {"ExclusiveStartKey": self._last_key} if self._last_key else {}
            response = self._source.scan(**kwargs)
            self._page = [from_dynamo(i) for i in response.get("Items", [])]
            self._last_key = response.get("LastEvaluatedKey")
            self._started = True
        if not self._page:
            raise StopIteration
        return self._page.pop(0)


class TablaDatosCorporativos(metaclass=MetaclaseSingleton):
    """Singleton de acceso físico a la tabla CorporateData."""

    def __init__(self) -> None:
        """Abre la tabla (DynamoDB o memoria según el entorno)."""
        self._lock = threading.Lock()
        self._memory: dict[str, Registro] | None = {} if use_memory() else None
        self._table: Any = None if use_memory() else _dynamo_table("CorporateData")

    def get_item(self, record_id: str) -> Registro | None:
        """Lee un registro por clave; ``None`` si no existe."""
        if self._memory is not None:
            with self._lock:
                item = self._memory.get(record_id)
                return dict(item) if item else None
        response = self._table.get_item(Key={"id": record_id})
        item = response.get("Item")
        return from_dynamo(item) if item else None

    def put_item(self, item: Registro) -> None:
        """Crea o reemplaza un registro completo."""
        if self._memory is not None:
            with self._lock:
                self._memory[str(item["id"])] = dict(item)
            return
        self._table.put_item(Item=to_dynamo(item))

    def scan(self) -> Iterator[Registro]:
        """Recorre todos los registros mediante ``CorporateDataIterator``."""
        if self._memory is not None:
            with self._lock:
                snapshot = {k: dict(v) for k, v in self._memory.items()}
            return IteradorDatosCorporativos(snapshot)
        return IteradorDatosCorporativos(self._table)


class TablaRegistroCorporativo(metaclass=MetaclaseSingleton):
    """Singleton de acceso físico a la tabla CorporateLog."""

    def __init__(self) -> None:
        """Abre la tabla (DynamoDB o memoria según el entorno)."""
        self._lock = threading.Lock()
        self._memory: list[Registro] | None = [] if use_memory() else None
        self._table: Any = None if use_memory() else _dynamo_table("CorporateLog")

    def put_item(self, entry: Registro) -> None:
        """Inserta un registro de auditoría."""
        if self._memory is not None:
            with self._lock:
                self._memory.append(dict(entry))
            return
        self._table.put_item(Item=to_dynamo(entry))

    def entries(self) -> list[Registro]:
        """Devuelve todos los registros de auditoría."""
        if self._memory is not None:
            with self._lock:
                return [dict(e) for e in self._memory]
        items: list[Registro] = []
        kwargs: dict[str, Any] = {}
        while True:
            response = self._table.scan(**kwargs)
            items.extend(from_dynamo(i) for i in response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            kwargs = {"ExclusiveStartKey": response["LastEvaluatedKey"]}
