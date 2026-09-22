"""Eko 2.0 — Invoice E2E authority regression (CASI / XOR / ownership)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.services.eko_action_runtime import (
    ActionRequest,
    ActionResult,
    TrustedContext,
    _exec_show_invoice,
    bootstrap_registry,
    is_registered,
)
from app.services.eko_capability_contract import build_capability
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
    bootstrap_registry()


def _inv(
    *,
    invoice_id: int = 1,
    number: str = "0013-00097239",
    amount: str = "22648.67",
    status: str = "Registrado",
    client_number: str = "18099",
    issued_at: datetime | None = None,
) -> InvoiceHeader:
    return InvoiceHeader(
        invoice_id=invoice_id,
        invoice_number=number,
        full_type="FC B",
        type="FC",
        client_number=client_number,
        account_number=client_number,
        amount=amount,
        issued_at=issued_at or datetime(2026, 9, 18, 12, 18, 9, tzinfo=UTC),
        status=status,
    )


def _show_invoice_ar(inv: InvoiceHeader | None = None, *, empty: bool = False) -> ActionResult:
    if empty:
        return ActionResult(
            action="show_invoice",
            status="success",
            reason_code="no_fc_invoices",
            user_message="No encuentro facturas (FC) para tu cuenta en este momento.",
            data={"invoices": [], "count": 0},
            execution_path="runtime",
        )
    assert inv is not None
    return ActionResult(
        action="show_invoice",
        status="success",
        user_message=format_invoice_headers_message([inv]),
        data={"invoices": [inv.to_dict()], "count": 1},
        execution_path="runtime",
    )


def _ov_ar() -> ActionResult:
    return ActionResult(
        action="open_OV",
        status="success",
        user_message="https://ov.example/my",
        data={"url": "https://ov.example/my", "destination": "my"},
        execution_path="runtime",
    )


def _bal_ar() -> ActionResult:
    return ActionResult(
        action="show_balance",
        status="success",
        user_message="Saldo padrón $2500",
        data={"amount": "2500"},
        execution_path="runtime",
    )


# --- Registry / CASI inspection ---


def test_inspection_show_invoice_registered_and_authorized():
    bootstrap_registry()
    assert is_registered("show_invoice")
    cap = build_capability("show_invoice")
    assert cap is not None
    assert cap.domain == "billing"
    assert cap.type == "READ"
    assert cap.requires_authorization is True


# --- E2E ---


def test_e2e_01_single_account(monkeypatch):
    _enable(monkeypatch)
    inv = _inv()
    counts = {"show_invoice": 0, "legacy_read": 0, "reader": 0}

    def _disp(action, **kwargs):
        if action == "show_invoice":
            counts["show_invoice"] += 1
            counts["reader"] += 1  # Runtime executor → reader (una vez)
            return _show_invoice_ar(inv)
        if action == "open_OV":
            return _ov_ar()
        return ActionResult(action=action, status="unavailable")

    def _legacy_forbidden(**kwargs):
        counts["legacy_read"] += 1
        raise AssertionError("legacy read_invoices_fc must not run when runtime handles")

    with (
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp),
        patch(
            "app.services.eko_invoice_reader.read_invoices_fc",
            side_effect=_legacy_forbidden,
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Quiero ver mi factura",
            canal="wa",
            ctx={},
        )

    assert t is not None
    assert t.journey == "billing_self_service"
    assert t.data.get("billing_act") == "invoice"
    assert t.action == "show_invoice"
    assert t.action_status == "success"
    assert counts["show_invoice"] == 1
    assert counts["legacy_read"] == 0
    assert counts["reader"] == 1
    assert "0013-00097239" in (t.user_message or "")
    assert "22.648" in (t.user_message or "") or "22648" in (t.user_message or "")
    assert "Registrado" in (t.user_message or "")
    low = (t.user_message or "").lower()
    assert "vence" not in low
    assert "período" not in low and "periodo" not in low
    inv_dicts = t.data.get("invoices") or []
    assert inv_dicts and inv_dicts[0]["amount"] == "22648.67"
    assert inv_dicts[0].get("currency") is None
    assert inv_dicts[0].get("due_date") is None
    assert inv_dicts[0].get("period") is None
    assert inv_dicts[0]["status"] == "Registrado"

def test_e2e_02_multi_candidate_needs_input(monkeypatch):
    _enable(monkeypatch)
    ctx = {"phone_candidates": [{"dni": "1"}, {"dni": "2"}]}
    with (
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
        patch("app.services.eko_invoice_reader.read_invoices_fc") as reader,
    ):
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
    assert t.data.get("needs_input") == "account_selection"
    disp.assert_not_called()
    reader.assert_not_called()


def test_e2e_03_empty_client_number(monkeypatch):
    _enable(monkeypatch)
    with (
        patch("app.services.eko_journeys.dispatch_runtime") as disp,
        patch("app.services.eko_invoice_reader.read_invoices_fc") as reader,
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(client_number=""),
            "Quiero ver mi factura",
            canal="wa",
            ctx={},
        )
    assert t and t.action_status == "needs_input"
    assert t.reason_code == "missing_client_number"
    disp.assert_not_called()
    reader.assert_not_called()


def test_e2e_04_trusted_ownership_immutable():
    bootstrap_registry()
    trusted = TrustedContext(
        abonado=_abo(client_number="AAAA"),
        organization_id="org",
        conversation_id="c1",
    )
    req = ActionRequest(
        action="show_invoice",
        parameters={"client_number": "BBBB"},
        source="llm_proposal",
    )
    with patch("app.services.eko_invoice_reader.read_invoices_fc") as reader:
        ar = _exec_show_invoice(req, trusted)
    assert ar.status == "denied"
    assert ar.reason_code == "client_number_mismatch"
    reader.assert_not_called()


def test_e2e_05_no_double_execution_runtime_xor_legacy(monkeypatch):
    _enable(monkeypatch)
    inv = _inv()
    counts = {"runtime": 0, "legacy": 0, "reader": 0}

    def _disp(action, **kwargs):
        if action == "show_invoice":
            counts["runtime"] += 1
            counts["reader"] += 1
            return _show_invoice_ar(inv)
        if action == "open_OV":
            return _ov_ar()
        return ActionResult(action=action, status="unavailable")

    def _legacy_read(**kwargs):
        counts["legacy"] += 1
        counts["reader"] += 1
        raise AssertionError("legacy should not run alongside runtime")

    with (
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp),
        patch(
            "app.services.eko_invoice_reader.read_invoices_fc",
            side_effect=_legacy_read,
        ),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Quiero ver mi factura",
            canal="wa",
            ctx={},
        )

    assert t and t.action == "show_invoice"
    assert counts["runtime"] == 1
    assert counts["legacy"] == 0
    assert counts["runtime"] + counts["legacy"] == 1
    assert counts["reader"] == 1


def test_e2e_05b_legacy_xor_when_runtime_off(monkeypatch):
    """Runtime off → dispatch no ejecuta; solo legacy lee (XOR)."""
    _enable(monkeypatch, "show_balance", "open_OV", "show_invoice")
    monkeypatch.setattr(bridge, "ACTION_RUNTIME_ENABLED", False)
    inv = _inv()
    counts = {"runtime_exec": 0, "legacy": 0}

    from app.services.eko_invoice_reader import InvoiceReadResult

    def _read(**kwargs):
        counts["legacy"] += 1
        return InvoiceReadResult(status="ok", invoices=[inv])

    real_exec = None
    import app.services.eko_action_runtime as rt

    real_exec = rt.execute_action

    def _exec_guard(req, trusted):
        if getattr(req, "action", "") == "show_invoice":
            counts["runtime_exec"] += 1
        return real_exec(req, trusted)

    with (
        patch.object(rt, "execute_action", side_effect=_exec_guard),
        patch("app.services.eko_invoice_reader.read_invoices_fc", side_effect=_read),
    ):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Quiero ver mi factura",
            canal="wa",
            ctx={},
        )

    assert t and t.action == "show_invoice"
    assert counts["runtime_exec"] == 0
    assert counts["legacy"] == 1
    assert counts["runtime_exec"] + counts["legacy"] == 1
    assert "0013-00097239" in (t.user_message or "")


def test_e2e_06_no_invoice(monkeypatch):
    _enable(monkeypatch)

    def _disp(action, **kwargs):
        if action == "show_invoice":
            return _show_invoice_ar(empty=True)
        if action == "open_OV":
            return _ov_ar()
        return ActionResult(action=action, status="unavailable")

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Quiero ver mi factura",
            canal="wa",
            ctx={},
        )
    assert t and t.action == "show_invoice"
    assert t.reason_code == "no_fc_invoices"
    assert t.action_status == "success"
    assert "no encuentro facturas" in (t.user_message or "").lower()


def test_e2e_07_balance_vs_invoice(monkeypatch):
    _enable(monkeypatch)
    actions: list[str] = []

    def _disp(action, **kwargs):
        actions.append(action)
        if action == "show_balance":
            return _bal_ar()
        if action == "show_invoice":
            return _show_invoice_ar(_inv())
        if action == "open_OV":
            return _ov_ar()
        return ActionResult(action=action, status="unavailable")

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp):
        t1 = maybe_handle_journey_turn(
            MagicMock(), "org", _conv(), _abo(), "¿Cuánto debo?", canal="wa", ctx={}
        )
        t2 = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Quiero ver mi factura",
            canal="wa",
            ctx={},
        )
    assert t1 and t1.action == "show_balance"
    assert "show_invoice" not in actions[:1]
    assert t2 and t2.action == "show_invoice"
    assert "show_invoice" in actions


def test_e2e_08_due_date_no_contamination(monkeypatch):
    _enable(monkeypatch)

    def _disp(action, **kwargs):
        assert action != "show_invoice"
        return _ov_ar()

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp) as disp:
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "¿Cuándo vence mi factura?",
            canal="wa",
            ctx={},
        )
    assert t and t.data.get("honest_unavailable") == "due_date"
    assert t.action == "open_OV"
    assert all(c.args[0] != "show_invoice" for c in disp.call_args_list)


def test_e2e_09_pay_no_contamination(monkeypatch):
    _enable(monkeypatch)

    def _disp(action, **kwargs):
        assert action == "open_OV"
        assert kwargs.get("parameters", {}).get("destination") == "pagar"
        return ActionResult(
            action="open_OV",
            status="success",
            user_message="https://ov.example/pagar",
            data={"destination": "pagar"},
        )

    with patch("app.services.eko_journeys.dispatch_runtime", side_effect=_disp) as disp:
        t = maybe_handle_journey_turn(
            MagicMock(),
            "org",
            _conv(),
            _abo(),
            "Quiero pagar la factura",
            canal="wa",
            ctx={},
        )
    assert t and t.data.get("billing_act") == "pay"
    assert t.action == "open_OV"
    assert all(c.args[0] != "show_invoice" for c in disp.call_args_list)


def test_e2e_10_ic_exclusion():
    rows = [
        {
            "id": 1,
            "number": "FC-1",
            "full_type": "FC B",
            "type": "FC",
            "account_number": "18099",
            "amount": Decimal("10"),
            "date": datetime(2026, 9, 1, tzinfo=UTC),
            "state": "Registrado",
        },
        {
            "id": 2,
            "number": "IC-1",
            "full_type": "IC",
            "type": "IC",
            "account_number": "18099",
            "amount": Decimal("99"),
            "date": datetime(2026, 9, 2, tzinfo=UTC),
            "state": "Registrado",
        },
    ]

    class _R:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return self

        def all(self):
            return self._rows

    class _C:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt, params=None):
            cn = str((params or {}).get("client_number") or "")
            lim = int((params or {}).get("limit") or 5)
            out = [r for r in rows if r["account_number"] == cn and r["type"] == "FC"]
            return _R(out[:lim])

    class _E:
        def connect(self):
            return _C()

        def dispose(self):
            return None

    with patch(
        "app.services.billtrack._billtrack_engine",
        return_value=(_E(), {}, False),
    ):
        result = read_invoices_fc(client_number="18099")
    assert result.status == "ok"
    assert all(i.type == "FC" for i in result.invoices)
    assert all(i.invoice_number != "IC-1" for i in result.invoices)


def test_e2e_11_amount_authority_no_concepts_query():
    """Reader no consulta billed_concept; amount = api_invoice.amount."""
    x = Decimal("22648.67")
    y = Decimal("18717.91")
    assert x != y
    rows = [
        {
            "id": 1,
            "number": "0013-1",
            "full_type": "FC B",
            "type": "FC",
            "account_number": "18099",
            "amount": x,
            "date": datetime(2026, 9, 1, tzinfo=UTC),
            "state": "Registrado",
        }
    ]

    class _R:
        def mappings(self):
            return self

        def all(self):
            return rows

    class _C:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt, params=None):
            sql = str(stmt)
            assert "billed_concept" not in sql.lower()
            assert "sum(" not in sql.lower()
            return _R()

    class _E:
        def connect(self):
            return _C()

        def dispose(self):
            return None

    with patch(
        "app.services.billtrack._billtrack_engine",
        return_value=(_E(), {}, False),
    ):
        result = read_invoices_fc(client_number="18099")
    assert result.invoices[0].amount == "22648.67"
    assert Decimal(result.invoices[0].amount) != y


def test_e2e_12_state_from_invoice_not_statement():
    inv = _inv(status="Registrado")
    d = inv.to_dict()
    assert d["status"] == "Registrado"
    # No hay campo statement_status en DTO
    assert "statement_status" not in d
    msg = format_invoice_headers_message([inv])
    assert "Registrado" in msg
    assert "Habilitado" not in msg  # statement status típico no aparece


def test_e2e_13_order_deterministic():
    same = datetime(2026, 9, 18, tzinfo=UTC)
    rows = [
        {
            "id": 100,
            "number": "A",
            "full_type": "FC B",
            "type": "FC",
            "account_number": "18099",
            "amount": Decimal("1"),
            "date": same,
            "state": "Registrado",
        },
        {
            "id": 101,
            "number": "B",
            "full_type": "FC B",
            "type": "FC",
            "account_number": "18099",
            "amount": Decimal("2"),
            "date": same,
            "state": "Registrado",
        },
    ]

    class _R:
        def __init__(self, data):
            self._data = data

        def mappings(self):
            return self

        def all(self):
            return self._data

    class _C:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt, params=None):
            lim = int((params or {}).get("limit") or 5)
            ordered = sorted(rows, key=lambda r: (r["date"], r["id"]), reverse=True)
            return _R(ordered[:lim])

    class _E:
        def connect(self):
            return _C()

        def dispose(self):
            return None

    with patch(
        "app.services.billtrack._billtrack_engine",
        return_value=(_E(), {}, False),
    ):
        result = read_invoices_fc(client_number="18099")
    assert [i.invoice_id for i in result.invoices] == [101, 100]


def test_e2e_14_limit():
    rows = [
        {
            "id": i,
            "number": f"N{i}",
            "full_type": "FC B",
            "type": "FC",
            "account_number": "18099",
            "amount": Decimal("1"),
            "date": datetime(2026, 1, i % 28 + 1, tzinfo=UTC),
            "state": "Registrado",
        }
        for i in range(1, 30)
    ]

    class _R:
        def __init__(self, data):
            self._data = data

        def mappings(self):
            return self

        def all(self):
            return self._data

    class _C:
        def __init__(self):
            self.last_limit = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt, params=None):
            lim = int((params or {}).get("limit") or 5)
            self.last_limit = lim
            ordered = sorted(rows, key=lambda r: (r["date"], r["id"]), reverse=True)
            return _R(ordered[:lim])

    conn = _C()

    class _E:
        def connect(self):
            return conn

        def dispose(self):
            return None

    with patch(
        "app.services.billtrack._billtrack_engine",
        return_value=(_E(), {}, False),
    ):
        r_default = read_invoices_fc(client_number="18099")
        r_max = read_invoices_fc(client_number="18099", limit=20)
        r_over = read_invoices_fc(client_number="18099", limit=100)
    assert len(r_default.invoices) == 5
    assert len(r_max.invoices) == 20
    assert len(r_over.invoices) == 20
