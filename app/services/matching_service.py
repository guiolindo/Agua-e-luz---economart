import re

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


def _norm(text: str | None) -> str:
    """'CD 300' / 'cd-300' / 'CD300' -> 'CD300' (sem acentos, só letras/dígitos)."""
    import unicodedata

    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]", "", t).upper()


def find_store_by_hint(db: Session, hint: str | None):
    """Loja citada em anotação à mão/texto livre: compara código, nome e apelidos (igualdade, sem fuzzy).

    Retorna None se não houver correspondência única — nunca chuta (um dígito errado seria outra loja).
    """
    from app.models import Store

    key = _norm(hint)
    if not key:
        return None
    hits = []
    for store in db.scalars(select(Store)):
        names = [store.code, store.name, *(store.aliases or [])]
        if key in {_norm(n) for n in names if n}:
            hits.append(store)
    return hits[0] if len(hits) == 1 else None


def type_for_utility(types, utility: str | None):
    """Tipo de conta (CEMIG, COELBA...) cujo nome/código aparece no texto da distribuidora lida da conta."""
    key = _norm(utility)
    if not key:
        return None
    best = None
    for t in types:
        if not t.is_bill:
            continue
        for candidate in (t.name, t.code):
            c = _norm(candidate)
            if c and c in key and (best is None or len(c) > best[0]):
                best = (len(c), t)
    return best[1] if best else None
