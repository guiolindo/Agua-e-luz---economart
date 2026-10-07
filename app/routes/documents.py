from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, User
from app.security import current_user

router = APIRouter()


@router.get("/documents/{doc_id}")
def document(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    return Response(doc.data, media_type=doc.content_type,
                    headers={"Content-Disposition": f'inline; filename="{doc.filename}"',
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})
