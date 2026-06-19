import teams.api as teams_api


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
    text = msg.get("content") or msg.get("text") or ""
    if text:
        return text
    media = (msg.get("mediaType") or msg.get("messageType") or "").lower()
    if "audio" in media:
        return "[Áudio]"
    if "sticker" in media:
        return "[Figurinha]"
    if media:
        return "[Mídia não suportada]"
    return None


async def handle_incoming(payload: dict) -> None:
    print(f"[WA handler] chaves: {list(payload.keys())}")

    msg = payload.get("message")

    if msg and isinstance(msg, dict) and "chatid" in msg:
        # Uazapi flat format
        if msg.get("fromMe") or msg.get("wasSentByApi"):
            return

        group_id: str = msg.get("chatid", "")
        if not group_id.endswith("@g.us"):
            print(f"[WA handler] ignorado (não é grupo): {group_id[:40]}")
            return

        message_id: str = msg.get("messageid") or msg.get("id", "")
        if not message_id:
            return

        sender_name: str = msg.get("senderName") or "Desconhecido"
        sender_number: str = (msg.get("sender") or "").replace("@s.whatsapp.net", "") or group_id
        group_name: str = msg.get("groupName") or group_id.replace("@g.us", "")
        text = _extract_text_uazapi(msg)

    else:
        # Evolution API / generic format
        data = payload.get("data") or payload
        key = data.get("key") or {}

        if key.get("fromMe"):
            return

        group_id = key.get("remoteJid", "")
        if not group_id.endswith("@g.us"):
            print(f"[WA handler] ignorado (não é grupo): {group_id[:40]}")
            return

        message_id = key.get("id", "")
        if not message_id:
            return

        sender_jid: str = data.get("participant") or key.get("participant", "")
        sender_name = data.get("pushName") or data.get("notifyName") or "Desconhecido"
        sender_number = sender_jid.replace("@s.whatsapp.net", "") or group_id
        chat_obj = payload.get("chat") or {}
        group_name = (
            chat_obj.get("name")
            or chat_obj.get("subject")
            or (data.get("groupMetadata") or {}).get("subject")
            or group_id.replace("@g.us", "")
        )
        text = _extract_text(data.get("message"))

    if not text:
        print(f"[WA handler] sem texto extraível")
        return

    print(f'[WA→Teams] Grupo: "{group_name}" | De: {sender_name} | Msg: "{text[:80]}"')

    try:
        await teams_api.post_to_channel(
            group_id=group_id,
            group_name=group_name,
            sender_name=sender_name,
            sender_number=sender_number,
            message_text=text,
            wa_message_id=message_id,
        )
        print(f"[WA→Teams] ✓ Postado no Teams")
    except Exception as e:
        print(f"[WA→Teams] Erro ao postar no Teams: {e}")
