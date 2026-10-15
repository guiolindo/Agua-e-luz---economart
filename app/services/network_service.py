"""Rede da empresa pelo IP do link de internet (COMPANY_NETWORKS). Só informativo (auditoria e Painel admin).

Não pede nada ao usuário: o servidor já vê o IP em todo acesso. Dois links de internet são normais (cada site pode ver
a empresa saindo por um deles): cadastre os dois. Só funciona com IP fixo (o link Algar é fixo).
"""
import ipaddress
from functools import lru_cache

from app.config import get_settings


@lru_cache(maxsize=8)
def _networks(raw: str):
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return tuple(nets)


def is_company_ip(ip: str | None) -> bool:
    nets = _networks(get_settings().company_networks)
    if not ip or not nets:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)


def label(ip: str | None) -> tuple[str, str]:
    return ("Rede da empresa", "ok") if is_company_ip(ip) else ("Fora da rede da empresa", "warn")
