"""Carrega dados de demonstração: loja CD300 reproduzindo a planilha impressa (todos os fornecedores, jan–set/2026).

Uso: python -m scripts.seed_demo

Atenção: os valores da CEMIG Distribuição vêm da tabela da planilha (por mês de VENCIMENTO). A conta que vence em
jan/2026 é a de referência dez/2025, e assim por diante. As datas de vencimento dia 9 são ASSUMIDAS (só a de SET/2026,
09/10/2026, vem de uma conta real). Os demais fornecedores entram como lançamento manual no próprio mês da tabela.
"""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from app import database, models  # noqa: F401
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.seed import seed

DATA = json.loads((Path(__file__).parent / "demo_cd300.json").read_text(encoding="utf-8"))


def _month(s: str) -> date:
    y, m = s.split("-")
    return date(int(y), int(m), 1)


def main():
    database.Base.metadata.create_all(database.engine)
    with database.SessionLocal() as db:
        seed(db)
        if db.query(Store).filter_by(code="CD300").first():
            print("CD300 já existe; nada a fazer.")
            return
        types = {t.code: t for t in db.query(RecordType)}
        store = Store(code="CD300", name="CD Ribeirão das Neves", location="Ribeirão das Neves/MG", aliases=["CD 300"])
        db.add(store)
        db.flush()
        unit = ConsumerUnit(store_id=store.id, number="12.060.073.018-19", number_normalized="1206007301819",
                            description="Unidade principal", record_type_id=types["cemig"].id)
        db.add(unit)
        db.flush()
        months = [_month(m) for m in DATA["meses"]]
        for code, values in DATA["linhas"].items():
            for due_month, value in zip(months, values):
                if value is None:
                    continue
                if code == "cemig":
                    # a conta vence no mês da coluna; a referência (consumo) é o mês anterior
                    ref = date(due_month.year - (due_month.month == 1), 12 if due_month.month == 1 else due_month.month - 1, 1)
                    db.add(EnergyBill(unit_id=unit.id, record_type_id=types["cemig"].id, source="manual", reference=ref,
                                      due_date=date(due_month.year, due_month.month, 9), total_value=Decimal(value),
                                      days=DATA["cemig_dias_por_referencia"].get(ref.strftime("%Y-%m"))))
                else:
                    db.add(ManualRecord(store_id=store.id, record_type_id=types[code].id, reference=due_month,
                                        value=Decimal(value), data={}))
        db.commit()
        print("Dados de demonstração criados (CD300, jan–set/2026).")


if __name__ == "__main__":
    main()
