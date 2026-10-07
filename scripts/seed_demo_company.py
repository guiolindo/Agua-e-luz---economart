"""Demonstração do PAINEL DA DIRETORIA. Uso: python -m scripts.seed_demo_company  (rode depois de scripts.seed_demo)

ATENÇÃO — DADOS FICTÍCIOS: além do CD300 (valores reais da planilha, criado por seed_demo), cria lojas
'DEMO-01..DEMO-08' com valores gerados por fórmula, só para visualizar comparações. Não use em produção.
"""
import math
import random
from datetime import date
from decimal import Decimal

from app import database, models  # noqa: F401
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.models.mixins import utcnow  # noqa: F401
from app.seed import seed


def main():
    database.Base.metadata.create_all(database.engine)
    with database.SessionLocal() as db:
        seed(db)
        if db.query(Store).filter(Store.code.like("DEMO-%")).first():
            print("Lojas DEMO já existem.")
            return
        types = {t.code: t for t in db.query(RecordType)}
        cd300 = db.query(Store).filter_by(code="CD300").first()
        if cd300 and not cd300.region:
            cd300.region = "MG"
        rnd = random.Random(300)
        months = [date(2025 + (i // 12), i % 12 + 1, 1) for i in range(8, 20)]   # set/2025 .. ago/2026
        for n in range(1, 9):
            ba = n % 3 == 0
            store = Store(code=f"DEMO-{n:02d}", name=f"Loja Demonstração {n}", region="BA" if ba else "MG")
            db.add(store)
            db.flush()
            rtype = types["coelba" if ba else "cemig"]
            unit = ConsumerUnit(store_id=store.id, number=f"99.000.000.{n:03d}-00", number_normalized=f"99000000{n:03d}00",
                                description="Unidade (fictícia)", record_type_id=rtype.id)
            db.add(unit)
            db.flush()
            base = rnd.uniform(9000, 38000)
            kwh_base = base / rnd.uniform(0.34, 0.52)
            contracted = rnd.choice([120, 180, 210, 300, 420])
            for i, m in enumerate(months):
                season = 1 + 0.12 * math.sin((m.month - 2) / 12 * 2 * math.pi) + rnd.uniform(-0.05, 0.05)
                value = Decimal(f"{base * season * (1 + 0.004 * i):.2f}")
                kwh = Decimal(f"{kwh_base * season:.2f}")
                demand = Decimal(f"{contracted * rnd.uniform(0.62, 1.12):.2f}")
                db.add(EnergyBill(unit_id=unit.id, record_type_id=rtype.id, source="manual", reference=m, total_value=value,
                                  due_date=date(m.year + (m.month == 12), m.month % 12 + 1, 10), days=rnd.choice([29, 30, 31]),
                                  consumption_hfp=kwh * Decimal("0.9"), consumption_hp=kwh * Decimal("0.1"),
                                  demand_hfp=demand, demand_hp=demand * Decimal("0.8"), contracted_demand=Decimal(contracted)))
                if n % 2 == 0:
                    db.add(ManualRecord(store_id=store.id, record_type_id=types["ll-energia"].id, reference=m,
                                        value=Decimal(f"{rnd.uniform(1800, 2400):.2f}"), data={}))
                if n % 3 == 1:
                    db.add(ManualRecord(store_id=store.id, record_type_id=types["ccee"].id, reference=m,
                                        value=Decimal(f"{rnd.uniform(2500, 9000):.2f}"), data={}))
        db.commit()
        print("Lojas DEMO (fictícias) criadas.")


if __name__ == "__main__":
    main()
