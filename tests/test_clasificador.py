"""Tests del motor de clasificación demo N1/N2."""

from app.domain.taxonomia import AccionClasificacion, NivelTicket
from app.services.clasificador import clasificar_caso


def _base_triaje(**kwargs):
    base = {
        "cooperativa": "Coop Batán",
        "linea": "2235402690",
        "dispositivo": "Samsung A22",
        "geolocalizacion": "",
        "sintoma": "No tiene datos móviles",
        "completo": True,
    }
    base.update(kwargs)
    return base


def _base_diag(**kwargs):
    base = {
        "diagnostico": "Caso aislado",
        "anomalia_red": False,
        "categoria": "General",
        "ficha_jsc": None,
    }
    base.update(kwargs)
    return base


def test_pedir_datos_sin_linea():
    r = clasificar_caso(
        {"sintoma": "no anda", "completo": False},
        _base_diag(),
        {"encontrado": False, "modo": "escalamiento"},
        [],
    )
    assert r.accion == AccionClasificacion.PEDIR_DATOS
    assert "linea" in r.datos_faltantes


def test_anomalia_red_correlacionada_crea_n2():
    r = clasificar_caso(
        _base_triaje(),
        _base_diag(anomalia_red=True, anomalia_red_correlacionada=True, elemento_afectado="Core Güemes"),
        {"encontrado": False},
        [],
    )
    assert r.accion == AccionClasificacion.CREAR_TICKET_N2
    assert r.nivel == NivelTicket.N2
    assert r.regla_aplicada == "anomalia_red_correlacionada"


def test_anomalia_global_sin_correlacion_no_fuerza_n2():
    r = clasificar_caso(
        _base_triaje(sintoma="cliente consulta por un problema administrativo no resuelto", completo=True),
        _base_diag(
            anomalia_red=False,
            anomalia_red_global=True,
            anomalia_red_correlacionada=False,
        ),
        {"encontrado": False},
        [],
    )
    assert r.accion != AccionClasificacion.CREAR_TICKET_N2 or r.regla_aplicada != "anomalia_red_correlacionada"
    assert r.regla_aplicada in ("ticket_n1_demo", "triaje_completo_n2", "default_n1", "escalamiento_explicito")


def test_kb_resolucion_mantiene_n1():
    r = clasificar_caso(
        _base_triaje(sintoma="problema con apn de datos"),
        _base_diag(categoria="APN"),
        {"encontrado": True, "modo": "resolucion", "articulos": [{"contenido": "- Verificar APN"}]},
        [],
    )
    assert r.accion == AccionClasificacion.RESOLVER_N1
    assert r.nivel == NivelTicket.N1


def test_esim_completo_crea_n2_con_proveedor_sugerido():
    r = clasificar_caso(
        _base_triaje(sintoma="el esim no activa el perfil", completo=True),
        _base_diag(),
        {"encontrado": False},
        [],
        forzar_escalamiento=True,
    )
    assert r.accion == AccionClasificacion.CREAR_TICKET_N2
    assert r.nivel == NivelTicket.N2
    assert "SIM" in r.proveedor


def test_caso_general_completo_sin_kb_crea_n1():
    r = clasificar_caso(
        _base_triaje(sintoma="cliente consulta por un problema administrativo no resuelto", completo=True),
        _base_diag(),
        {"encontrado": False},
        [],
    )
    assert r.accion == AccionClasificacion.CREAR_TICKET_N1
    assert r.nivel == NivelTicket.N1
    assert r.regla_aplicada == "ticket_n1_demo"


def test_cuenta_suspendida_resuelve_n1():
    r = clasificar_caso(
        _base_triaje(),
        _base_diag(ficha_jsc={"estado_linea": "Suspendida", "estado_cuenta": "Deuda"}),
        {"encontrado": False},
        [],
    )
    assert r.accion == AccionClasificacion.RESOLVER_N1
    assert r.regla_aplicada == "cuenta_suspendida"
