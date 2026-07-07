# Compatível com Uazapi v2. Se usar outra versão, ajuste os endpoints abaixo.
import httpx
from config import settings


def _headers() -> dict:
    return {"token": settings.uazapi_token, "Content-Type": "application/json"}


async def send_text(chat_id: str, text: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.uazapi_base}/send/text",
            headers=_headers(),
            json={"number": chat_id, "text": text},
        )
        resp.raise_for_status()
        return resp.json()


async def send_image(chat_id: str, image_bytes: bytes, mimetype: str, caption: str = "") -> dict:
    """Envia imagem via Uazapi: tenta múltiplos formatos até um funcionar."""
    ext = mimetype.split("/")[-1].split("+")[0] if "/" in mimetype else "jpg"
    filename = f"image.{ext}"
    headers = {"token": settings.uazapi_token}
    errors = []
    # Formato sem sufixo @domain (alguns endpoints esperam só o número)
    phone = chat_id.split("@")[0] if "@" in chat_id else chat_id

    async with httpx.AsyncClient(timeout=30) as client:
        # Tentativa 1: data= dict (campos de formulário) + files= separados (padrão httpx multipart)
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=headers,
                data={"number": chat_id, "caption": caption or ""},
                files={"file": (filename, image_bytes, mimetype)},
            )
            if resp.is_success:
                print("[WA API] send_image OK (data dict + files)")
                return resp.json() if resp.content else {}
            errors.append(f"data+files: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"data+files: {e}")

        # Tentativa 2: número sem @domain via data=
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=headers,
                data={"number": phone, "caption": caption or ""},
                files={"file": (filename, image_bytes, mimetype)},
            )
            if resp.is_success:
                print("[WA API] send_image OK (phone sem @domain)")
                return resp.json() if resp.content else {}
            errors.append(f"phone: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"phone: {e}")

        # Tentativa 3: campo number dentro de lista de tuplas (multipart puro)
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=headers,
                files=[
                    ("number",  (None, chat_id)),
                    ("caption", (None, caption or "")),
                    ("file",    (filename, image_bytes, mimetype)),
                ],
            )
            if resp.is_success:
                print("[WA API] send_image OK (number em tuples)")
                return resp.json() if resp.content else {}
            errors.append(f"tuples+number: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"tuples+number: {e}")

        # Tentativa 4: número sem @domain em lista de tuplas
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=headers,
                files=[
                    ("number",  (None, phone)),
                    ("caption", (None, caption or "")),
                    ("file",    (filename, image_bytes, mimetype)),
                ],
            )
            if resp.is_success:
                print("[WA API] send_image OK (phone sem @domain em tuples)")
                return resp.json() if resp.content else {}
            errors.append(f"tuples+phone: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"tuples+phone: {e}")

    raise Exception(f"send_image falhou: {errors}")


async def send_reply(chat_id: str, quoted_msg_id: str, text: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.uazapi_base}/send/text",
            headers=_headers(),
            json={"number": chat_id, "text": text, "quoted": quoted_msg_id},
        )
        resp.raise_for_status()
        return resp.json()


async def download_media(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def download_media_by_id(message_id: str, chat_id: str) -> bytes:
    """Baixa mídia via API do Uazapi usando o ID da mensagem (Uazapi descriptografa internamente)."""
    import base64
    errors = []
    async with httpx.AsyncClient(timeout=30) as client:
        # Tenta GET com query params (mais comum no Uazapi v2)
        for path in ("/message/download-media", "/getMedia", "/message/download"):
            try:
                resp = await client.get(
                    f"{settings.uazapi_base}{path}",
                    headers=_headers(),
                    params={"messageId": message_id, "chatId": chat_id},
                )
                if resp.is_success:
                    ct = resp.headers.get("content-type", "")
                    if "json" in ct:
                        data = resp.json()
                        b64 = data.get("data") or data.get("base64") or data.get("media") or ""
                        return base64.b64decode(b64)
                    return resp.content
                errors.append(f"GET {path}: {resp.status_code}")
            except Exception as e:
                errors.append(f"GET {path}: {e}")
    raise Exception(f"Todos os endpoints falharam: {errors}")
