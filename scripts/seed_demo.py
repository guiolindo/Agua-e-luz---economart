"""Carrega dados de demonstração (CD300 com o histórico CEMIG de jan–ago/2026). Uso: python -m scripts.seed_demo"""
from datetime import date
from decimal import Decimal

from app import database, models  # noqa: F401
from app.models import ConsumerUnit, EnergyBill, ManualRecord, RecordType, Store
from app.seed import seed

CEMIG = [("22543.10", 31), ("19560.38", 28), ("24144.83", 31), ("23153.69", 30), ("16959.69", 31),
         ("18020.14", 30), ("18835.58", 31), ("19536.31", 31)]
LL = ["1571.58", None, None, None, None, "6125.52", "5036.44", "2116.17"]


def main():
    database.Base.metadata.create_all(database.engine)
    with database.SessionLocal() as db:
        seed(db)
        if db.query(Store).filter_by(code="CD300").first():
            print("CD300 já existe; nada a fazer.")
            return
        cemig = db.query(RecordType).filter_by(code="cemig").one()
        ll = db.query(RecordType).filter_by(code="ll-energia").one()
        store = Store(code="CD300", name="CD Ribeirão das Neves", location="Ribeirão das Neves/MG")
        db.add(store)
        db.flush()
        unit = ConsumerUnit(store_id=store.id, number="12.060.073.018-19", number_normalized="1206007301819",
                            description="Unidade principal", record_type_id=cemig.id)
        db.add(unit)
        db.flush()
        for i, (value, days) in enumerate(CEMIG, start=1):
            db.add(EnergyBill(unit_id=unit.id, record_type_id=cemig.id, source="manual", reference=date(2026, i, 1),
                              total_value=Decimal(value), days=days))
        for i, value in enumerate(LL, start=1):
            if value:
                db.add(ManualRecord(store_id=store.id, record_type_id=ll.id, reference=date(2026, i, 1),
                                    value=Decimal(value), data={}))
        db.commit()
        print("Dados de demonstração criados.")


if __name__ == "__main__":
    main()
