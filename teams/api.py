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


# ─────────────────────────────────────────────
# Postagem em chat + citação (reply/quote)
# ─────────────────────────────────────────────
# Uma citação é um dict {"teams_message_id": str | None, "sender": str, "preview": str}:
#  - com teams_message_id → tenta o cartão de citação nativo do Teams (attachment messageReference);
#  - sem ele, ou se o Graph recusar → bloco <blockquote> com remetente e trecho da mensagem citada.

_QUOTE_PREVIEW_MAX = 200


def _truncate(text: str, limit: int = _QUOTE_PREVIEW_MAX) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _quote_blockquote(quote: dict) -> str:
    sender = quote.get("sender") or ""
    head = f"<strong>{_esc(sender)}</strong><br>" if sender else ""
    return f"<blockquote>{head}{_esc(_truncate(quote.get('preview') or ''))}</blockquote>"


async def _quote_reference(chat_id: str, quote: dict) -> tuple[str, dict] | None:
    """Monta o attachment messageReference. Busca a mensagem citada no Graph para usar o
    remetente real (o Teams exige uma identidade válida); se não achar, retorna None."""
    import json
    msg_id = quote.get("teams_message_id")
    if not msg_id:
        return None
    try:
        quoted_msg = await get_chat_message(chat_id, msg_id)
    except Exception as e:
        print(f"[Teams] Mensagem citada {msg_id} não encontrada no Graph ({e})")
        return None
    user = dict(((quoted_msg.get("from") or {}).get("user")) or {})
    if not user.get("id"):
        return None
    # Mostra o nome de quem escreveu no WhatsApp, e não o da conta-ponte que postou no Teams.
    if quote.get("sender"):
        user["displayName"] = quote["sender"]
    user.setdefault("userIdentityType", "aadUser")
    attachment = {
        "id": msg_id,
        "contentType": "messageReference",
        "content": json.dumps({
            "messageId": msg_id,
            "messagePreview": _truncate(quote.get("preview") or ""),
            "messageSender": {"application": None, "device": None, "user": user},
        }),
    }
    return f'<attachment id="{msg_id}"></attachment>', attachment


async def _send_chat_message(
    chat_id: str,
    content: str,
    attachments: list[dict] | None = None,
    hosted_contents: list[dict] | None = None,
    timeout: int = 30,
) -> str:
    token = await _get_delegated_token()
    payload: dict = {"body": {"contentType": "html", "content": content}}
    if attachments:
        payload["attachments"] = attachments
    if hosted_contents:
        payload["hostedContents"] = hosted_contents
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
    if not resp.is_success:
        raise Exception(f"Chat post {resp.status_code}: {resp.text[:300]}")
    return (resp.json() if resp.content else {}).get("id", "")


async def _post_with_quote(
    chat_id: str,
    header_html: str,
    body_html: str,
    quote: dict | None = None,
    attachments: list[dict] | None = None,
    hosted_contents: list[dict] | None = None,
    timeout: int = 30,
) -> str:
    """Posta header + (citação) + body e retorna o ID da mensagem criada no Teams."""
    attachments = list(attachments or [])
    if quote:
        reference = await _quote_reference(chat_id, quote)
        if reference:
            ref_html, ref_attachment = reference
            try:
                return await _send_chat_message(
                    chat_id,
                    ref_html + header_html + body_html,
                    attachments + [ref_attachment],
                    hosted_contents,
                    timeout,
                )
            except Exception as e:
                print(f"[Teams] Citação nativa recusada ({e}), usando bloco de citação")
        header_html += _quote_blockquote(quote)
    return await _send_chat_message(chat_id, header_html + body_html, attachments, hosted_contents, timeout)


def _wa_header(sender_name: str, chat_name: str) -> str:
    return f"<p>📱 <strong>{_esc(sender_name)}</strong> &nbsp;·&nbsp; {_esc(chat_name)}</p>"


def _wa_ref(wa_chat_id: str, wa_message_id: str, sender_name: str) -> str:
    """Rodapé técnico com a origem no WhatsApp. Só aparece com TEAMS_SHOW_WA_REF=true: o Teams
    copia o texto da mensagem para o cartão de citação, então o rodapé poluiria as citações."""
    if not settings.teams_show_wa_ref:
        return ""
    safe_sender = sender_name.replace("|", "").replace("[", "").replace("]", "")
    ref = f"[wa:{wa_chat_id}|{wa_message_id}|{safe_sender}]"
    return f"<p><em><span style='font-size:11px;color:gray'>{ref}</span></em></p>"


async def post_image_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    image_bytes: bytes,
    content_type: str,
    wa_chat_id: str,
    wa_message_id: str,
    caption: str = "",
    quote: dict | None = None,
) -> str:
    import base64
    caption_html = f"<p>{_esc(caption)}</p>" if caption else ""
    body = (
        f'<p><img src="../hostedContents/1/$value" style="max-width:600px"></p>'
        f"{caption_html}"
        f"{_wa_ref(wa_chat_id, wa_message_id, sender_name)}"
    )
    return await _post_with_quote(
        chat_id,
        _wa_header(sender_name, chat_name),
        body,
        quote=quote,
        hosted_contents=[
            {
                "@microsoft.graph.temporaryId": "1",
                "contentBytes": base64.b64encode(image_bytes).decode(),
                "contentType": content_type,
            }
        ],
    )


async def post_image_only(chat_id: str, image_bytes: bytes, content_type: str) -> str:
    import base64
    return await _send_chat_message(
        chat_id,
        '<p><img src="../hostedContents/1/$value" style="max-width:600px"></p><p><span style="font-size:1px">📱</span></p>',
        hosted_contents=[
            {
                "@microsoft.graph.temporaryId": "1",
                "contentBytes": base64.b64encode(image_bytes).decode(),
                "contentType": content_type,
            }
        ],
    )


