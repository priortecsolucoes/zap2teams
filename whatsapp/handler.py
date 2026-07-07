import teams.api as teams_api
import whatsapp.api as wa_api
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
    return None


def _uazapi_media(msg: dict) -> tuple[str, str, str, str]:
    """Retorna (msg_type, media_url, mimetype, caption)."""
    msg_type = (msg.get("messageType") or msg.get("mediaType") or "").lower()
    media_url = msg.get("url") or msg.get("mediaUrl") or msg.get("fileUrl") or ""
    if not isinstance(media_url, str):
        media_url = ""
    mimetype = (msg.get("mimetype") or msg.get("mimeType") or "").lower()
    if not mimetype:
        if "image" in msg_type:
            mimetype = "image/jpeg"
        elif "video" in msg_type:
            mimetype = "video/mp4"
        elif "document" in msg_type:
            mimetype = "application/octet-stream"
    caption = msg.get("caption") or ""
    if not isinstance(caption, str):
        caption = ""
    return msg_type, media_url, mimetype, caption


def _media_label(msg_type: str, caption: str, msg: dict) -> str:
    cap = f" — {caption}" if caption else ""
    if "image" in msg_type:
        return f"📷 [Foto]{cap}"
    if "video" in msg_type:
        return f"🎥 [Vídeo]{cap}"
    if "audio" in msg_type:
        return f"🎵 [Áudio]{cap}"
    if "document" in msg_type:
        filename = msg.get("filename") or msg.get("fileName") or ""
        name = f": {filename}" if filename else ""
        return f"📄 [Documento{name}]{cap}"
    if "sticker" in msg_type:
        return "🖼️ [Figurinha]"
    if "contact" in msg_type:
        return f"👤 [Contato]{cap}"
    return f"[{msg_type or 'Mídia'}]{cap}"


async def handle_incoming(payload: dict) -> None:
    print(f"[WA handler] chaves: {list(payload.keys())}")

    msg = payload.get("message")
    msg_type = ""
    media_url = ""
    mimetype = ""
    caption = ""

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

        msg_type, media_url, mimetype, caption = _uazapi_media(msg)
        # Fallback 1: Uazapi pode colocar URL no root do payload
        if not media_url:
            _, media_url_root, mimetype_root, caption_root = _uazapi_media(payload)
            if media_url_root:
                msg_type = msg_type or (msg.get("messageType") or payload.get("messageType") or "").lower()
                media_url = media_url_root
                mimetype = mimetype_root or mimetype
                caption = caption_root or caption
                print(f"[WA handler] URL de mídia encontrada no root payload: {media_url[:80]}")
        # Fallback 2: msg pode ter sub-objeto "message" com formato Evolution (imageMessage etc.)
        if not media_url:
            inner = msg.get("message") or {}
            if isinstance(inner, dict):
                img = inner.get("imageMessage") or {}
                vid = inner.get("videoMessage") or {}
                doc = inner.get("documentMessage") or {}
                aud = inner.get("audioMessage") or {}
                sub = img or vid or doc or aud
                if sub:
                    media_url = sub.get("url") or sub.get("directPath") or ""
                    mimetype = (sub.get("mimetype") or "").lower()
                    caption = sub.get("caption") or ""
                    if img:
                        msg_type = "imagemessage"
                    elif vid:
                        msg_type = "videomessage"
                    elif doc:
                        msg_type = "documentmessage"
                    elif aud:
                        msg_type = "audiomessage"
                    if media_url:
                        print(f"[WA handler] URL de mídia encontrada no msg.message: {media_url[:80]}")
        if not media_url and not (msg.get("content") or msg.get("text") or msg.get("body") or msg.get("conversation")):
            print(f"[WA handler] msg keys: {list(msg.keys())} | msg sample: {str(msg)[:400]}")
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

    is_image = bool("image" in msg_type and media_url)

    if not text and not media_url:
        print("[WA handler] sem texto nem mídia extraível")
        return

    display = text or caption or _media_label(msg_type, caption, msg if "chatid" in (msg or {}) else {})
    print(f'[WA→Teams] Chat: "{group_name}" | De: {sender_name} | Msg: "{display[:80]}"')

    teams_chat_id = settings.wa_to_teams.get(group_name)
    if not teams_chat_id:
        print(f"[WA→Teams] Grupo '{group_name}' sem mapeamento Teams, ignorado")
        return

    is_uazapi_msg = isinstance(msg, dict) and "chatid" in msg
    media_ctx = msg if is_uazapi_msg else {}

    try:
        if text and is_image:
            # Texto + imagem: posta o texto primeiro (com ref [wa:]) e depois a imagem
            await teams_api.post_to_chat(
                teams_chat_id,
                sender_name=sender_name,
                chat_name=group_name,
                text=text,
                wa_chat_id=chat_id,
                wa_message_id=message_id,
            )
            print("[WA→Teams] ✓ Texto enviado ao chat")
            try:
                image_bytes = await wa_api.download_media(media_url)
                if len(image_bytes) > 4 * 1024 * 1024:
                    raise Exception("imagem maior que 4 MB")
                await teams_api.post_image_only(teams_chat_id, image_bytes, mimetype or "image/jpeg")
                print("[WA→Teams] ✓ Imagem enviada ao chat")
            except Exception as img_err:
                print(f"[WA→Teams] Falha ao enviar imagem ({img_err})")

        elif is_image:
            # Só imagem (sem texto): posta com cabeçalho de remetente e ref [wa:]
            try:
                image_bytes = await wa_api.download_media(media_url)
                if len(image_bytes) > 4 * 1024 * 1024:
                    raise Exception("imagem maior que 4 MB")
                await teams_api.post_image_to_chat(
                    teams_chat_id,
                    sender_name=sender_name,
                    chat_name=group_name,
                    image_bytes=image_bytes,
                    content_type=mimetype or "image/jpeg",
                    wa_chat_id=chat_id,
                    wa_message_id=message_id,
                    caption=caption,
                )
                print("[WA→Teams] ✓ Imagem enviada ao chat")
            except Exception as img_err:
                print(f"[WA→Teams] Falha ao enviar imagem ({img_err}), enviando como texto")
                await teams_api.post_to_chat(
                    teams_chat_id,
                    sender_name=sender_name,
                    chat_name=group_name,
                    text=_media_label(msg_type, caption, media_ctx),
                    wa_chat_id=chat_id,
                    wa_message_id=message_id,
                )
                print("[WA→Teams] ✓ Texto (fallback) enviado ao chat")

        else:
            # Texto ou label de mídia
            send_text = text or _media_label(msg_type, caption, media_ctx)
            await teams_api.post_to_chat(
                teams_chat_id,
                sender_name=sender_name,
                chat_name=group_name,
                text=send_text,
                wa_chat_id=chat_id,
                wa_message_id=message_id,
            )
            print("[WA→Teams] ✓ Nova mensagem no chat")

    except Exception as e:
        print(f"[WA→Teams] Erro ao postar no Teams: {e}")
