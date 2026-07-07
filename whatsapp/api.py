# Compatível com Uazapi v2. Se usar outra versão, ajuste os endpoints abaixo.
import asyncio
import httpx
from config import settings

# Armazenamento temporário de imagens para servir ao Uazapi via URL
_temp_images: dict[str, tuple[bytes, str]] = {}


def store_temp_image(image_bytes: bytes, mimetype: str) -> str:
    import uuid
    token = str(uuid.uuid4()).replace("-", "")
    _temp_images[token] = (image_bytes, mimetype)
    return token


def pop_temp_image(token: str) -> tuple[bytes, str] | None:
    return _temp_images.pop(token, None)


async def _cleanup_temp_image(token: str) -> None:
    await asyncio.sleep(60)
    _temp_images.pop(token, None)


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
    """Envia imagem via Uazapi usando URL temporária hospedada no próprio servidor."""
    token = store_temp_image(image_bytes, mimetype)
    image_url = f"{settings.webhook_base}/temp-media/{token}"
    asyncio.create_task(_cleanup_temp_image(token))
    errors = []

    async with httpx.AsyncClient(timeout=30) as client:
        # Tentativa 1: campo "url" (formato mais comum no Uazapi v2)
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=_headers(),
                json={"number": chat_id, "url": image_url, "mimetype": mimetype, "caption": caption or ""},
            )
            if resp.is_success:
                print(f"[WA API] send_image OK (url field) → {image_url}")
                return resp.json() if resp.content else {}
            errors.append(f"url: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"url: {e}")

        # Tentativa 2: campo "mediaUrl"
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=_headers(),
                json={"number": chat_id, "mediaUrl": image_url, "mimetype": mimetype, "caption": caption or ""},
            )
            if resp.is_success:
                print(f"[WA API] send_image OK (mediaUrl field)")
                return resp.json() if resp.content else {}
            errors.append(f"mediaUrl: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"mediaUrl: {e}")

        # Tentativa 3: campo "file" com a URL (fallback)
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=_headers(),
                json={"number": chat_id, "file": image_url, "text": caption or "", "mimetype": mimetype},
            )
            if resp.is_success:
                print(f"[WA API] send_image OK (file=url)")
                return resp.json() if resp.content else {}
            errors.append(f"file=url: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"file=url: {e}")

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
