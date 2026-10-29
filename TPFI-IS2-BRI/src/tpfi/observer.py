"""Patrón Observer: gestión de suscripciones y notificaciones."""

import logging
import socket
import threading
from abc import ABC, abstractmethod
from typing import Any

from tpfi.jsonio import codificar_json


class Observador(ABC):
    """Interfaz de un observador suscripto a cambios de CorporateData."""

    @abstractmethod
    def update(self, message: dict[str, Any]) -> None:
        """Recibe una notificación; lanza ``OSError`` si ya no está disponible."""


class ObservadorSocket(Observador):
    """Observador remoto representado por el socket de un cliente suscripto."""

    def __init__(self, conn: socket.socket, client_uuid: str) -> None:
        """Asocia el socket abierto y el UUID del cliente."""
        self.conn = conn
        self.client_uuid = client_uuid
        self._send_lock = threading.Lock()

    def update(self, message: dict[str, Any]) -> None:
        """Envía el mensaje como una línea JSON al cliente."""
        with self._send_lock:
            self.conn.sendall(codificar_json(message))


class SujetoObservable:
    """Sujeto observable: mantiene los suscriptores y los notifica."""

    def __init__(self) -> None:
        """Crea el sujeto sin suscriptores."""
        self._lock = threading.Lock()
        self._observers: list[Observador] = []

    def attach(self, observer: Observador) -> None:
        """Suscribe un observador."""
        with self._lock:
            self._observers.append(observer)

    def detach(self, observer: Observador) -> None:
        """Da de baja un observador (si estaba suscripto)."""
        with self._lock:
            if observer in self._observers:
                self._observers.remove(observer)

    @property
    def count(self) -> int:
        """Cantidad de suscriptores actuales."""
        with self._lock:
            return len(self._observers)

    def notificar(self, message: dict[str, Any]) -> None:
        """Notifica a todos; los que fallan con ``OSError`` se dan de baja."""
        with self._lock:
            targets = list(self._observers)
        logging.debug("Notificando a %d observadores: %s", len(targets), message)
        for observer in targets:
            try:
                observer.update(message)
            except OSError as exc:
                logging.info("Observador descartado: %s", exc)
                self.detach(observer)
