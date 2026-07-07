import re

import whatsapp.api as wa_api
import teams.api as teams_api
from config import settings
from storage import db


async def process_notifications(body: dict) -> None:
    notifications = body.get("value", [])
    if not isinstance(notifications, list):
        return

    print(f"[Teams→WA] {len(notifications)} notificação(ões) recebida(s)")
    for notification in notifications:
        resource = notification.get("resource", "")
        print(f"[Teams→WA] resource: {resource}")
        if notification.get("clientState") != settings.teams_notification_secret:
            print("[Teams→WA] clientState inválido, ignorado")
            continue
        if notification.get("lifecycleEvent"):
            continue
        try:
            await _process_one(notification)
        except Exception as e:
            print(f"[Teams→WA] Erro ao processar notificação: {e}")


def _get_chat_id_from_resource(resource: str) -> str | None:
    match = re.search(r"chats\('([^']+)'\)", resource)
    return match.group(1) if match else None


async def _process_one(notification: dict) -> None:
    resource: str = notification.get("resource", "")

    teams_chat_id = _get_chat_id_from_resource(resource)
    if not teams_chat_id or teams_chat_id not in settings.chat_mappings:
        return

    reply_match = re.search(r"messages\('([^']+)'\)/replies\('([^']+)'\)$", resource)
    top_match = re.search(r"messages\('([^']+)'\)$", resource)

    if reply_match:
        parent_id, reply_id = reply_match.group(1), reply_match.group(2)
        message = await teams_api.get_chat_reply(teams_chat_id, parent_id, reply_id)
        parent_message_id = parent_id
    elif top_match:
        message_id = top_match.group(1)
        message = await teams_api.get_chat_message(teams_chat_id, message_id)
        content_peek = (message.get("body") or {}).get("content", "")
        if not message.get("replyToId"):
            if "📱" in content_peek:
                _maybe_save_thread(message_id, message, teams_chat_id)
            else:
                await _route_direct_message(message, teams_chat_id)
            return
        parent_message_id = message["replyToId"]
    else:
        return

    if message.get("messageType") != "message":
        return

    from_info = message.get("from") or {}
    content: str = (message.get("body") or {}).get("content", "")

    if "📱" in content:
        return

    reply_text = _strip_html(content).strip()
    images = await _extract_images(message, teams_chat_id)

    if not reply_text and not images:
        return

    sender_name: str = from_info.get("user", {}).get("displayName", "Colaborador")

    parent_message = await teams_api.get_chat_message(teams_chat_id, parent_message_id)
    parent_content: str = (parent_message.get("body") or {}).get("content", "")
    wa_match = re.search(r'\[wa:([^|\]]+)\|([^|\]]+)\|([^\]]+)\]', parent_content)
    if not wa_match:
        print(f"[Teams→WA] Ref WA não encontrada na msg pai {parent_message_id}")
        return

    wa_chat_id = wa_match.group(1).strip()
    wa_message_id = wa_match.group(2).strip()

    if reply_text:
        message_text = f"*{sender_name}:*\n{reply_text}"
        print(f'[Teams→WA] "{sender_name}" → {wa_chat_id[:30]} | "{reply_text[:80]}"')
        await wa_api.send_reply(wa_chat_id, wa_message_id, message_text)

    for img_bytes, mimetype in images:
        caption = f"*{sender_name}*" if not reply_text else ""
        print(f'[Teams→WA] "{sender_name}" → imagem {mimetype} ({len(img_bytes)} bytes) → {wa_chat_id[:30]}')
        await wa_api.send_image(wa_chat_id, img_bytes, mimetype, caption)

    db.update_thread_timestamp(wa_chat_id)
    print(f"[Teams→WA] ✓ Enviado para {wa_chat_id[:30]}")


async def _extract_images(message: dict, teams_chat_id: str) -> list[tuple[bytes, str]]:
    """Extrai imagens de uma mensagem do Teams. Retorna lista de (bytes, mimetype)."""
    results = []
    msg_id = message.get("id", "")
    content = (message.get("body") or {}).get("content", "")

    # Imagens inline coladas ou arrastadas (hostedContents)
    for hc_id in re.findall(r'hostedContents/([^/\s"\']+)/\$value', content):
        try:
            img_bytes, ct = await teams_api.download_graph_binary(
                f"/chats/{teams_chat_id}/messages/{msg_id}/hostedContents/{hc_id}/$value"
            )
            if img_bytes:
                results.append((img_bytes, ct.split(";")[0] or "image/jpeg"))
                print(f"[Teams→WA] Hosted content baixado: {len(img_bytes)} bytes ({ct.split(';')[0]})")
        except Exception as e:
            print(f"[Teams→WA] Hosted content {hc_id[:30]} falhou: {e}")

    # Imagens enviadas como arquivo anexo
    for att in message.get("attachments") or []:
        if att.get("contentType") != "reference":
            continue
        name = att.get("name", "").lower()
        if not any(name.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            continue
        ct_url = att.get("contentUrl", "")
        if not ct_url:
            continue
        try:
            img_bytes = await wa_api.download_media(ct_url)
            mime = "image/png" if name.endswith(".png") else "image/gif" if name.endswith(".gif") else "image/jpeg"
            results.append((img_bytes, mime))
            print(f"[Teams→WA] Anexo '{name}' baixado: {len(img_bytes)} bytes")
        except Exception as e:
            print(f"[Teams→WA] Anexo '{name}' falhou: {e}")

    return results


async def _route_direct_message(message: dict, teams_chat_id: str) -> None:
    if message.get("messageType") != "message":
        return

    from_info = message.get("from") or {}
    content: str = (message.get("body") or {}).get("content", "")
    reply_text = _strip_html(content).strip()
    images = await _extract_images(message, teams_chat_id)

    if not reply_text and not images:
        return

    wa_jid = db.find_wa_jid_by_teams_chat(teams_chat_id)
    if not wa_jid:
        wa_group_name = settings.chat_mappings.get(teams_chat_id, teams_chat_id[:30])
        print(f"[Teams→WA] JID WA não encontrado para '{wa_group_name}' — aguardando primeira msg WA")
        return

    sender_name = from_info.get("user", {}).get("displayName", "Colaborador")

    if reply_text:
        message_text = f"*{sender_name}:*\n{reply_text}"
        print(f'[Teams→WA] "{sender_name}" (direto) → {wa_jid[:30]} | "{reply_text[:80]}"')
        await wa_api.send_text(wa_jid, message_text)

    for img_bytes, mimetype in images:
        caption = f"*{sender_name}*" if not reply_text else ""
        print(f'[Teams→WA] "{sender_name}" → imagem {mimetype} ({len(img_bytes)} bytes) → {wa_jid[:30]}')
        await wa_api.send_image(wa_jid, img_bytes, mimetype, caption)

    db.update_thread_timestamp(wa_jid)
    print(f"[Teams→WA] ✓ Enviado para {wa_jid[:30]}")


def _maybe_save_thread(message_id: str, message: dict, teams_chat_id: str = "") -> None:
    content: str = (message.get("body") or {}).get("content", "")
    wa_match = re.search(r'\[wa:([^|\]]+)\|([^|\]]+)\|([^\]]+)\]', content)
    if wa_match:
        wa_chat_id = wa_match.group(1).strip()
        db.save_thread(wa_chat_id, message_id, teams_chat_id)
        print(f"[Teams] Thread mapeada: {wa_chat_id[:30]} → {message_id}")


def _strip_html(html_str: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html_str, flags=re.IGNORECASE)
    text = re.sub(r"</p>|</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip()
