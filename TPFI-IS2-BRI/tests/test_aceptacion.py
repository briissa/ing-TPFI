"""Pruebas de aceptación y de los patrones exigidos por el enunciado."""

import decimal
import json
import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from tpfi import jsonio, storage
from tpfi.common import CAMPOS_CORPORATIVOS, actualizaciones_corporativas
from tpfi.observer import Observador, SujetoObservable
from tpfi.observer_client import ClienteObservador
from tpfi.observer_client import main as observer_main
from tpfi.server import ErrorInicioServidor, ServidorTPFI
from tpfi.server import main as server_main
from tpfi.service import (
    ContextoSolicitud,
    ProxyCorporativo,
    RegistroAuditoria,
    ServicioCorporativoReal,
)
from tpfi.singleton_client import ClienteSingleton, main_get, main_list, main_set
from tpfi.singleton_client import main as client_main
from tpfi.storage import (
    TablaDatosCorporativos,
    TablaRegistroCorporativo,
)


@pytest.fixture
def servidor() -> Iterator[ServidorTPFI]:
    """Inicia un servidor real en loopback conectado a tablas AWS de prueba."""
    instancia = ServidorTPFI(host="127.0.0.1", port=0)
    hilo = threading.Thread(target=instancia.servir_permanentemente, daemon=True)
    hilo.start()
    assert instancia.ready.wait(5)
    yield instancia
    instancia.cerrar_servidor()
    hilo.join(timeout=2)


def _enviar_solicitud_sin_validar(servidor: ServidorTPFI, solicitud: object) -> Any:
    """Envía un JSON sin validaciones del cliente para probar el servidor."""
    with socket.create_connection(("127.0.0.1", servidor.port), timeout=2) as conexion:
        conexion.sendall(jsonio.codificar_json(solicitud))
        respuesta_bytes = b""
        while chunk := conexion.recv(4096):
            respuesta_bytes += chunk
    return json.loads(respuesta_bytes.decode("utf-8"))


def test_aceptacion_acciones_y_auditoria(servidor: ServidorTPFI) -> None:
    """Verifica persistencia parcial, respuestas y auditoría de las acciones."""
    cliente = ClienteSingleton("127.0.0.1", servidor.port)
    primero = cliente.enviar_solicitud(
        cliente.construir_solicitud(
            {"UUID": "cpu-test", "ACTION": "set", "ID": "A", "cp": "3260"}
        )
    )
    actualizado = cliente.enviar_solicitud(
        cliente.construir_solicitud(
            {"UUID": "cpu-test", "ACTION": "set", "ID": "A", "sede": "FCyT"}
        )
    )
    assert primero["web"] == ""
    assert actualizado["cp"] == "3260"
    assert actualizado["sede"] == "FCyT"
    assert (
        cliente.enviar_solicitud(
            cliente.construir_solicitud(
                {"UUID": "cpu-test", "ACTION": "get", "ID": "A"}
            )
        )
        == actualizado
    )
    assert cliente.enviar_solicitud(
        cliente.construir_solicitud({"UUID": "cpu-test", "ACTION": "list"})
    ) == [actualizado]
    assert _enviar_solicitud_sin_validar(
        servidor, {"UUID": "cpu-test", "ACTION": "get", "ID": "missing"}
    ) == {"Error": "Not found: missing"}

    entries = TablaRegistroCorporativo().entries()
    assert sorted(entrada["accion"] for entrada in entries) == sorted(
        ["set", "set", "get", "list", "get"]
    )
    assert all(entrada["CPUid"] == "cpu-test" for entrada in entries)
    assert all(entrada["sessionid"] and entrada["timestamp"] for entrada in entries)
    assert sorted(
        entrada["idsolicitado"] for entrada in entries if entrada["accion"] == "set"
    ) == ["A", "A"]
    assert sorted(
        entrada["idsolicitado"] for entrada in entries if entrada["accion"] == "get"
    ) == ["A", "missing"]
    assert all(
        "idsolicitado" not in entrada
        for entrada in entries
        if entrada["accion"] == "list"
    )


def test_aceptacion_rechaza_solicitudes_invalidas(
    servidor: ServidorTPFI,
) -> None:
    """El servidor informa errores y no audita pedidos rechazados."""
    assert _enviar_solicitud_sin_validar(servidor, {"ACTION": "list"}) == {
        "Error": "UUID is required"
    }
    assert _enviar_solicitud_sin_validar(
        servidor, {"UUID": "cpu", "ACTION": "unknown"}
    ) == {"Error": "Unknown ACTION: unknown"}
    assert _enviar_solicitud_sin_validar(
        servidor, {"UUID": "cpu", "ACTION": "get"}
    ) == {"Error": "get requires ID"}
    assert _enviar_solicitud_sin_validar(
        servidor, {"UUID": "cpu", "ACTION": "set", "ID": "A"}
    ) == {"Error": "set requires at least one CorporateData field"}
    assert _enviar_solicitud_sin_validar(servidor, ["not", "an", "object"]) == {
        "Error": "Request must be a JSON object"
    }
    assert TablaRegistroCorporativo().entries() == []


