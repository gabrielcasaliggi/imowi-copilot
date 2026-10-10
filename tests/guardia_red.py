"""Guardia de red para pytest: ninguna conexión a hosts no locales.

Se instala desde tests/conftest.py antes de importar app.*. Cubre sockets de Python
(httpx, requests, urllib, smtplib…) y psycopg, que conecta por libpq sin pasar por
``socket``. Permitidos: loopback, ``localhost``, ``testserver`` (TestClient) y sockets unix.

Una conexión bloqueada levanta ``ConexionBloqueadaEnTests`` (subclase de
ConnectionRefusedError, así el código bajo prueba la trata como cualquier caída de red)
y queda anotada con el test que la abrió. Nunca se registra el host ni credenciales.
"""

from __future__ import annotations

import ipaddress
import os
import socket

HOSTS_PERMITIDOS = frozenset({"localhost", "testserver"})

# nodeid del test → cantidad de conexiones bloqueadas
BLOQUEADAS: dict[str, int] = {}


class ConexionBloqueadaEnTests(ConnectionRefusedError):
    pass


def es_host_local(host: str) -> bool:
    h = (host or "").strip().strip("[]").lower()
    if not h or h in HOSTS_PERMITIDOS or h.startswith("/"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _bloquear(host: str) -> None:
    if es_host_local(host):
        return
    test = os.environ.get("PYTEST_CURRENT_TEST", "<fuera de un test>").split(" ")[0]
    BLOQUEADAS[test] = BLOQUEADAS.get(test, 0) + 1
    raise ConexionBloqueadaEnTests(f"conexión a un host no local bloqueada en tests ({test})")


def _host_de(address) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return "/unix"


def _instalar_socket() -> None:
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def _connect(self, address):
        _bloquear(_host_de(address))
        return connect(self, address)

    def _connect_ex(self, address):
        _bloquear(_host_de(address))
        return connect_ex(self, address)

    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex


def _instalar_psycopg() -> None:
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
    except ImportError:
        return
    original = psycopg.Connection.connect.__func__

    def _connect(cls, conninfo: str = "", **kwargs):
        try:
            params = conninfo_to_dict(make_conninfo(conninfo, **kwargs))
            hosts = str(params.get("host") or params.get("hostaddr") or "").split(",")
        except Exception:
            hosts = ["<no interpretable>"]
        for host in hosts:
            _bloquear(host)
        return original(cls, conninfo, **kwargs)

    psycopg.Connection.connect = classmethod(_connect)
    psycopg.connect = psycopg.Connection.connect


_instalada = False


def instalar() -> None:
    global _instalada
    if _instalada:
        return
    _instalar_socket()
    _instalar_psycopg()
    _instalada = True
