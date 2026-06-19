import re

import whatsapp.api as wa_api
import teams.api as teams_api
from config import settings


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
        print(f"[Teams→WA] buscando msg top-level {message_id}")
        message = await teams_api.get_message(message_id)
        parent_message_id = message.get("replyToId")
        if not parent_message_id:
            print(f"[Teams→WA] ignorado (top-level sem replyToId)")
            return
    else:
        return

    msg_type = message.get("messageType")
    print(f"[Teams→WA] messageType={msg_type}")
    if msg_type != "message":
        return

    content: str = (message.get("body") or {}).get("content", "")
    print(f"[Teams→WA] content={content[:200]}")
    if "📱 Mensagem WhatsApp" in content:
        print(f"[Teams→WA] ignorado (é o próprio card WA)")
        return

    reply_text = _strip_html(content).strip()
    print(f"[Teams→WA] reply_text={reply_text[:100]!r}")
    if not reply_text:
        return

    sender_name: str = (message.get("from") or {}).get("user", {}).get("displayName", "Colaborador")

    print(f"[Teams→WA] buscando msg pai {parent_message_id}")
    parent_message = await teams_api.get_message(parent_message_id)
    parent_content: str = (parent_message.get("body") or {}).get("content", "")
    for att in parent_message.get("attachments") or []:
        parent_content += " " + (att.get("content") or "")
    print(f"[Teams→WA] parent_content={parent_content[:300]}")
    wa_match = re.search(r'\[wa:([^|\]]+)\|([^|\]]+)\|([^\]]+)\]', parent_content)
    if not wa_match:
        print(f"[Teams→WA] Metadados WA não encontrados na mensagem pai: {parent_message_id}")
        print(f"[Teams→WA] parent_content completo: {parent_content[:600]}")
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
