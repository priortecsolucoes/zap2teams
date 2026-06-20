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
    if not reply_text:
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

    print(f'[Teams→WA] "{sender_name}" → {wa_chat_id[:30]} | "{reply_text[:80]}"')
    await wa_api.send_reply(wa_chat_id, wa_message_id, reply_text)
    db.update_thread_timestamp(wa_chat_id)
    print(f"[Teams→WA] ✓ Enviado para {wa_chat_id[:30]}")


async def _route_direct_message(message: dict, teams_chat_id: str) -> None:
    if message.get("messageType") != "message":
        return

    from_info = message.get("from") or {}
    content: str = (message.get("body") or {}).get("content", "")
    reply_text = _strip_html(content).strip()
    if not reply_text:
        return

    wa_jid = db.find_wa_jid_by_teams_chat(teams_chat_id)
    if not wa_jid:
        wa_group_name = settings.chat_mappings.get(teams_chat_id, teams_chat_id[:30])
        print(f"[Teams→WA] JID WA não encontrado para '{wa_group_name}' — aguardando primeira msg WA")
        return

    sender_name = from_info.get("user", {}).get("displayName", "Colaborador")
    print(f'[Teams→WA] "{sender_name}" (direto) → {wa_jid[:30]} | "{reply_text[:80]}"')
    await wa_api.send_text(wa_jid, reply_text)
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
