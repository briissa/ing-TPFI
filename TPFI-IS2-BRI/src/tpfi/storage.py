"""Acceso físico a las tablas CorporateData y CorporateLog (patrón Singleton).

Cada tabla tiene su propio Singleton y se conecta a DynamoDB. Los nombres se
pueden configurar con ``TPFI_DATA_TABLE`` y ``TPFI_LOG_TABLE``.
"""

import decimal
import os
import threading
from collections.abc import Iterator
from typing import Any, ClassVar

Registro = dict[str, Any]


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

    env_name = {
        "CorporateData": "TPFI_DATA_TABLE",
        "CorporateLog": "TPFI_LOG_TABLE",
    }[name]
    resource: Any = boto3.resource("dynamodb")
    return resource.Table(os.environ.get(env_name, name))


class IteradorDatosCorporativos:
    """Patrón Iterator: recorre CorporateData página por página."""

    def __init__(self, source: Any, page_size: int | None = None) -> None:
        """Crea el iterador sobre una tabla DynamoDB."""
        self._source = source
        self._page_size = page_size
        self._page: list[Registro] = []
        self._last_key: Any = None
        self._started = False

    def __iter__(self) -> "IteradorDatosCorporativos":
        """Devuelve el propio iterador."""
        return self

    def __next__(self) -> Registro:
        """Devuelve el siguiente registro o lanza ``StopIteration``."""
        if not self._page:
            if self._started and self._last_key is None:
                raise StopIteration
            kwargs: dict[str, Any] = (
                {"ExclusiveStartKey": self._last_key} if self._last_key else {}
            )
            if self._page_size is not None:
                kwargs["Limit"] = self._page_size
            kwargs["ConsistentRead"] = True
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
        """Abre la tabla DynamoDB CorporateData."""
        self._table: Any = _dynamo_table("CorporateData")

    def get_item(self, record_id: str) -> Registro | None:
        """Lee un registro por clave; ``None`` si no existe."""
        response = self._table.get_item(Key={"id": record_id}, ConsistentRead=True)
        item = response.get("Item")
        return from_dynamo(item) if item else None

    def put_item(self, item: Registro) -> None:
        """Crea o reemplaza un registro completo."""
        self._table.put_item(Item=to_dynamo(item))

    def scan(self, page_size: int | None = None) -> Iterator[Registro]:
        """Recorre todos los registros mediante ``CorporateDataIterator``."""
        return IteradorDatosCorporativos(self._table, page_size)


class TablaRegistroCorporativo(metaclass=MetaclaseSingleton):
    """Singleton de acceso físico a la tabla CorporateLog."""

    def __init__(self) -> None:
        """Abre la tabla DynamoDB CorporateLog."""
        self._table: Any = _dynamo_table("CorporateLog")

    def put_item(self, entry: Registro) -> None:
        """Inserta un registro de auditoría."""
        self._table.put_item(Item=to_dynamo(entry))

    def entries(self, page_size: int | None = None) -> list[Registro]:
        """Devuelve todos los registros de auditoría."""
        items: list[Registro] = []
        kwargs: dict[str, Any] = {"ConsistentRead": True}
        if page_size is not None:
            kwargs["Limit"] = page_size
        while True:
            response = self._table.scan(**kwargs)
            items.extend(from_dynamo(i) for i in response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            kwargs = {
                "ExclusiveStartKey": response["LastEvaluatedKey"],
                "ConsistentRead": True,
            }
            if page_size is not None:
                kwargs["Limit"] = page_size