def test_aceptacion_rechaza_servidor_duplicado(servidor: ServidorTPFI) -> None:
    """Comprueba que no se puede levantar otro servidor en el puerto ocupado."""
    second = ServidorTPFI(host="127.0.0.1", port=servidor.port)
    with pytest.raises(ErrorInicioServidor):
        second.servir_permanentemente()


class ObservadorDePrueba(Observador):
    """Observador de prueba que guarda mensajes recibidos."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def update(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


class ObservadorDesconectado(Observador):
    """Observador que simula una conexión ya interrumpida."""

    def update(self, message: dict[str, Any]) -> None:
        del message
        raise OSError("disconnected")


def test_sujeto_notifica_y_descarta_suscriptores_caidos() -> None:
    """Comprueba attach, notify y detach automático del patrón Observer."""
    sujeto = SujetoObservable()
    observador = ObservadorDePrueba()
    sujeto.attach(observador)
    sujeto.attach(ObservadorDesconectado())
    assert sujeto.count == 2
    sujeto.notificar({"ACTION": "change"})
    assert observador.messages == [{"ACTION": "change"}]
    assert sujeto.count == 1
    sujeto.detach(observador)
    sujeto.detach(observador)
    assert sujeto.count == 0


def test_aceptacion_suscripcion_recibe_notificaciones(
    servidor: ServidorTPFI, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """El cliente observer permanece conectado y muestra los cambios recibidos."""
    salida = tmp_path / "notifications.json"
    observador = ClienteObservador("127.0.0.1", servidor.port, str(salida))
    assert observador.connect()
    assert observador.subscribe()
    hilo_oyente = threading.Thread(target=observador.listen, daemon=True)
    hilo_oyente.start()
    for _ in range(100):
        if servidor.sujeto.count == 1:
            break
        time.sleep(0.01)
    assert servidor.sujeto.count == 1

    cliente = ClienteSingleton("127.0.0.1", servidor.port)
    cliente.enviar_solicitud(
        cliente.construir_solicitud({"ACTION": "set", "ID": "B", "sede": "FCyT"})
    )
    for _ in range(100):
        if salida.exists():
            break
        time.sleep(0.01)
    observador.disconnect()
    hilo_oyente.join(timeout=2)

    notificacion = json.loads(salida.read_text(encoding="utf-8").strip())
    assert notificacion["ACTION"] == "change"
    assert notificacion["Data"]["id"] == "B"
    assert "change" in capsys.readouterr().out
    assert sorted(
        entrada["accion"] for entrada in TablaRegistroCorporativo().entries()
    ) == ["set", "subscribe"]


def test_proxy_delega_y_audita_operaciones() -> None:
    """El Proxy registra acceso y delega get, set y list en el servicio real."""
    contexto = ContextoSolicitud(uuid="cpu", session_id="session")
    intermediario = ProxyCorporativo(ServicioCorporativoReal(), RegistroAuditoria())
    creado = intermediario.set(contexto, "A", {"localidad": "UADER"})
    assert creado["localidad"] == "UADER"
    assert intermediario.get(contexto, "A") == creado
    assert intermediario.list(contexto) == [creado]
    entries = TablaRegistroCorporativo().entries()
    assert sorted(entrada["accion"] for entrada in entries) == ["get", "list", "set"]
    assert all(
        entrada["idsolicitado"] == "A"
        for entrada in entries
        if entrada["accion"] in {"get", "set"}
    )
    assert all(
        "idsolicitado" not in entrada
        for entrada in entries
        if entrada["accion"] == "list"
    )
    with pytest.raises(ValueError, match="requires ID"):
        intermediario.get(contexto, "")
    with pytest.raises(ValueError, match="requires ID"):
        intermediario.set(contexto, "", {"cp": "3260"})
    with pytest.raises(ValueError, match="at least one"):
        intermediario.set(contexto, "A", {})
    assert len(TablaRegistroCorporativo().entries()) == 3


def test_almacenamiento_singletons_e_iteracion() -> None:
    """Verifica instancias únicas, DynamoDB y utilidades."""
    assert TablaDatosCorporativos() is TablaDatosCorporativos()
    assert TablaRegistroCorporativo() is TablaRegistroCorporativo()
    assert TablaDatosCorporativos() is not TablaRegistroCorporativo()
    table = TablaDatosCorporativos()
    assert list(table.scan()) == []
    table.put_item({"id": "A", "value": 1})
    assert table.get_item("A") == {"id": "A", "value": 1}
    assert table.get_item("missing") is None
    assert list(table.scan()) == [{"id": "A", "value": 1}]
    assert storage.from_dynamo(
        {"whole": decimal.Decimal("3"), "fraction": decimal.Decimal("1.5")}
    ) == {"whole": 3, "fraction": 1.5}
    assert storage.from_dynamo([decimal.Decimal("2")]) == [2]
    assert storage.to_dynamo({"ratio": 1.25}) == {"ratio": decimal.Decimal("1.25")}
    assert actualizaciones_corporativas({"cp": "3260", "ignored": "x"}) == {
        "cp": "3260"
    }
    assert CAMPOS_CORPORATIVOS


def test_almacenamiento_dynamodb_y_paginacion() -> None:
    """Prueba escritura, lectura y paginación contra tablas reales de prueba."""
    data_table = TablaDatosCorporativos()
    for record_id in ["A", "B", "C"]:
        data_table.put_item({"id": record_id, "fraction": 1.5})
    assert data_table.get_item("A") == {"id": "A", "fraction": 1.5}
    assert sorted(item["id"] for item in data_table.scan(page_size=1)) == [
        "A",
        "B",
        "C",
    ]

    log_table = TablaRegistroCorporativo()
    for record_id in ["1", "2", "3"]:
        log_table.put_item({"id": record_id})
    assert sorted(entry["id"] for entry in log_table.entries(page_size=1)) == [
        "1",
        "2",
        "3",
    ]


def test_protocolo_json_lineas_vacias_y_decimales() -> None:
    """Valida encoding, lectura con y sin salto y los errores de protocolo."""

    class Reader:
        def __init__(self, chunks: list[bytes]) -> None:
            self.chunks = iter(chunks)

        def recv(self, size: int) -> bytes:
            del size
            return next(self.chunks, b"")

    assert jsonio.codificar_json({"value": decimal.Decimal("4")}) == b'{"value": 4}\n'
    assert (
        jsonio.codificar_json({"value": decimal.Decimal("1.5")}) == b'{"value": 1.5}\n'
    )
    with pytest.raises(TypeError, match="Not JSON serializable"):
        jsonio.codificar_json(object())
    assert jsonio.leer_mensaje_json(Reader([b'{"ACTION":', b'"list"}\nextra'])) == {
        "ACTION": "list"
    }
    assert jsonio.leer_mensaje_json(Reader([b"\n", b'{"ACTION":"get"}'])) == {
        "ACTION": "get"
    }
    with pytest.raises(ValueError, match="Empty request"):
        jsonio.leer_mensaje_json(Reader([b""]))
    with pytest.raises(json.JSONDecodeError):
        jsonio.leer_mensaje_json(Reader([b"{invalid}"]))


def test_cliente_singleton_validacion_conexion_y_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Prueba validaciones, caída del servidor y salida del cliente CLI."""
    with pytest.raises(ValueError, match="JSON object"):
        ClienteSingleton.construir_solicitud([])
    with pytest.raises(ValueError, match="ACTION"):
        ClienteSingleton.construir_solicitud({"ACTION": "delete"})
    with pytest.raises(ValueError, match="requires an ID"):
        ClienteSingleton.construir_solicitud({"ACTION": "get"})
    with pytest.raises(ValueError, match="at least one"):
        ClienteSingleton.construir_solicitud({"ACTION": "set", "ID": "A"})
    solicitud = ClienteSingleton.construir_solicitud(
        {"ACTION": "list", "ID": "ignored", "unknown": "value"}
    )
    assert "ID" not in solicitud
    assert solicitud["UUID"]

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        unused_port = sock.getsockname()[1]
    with pytest.raises(ConnectionError, match="Could not connect"):
        ClienteSingleton("127.0.0.1", unused_port).enviar_solicitud({"ACTION": "list"})

    ruta_entrada = tmp_path / "input.json"
    ruta_salida = tmp_path / "output.json"
    ruta_entrada.write_text('{"ACTION":"list"}', encoding="utf-8")
    monkeypatch.setattr(
        ClienteSingleton, "enviar_solicitud", lambda self, solicitud: [solicitud]
    )
    assert client_main(["-i", str(ruta_entrada)]) == 0
    assert json.loads(capsys.readouterr().out)[0]["ACTION"] == "list"
    assert client_main(["-i", str(ruta_entrada), "-o", str(ruta_salida)]) == 0
    assert json.loads(ruta_salida.read_text(encoding="utf-8"))[0]["ACTION"] == "list"
    ruta_entrada.write_text("{", encoding="utf-8")
    assert client_main(["-i", str(ruta_entrada)]) == 1
    with pytest.raises(SystemExit):
        client_main([])
    with pytest.raises(SystemExit):
        client_main(["-i", str(ruta_entrada), "-p", "invalid"])


