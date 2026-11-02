"""Fixtures de integración que aíslan las pruebas en tablas reales de AWS."""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest

from tpfi.storage import MetaclaseSingleton


def _clear_table(table: Any) -> None:
    """Elimina los elementos de una tabla de prueba, respetando la paginación."""
    kwargs: dict[str, Any] = {
        "ProjectionExpression": "#partition_key",
        "ExpressionAttributeNames": {"#partition_key": "id"},
    }
    while True:
        response = table.scan(**kwargs)
        with table.batch_writer() as batch:
            for item in response.get("Items", []):
                batch.delete_item(Key={"id": item["id"]})
        if "LastEvaluatedKey" not in response:
            return
        kwargs = {
            "ExclusiveStartKey": response["LastEvaluatedKey"],
            "ProjectionExpression": "#partition_key",
            "ExpressionAttributeNames": {"#partition_key": "id"},
        }


@pytest.fixture(scope="session")
def aws_tables() -> Iterator[dict[str, Any]]:
    """Crea y elimina tablas efímeras; requiere credenciales y permisos AWS."""
    resource = boto3.resource("dynamodb")
    suffix = uuid.uuid4().hex
    names = {
        "data": f"tpfi-test-{suffix}-data",
        "log": f"tpfi-test-{suffix}-log",
    }
    env_values = {
        "TPFI_DATA_TABLE": os.environ.get("TPFI_DATA_TABLE"),
        "TPFI_LOG_TABLE": os.environ.get("TPFI_LOG_TABLE"),
    }
    created: list[Any] = []
    try:
        for name in names.values():
            table = resource.create_table(
                TableName=name,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            created.append(table)
        for table in created:
            table.wait_until_exists()

        os.environ["TPFI_DATA_TABLE"] = names["data"]
        os.environ["TPFI_LOG_TABLE"] = names["log"]
        yield dict(zip(names, created, strict=True))
    finally:
        MetaclaseSingleton.reset()
        for key, value in env_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for table in created:
            table.delete()
            table.wait_until_not_exists()


@pytest.fixture(autouse=True)
def clear_aws_tables(aws_tables: dict[str, Any]) -> Iterator[None]:
    """Aísla cada prueba vaciando solo las tablas efímeras de esta ejecución."""
    MetaclaseSingleton.reset()
    for table in aws_tables.values():
        _clear_table(table)
    yield
    MetaclaseSingleton.reset()
