import asyncio
import time

import httpx

from config import settings

_token_cache: dict = {"token": None, "expiry": 0.0}
_delegated_cache: dict = {"token": None, "expiry": 0.0}
_token_lock = asyncio.Lock()
_delegated_lock = asyncio.Lock()


async def _get_access_token() -> str:
    async with _token_lock:
        if _token_cache["token"] and time.time() < _token_cache["expiry"] - 60:
            return _token_cache["token"]

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://login.microsoftonline.com/{settings.teams_tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.teams_client_id,
                    "client_secret": settings.teams_client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

        _token_cache["token"] = data["access_token"]
        _token_cache["expiry"] = time.time() + data["expires_in"]
        return _token_cache["token"]


async def _get_delegated_token() -> str:
    async with _delegated_lock:
        if _delegated_cache["token"] and time.time() < _delegated_cache["expiry"] - 60:
            return _delegated_cache["token"]

        from storage import db
        refresh_token = db.get_refresh_token()
        if not refresh_token:
            raise Exception("Sem refresh token. Acesse /auth/setup para autenticar.")

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://login.microsoftonline.com/{settings.teams_tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.teams_client_id,
                    "refresh_token": refresh_token,
                    "scope": "offline_access ChatMessage.Send Files.ReadWrite",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

        if "refresh_token" in data:
            db.save_refresh_token(data["refresh_token"])

        _delegated_cache["token"] = data["access_token"]
        _delegated_cache["expiry"] = time.time() + data["expires_in"]
        return _delegated_cache["token"]


async def graph_request(method: str, path: str, body: dict | None = None) -> dict:
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(
            method,
            f"https://graph.microsoft.com/v1.0{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        if not resp.is_success:
            raise Exception(f"Graph API {resp.status_code} em {method} {path}: {resp.text}")
        return resp.json() if resp.content else {}


async def download_graph_binary(path: str) -> tuple[bytes, str]:
    """Baixa conteúdo binário da Graph API (ex: hostedContents de imagens)."""
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(
            f"https://graph.microsoft.com/v1.0{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if not resp.is_success:
            raise Exception(f"Graph binary {resp.status_code}: {resp.text[:200]}")
        return resp.content, resp.headers.get("content-type", "image/jpeg")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def post_image_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    image_bytes: bytes,
    content_type: str,
    wa_chat_id: str,
    wa_message_id: str,
    caption: str = "",
) -> None:
    import base64
    token = await _get_delegated_token()
    safe_sender = sender_name.replace("|", "").replace("[", "").replace("]", "")
    ref = f"[wa:{wa_chat_id}|{wa_message_id}|{safe_sender}]"
    caption_html = f"<p>{_esc(caption)}</p>" if caption else ""
    content = (
        f"<p>📱 <strong>{_esc(sender_name)}</strong> &nbsp;·&nbsp; {_esc(chat_name)}</p>"
        f'<p><img src="../hostedContents/1/$value" style="max-width:600px"></p>'
        f"{caption_html}"
        f"<p><em><span style='font-size:11px;color:gray'>{ref}</span></em></p>"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "body": {"contentType": "html", "content": content},
                "hostedContents": [
                    {
                        "@microsoft.graph.temporaryId": "1",
                        "contentBytes": base64.b64encode(image_bytes).decode(),
                        "contentType": content_type,
                    }
                ],
            },
        )
        if not resp.is_success:
            raise Exception(f"Chat image post {resp.status_code}: {resp.text}")


async def post_image_only(chat_id: str, image_bytes: bytes, content_type: str) -> None:
    import base64
    token = await _get_delegated_token()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "body": {
                    "contentType": "html",
                    "content": '<p><img src="../hostedContents/1/$value" style="max-width:600px"></p>',
                },
                "hostedContents": [
                    {
                        "@microsoft.graph.temporaryId": "1",
                        "contentBytes": base64.b64encode(image_bytes).decode(),
                        "contentType": content_type,
                    }
                ],
            },
        )
        if not resp.is_success:
            raise Exception(f"Chat image post {resp.status_code}: {resp.text}")


