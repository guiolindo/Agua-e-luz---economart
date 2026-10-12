from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Document, EnergyBill, User
from app.security import current_user
from app.web import render
from app.services import pdf_pages
from app.services.crypto_service import CryptoError

router = APIRouter()


def _content_disposition(filename: str) -> str:
    """Nome em ASCII para o `filename=` clássico (headers HTTP só aceitam Latin-1) e o nome de verdade, em UTF-8,
    no `filename*=` (RFC 6266) para o navegador preferir. Sem isso, um nome com acento quebra o download (500)."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    from urllib.parse import quote

    return f'inline; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


def _visible(doc_id: int, user: User, db: Session) -> bool:
    """Documento de conta já confirmada: qualquer perfil logado vê (ex.: imprimir a conta com a foto).
    Documento ainda em revisão (sem conta confirmada): só quem lança contas, e só enquanto durar a conferência."""
    if db.scalar(select(EnergyBill.id).where(EnergyBill.document_id == doc_id)) is not None:
        return True
    return bool(user.can_write)


@router.get("/documents/{doc_id}")
def document(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    if not _visible(doc_id, user, db):
        raise HTTPException(403, "Documento não disponível para o seu perfil.")
    if doc.data is None:
        raise HTTPException(410, "O arquivo original expirou e foi removido (os arquivos são guardados por 6 meses). "
                                 "Os dados lidos da conta continuam salvos.")
    try:
        content = doc.plain()
    except CryptoError:
        raise HTTPException(500, "Não foi possível abrir o documento (erro de chave de criptografia).")
    headers = {"Content-Disposition": _content_disposition(doc.filename), "X-Content-Type-Options": "nosniff",
               "Cache-Control": "no-store"}
    if doc.content_type != "application/pdf":  # imagem: nada de script/rede mesmo que o conteúdo seja malicioso
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self' data:; sandbox"
    return Response(content, media_type=doc.content_type, headers=headers)


@router.get("/impressao/original/{doc_id}")
def print_original(request: Request, doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A conta original SOZINHA, num trabalho de impressão de uma orientação só (a da 1ª página), pronta para imprimir:
    foto = a própria foto; PDF = as páginas em ~190 dpi. Cada página mantém a proporção (nunca estica). Serve de 2º passo
    do "Imprimir tudo": impressoras e drivers aplicam UMA orientação por trabalho, então folha deitada e conta em pé
    vão em trabalhos separados, um logo depois do outro."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    if not _visible(doc_id, user, db):
        raise HTTPException(403, "Documento não disponível para o seu perfil.")
    if doc.data is None:
        raise HTTPException(410, "O arquivo original expirou e foi removido.")
    try:
        raw = doc.plain()
    except CryptoError:
        raise HTTPException(500, "Não foi possível abrir o documento (erro de chave de criptografia).")
    if doc.content_type == "application/pdf":
        sizes = pdf_pages.page_sizes(raw)
        if not sizes:
            return RedirectResponse(f"/documents/{doc_id}", status_code=303)       # PDF ilegível: o leitor do navegador tenta
        land = sizes[0][0] > sizes[0][1]
        pages = [f"/documents/{doc_id}/pages/{n}.png?hq=1" for n in range(1, len(sizes) + 1)]
    else:
        size = pdf_pages.image_display_size(raw)
        land = bool(size and size[0] > size[1])
        pages = [f"/documents/{doc_id}"]
    return render(request, "documents/print_original.html", user=user, doc=doc, land=land, pages=pages)


@router.get("/documents/{doc_id}/pages/{number}.png")
def document_page(doc_id: int, number: int, hq: int = 0, rot: int = 0, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Página `number` do original como imagem (impressão da conta). PDF: a página; foto: só a página 1.
    `rot=1` gira 90° (página em pé numa impressão toda deitada)."""
    doc = db.get(Document, doc_id)
    is_pdf = bool(doc) and doc.content_type == "application/pdf"
    if not doc or (not is_pdf and number != 1):
        raise HTTPException(404, "Página não encontrada.")
    if not _visible(doc_id, user, db):
        raise HTTPException(403, "Documento não disponível para o seu perfil.")
    if doc.data is None:
        raise HTTPException(410, "O arquivo original expirou e foi removido.")
    try:
        content = doc.plain()
    except CryptoError:
        raise HTTPException(500, "Não foi possível abrir o documento (erro de chave de criptografia).")
    if is_pdf:
        img, mime = pdf_pages.render_page(content, number, pdf_pages.PRINT_SCALE if hq else pdf_pages.SCALE, rotate=bool(rot)), "image/png"
    else:
        img, mime = pdf_pages.render_photo(content, rotate=bool(rot)), "image/jpeg"
    if img is None:
        raise HTTPException(404, "Página não encontrada.")
    return Response(img, media_type=mime, headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; sandbox"})
