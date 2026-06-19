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
            print("[Teams→WA] clientState inválido, notificação ignorada")
            continue
        if notification.get("lifecycleEvent"):
            print(f"[Teams→WA] Evento de ciclo de vida recebido: {notification['lifecycleEvent']} (ignorado)")
            continue
        try:
            await _process_one(notification)
        except Exception as e:
            print(f"[Teams→WA] Erro ao processar notificação: {e}")


async def _process_one(notification: dict) -> None:
    resource: str = notification.get("resource", "")

    # OData: messages('parentId')/replies('replyId')
    reply_match = re.search(r"messages\('([^']+)'\)/replies\('([^']+)'\)$", resource)
    # OData: messages('messageId')
    top_match = re.search(r"messages\('([^']+)'\)$", resource)

    message: dict
    parent_message_id: str | None

    if reply_match:
        parent_id, reply_id = reply_match.group(1), reply_match.group(2)
        parent_message_id = parent_id
        print(f"[Teams→WA] buscando reply {reply_id} da msg {parent_id}")
        message = await teams_api.get_reply(parent_id, reply_id)
    elif top_match:
        message_id = top_match.group(1)
        message = await teams_api.get_message(message_id)
        parent_message_id = message.get("replyToId")
        if not parent_message_id:
            # Mensagem top-level: verificar se é card WA e salvar thread mapping
            _maybe_save_thread(message_id, message)
            return
    else:
        return

    if message.get("messageType") != "message":
        return

    # Ignorar mensagens enviadas pelo próprio app (via Graph API)
    from_info = message.get("from") or {}
    if from_info.get("application"):
        return

    content: str = (message.get("body") or {}).get("content", "")
    if "📱 Mensagem WhatsApp" in content:
        return

    reply_text = _strip_html(content).strip()
    if not reply_text:
        return

    sender_name: str = from_info.get("user", {}).get("displayName", "Colaborador")

    parent_message = await teams_api.get_message(parent_message_id)
    parent_content: str = (parent_message.get("body") or {}).get("content", "")
    for att in parent_message.get("attachments") or []:
        parent_content += " " + (att.get("content") or "")
    wa_match = re.search(r'\[wa:([^|\]]+)\|([^|\]]+)\|([^\]]+)\]', parent_content)
    if not wa_match:
        print(f"[Teams→WA] Metadados WA não encontrados na mensagem pai: {parent_message_id}")
        return

    wa_group_id = wa_match.group(1).strip()
    wa_message_id = wa_match.group(2).strip()
    wa_sender_name = wa_match.group(3).strip()

    print(
        f'[Teams→WA] Resposta de "{sender_name}" → '
        f'Grupo: "{wa_group_id}" | Texto: "{reply_text[:80]}"'
    )

    await wa_api.send_reply(wa_group_id, wa_message_id, reply_text)
    print(f"[Teams→WA] ✓ Resposta enviada para {wa_group_id}")


def _maybe_save_thread(message_id: str, message: dict) -> None:
    """Se a mensagem top-level for um card WA, salva o mapping chat_id → thread."""
    content: str = (message.get("body") or {}).get("content", "")
    for att in message.get("attachments") or []:
        content += " " + (att.get("content") or "")
    wa_match = re.search(r'\[wa:([^|\]]+)\|([^|\]]+)\|([^\]]+)\]', content)
    if wa_match:
        wa_chat_id = wa_match.group(1).strip()
        db.save_thread(wa_chat_id, message_id)
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
