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

    # Uazapi format: single 'message' object at root level
    msg = payload.get("message")
    print(f"[WA handler] message type={type(msg).__name__} | value={str(msg)[:300]}")
    if msg and isinstance(msg, dict):
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
    # TEMP: aceitar qualquer remetente para debug
    print(f"[WA handler] group_id={group_id[:40]} | is_group={group_id.endswith('@g.us')}")

    message_id: str = key.get("id", "")
    print(f"[WA handler] message_id={message_id}")

    sender_name: str = push_name or "Desconhecido"
    sender_number: str = participant.replace("@s.whatsapp.net", "") or group_id or "debug"

    chat_obj = payload.get("chat") or {}
    group_name: str = (
        chat_obj.get("name")
        or chat_obj.get("subject")
        or group_id.replace("@g.us", "")
        or "debug-direto"
    )

    text = _extract_text(message_content)
    print(f"[WA handler] text={str(text)[:100]}")
    if not text:
        print(f"[WA handler] sem texto extraível | message_content={str(message_content)[:200]}")
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
