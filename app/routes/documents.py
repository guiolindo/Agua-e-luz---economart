from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, User
from app.security import current_user
from app.services import pdf_pages
from app.services.crypto_service import CryptoError

router = APIRouter()


@router.get("/documents/{doc_id}")
def document(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    if doc.data is None:
        raise HTTPException(410, "O arquivo original expirou e foi removido (os arquivos são guardados por 6 meses). "
                                 "Os dados lidos da conta continuam salvos.")
    try:
        content = doc.plain()
    except CryptoError:
        raise HTTPException(500, "Não foi possível abrir o documento (erro de chave de criptografia).")
    headers = {"Content-Disposition": f'inline; filename="{doc.filename}"', "X-Content-Type-Options": "nosniff",
               "Cache-Control": "no-store"}
    if doc.content_type != "application/pdf":  # imagem: nada de script/rede mesmo que o conteúdo seja malicioso
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; sandbox"
    return Response(content, media_type=doc.content_type, headers=headers)


@router.get("/documents/{doc_id}/pages/{number}.png")
def document_page(doc_id: int, number: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Página `number` de um PDF original como PNG (usada na impressão da conta)."""
    doc = db.get(Document, doc_id)
    if not doc or doc.content_type != "application/pdf":
        raise HTTPException(404, "Página não encontrada.")
    if doc.data is None:
        raise HTTPException(410, "O arquivo original expirou e foi removido.")
    try:
        content = doc.plain()
    except CryptoError:
        raise HTTPException(500, "Não foi possível abrir o documento (erro de chave de criptografia).")
    png = pdf_pages.render_page(content, number)
    if png is None:
        raise HTTPException(404, "Página não encontrada.")
    return Response(png, media_type="image/png", headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; sandbox"})
