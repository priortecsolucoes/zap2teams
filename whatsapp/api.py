# Compatível com Uazapi v2. Se usar outra versão, ajuste os endpoints abaixo.
import httpx
from config import settings


def _headers() -> dict:
    return {"token": settings.uazapi_token, "Content-Type": "application/json"}


async def send_text(group_id: str, text: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.uazapi_base}/message/sendText/{settings.uazapi_instance}",
            headers=_headers(),
            json={"number": group_id, "text": text},
        )
        resp.raise_for_status()
        return resp.json()


async def send_reply(group_id: str, quoted_msg_id: str, text: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{settings.uazapi_base}/message/sendText/{settings.uazapi_instance}",
            headers=_headers(),
            json={
                "number": group_id,
                "text": text,
                "quoted": {
                    "key": {
                        "id": quoted_msg_id,
                        "remoteJid": group_id,
                        "fromMe": False,
                    }
                },
            },
        )
        resp.raise_for_status()
        return resp.json()
