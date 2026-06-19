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


async def handle_incoming(payload: dict) -> None:
    data = payload.get("data") or payload
    key = data.get("key") or {}

    if key.get("fromMe"):
        return

    group_id: str = key.get("remoteJid", "")
    if not group_id.endswith("@g.us"):
        return

    message_id: str = key.get("id", "")
    if not message_id:
        return

    sender_jid: str = data.get("participant") or (key.get("participant") or "")
    sender_name: str = data.get("pushName") or data.get("notifyName") or "Desconhecido"
    sender_number: str = sender_jid.replace("@s.whatsapp.net", "") or group_id
    group_name: str = (
        (data.get("chat") or {}).get("name")
        or (data.get("groupMetadata") or {}).get("subject")
        or group_id.replace("@g.us", "")
    )
    text = _extract_text(data.get("message"))
    if not text:
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
