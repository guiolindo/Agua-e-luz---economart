"""De onde a pessoa está acessando: IP de um dos links da empresa e/ou máquina que enxerga a intranet.

Só informativo (auditoria e Painel admin), nunca bloqueia: o teste da intranet roda no navegador da pessoa e o
resultado pode ser falseado; o IP depende de a empresa ter IP fixo (o link Algar tem). Dois links de internet são
normais: cada site pode ver a empresa saindo por um deles.
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


def label(details: dict | None) -> tuple[str, str]:
    """(texto, tom) para mostrar um registro "network_check"."""
    d = details or {}
    if d.get("intranet"):
        return "Máquina da empresa", "ok"
    if d.get("ip_empresa"):
        return "Rede da empresa", "ok"
    if d.get("intranet") is False and get_settings().intranet_probe_url:
        return "Fora da empresa", "warn"
    return "Fora da rede da empresa", "warn"
