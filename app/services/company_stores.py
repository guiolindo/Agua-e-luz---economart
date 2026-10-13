"""Lista oficial de lojas da empresa: leitura da lista colada pelo administrador, carga e vínculo das lojas antigas.

A lista vem da planilha da empresa, copiada e colada (colunas separadas por TAB):

    MULTICOM ATACADO E VAREJO - ECONOMART (MINAS GERAIS)          <- título de bloco (sem CNPJ)
    MULTICOM  24  189018  Contagem Colonial  28.548.486/0022-40  003.034.575-1493  72196218  32.044-200  Rua ...

Colunas de uma loja: empresa, número da loja, código interno, nome, CNPJ, inscrição estadual, inscrição municipal,
CEP e endereço. O CNPJ é a âncora da linha: o que vem antes dele é empresa/número/código/nome, o que vem depois
são os registros, o CEP e o endereço. A UF sai do CEP (com o endereço e o título do bloco como reserva).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import EnergyBill, Import, ManualRecord, Store
from app.repositories.stores import store_sort_key

CNPJ_RE = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
CEP_RE = re.compile(r"^\d{2}\.?\d{3}-\d{3}$")
MAX_ROWS = 500

# faixas de CEP (5 primeiros dígitos) por UF
_CEP_UF = [
    (1000, 19999, "SP"), (20000, 28999, "RJ"), (29000, 29999, "ES"), (30000, 39999, "MG"), (40000, 48999, "BA"),
    (49000, 49999, "SE"), (50000, 56999, "PE"), (57000, 57999, "AL"), (58000, 58999, "PB"), (59000, 59999, "RN"),
    (60000, 63999, "CE"), (64000, 64999, "PI"), (65000, 65999, "MA"), (66000, 68899, "PA"), (68900, 68999, "AP"),
    (69000, 69299, "AM"), (69300, 69399, "RR"), (69400, 69899, "AM"), (69900, 69999, "AC"), (70000, 72799, "DF"),
    (72800, 72999, "GO"), (73000, 73699, "DF"), (73700, 76799, "GO"), (76800, 76999, "RO"), (77000, 77999, "TO"),
    (78000, 78899, "MT"), (79000, 79999, "MS"), (80000, 87999, "PR"), (88000, 89999, "SC"), (90000, 99999, "RS"),
]
_UFS = {uf for *_, uf in _CEP_UF}
_STATE_NAMES = {
    "MINAS GERAIS": "MG", "BAHIA": "BA", "PERNAMBUCO": "PE", "SAO PAULO": "SP", "RIO DE JANEIRO": "RJ",
    "ESPIRITO SANTO": "ES", "GOIAS": "GO", "SERGIPE": "SE", "ALAGOAS": "AL", "PARANA": "PR",
}


def _plain(text: str) -> str:
    """Sem acento, maiúsculas, espaços simples (para comparar nomes)."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def uf_from_cep(cep: str) -> str | None:
    digits = re.sub(r"\D", "", cep or "")
    if len(digits) != 8:
        return None
    n = int(digits[:5])
    return next((uf for lo, hi, uf in _CEP_UF if lo <= n <= hi), None)


def _uf_from_text(text: str) -> str | None:
    t = _plain(text)
    m = re.search(r"[/\-]\s*([A-Z]{2})\s*$", t)
    if m and m.group(1) in _UFS:
        return m.group(1)
    return next((uf for name, uf in _STATE_NAMES.items() if name in t), None)


def _blank(v: str) -> str:
    v = (v or "").strip()
    return "" if v in ("-", "—") else v


@dataclass
class Row:
    line: int
    company: str = ""
    code: str = ""
    internal_code: str = ""
    name: str = ""
    cnpj: str = ""
    state_reg: str = ""
    municipal_reg: str = ""
    cep: str = ""
    address: str = ""
    uf: str = ""
    group: str = ""
    error: str = ""
    status: str = ""            # "nova" | "atualiza" (preenchido no plano)
    note: str = ""

    @property
    def label(self) -> str:
        return f"{self.code} — {self.name}"

    def details(self) -> dict:
        data = {"internal_code": self.internal_code, "state_reg": self.state_reg, "municipal_reg": self.municipal_reg,
                "cep": self.cep, "address": self.address}
        return {k: v for k, v in data.items() if v}


