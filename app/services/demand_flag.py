"""O sistema mostra demanda (gráficos, colunas, aba Contratos) só se ALGUMA conta já trouxe esse dado.

Loja de baixa tensão (Grupo B) não tem demanda na fatura; se nenhuma conta tem, o assunto some das telas. Quando a
primeira conta com demanda for salva, tudo aparece sozinho. Resultado guardado por 60 s (é consultado em toda tela).
"""
import time

from sqlalchemy import or_, select

_cache = {"at": 0.0, "value": False}
TTL = 60


def reset() -> None:
    _cache["at"] = 0.0


def demand_in_use() -> bool:
    if time.monotonic() - _cache["at"] < TTL:
        return _cache["value"]
    from app.database import SessionLocal
    from app.models import EnergyBill

    try:
        with SessionLocal() as db:
            found = db.scalar(select(EnergyBill.id).where(or_(EnergyBill.contracted_demand > 0, EnergyBill.demand_hp > 0,
                                                              EnergyBill.demand_hfp > 0)).limit(1)) is not None
    except Exception:  # noqa: BLE001 — banco indisponível: não esconde nada por engano
        return True
    _cache.update(at=time.monotonic(), value=found)
    return found
