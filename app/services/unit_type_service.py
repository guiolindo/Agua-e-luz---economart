"""Fornecedor (tipo de conta) da unidade consumidora e das contas dela.

Cada conta guarda o próprio tipo (CEMIG, CEMIG Geração e Transmissão...), e os painéis somam por ele. Uma unidade
consumidora é de UM fornecedor: quando o cadastro da unidade troca de fornecedor, as contas já lançadas dela
passam junto. Conta que viraria duplicada (já existe outra da mesma unidade, do novo tipo, no mesmo mês) fica
como está e é informada.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConsumerUnit, EnergyBill, RecordType


def mismatched(db: Session, unit: ConsumerUnit) -> list[EnergyBill]:
    """Contas da unidade com tipo diferente do cadastro da unidade."""
    if not unit.record_type_id:
        return []
    return list(db.scalars(select(EnergyBill).where(EnergyBill.unit_id == unit.id,
                                                    EnergyBill.record_type_id != unit.record_type_id)))


def align(db: Session, unit: ConsumerUnit) -> tuple[int, int]:
    """Passa as contas da unidade para o tipo do cadastro. Devolve (movidas, mantidas por duplicidade)."""
    target = db.get(RecordType, unit.record_type_id) if unit.record_type_id else None
    if target is None or not target.is_bill:
        return 0, 0
    taken = {b.reference for b in db.scalars(select(EnergyBill).where(EnergyBill.unit_id == unit.id,
                                                                     EnergyBill.record_type_id == target.id))}
    moved = kept = 0
    for bill in sorted(mismatched(db, unit), key=lambda b: (b.reference, b.id)):
        if bill.reference in taken:
            kept += 1
            continue
        bill.record_type_id = target.id
        taken.add(bill.reference)
        moved += 1
    db.flush()
    return moved, kept