@dataclass
class Parsed:
    rows: list[Row] = field(default_factory=list)
    errors: list[Row] = field(default_factory=list)


def _split_before(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\t+|\s{2,}", text.strip()) if p.strip()]
    if len(parts) < 3:                         # colado sem TAB: separa por espaço (empresa, número, código, nome...)
        parts = text.split()
    return parts


def parse(text: str) -> Parsed:
    out, group, seen = Parsed(), "", {}
    for n, raw in enumerate((text or "").splitlines()[:MAX_ROWS * 2], 1):
        if not raw.strip():
            continue
        m = CNPJ_RE.search(raw)
        if not m:
            group = re.sub(r"\s+", " ", raw).strip()[:120]           # título de bloco
            continue
        row = Row(line=n, group=group, cnpj=m.group(0))
        parts = _split_before(raw[:m.start()])
        if len(parts) >= 4 and parts[2].isdigit():
            row.company, row.code, row.internal_code, row.name = parts[0], parts[1], parts[2], " ".join(parts[3:])
        elif len(parts) >= 3:
            row.company, row.code, row.name = parts[0], parts[1], " ".join(parts[2:])
        after = raw[m.end():]
        fields = [_blank(f) for f in after.split("\t")]
        if fields and fields[0] == "" and after.startswith("\t"):
            fields = fields[1:]
        cep_at = next((i for i, f in enumerate(fields) if CEP_RE.match(f)), None)
        if cep_at is not None:
            row.state_reg = fields[0] if cep_at >= 1 else ""
            row.municipal_reg = " ".join(f for f in fields[1:cep_at] if f)
            row.cep = fields[cep_at]
            row.address = " ".join(f for f in fields[cep_at + 1:] if f)
        else:                                                      # sem TAB depois do CNPJ: procura o CEP no texto
            cm = re.search(r"(?<![\d.\-/])(\d{2}\.?\d{3}-\d{3})(?![\d\-])", after)
            if cm:
                row.cep, row.address = cm.group(1), after[cm.end():].strip()
        row.name = re.sub(r"\s+", " ", row.name).strip()[:200]
        row.company = row.company[:60]
        row.address = re.sub(r"\s+", " ", row.address).strip()[:200]
        row.uf = uf_from_cep(row.cep) or _uf_from_text(row.address) or _uf_from_text(row.group) or ""
        if not row.code.isdigit():
            row.error = "Número da loja não encontrado (precisa ser só números)."
        elif not row.name:
            row.error = "Nome da loja não encontrado."
        elif row.code in seen:
            row.error = f"Número {row.code} repetido (já está na linha {seen[row.code]})."
        if row.error:
            out.errors.append(row)
        else:
            seen[row.code] = n
            out.rows.append(row)
        if len(out.rows) >= MAX_ROWS:
            break
    return out


def _by_code(db: Session, code: str) -> Store | None:
    return db.scalar(select(Store).where(func.lower(Store.code) == code.lower()))


def plan(db: Session, parsed: Parsed) -> Parsed:
    """Marca cada linha como loja nova ou atualização de uma loja que já tem esse número."""
    for row in parsed.rows:
        store = _by_code(db, row.code)
        if store is None:
            row.status = "nova"
        else:
            row.status = "atualiza"
            if not store.is_official:
                row.note = f"já existia como {store.label}: passa a ser a loja oficial"
            elif _plain(store.name or "") != _plain(row.name):
                row.note = f"nome atual: {store.name or '—'}"
    return parsed


def apply(db: Session, parsed: Parsed) -> tuple[int, int]:
    """Cria ou atualiza as lojas oficiais. Lojas fora da lista não são apagadas nem desativadas."""
    created = updated = 0
    for row in parsed.rows:
        store = _by_code(db, row.code)
        if store is None:
            store = Store(code=row.code, aliases=[])
            db.add(store)
            created += 1
        else:
            updated += 1
            if store.name and _plain(store.name) != _plain(row.name):
                store.aliases = _merge_aliases(store, [store.name], row.code, row.name)
        store.name, store.official, store.cnpj = row.name, True, row.cnpj
        store.company, store.group_name, store.details = row.company or None, row.group or None, row.details()
        store.location = row.address or store.location
        store.region = row.uf or store.region
        store.active = True
    db.flush()
    return created, updated


def has_official(db: Session) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Store).where(Store.official.is_(True))))


