"""Desbloqueia um usuário travado por tentativas erradas (use quando é o único administrador e ele mesmo ficou bloqueado).

    python -m scripts.unlock_user <usuario>

Não mexe na senha nem no 2FA, só zera o bloqueio e o contador de tentativas. Precisa de acesso ao servidor/banco
(mesmo DATABASE_URL do app), por isso não é uma brecha remota.
"""
import sys

from sqlalchemy import select

from app import database
from app.models import User
from app.services import audit_service, auth_service


def main(username: str) -> int:
    with database.SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            print(f"Usuário '{username}' não encontrado.")
            return 1
        if auth_service.is_blocked(user) is None and not user.failed_attempts:
            print(f"'{username}' não está bloqueado.")
            return 0
        auth_service.unlock(user)
        audit_service.log(db, None, "account_unlocked", "user", user.id, {"by": "script"})
        db.commit()
        print(f"'{username}' desbloqueado.")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
