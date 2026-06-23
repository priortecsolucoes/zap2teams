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
