"""Prueba de humo extremo a extremo contra DynamoDB."""

import json
import threading
from collections.abc import Iterator

import pytest

from tpfi.observer_client import ClienteObservador
from tpfi.server import ServidorTPFI
from tpfi.singleton_client import ClienteSingleton
from tpfi.storage import (
    TablaDatosCorporativos,
    TablaRegistroCorporativo,
)


@pytest.fixture
def servidor() -> Iterator[ServidorTPFI]:
    srv = ServidorTPFI(host="127.0.0.1", port=0)
    threading.Thread(target=srv.servir_permanentemente, daemon=True).start()
    assert srv.ready.wait(5)
    yield srv
    srv.cerrar_servidor()


def test_establecer_obtener_listar_y_auditar(servidor: ServidorTPFI) -> None:
    cliente = ClienteSingleton("127.0.0.1", servidor.port)
    registro = cliente.enviar_solicitud(
        cliente.construir_solicitud({"ACTION": "set", "ID": "A", "cp": "3260"})
    )
    assert registro["id"] == "A" and registro["cp"] == "3260" and registro["web"] == ""
    obtenido = cliente.enviar_solicitud(
        cliente.construir_solicitud({"ACTION": "get", "ID": "A"})
    )
    assert obtenido == registro
    assert cliente.enviar_solicitud(
        cliente.construir_solicitud({"ACTION": "list"})
    ) == [registro]
    acciones = [e["accion"] for e in TablaRegistroCorporativo().entries()]
    assert sorted(acciones) == ["get", "list", "set"]
    assert TablaDatosCorporativos() is TablaDatosCorporativos()


def test_observador_recibe_cambios(
    servidor: ServidorTPFI, capsys: pytest.CaptureFixture[str]
) -> None:
    observador = ClienteObservador("127.0.0.1", servidor.port)
    assert observador.connect() and observador.subscribe()
    hilo = threading.Thread(target=observador.listen, daemon=True)
    hilo.start()
    for _ in range(100):
        if servidor.sujeto.count:
            break
        threading.Event().wait(0.05)
    cliente = ClienteSingleton("127.0.0.1", servidor.port)
    cliente.enviar_solicitud(
        cliente.construir_solicitud({"ACTION": "set", "ID": "B", "sede": "FCyT"})
    )
    for _ in range(100):
        if "change" in capsys.readouterr().out:
            break
        threading.Event().wait(0.05)
    else:
        pytest.fail("no llegó la notificación")
    observador.disconnect()
    assert json.dumps({}) == "{}"
