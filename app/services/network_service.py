"""Rede da empresa pelo IP do link de internet. Só informativo (auditoria e Painel admin); nada é bloqueado.

Os IPs vêm do cadastro feito pelo administrador (tela "Rede da empresa") e, opcionalmente, da variável
COMPANY_NETWORKS. Cada evento da auditoria grava, no momento em que acontece, se veio da rede da empresa: se o IP do
link mudar depois, o histórico continua certo. Quando a operadora troca o IP, o novo aparece em "IPs frequentes não
cadastrados" e o administrador cadastra com um clique. Dois links de internet são normais: cadastre os dois.
"""
from __future__ import annotations

import ipaddress
import time
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings

_cache = {"at": 0.0, "nets": ()}
TTL = 60


def reset() -> None:
    _cache["at"] = 0.0


def parse(value: str):
    """'187.32.111.41' ou '186.248.0.0/16' -> rede; None se inválido."""
    try:
        return ipaddress.ip_network((value or "").strip(), strict=False)
    except ValueError:
        return None


def networks() -> tuple:
    if time.monotonic() - _cache["at"] < TTL:
        return _cache["nets"]
    nets = [n for n in (parse(p) for p in get_settings().company_networks.split(",")) if n]
    try:
        from app.database import SessionLocal
        from app.models import CompanyNetwork

        with SessionLocal() as db:
            nets += [n for n in (parse(c) for c in db.scalars(select(CompanyNetwork.cidr))) if n]
    except Exception:  # noqa: BLE001 — banco fora do ar: fica só com a variável
        pass
    _cache.update(at=time.monotonic(), nets=tuple(dict.fromkeys(nets)))
    return _cache["nets"]


def configured() -> bool:
    return bool(networks())


def is_company_ip(ip: str | None) -> bool:
    nets = networks()
    if not ip or not nets:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)


def where(ip: str | None) -> str | None:
    """'empresa' / 'fora' para gravar no evento; None se nenhuma rede foi cadastrada (não afirma nada)."""
    if not ip or not configured():
        return None
    return "empresa" if is_company_ip(ip) else "fora"


def label(rede: str | None) -> tuple[str, str] | None:
    return {"empresa": ("Na empresa", "ok"), "fora": ("Fora da empresa", "warn")}.get(rede or "")


def frequent_unknown(db: Session, days: int = 7, limit: int = 8) -> list[dict]:
    """IPs de login dos últimos dias que não estão cadastrados (ex.: a operadora trocou o IP da empresa)."""
    from app.models import AuditLog
    from app.models.mixins import utcnow

    since = utcnow() - timedelta(days=days)
    hits, people, last = Counter(), defaultdict(set), {}
    for a in db.scalars(select(AuditLog).where(AuditLog.action.in_(("login", "login_2fa")), AuditLog.at >= since)):
        ip = (a.details or {}).get("ip")
        if not ip or str(ip).startswith("h:") or is_company_ip(ip):
            continue
        hits[ip] += 1
        people[ip].add(a.user_id)
        last[ip] = max(last.get(ip, a.at), a.at)
    return [{"ip": ip, "logins": n, "people": len(people[ip]), "last": last[ip]} for ip, n in hits.most_common(limit)]
