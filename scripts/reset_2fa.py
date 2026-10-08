"""Remove o 2FA de um administrador (use quando o único admin perdeu o celular E os códigos de recuperação).

    python -m scripts.reset_2fa <usuario>

Precisa de acesso ao servidor/banco (mesmo DATABASE_URL do app), por isso não é uma brecha remota.
"""
import sys

from sqlalchemy import select

from app import database
from app.models import User
from app.services import audit_service, totp_service


def main(username: str) -> int:
    with database.SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            print(f"Usuário '{username}' não encontrado.")
            return 1
        totp_service.disable(user)
        audit_service.log(db, None, "2fa_reset", "user", user.id, {"by": "script"})
        db.commit()
        print(f"2FA de '{username}' removido; sessões encerradas. Configure de novo em /account/2fa.")
        return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
