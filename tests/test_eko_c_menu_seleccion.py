"""EKO C — el menú de selección distingue servicios iguales mostrando la línea.

La selección por número no cambia: se resuelve por posición/ID del catálogo.
"""

from __future__ import annotations

from app.services.eko_action_runtime import format_service_list_message
from app.services.eko_service_selection import (
    ServiceRef,
    _normalize_options,
    format_selection_options,
    option_from_row,
    resolve_service_selection,
)
from tests.test_eko_a_intencion_menu import chat  # noqa: F401  (fixture e2e)

CN = "18099"
ROWS = [
    {"id": "m1", "login": "2235550001", "type": "movil", "label": "Imowi 5 GB", "product": "Imowi 5 GB", "active": True, "line_msisdn": "2235550001"},
    {"id": "m2", "login": "2235550002", "type": "movil", "label": "Imowi 3 GB", "product": "Imowi 3 GB", "active": True, "line_msisdn": "2235550002"},
    {"id": "m3", "login": "2235550003", "type": "movil", "label": "Imowi 3 GB", "product": "Imowi 3 GB", "active": True, "line_msisdn": "2235550003"},
    {"id": "m4", "login": "2235550004", "type": "movil", "label": "Imowi 1.5 GB", "product": "Imowi 1.5 GB", "active": True, "line_msisdn": "2235550004"},
]


def _menu(rows=ROWS) -> str:
    return format_selection_options([option_from_row(r) for r in rows])


def test_dos_filas_iguales_se_distinguen_por_la_linea():
    menu = _menu()
    assert "2) Móvil: Imowi 3 GB · línea 2235550002" in menu
    assert "3) Móvil: Imowi 3 GB · línea 2235550003" in menu
    assert menu.splitlines()[0].startswith("¿Cuál servicio querés usar?")


def test_ya_no_sale_el_prefijo_crudo_movil():
    menu = _menu()
    assert "movil:" not in menu
    assert " movil" not in menu.lower().replace("móvil", "")


def test_misma_etiqueta_que_el_listado_de_servicios():
    listado = format_service_list_message(ROWS)
    for fila in ("Móvil: Imowi 3 GB · línea 2235550002", "Móvil: Imowi 5 GB · línea 2235550001"):
        assert fila in listado and fila in _menu()


def test_sin_linea_ni_tipo_no_inventa_datos():
    menu = format_selection_options(
        [
            {"service_id": "i1", "type": "internet", "label": "Fibra 100", "product": "Fibra 100"},
            {"service_id": "x1", "login": "INTX", "label": "INTX"},
        ]
    )
    assert "1) Internet: Fibra 100" in menu and "línea" not in menu
    assert "2) INTX" in menu


def test_las_opciones_normalizadas_conservan_la_linea():
    opts = _normalize_options([option_from_row(r) for r in ROWS])
    assert [o["line_msisdn"] for o in opts] == ["2235550001", "2235550002", "2235550003", "2235550004"]
    assert "línea 2235550003" in format_selection_options(opts)


def test_seleccion_por_numero_devuelve_el_servicio_correcto_en_cada_posicion():
    pool = [option_from_row(r) for r in ROWS]
    for pos, row in enumerate(ROWS, start=1):
        res = resolve_service_selection(
            texto=str(pos), catalog=ROWS, client_number=CN, pending_options=pool
        )
        assert res.status == "selected", (pos, res)
        assert res.ref.service_id == row["id"] and res.ref.login == row["login"]


def test_la_seleccion_no_usa_el_texto_de_la_linea():
    # Aun con el número de línea en el texto, manda el pool/ID del catálogo, no el menú.
    pool = [option_from_row(r) for r in ROWS]
    res = resolve_service_selection(
        texto="2", catalog=ROWS, client_number=CN, pending_options=pool
    )
    assert res.ref.service_id == "m2"


def test_service_ref_no_cambia_de_forma_ni_incorpora_la_linea():
    ref = ServiceRef(service_id="m2", login="2235550002", service_type="movil", client_number=CN)
    assert set(ref.to_dict()) == {
        "service_id", "login", "service_type", "client_number", "label", "product", "active",
    }
    res = resolve_service_selection(texto="2", catalog=ROWS, client_number=CN, pending_options=[option_from_row(r) for r in ROWS])
    assert "line_msisdn" not in res.ref.to_dict()


def test_e2e_whatsapp_el_menu_muestra_las_lineas(chat):  # noqa: F811
    say = chat
    say("hola")
    sent, _ctx, _t = say("tengo problemas con mi linea de imowi")
    assert len(sent) == 1
    assert "Móvil: Imowi 3 GB · línea 2235550002" in sent[0]
    assert "Móvil: Imowi 3 GB · línea 2235550003" in sent[0]
    assert "movil:" not in sent[0]
    sent2, ctx2, _t = say("3")
    assert "Listo: seleccioné" in sent2[0] and "2235550003" in sent2[0]
    assert ctx2["eko_journey"]["selected_service_ref"]["service_id"] == "m3"
