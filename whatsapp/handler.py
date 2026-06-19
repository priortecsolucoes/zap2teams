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
    print(f"[WA handler] chaves: {list(payload.keys())}")

    # Uazapi format: messages array at root level
    messages_list = payload.get("messages")
    if messages_list and isinstance(messages_list, list):
        msg = messages_list[0]
        print(f"[WA handler] Uazapi msg chaves: {list(msg.keys())}")
        key = msg.get("key") or {}
        message_content = msg.get("message")
        push_name = msg.get("pushName") or msg.get("notifyName")
        participant = msg.get("participant") or key.get("participant", "")
    else:
        # Evolution API / generic format
        data = payload.get("data") or payload
        key = data.get("key") or {}
        message_content = data.get("message")
        push_name = data.get("pushName") or data.get("notifyName")
        participant = data.get("participant") or key.get("participant", "")

    print(f"[WA handler] key={key} | fromMe={key.get('fromMe')} | remoteJid={key.get('remoteJid', '')[:40]}")

    if key.get("fromMe"):
        return

    group_id: str = key.get("remoteJid", "")
    if not group_id.endswith("@g.us"):
        print(f"[WA handler] ignorado (não é grupo): {group_id[:40]}")
        return

    message_id: str = key.get("id", "")
    if not message_id:
        return

    sender_name: str = push_name or "Desconhecido"
    sender_number: str = participant.replace("@s.whatsapp.net", "") or group_id

    chat_obj = payload.get("chat") or {}
    group_name: str = (
        chat_obj.get("name")
        or chat_obj.get("subject")
        or group_id.replace("@g.us", "")
    )

    text = _extract_text(message_content)
    if not text:
        print(f"[WA handler] sem texto extraível | message_content={message_content}")
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
