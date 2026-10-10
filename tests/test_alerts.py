"""Central de alertas: regras sobre o histórico da própria unidade, conferência e permissões."""
from datetime import date
from decimal import Decimal as D

import pytest

from app.models import AlertAck, ConsumerUnit, EnergyBill, RecordType, Store
from app.services import alert_service
from tests.test_director import _user

TODAY = date(2026, 10, 10)          # contas recentes = de jul/2026 em diante


@pytest.fixture(autouse=True)
def _fresh_cache():
    alert_service.reset_cache()
    yield
    alert_service.reset_cache()


def _unit(db, code, number=None):
    cemig = db.query(RecordType).filter_by(code="cemig").one()
    s = Store(code=code, name=f"Loja {code}")
    db.add(s)
    db.flush()
    u = ConsumerUnit(store_id=s.id, number=number or code, number_normalized=number or code, record_type_id=cemig.id)
    db.add(u)
    db.flush()
    return u, cemig


def _bill(db, u, rt, ym, total, **kw):
    b = EnergyBill(unit_id=u.id, record_type_id=rt.id, reference=date(ym[0], ym[1], 1), total_value=D(total), **kw)
    db.add(b)
    db.commit()
    return b


def _history(db, u, rt, last, months=((2026, 3), (2026, 4), (2026, 5), (2026, 6), (2026, 7)), base=1000, **kw):
    for ym in months:
        _bill(db, u, rt, ym, base)
    return _bill(db, u, rt, (2026, 8), last, **kw)


def _kinds(db, **kw):
    return {(a.kind, a.severity) for a in alert_service.compute(db, TODAY, **kw)}


def test_value_spike_is_flagged_with_severity_by_size(db):
    u, rt = _unit(db, "A")
    _history(db, u, rt, 1350)                                  # +35% -> média
    u2, _ = _unit(db, "B")
    _history(db, u2, rt, 1600)                                 # +60% -> alta
    u3, _ = _unit(db, "C")
    _history(db, u3, rt, 1100)                                 # +10% -> nada
    got = {(a.store_code, a.severity) for a in alert_service.compute(db, TODAY) if a.kind == "valor"}
    assert got == {("A", "media"), ("B", "alta")}


def test_sharp_drop_and_short_history_rules(db):
    u, rt = _unit(db, "A")
    _history(db, u, rt, 500)                                   # -50%: pode ser estimativa
    assert ("valor", "media") in _kinds(db)
    u2, _ = _unit(db, "NOVA")
    for ym in ((2026, 7), (2026, 8)):
        _bill(db, u2, rt, ym, 5000 if ym[1] == 8 else 1000)    # só 1 conta anterior: sem base para comparar
    assert not [a for a in alert_service.compute(db, TODAY) if a.store_code == "NOVA"]


def test_old_bills_do_not_alert(db):
    u, rt = _unit(db, "A")
    for ym in ((2025, 1), (2025, 2), (2025, 3), (2025, 4)):
        _bill(db, u, rt, ym, 1000)
    _bill(db, u, rt, (2025, 5), 5000)                          # pico, mas de mais de 3 meses atrás
    assert alert_service.compute(db, TODAY) == []


def test_demand_above_contracted_and_price_per_kwh(db):
    u, rt = _unit(db, "A")
    for ym in ((2026, 3), (2026, 4), (2026, 5), (2026, 6), (2026, 7)):
        _bill(db, u, rt, ym, 1000, consumption_hfp=D(10000))                 # R$ 0,10/kWh
    _bill(db, u, rt, (2026, 8), 1000, consumption_hfp=D(7000), demand_hfp=D(125), contracted_demand=D(100))   # R$ 0,143/kWh (+43%)
    kinds = _kinds(db)
    assert ("demanda", "alta") in kinds and ("tarifa", "media") in kinds


def test_items_that_do_not_add_up_and_odd_period(db):
    u, rt = _unit(db, "A")
    _bill(db, u, rt, (2026, 8), 1000, source="import", days=12, line_items=[{"value": 300}, {"value": 400}])
    kinds = _kinds(db)
    assert ("itens", "baixa") in kinds and ("periodo", "baixa") in kinds
    ok = _unit(db, "B")[0]
    _bill(db, ok, rt, (2026, 8), 1000, source="import", days=30, line_items=[{"value": 600}, {"value": 400}])
    assert not [a for a in alert_service.compute(db, TODAY) if a.store_code == "B"]


def test_duplicate_invoice_number_is_high_severity(db):
    u, rt = _unit(db, "A")
    u2, _ = _unit(db, "B")
    _bill(db, u, rt, (2026, 7), 1000, invoice_number="000123")
    _bill(db, u2, rt, (2026, 8), 2000, invoice_number="123")
    assert ("nota", "alta") in _kinds(db)


def test_inactive_units_and_stores_are_ignored(db):
    u, rt = _unit(db, "A")
    _history(db, u, rt, 1600)
    assert alert_service.compute(db, TODAY)
    u.active = False
    db.commit()
    assert alert_service.compute(db, TODAY) == []


def test_acknowledging_removes_the_alert_and_is_audited(client, db):
    u, rt = _unit(db, "A")
    b = _history(db, u, rt, 1600)
    html = client.get("/alertas").text
    assert "Alertas" in html and "acima da média da unidade" in html
    key = f"valor:{b.id}"
    r = client.post("/alertas/conferido", {"key": key})
    assert r.status_code == 303
    assert db.query(AlertAck).filter_by(key=key).count() == 1
    assert "acima da média da unidade" not in client.get("/alertas").text
    assert "Alerta conferido" in client.get("/admin/audit").text


def test_ack_ignores_unknown_keys_and_viewer_cannot_ack(client, db):
    u, rt = _unit(db, "A")
    b = _history(db, u, rt, 1600)
    client.post("/alertas/conferido", {"key": "valor:999999"})
    assert db.query(AlertAck).count() == 0
    viewer = _user(client, "consul20", "viewer")
    assert viewer.get("/alertas").status_code == 200 and "Conferido</button>" not in viewer.get("/alertas").text
    assert viewer.post("/alertas/conferido", {"key": f"valor:{b.id}"}).status_code == 403


def test_count_endpoint_and_entry_screens_show_the_number(client, db):
    u, rt = _unit(db, "A")
    _history(db, u, rt, 1600)
    # o "hoje" real do teste é posterior ao de TODAY: as contas de ago/2026 já podem estar fora da janela;
    # por isso só conferimos a forma da resposta e a presença do link nas telas.
    d = client.get("/api/alertas/contagem").json()
    assert set(d) == {"count", "high"} and isinstance(d["count"], int)
    assert 'href="/alertas"' in client.get("/").text and 'href="/alertas"' in client.get("/diretoria").text