def test_comandos_singleton_set_get_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Los comandos instalados construyen pedidos sin archivos JSON."""
    solicitudes: list[dict[str, Any]] = []

    def enviar(
        self: ClienteSingleton, request: dict[str, Any]
    ) -> dict[str, Any] | list[dict[str, Any]]:
        del self
        solicitudes.append(request)
        if request["ACTION"] == "list":
            return [{"id": "A"}]
        return {"id": request["ID"], "cp": request.get("cp", "3260")}

    monkeypatch.setattr(ClienteSingleton, "enviar_solicitud", enviar)

    assert main_set(["--id", "A", "--cp", "3260", "--sede", "FCyT"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "A"
    assert main_get(["--id", "A"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "A"
    assert main_list([]) == 0
    assert json.loads(capsys.readouterr().out) == [{"id": "A"}]
    assert [request["ACTION"] for request in solicitudes] == ["set", "get", "list"]
    assert solicitudes[0]["sede"] == "FCyT"
    assert solicitudes[0]["UUID"]

    assert main_set(["--id", "A"]) == 1
    captured = capsys.readouterr()
    assert "at least one CorporateData field" in captured.out


def test_cliente_observador_reintenta_notifica_y_desconecta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Prueba conexión caída, suscripción, notificación y reconexión controlada."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        unused_port = sock.getsockname()[1]
    cliente = ClienteObservador("127.0.0.1", unused_port, retry_interval=0)
    assert not cliente.connect()
    assert not cliente.subscribe()

    ruta_salida = tmp_path / "observer.jsonl"
    cliente.output_file = str(ruta_salida)
    cliente.notificar({"ACTION": "change"})
    assert ruta_salida.read_text(encoding="utf-8").strip() == '{"ACTION": "change"}'
    assert "change" in capsys.readouterr().out

    receiver, sender = socket.socketpair()
    cliente.sock = receiver
    sender.sendall(b'{"ACTION":"change"}\n{bad}\n')
    sender.close()
    assert not cliente.listen()
    cliente.disconnect()
    cliente.disconnect()

    cliente_reintentando = ClienteObservador("localhost", 1, retry_interval=0)
    intentos: list[str] = []

    def conectar_simulado() -> bool:
        intentos.append("connect")
        return True

    def suscribir_simulado() -> bool:
        intentos.append("subscribe")
        return False

    monkeypatch.setattr(cliente_reintentando, "connect", conectar_simulado)
    monkeypatch.setattr(cliente_reintentando, "subscribe", suscribir_simulado)

    def detener_despues_reintento(timeout: float) -> bool:
        assert timeout == 0
        intentos.append("wait")
        cliente_reintentando.stop()
        return True

    monkeypatch.setattr(cliente_reintentando._stop, "wait", detener_despues_reintento)
    cliente_reintentando.run()
    assert intentos == ["connect", "subscribe", "wait"]
    cliente_reintentando.stop()

    with pytest.raises(SystemExit):
        observer_main(["--port", "invalid"])


def test_servidor_argumentos_y_cierre(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cubre argumentos del servidor, cierre normal y errores de inicio."""
    with pytest.raises(SystemExit):
        server_main(["--port", "invalid"])

    class SuccessfulServer:
        def __init__(self, port: int) -> None:
            assert port == 8123
            self.stopped = False

        def servir_permanentemente(self) -> None:
            return

        def cerrar_servidor(self) -> None:
            self.stopped = True

    monkeypatch.setattr("tpfi.server.ServidorTPFI", SuccessfulServer)
    assert server_main(["-p", "8123"]) == 0

    class FailingServer(SuccessfulServer):
        def servir_permanentemente(self) -> None:
            raise ErrorInicioServidor("port busy")

    monkeypatch.setattr("tpfi.server.ServidorTPFI", FailingServer)
    assert server_main(["-p", "8123"]) == 1

    class InterruptedServer(SuccessfulServer):
        def servir_permanentemente(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr("tpfi.server.ServidorTPFI", InterruptedServer)
    assert server_main(["-p", "8123"]) == 0


def test_registro_y_auditoria_con_id_opcional() -> None:
    """Comprueba generación de sesión y registro opcional del ID solicitado."""
    from tpfi.common import configurar_registro, uuid_cpu

    assert uuid_cpu()
    configurar_registro(False)
    contexto = ContextoSolicitud(uuid="cpu", session_id="session")
    RegistroAuditoria().registrar(contexto, "list")
    RegistroAuditoria().registrar(contexto, "get", "A")
    entries = TablaRegistroCorporativo().entries()
    assert len(entries) == 2
    assert any("idsolicitado" not in entry for entry in entries)
    assert any(entry.get("idsolicitado") == "A" for entry in entries)
