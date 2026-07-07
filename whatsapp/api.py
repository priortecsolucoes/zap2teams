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
    import base64 as _b64
    ext = mimetype.split("/")[-1].split("+")[0] if "/" in mimetype else "jpg"
    filename = f"image.{ext}"
    errors = []

    async with httpx.AsyncClient(timeout=30) as client:
        # Tentativa 1: multipart construído manualmente (controle total do encoding)
        try:
            boundary = "----FormBoundary7MA4YWxkTrZu0gW"
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="number"\r\n\r\n'
                f"{chat_id}\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="caption"\r\n\r\n'
                f"{caption or ''}\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: {mimetype}\r\n\r\n"
            ).encode("utf-8") + image_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers={
                    "token": settings.uazapi_token,
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                },
                content=body,
            )
            if resp.is_success:
                print("[WA API] send_image OK (multipart manual)")
                return resp.json() if resp.content else {}
            errors.append(f"manual-mp: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"manual-mp: {e}")

        # Tentativa 2: JSON com base64 + caption + filename
        try:
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=_headers(),
                json={
                    "number": chat_id,
                    "caption": caption or "",
                    "text": caption or "",
                    "file": _b64.b64encode(image_bytes).decode(),
                    "mimetype": mimetype,
                    "filename": filename,
                },
            )
            if resp.is_success:
                print("[WA API] send_image OK (JSON file+caption+filename)")
                return resp.json() if resp.content else {}
            errors.append(f"json+caption: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"json+caption: {e}")

        # Tentativa 3: JSON com base64 como data URL
        try:
            data_url = f"data:{mimetype};base64,{_b64.b64encode(image_bytes).decode()}"
            resp = await client.post(
                f"{settings.uazapi_base}/send/media",
                headers=_headers(),
                json={
                    "number": chat_id,
                    "text": caption or "",
                    "file": data_url,
                    "mimetype": mimetype,
                },
            )
            if resp.is_success:
                print("[WA API] send_image OK (JSON data URL)")
                return resp.json() if resp.content else {}
            errors.append(f"json+dataurl: {resp.status_code} {resp.text[:120]}")
        except Exception as e:
            errors.append(f"json+dataurl: {e}")

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
