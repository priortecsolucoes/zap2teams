import teams.api as teams_api
from config import settings
from storage import db


def _extract_text(message: dict) -> str | None:
    if not message:
        return None
    return (
        message.get("conversation")
        or (message.get("extendedTextMessage") or {}).get("text")
        or (message.get("imageMessage") or {}).get("caption")
        or (message.get("videoMessage") or {}).get("caption")
        or (message.get("documentMessage") or {}).get("caption")
        or ("[Áudio]" if "audioMessage" in message else None)
        or ("[Figurinha]" if "stickerMessage" in message else None)
        or "[Mídia não suportada]"
    )


def _extract_text_uazapi(msg: dict) -> str | None:
    raw = msg.get("content") or msg.get("text") or msg.get("body")
    if isinstance(raw, str) and raw:
        return raw
    # Mensagem com citação: content pode ser dict com o texto dentro
    if isinstance(raw, dict):
        inner = raw.get("text") or raw.get("conversation") or raw.get("caption") or ""
        if isinstance(inner, str) and inner:
            return inner
    media = (msg.get("mediaType") or msg.get("messageType") or "").lower()
    if "audio" in media:
        return "[Áudio]"
    if "sticker" in media:
        return "[Figurinha]"
    if media:
        print(f"[WA handler] mídia sem texto | messageType={msg.get('messageType')} | chaves msg={list(msg.keys())}")
        return "[Mídia não suportada]"
    return None


async def handle_incoming(payload: dict) -> None:
    print(f"[WA handler] chaves: {list(payload.keys())}")

    msg = payload.get("message")

    if msg and isinstance(msg, dict) and "chatid" in msg:
        # Uazapi flat format
        if msg.get("wasSentByApi"):
            return

        chat_id: str = msg.get("chatid", "")
        message_id: str = msg.get("messageid") or msg.get("id", "")
        if not message_id:
            return

        is_group: bool = msg.get("isGroup") or chat_id.endswith("@g.us")
        sender_name: str = msg.get("senderName") or "Desconhecido"
        sender_number: str = (msg.get("sender") or "").replace("@s.whatsapp.net", "") or chat_id
        group_name: str = (
            msg.get("groupName")
            or (chat_id.replace("@g.us", "") if is_group else sender_name)
        )
        text = _extract_text_uazapi(msg)

    else:
        # Evolution API / generic format
        data = payload.get("data") or payload
        key = data.get("key") or {}

        if key.get("fromMe"):
            return

        chat_id = key.get("remoteJid", "")
        message_id = key.get("id", "")
        if not message_id:
            return

        is_group = chat_id.endswith("@g.us")
        sender_jid: str = data.get("participant") or key.get("participant", "")
        sender_name = data.get("pushName") or data.get("notifyName") or "Desconhecido"
        sender_number = sender_jid.replace("@s.whatsapp.net", "") or chat_id
        chat_obj = payload.get("chat") or {}
        group_name = (
            chat_obj.get("name")
            or chat_obj.get("subject")
            or (data.get("groupMetadata") or {}).get("subject")
            or (chat_id.replace("@g.us", "") if is_group else sender_name)
        )
        text = _extract_text(data.get("message"))

    if not text:
        print(f"[WA handler] sem texto extraível")
        return

    print(f'[WA→Teams] Chat: "{group_name}" | De: {sender_name} | Msg: "{text[:80]}"')

    teams_chat_id = settings.wa_to_teams.get(group_name)
    if not teams_chat_id:
        print(f"[WA→Teams] Grupo '{group_name}' sem mapeamento Teams, ignorado")
        return

    active_thread = db.get_active_thread(chat_id)

    try:
        if active_thread:
            try:
                await teams_api.post_reply_to_chat(
                    teams_chat_id,
                    active_thread["teams_message_id"],
                    sender_name,
                    text,
                )
                db.update_thread_timestamp(chat_id)
                print(f"[WA→Teams] ✓ Reply na thread {active_thread['teams_message_id']}")
                return
            except Exception as reply_err:
                print(f"[WA→Teams] Falha ao responder thread ({reply_err}), postando nova mensagem...")

        await teams_api.post_to_chat(
            teams_chat_id,
            sender_name=sender_name,
            chat_name=group_name,
            text=text,
            wa_chat_id=chat_id,
            wa_message_id=message_id,
        )
        print(f"[WA→Teams] ✓ Nova mensagem no chat")
    except Exception as e:
        print(f"[WA→Teams] Erro ao postar no Teams: {e}")
