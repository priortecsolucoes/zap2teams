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


async def send_image(
    chat_id: str, image_bytes: bytes, mimetype: str, caption: str = "", reply_id: str = ""
) -> dict:
    """Envia imagem via Uazapi /send/media com type=image e arquivo em base64.
    Com reply_id, a imagem sai citando essa mensagem (se a uazapi recusar, envia sem citar)."""
    import base64 as _b64
    payload = {
        "number": chat_id,
        "type": "image",
        "file": _b64.b64encode(image_bytes).decode(),
        "text": caption or "",
    }
    if reply_id:
        payload["replyid"] = reply_id
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{settings.uazapi_base}/send/media", headers=_headers(), json=payload)
        if not resp.is_success and reply_id:
            print(f"[WA API] Citação na imagem recusada ({resp.status_code}), enviando sem citar")
            payload.pop("replyid")
            resp = await client.post(f"{settings.uazapi_base}/send/media", headers=_headers(), json=payload)
        if not resp.is_success:
            raise Exception(f"send/media {resp.status_code}: {resp.text[:200]}")
        print("[WA API] send_image OK")
        return resp.json() if resp.content else {}


async def send_reply(chat_id: str, quoted_msg_id: str, text: str) -> dict:
    """Envia texto citando uma mensagem (citação nativa do WhatsApp).

    A uazapi só consegue citar mensagens que ainda estão no histórico local dela (até ~7 dias).
    Se ela recusar a citação (resposta HTTP de erro), reenvia sem citar para não perder a
    mensagem. Em timeout não reenvia: a primeira tentativa pode ter saído (evita duplicar)."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.uazapi_base}/send/text",
            headers=_headers(),
            json={"number": chat_id, "text": text, "replyid": quoted_msg_id},
        )
    if resp.is_success:
        return resp.json() if resp.content else {}
    print(f"[WA API] Citação recusada ({resp.status_code}: {resp.text[:200]}), enviando sem citar")
    return await send_text(chat_id, text)


def get_message_id(send_response: dict) -> str:
    """Extrai o ID do WhatsApp (messageid) da resposta de um envio da uazapi."""
    if not isinstance(send_response, dict):
        return ""
    nested = send_response.get("message")
    return (
        send_response.get("messageid")
        or (nested.get("messageid") if isinstance(nested, dict) else "")
        or ""
    )


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
