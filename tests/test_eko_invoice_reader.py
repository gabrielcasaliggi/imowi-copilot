"""Eko 2.0 — Invoice header reader (FC only)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import ActionResult
from app.services.eko_invoice_reader import (
    InvoiceHeader,
    format_invoice_headers_message,
    read_invoices_fc,
)
from app.services.eko_journeys import maybe_handle_journey_turn


def _abo(**kwargs):
    d = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "Ana",
        "dni": "30111222",
        "deuda_monto": "2500",
        "client_number": "18099",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _conv(**kwargs):
    d = {
        "id": "conv-1",
        "ticket_id": "",
        "estado": "bot",
        "telefono": "2235551234",
        "canal": "whatsapp",
        "abonado_id": "abo-1",
    }
    d.update(kwargs)
    return SimpleNamespace(**d)


def _enable(monkeypatch, *actions: str):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", True)
    monkeypatch.setattr(
        bridge,
        "ACTION_RUNTIME_ACTIONS",
        frozenset(actions or ("show_balance", "show_invoice", "open_OV")),
    )


def _row(
    *,
    id: int = 1,
    number: str = "0013-00097239",
    full_type: str = "FC B",
    type: str = "FC",
    account_number: str = "18099",
    amount: Decimal | str = Decimal("22648.67"),
    date: datetime | None = None,
    state: str = "Registrado",
) -> dict:
    return {
        "id": id,
        "number": number,
        "full_type": full_type,
        "type": type,
        "account_number": account_number,
        "amount": amount,
        "date": date or datetime(2026, 9, 18, 12, 18, 9, tzinfo=UTC),
        "state": state,
    }


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeConn:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.last_params: dict | None = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt, params=None):
        self.last_params = dict(params or {})
        # Filter like SQL for multi-type fixtures passed in
        cn = str((params or {}).get("client_number") or "")
        lim = int((params or {}).get("limit") or 5)
        filtered = [
            r
            for r in self._rows
            if str(r.get("account_number")) == cn and str(r.get("type")) == "FC"
        ]
        filtered = sorted(
            filtered,
            key=lambda r: (r.get("date") or datetime.min.replace(tzinfo=UTC), r.get("id") or 0),
            reverse=True,
        )[:lim]
        return _FakeResult(filtered)


class _FakeEngine:
    def __init__(self, rows: list[dict]):
        self.conn = _FakeConn(rows)

    def connect(self):
        return self.conn

    def dispose(self):
        return None


def _patch_engine(rows: list[dict]):
    eng = _FakeEngine(rows)
    return patch(
        "app.services.billtrack._billtrack_engine",
        return_value=(eng, {"enabled": True}, False),
    )


# --- Reader unit tests ---


def test_t01_fc_invoice_fields():
    rows = [_row()]
    with _patch_engine(rows):
        result = read_invoices_fc(client_number="18099")
    assert result.status == "ok"
    assert len(result.invoices) == 1
    inv = result.invoices[0]
    assert inv.type == "FC"
    assert inv.amount == "22648.67"
    assert inv.issued_at == rows[0]["date"]
    assert inv.status == "Registrado"
    assert inv.invoice_number == "0013-00097239"
    assert inv.client_number == "18099"
    assert inv.account_number == "18099"


def test_t02_ic_excluded():
    rows = [
        _row(id=1, type="FC", number="FC-1"),
        _row(id=2, type="IC", number="IC-1", amount=Decimal("100")),
    ]
    with _patch_engine(rows):
        result = read_invoices_fc(client_number="18099")
    assert result.status == "ok"
    assert all(i.type == "FC" for i in result.invoices)
    assert all(i.invoice_number != "IC-1" for i in result.invoices)


def test_t03_nc_nd_excluded():
    rows = [
        _row(id=1, type="FC", number="FC-1"),
        _row(id=2, type="NC", number="NC-1"),
        _row(id=3, type="ND", number="ND-1"),
    ]
    with _patch_engine(rows):
        result = read_invoices_fc(client_number="18099")
    assert [i.type for i in result.invoices] == ["FC"]


def test_t04_amount_from_invoice_not_concepts():
    """amount debe ser api_invoice.amount aunque conceptos sumen distinto."""
    inv_amount = Decimal("22648.67")
    # Conceptos ficticios que no coinciden — el reader ni los consulta
    rows = [_row(amount=inv_amount)]
    with _patch_engine(rows):
        result = read_invoices_fc(client_number="18099")
    assert result.invoices[0].amount == "22648.67"
    assert Decimal(result.invoices[0].amount) != Decimal("18717.91")


def test_t05_ownership_isolation():
    rows = [
        _row(id=1, account_number="AAAA", number="1"),
        _row(id=2, account_number="BBBB", number="2"),
    ]
    with _patch_engine(rows):
        result = read_invoices_fc(client_number="AAAA")
    assert result.status == "ok"
    assert all(i.account_number == "AAAA" for i in result.invoices)
    assert all(i.invoice_number != "2" for i in result.invoices)


def test_t06_empty_no_error():
    with _patch_engine([]):
        result = read_invoices_fc(client_number="18099")
    assert result.status == "empty"
    assert result.invoices == []
    assert result.reason_code == "no_fc_invoices"


def test_t07_invalid_client_number():
    with _patch_engine([_row()]):
        result = read_invoices_fc(client_number="")
    assert result.status == "invalid_input"
    assert result.reason_code == "missing_client_number"


def test_t08_db_error_not_empty():
    def _boom(*a, **k):
        raise RuntimeError("db down")

    with patch(
        "app.services.billtrack._billtrack_engine",
        return_value=(MagicMock(connect=_boom, dispose=lambda: None), {}, False),
    ):
        # Fake engine whose connect raises
        class Boom:
            def connect(self):
                raise RuntimeError("db down")

            def dispose(self):
                return None

        with patch(
            "app.services.billtrack._billtrack_engine",
            return_value=(Boom(), {}, False),
        ):
            result = read_invoices_fc(client_number="18099")
    assert result.status == "error"
    assert result.reason_code == "billtrack_query_failed"
    assert result.status != "empty"


def test_t09_deterministic_ordering():
    same = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)
    rows = [
        _row(id=10, number="A", date=same),
        _row(id=20, number="B", date=same),
        _row(id=15, number="C", date=same),
    ]
    with _patch_engine(rows):
        result = read_invoices_fc(client_number="18099", limit=10)
    ids = [i.invoice_id for i in result.invoices]
    assert ids == [20, 15, 10]


def test_t10_no_currency_inference():
    with _patch_engine([_row()]):
        result = read_invoices_fc(client_number="18099")
    d = result.invoices[0].to_dict()
    assert "currency" in d
    assert d["currency"] is None
    # DTO no confirma currency aunque el renderer pueda formatear montos


def test_t11_no_due_date():
    with _patch_engine([_row()]):
        result = read_invoices_fc(client_number="18099")
    d = result.invoices[0].to_dict()
    assert d.get("due_date") is None
    assert not hasattr(result.invoices[0], "due_date") or result.invoices[0].to_dict()[
        "due_date"
    ] is None
    msg = format_invoice_headers_message(result.invoices).lower()
    assert "vence" not in msg


def test_t12_multi_account_needs_input_no_reader(monkeypatch):
    _enable(monkeypatch)
    ctx = {"phone_candidates": [{"dni": "1"}, {"dni": "2"}]}
    with patch("app.services.eko_journeys.dispatch_runtime") as disp:
        with patch("app.services.eko_invoice_reader.read_invoices_fc") as reader:
            t = maybe_handle_journey_turn(
                MagicMock(),
                "org",
                _conv(),
                None,
                "Quiero ver mi factura",
                canal="wa",
                ctx=ctx,
            )
    assert t and t.action_status == "needs_input"
    reader.assert_not_called()
    # may not call dispatch either for identity
    assert all(
        (not c.args) or c.args[0] != "show_invoice" for c in disp.call_args_list
    )


def test_journey_invoice_uses_reader(monkeypatch):
    _enable(monkeypatch)
    inv = InvoiceHeader(
        invoice_id=1,
        invoice_number="0013-1",
        full_type="FC B",
        type="FC",
        client_number="18099",
        account_number="18099",
        amount="100.00",
        issued_at=datetime(2026, 9, 1, tzinfo=UTC),
        status="Registrado",
    )

    def _disp(action, **kwargs):
        if action == "show_invoice":
            return ActionResult(
                action="show_invoice",
                status="success",
                user_message=format_invoice_headers_message([inv]),
                data={"invoices": [inv.to_dict()], "count": 1},
            )
        if action == "open_OV":
            return ActionResult(
                action="open_OV",
                status="success",
                user_message="https://ov.example/my",
                data={"url": "https://ov.example/my"},
            )
        return ActionResult(action=action, status="unavailable")

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(client_number="18099"),
            "Quiero ver mi factura",
            canal="wa",
            ctx={},
        )
    assert t and t.action == "show_invoice"
    assert t.action_status == "success"
    assert "0013-1" in (t.user_message or "")
    assert "100" in (t.user_message or "")
    assert "vence el" not in (t.user_message or "").lower()


def test_unavailable_engine():
    with patch(
        "app.services.billtrack._billtrack_engine",
        return_value=(None, {}, True),
    ):
        result = read_invoices_fc(client_number="18099")
    assert result.status == "unavailable"
    assert result.reason_code == "billtrack_unavailable"