async def post_audio_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    audio_bytes: bytes,
    mimetype: str,
    wa_chat_id: str,
    wa_message_id: str,
    caption: str = "",
) -> None:
    """Envia áudio como arquivo anexo no Teams via OneDrive do usuário autenticado."""
    import re
    token = await _get_delegated_token()
    safe_sender = sender_name.replace("|", "").replace("[", "").replace("]", "")
    ref = f"[wa:{wa_chat_id}|{wa_message_id}|{safe_sender}]"

    ext_map = {
        "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/wav": "wav",
        "audio/m4a": "m4a", "audio/aac": "aac", "audio/mp4": "m4a",
    }
    ext = ext_map.get(mimetype.split(";")[0].strip(), "ogg")
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", wa_message_id)[:20]
    filename = f"audio_{safe_id}.{ext}"

    async with httpx.AsyncClient(timeout=60) as client:
        # 1. Faz upload para a pasta "WhatsApp-Audios" no OneDrive do usuário
        resp = await client.put(
            f"https://graph.microsoft.com/v1.0/me/drive/root:/WhatsApp-Audios/{filename}:/content",
            headers={"Authorization": f"Bearer {token}", "Content-Type": mimetype or "audio/ogg"},
            content=audio_bytes,
        )
        if not resp.is_success:
            raise Exception(f"audio upload {resp.status_code}: {resp.text[:300]}")
        item = resp.json()
        drive_id = item["parentReference"]["driveId"]
        item_id = item["id"]
        web_url = item.get("webUrl", "")
        print(f"[Teams] Áudio carregado no OneDrive: {filename}")

        # 2. Cria link de compartilhamento para toda a organização poder acessar
        link_resp = await client.post(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/createLink",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"type": "view", "scope": "organization"},
        )
        share_url = web_url
        if link_resp.is_success:
            share_url = link_resp.json().get("link", {}).get("webUrl", web_url)

        # 3. Posta mensagem no chat com o arquivo como anexo referenciado
        caption_html = f"<p>{_esc(caption)}</p>" if caption else ""
        content = (
            f"<p>📱 <strong>{_esc(sender_name)}</strong> &nbsp;·&nbsp; {_esc(chat_name)}</p>"
            f"<p>🎵 Áudio WhatsApp</p>"
            f"{caption_html}"
            f'<attachment id="{item_id}"></attachment>'
            f"<p><em><span style='font-size:11px;color:gray'>{ref}</span></em></p>"
        )
        resp = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "body": {"contentType": "html", "content": content},
                "attachments": [{
                    "id": item_id,
                    "contentType": "reference",
                    "contentUrl": share_url,
                    "name": f"Áudio WhatsApp.{ext}",
                }],
            },
        )
        if not resp.is_success:
            raise Exception(f"audio message post {resp.status_code}: {resp.text[:300]}")


async def post_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    text: str,
    wa_chat_id: str,
    wa_message_id: str,
) -> None:
    token = await _get_delegated_token()
    safe_sender = sender_name.replace("|", "").replace("[", "").replace("]", "")
    ref = f"[wa:{wa_chat_id}|{wa_message_id}|{safe_sender}]"
    content = (
        f"<p>📱 <strong>{_esc(sender_name)}</strong> &nbsp;·&nbsp; {_esc(chat_name)}</p>"
        f"<p>{_esc(text)}</p>"
        f"<p><em><span style='font-size:11px;color:gray'>{ref}</span></em></p>"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"body": {"contentType": "html", "content": content}},
        )
        if not resp.is_success:
            raise Exception(f"Chat post {resp.status_code}: {resp.text}")


async def post_reply_to_chat(
    chat_id: str,
    parent_message_id: str,
    sender_name: str,
    text: str,
) -> None:
    token = await _get_delegated_token()
    content = f"<p>📱 <strong>{_esc(sender_name)}:</strong> {_esc(text)}</p>"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}"
            f"/messages/{parent_message_id}/replies",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"body": {"contentType": "html", "content": content}},
        )
        if not resp.is_success:
            raise Exception(f"Chat reply {resp.status_code}: {resp.text}")


async def get_chat_message(chat_id: str, message_id: str) -> dict:
    return await graph_request(
        "GET",
        f"/chats/{chat_id}/messages/{message_id}",
    )


async def get_chat_reply(chat_id: str, parent_message_id: str, reply_id: str) -> dict:
    return await graph_request(
        "GET",
        f"/chats/{chat_id}/messages/{parent_message_id}/replies/{reply_id}",
    )


async def create_subscription(notification_url: str) -> dict:
    from datetime import datetime, timezone, timedelta

    expiration = (datetime.now(timezone.utc) + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return await graph_request(
        "POST",
        "/subscriptions",
        {
            "changeType": "created",
            "notificationUrl": notification_url,
            "lifecycleNotificationUrl": notification_url,
            "resource": "chats/getAllMessages",
            "expirationDateTime": expiration,
            "clientState": settings.teams_notification_secret,
        },
    )


async def list_subscriptions() -> list[dict]:
    result = await graph_request("GET", "/subscriptions")
    return result.get("value", [])


async def renew_subscription(subscription_id: str) -> dict:
    from datetime import datetime, timezone, timedelta

    expiration = (datetime.now(timezone.utc) + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return await graph_request(
        "PATCH",
        f"/subscriptions/{subscription_id}",
        {"expirationDateTime": expiration},
    )


async def update_subscription_url(subscription_id: str, notification_url: str) -> dict:
    from datetime import datetime, timezone, timedelta

    expiration = (datetime.now(timezone.utc) + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return await graph_request(
        "PATCH",
        f"/subscriptions/{subscription_id}",
        {
            "expirationDateTime": expiration,
            "notificationUrl": notification_url,
            "lifecycleNotificationUrl": notification_url,
        },
    )


async def delete_subscription(subscription_id: str) -> None:
    try:
        await graph_request("DELETE", f"/subscriptions/{subscription_id}")
    except Exception:
        pass
