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
    """Envia imagem via Uazapi usando multipart/form-data no endpoint /send/media."""
    ext = mimetype.split("/")[-1].split("+")[0] if "/" in mimetype else "jpg"
    filename = f"image.{ext}"
    # Sem Content-Type no header: httpx seta multipart/form-data automaticamente
    headers = {"token": settings.uazapi_token}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.uazapi_base}/send/media",
            headers=headers,
            files={"file": (filename, image_bytes, mimetype)},
            data={"number": chat_id, "caption": caption},
        )
        if resp.is_success:
            print(f"[WA API] send_image OK via /send/media")
            return resp.json() if resp.content else {}
        raise Exception(f"POST /send/media: {resp.status_code} {resp.text[:200]}")


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