async def post_audio_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    audio_bytes: bytes,
    mimetype: str,
    wa_chat_id: str,
    wa_message_id: str,
    caption: str = "",
    quote: dict | None = None,
) -> str:
    """Envia áudio como arquivo anexo no Teams via OneDrive do usuário autenticado."""
    import re
    token = await _get_delegated_token()

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
    body = (
        f"<p>🎵 Áudio WhatsApp</p>"
        f"{caption_html}"
        f'<attachment id="{item_id}"></attachment>'
        f"{_wa_ref(wa_chat_id, wa_message_id, sender_name)}"
    )
    return await _post_with_quote(
        chat_id,
        _wa_header(sender_name, chat_name),
        body,
        quote=quote,
        attachments=[{
            "id": item_id,
            "contentType": "reference",
            "contentUrl": share_url,
            "name": f"Áudio WhatsApp.{ext}",
        }],
        timeout=60,
    )


async def post_document_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    doc_bytes: bytes,
    mimetype: str,
    filename: str,
    wa_chat_id: str,
    wa_message_id: str,
    caption: str = "",
    quote: dict | None = None,
) -> str:
    """Envia documento como arquivo anexo no Teams via OneDrive do usuário autenticado."""
    import re
    token = await _get_delegated_token()

    safe_name = re.sub(r"[^\w\s\-\.]", "_", filename).strip() or "documento"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.put(
            f"https://graph.microsoft.com/v1.0/me/drive/root:/WhatsApp-Docs/{safe_name}:/content",
            headers={"Authorization": f"Bearer {token}", "Content-Type": mimetype or "application/octet-stream"},
            content=doc_bytes,
        )
        if not resp.is_success:
            raise Exception(f"doc upload {resp.status_code}: {resp.text[:300]}")
        item = resp.json()
        drive_id = item["parentReference"]["driveId"]
        item_id = item["id"]
        web_url = item.get("webUrl", "")

        link_resp = await client.post(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/createLink",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"type": "view", "scope": "organization"},
        )
        share_url = web_url
        if link_resp.is_success:
            share_url = link_resp.json().get("link", {}).get("webUrl", web_url)

    caption_html = f"<p>{_esc(caption)}</p>" if caption else ""
    body = (
        f"<p>📄 {_esc(filename)}</p>"
        f"{caption_html}"
        f'<attachment id="{item_id}"></attachment>'
        f"{_wa_ref(wa_chat_id, wa_message_id, sender_name)}"
    )
    return await _post_with_quote(
        chat_id,
        _wa_header(sender_name, chat_name),
        body,
        quote=quote,
        attachments=[{
            "id": item_id,
            "contentType": "reference",
            "contentUrl": share_url,
            "name": filename,
        }],
        timeout=60,
    )


async def post_video_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    video_bytes: bytes,
    mimetype: str,
    wa_chat_id: str,
    wa_message_id: str,
    caption: str = "",
    quote: dict | None = None,
) -> str:
    """Envia vídeo como arquivo anexo no Teams via OneDrive do usuário autenticado."""
    import re
    token = await _get_delegated_token()

    ext_map = {
        "video/mp4": "mp4", "video/quicktime": "mov", "video/3gpp": "3gp",
        "video/webm": "webm", "video/x-matroska": "mkv",
    }
    ext = ext_map.get(mimetype.split(";")[0].strip(), "mp4")
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", wa_message_id)[:20]
    filename = f"video_{safe_id}.{ext}"

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.put(
            f"https://graph.microsoft.com/v1.0/me/drive/root:/WhatsApp-Videos/{filename}:/content",
            headers={"Authorization": f"Bearer {token}", "Content-Type": mimetype or "video/mp4"},
            content=video_bytes,
        )
        if not resp.is_success:
            raise Exception(f"video upload {resp.status_code}: {resp.text[:300]}")
        item = resp.json()
        drive_id = item["parentReference"]["driveId"]
        item_id = item["id"]
        web_url = item.get("webUrl", "")
        print(f"[Teams] Vídeo carregado no OneDrive: {filename}")

        link_resp = await client.post(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/createLink",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"type": "view", "scope": "organization"},
        )
        share_url = web_url
        if link_resp.is_success:
            share_url = link_resp.json().get("link", {}).get("webUrl", web_url)

    caption_html = f"<p>{_esc(caption)}</p>" if caption else ""
    body = (
        f"<p>🎥 Vídeo WhatsApp</p>"
        f"{caption_html}"
        f'<attachment id="{item_id}"></attachment>'
        f"{_wa_ref(wa_chat_id, wa_message_id, sender_name)}"
    )
    return await _post_with_quote(
        chat_id,
        _wa_header(sender_name, chat_name),
        body,
        quote=quote,
        attachments=[{
            "id": item_id,
            "contentType": "reference",
            "contentUrl": share_url,
            "name": f"Vídeo WhatsApp.{ext}",
        }],
        timeout=60,
    )


async def post_to_chat(
    chat_id: str,
    sender_name: str,
    chat_name: str,
    text: str,
    wa_chat_id: str,
    wa_message_id: str,
    quote: dict | None = None,
) -> str:
    body = f"<p>{_esc(text)}</p>{_wa_ref(wa_chat_id, wa_message_id, sender_name)}"
    return await _post_with_quote(
        chat_id,
        _wa_header(sender_name, chat_name),
        body,
        quote=quote,
        timeout=20,
    )


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