def legacy_stores(db: Session) -> list[Store]:
    """Lojas criadas antes da lista oficial (só existem como pendência quando a lista já foi carregada)."""
    if not has_official(db):
        return []
    rows = db.scalars(select(Store).where((Store.official.is_(False)) | (Store.official.is_(None))))
    return sorted(rows, key=lambda s: s.code)


def official_stores(db: Session) -> list[Store]:
    return sorted(db.scalars(select(Store).where(Store.official.is_(True))), key=store_sort_key)


def suggest(legacy: Store, officials: list[Store]) -> Store | None:
    """Palpite de qual loja oficial é a antiga: mesmo número no código (CD300 -> 300) ou nome/apelido parecido."""
    digits = re.sub(r"\D", "", legacy.code)
    if digits:
        hit = [o for o in officials if o.code == digits.lstrip("0") or o.code == digits]
        if len(hit) == 1:
            return hit[0]
    names = {_plain(x) for x in [legacy.code, legacy.name or "", *(legacy.aliases or [])] if x}
    best = [o for o in officials if _plain(o.name or "") and any(_plain(o.name) == n or _plain(o.name) in n for n in names)]
    best.sort(key=lambda o: -len(o.name or ""))
    return best[0] if best else None


def _merge_aliases(target: Store, extra: list[str], *exclude: str) -> list[str]:
    skip = {_plain(x) for x in (target.code, target.name or "", *exclude) if x}
    out, seen = [], set()
    for a in [*(target.aliases or []), *extra]:
        a = (a or "").strip()[:60]
        if a and _plain(a) not in skip and _plain(a) not in seen:
            seen.add(_plain(a))
            out.append(a)
    return out[:20]


@dataclass
class LinkSummary:
    units: int
    bills: int
    records: int


def link_summary(legacy: Store, db: Session) -> LinkSummary:
    ids = [u.id for u in legacy.units]
    bills = db.scalar(select(func.count()).select_from(EnergyBill).where(EnergyBill.unit_id.in_(ids))) if ids else 0
    records = db.scalar(select(func.count()).select_from(ManualRecord).where(ManualRecord.store_id == legacy.id)) or 0
    return LinkSummary(units=len(legacy.units), bills=bills, records=records)


class LinkError(ValueError):
    pass


def link(db: Session, legacy: Store, official: Store) -> LinkSummary:
    """Junta a loja antiga na oficial: pontos de energia (com as contas), lançamentos manuais, importações e apelidos."""
    if legacy.id == official.id:
        raise LinkError("Escolha uma loja diferente.")
    if legacy.is_official:
        raise LinkError(f"{legacy.label} já é uma loja oficial.")
    if not official.is_official:
        raise LinkError(f"{official.label} não está na lista oficial.")
    summary = link_summary(legacy, db)
    for unit in list(legacy.units):
        unit.store = official                                     # move pela relação (o cascade não apaga o ponto)
    db.execute(update(ManualRecord).where(ManualRecord.store_id == legacy.id).values(store_id=official.id))
    db.execute(update(Import).where(Import.store_hint_id == legacy.id).values(store_hint_id=official.id))
    official.aliases = _merge_aliases(official, [*(legacy.aliases or []), legacy.code, legacy.name or ""])
    if not official.region and legacy.region:
        official.region = legacy.region
    if legacy.notes:
        official.notes = "\n".join(x for x in (official.notes, legacy.notes) if x)
    db.flush()
    db.refresh(legacy)
    if legacy.units:                                              # nunca apaga loja com ponto de energia
        raise LinkError("Não foi possível mover todos os pontos de energia.")
    db.delete(legacy)
    db.flush()
    return summary
