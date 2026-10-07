from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ConsumerUnit
from app.utils.parsing import normalize_uc


def find_unit_by_number(db: Session, number: str | None) -> ConsumerUnit | None:
    """Unidade (e, por ela, a loja) correspondente ao número lido da conta."""
    key = normalize_uc(number)
    if not key:
        return None
    return db.scalar(
        select(ConsumerUnit).options(joinedload(ConsumerUnit.store)).where(ConsumerUnit.number_normalized == key)
    )


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def suggest_similar_units(db: Session, number: str | None, max_distance: int = 2, limit: int = 3) -> list[ConsumerUnit]:
    """Quando a UC lida não existe: sugere cadastradas com 1–2 dígitos de diferença (provável erro de leitura)."""
    key = normalize_uc(number)
    if not key:
        return []
    units = db.scalars(select(ConsumerUnit).options(joinedload(ConsumerUnit.store))).all()
    scored = [(edit_distance(key, u.number_normalized), u) for u in units]
    scored = [(d, u) for d, u in scored if 0 < d <= max_distance]
    scored.sort(key=lambda t: t[0])
    return [u for _, u in scored[:limit]]
