import ai.watcher as ai_watcher
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
    caption = msg.get("caption") or ""

    # Uazapi pode colocar dados da mídia dentro de "content"
    content = msg.get("content")
    # content como string URL completa
    if not media_url and isinstance(content, str) and content.startswith("http"):
        media_url = content
    # content como dict com campos de mídia
    if not media_url and isinstance(content, dict):
        # Usa apenas URLs completas (nunca directPath, que não é downloadável)
        cand = content.get("url") or content.get("mediaUrl") or ""
        if isinstance(cand, str) and cand.startswith("http"):
            media_url = cand
        if not mimetype:
            mimetype = (content.get("mimetype") or content.get("mimeType") or "").lower()
        if not caption:
            caption = content.get("caption") or ""
        # sub-chaves imageMessage/videoMessage etc. dentro de content
        if not media_url:
            for key in ("imageMessage", "videoMessage", "audioMessage", "documentMessage", "stickerMessage"):
                inner = content.get(key)
                if isinstance(inner, dict):
                    inner_url = inner.get("url") or ""
                    if isinstance(inner_url, str) and inner_url.startswith("http"):
                        media_url = inner_url
                        if not msg_type:
                            msg_type = key.lower()
                        if not mimetype:
                            mimetype = (inner.get("mimetype") or "").lower()
                        if not caption:
                            caption = inner.get("caption") or ""
                        break

    if not isinstance(media_url, str):
        media_url = ""
    if not mimetype:
        if "image" in msg_type:
            mimetype = "image/jpeg"
        elif "video" in msg_type:
            mimetype = "video/mp4"
        elif "document" in msg_type:
            mimetype = "application/octet-stream"
    if not isinstance(caption, str):
        caption = ""
    return msg_type, media_url, mimetype, caption


_QUOTE_GENERIC = "↩️ Em resposta a uma mensagem anterior"


def _find_context_info(obj) -> dict:
    """Procura o contextInfo (dados da mensagem citada) no conteúdo bruto da mensagem.
    Ele fica no nível do tipo da mensagem: content.contextInfo (uazapi) ou
    message.extendedTextMessage.contextInfo / message.imageMessage.contextInfo etc."""
    if not isinstance(obj, dict):
        return {}
    ctx = obj.get("contextInfo")
    if isinstance(ctx, dict):
        return ctx
    for value in obj.values():
        if isinstance(value, dict) and isinstance(value.get("contextInfo"), dict):
            return value["contextInfo"]
    return {}


def _resolve_quote(quoted_id: str, context_info: dict, teams_chat_id: str) -> dict | None:
    """Monta os dados da mensagem citada para o Teams. Ordem: nosso mapa WA↔Teams (tem o ID no
    Teams, permite citação nativa) → contextInfo do payload (só texto) → frase genérica."""
    quoted_id = quoted_id or context_info.get("stanzaID") or context_info.get("stanzaId") or ""
    if not quoted_id and not context_info.get("quotedMessage"):
        return None

    teams_message_id = None
    sender = ""
    preview = ""

    row = db.find_by_wa_message_id(quoted_id) if quoted_id else None
    if row:
        # Só usa o ID do Teams se ele for do mesmo chat (o mapeamento pode ter mudado).
        if not row.get("teams_chat_id") or row["teams_chat_id"] == teams_chat_id:
            teams_message_id = row["teams_message_id"]
        sender = row.get("wa_sender_name") or ""
        preview = row.get("wa_message_text") or ""

    quoted_message = context_info.get("quotedMessage")
    if not preview and isinstance(quoted_message, dict):
        preview = _extract_text(quoted_message) or ""
    if not sender:
        participant = context_info.get("participant") or ""
        if participant.endswith("@s.whatsapp.net"):
            sender = "+" + participant.split("@")[0].split(":")[0]

    return {
        "teams_message_id": teams_message_id,
        "sender": sender,
        "preview": preview or _QUOTE_GENERIC,
    }


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


def _decrypt_wa_media(encrypted_bytes: bytes, media_key_b64: str, msg_type: str) -> bytes:
    """Descriptografa mídia do WhatsApp com AES-256-CBC usando chave derivada via HKDF-SHA256."""
    import base64
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    padded = media_key_b64 + "=" * (-len(media_key_b64) % 4)
    media_key = base64.b64decode(padded)

    if "image" in msg_type or "sticker" in msg_type:
        info = b"WhatsApp Image Keys"
    elif "video" in msg_type:
        info = b"WhatsApp Video Keys"
    elif "audio" in msg_type:
        info = b"WhatsApp Audio Keys"
    elif "document" in msg_type:
        info = b"WhatsApp Document Keys"
    else:
        info = b"WhatsApp Image Keys"

    keys = HKDF(algorithm=hashes.SHA256(), length=112, salt=b"\x00" * 32, info=info).derive(media_key)
    iv, cipher_key = keys[0:16], keys[16:48]

    # Formato: [dados_cifrados][10 bytes de MAC]
    ciphertext = encrypted_bytes[:-10]
    decryptor = Cipher(algorithms.AES(cipher_key), modes.CBC(iv)).decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove padding PKCS7
    pad_len = plaintext[-1]
    return plaintext[:-pad_len] if 1 <= pad_len <= 16 else plaintext


async def _download_image(
    media_url: str, message_id: str, chat_id: str, is_uazapi: bool,
    thumbnail_b64: str = "", media_key_b64: str = "", msg_type: str = ""
) -> bytes:
    """Obtém bytes da imagem: CDN+decrypt → URL direta → API Uazapi → thumbnail."""
    import base64
    # CDN + descriptografia (imagem em resolução completa)
    if media_url and media_url.startswith("http") and media_key_b64:
        try:
            encrypted = await wa_api.download_media(media_url)
            decrypted = _decrypt_wa_media(encrypted, media_key_b64, msg_type)
            print("[WA handler] Imagem descriptografada com sucesso (resolução completa)")
            return decrypted
        except Exception as e:
            print(f"[WA handler] Descriptografia falhou ({e}), tentando thumbnail...")
    # URL direta sem criptografia (algumas configurações)
    elif media_url and media_url.startswith("http") and not media_key_b64:
        try:
            return await wa_api.download_media(media_url)
        except Exception as e:
            print(f"[WA handler] Download direto falhou ({e})")
    # Thumbnail do payload (baixa resolução, mas imediatamente disponível)
    if thumbnail_b64:
        print("[WA handler] Usando thumbnail JPEG do payload Uazapi (baixa resolução)")
        return base64.b64decode(thumbnail_b64)
    # API Uazapi por ID
    if is_uazapi and message_id:
        try:
            return await wa_api.download_media_by_id(message_id, chat_id)
        except Exception as e:
            print(f"[WA handler] Download por ID falhou ({e})")
    raise Exception(f"Sem imagem disponível (url={media_url!r})")


async def handle_incoming(payload: dict) -> None:
    print(f"[WA handler] chaves: {list(payload.keys())}")

    msg = payload.get("message")
    msg_type = ""
    media_url = ""
    mimetype = ""
    caption = ""
    thumbnail_b64 = ""
    media_key_b64 = ""
    doc_filename = ""
    quoted_id = ""
    context_info: dict = {}

    if msg and isinstance(msg, dict) and "chatid" in msg:
        # Uazapi flat format
        chat_id: str = msg.get("chatid", "")
        # Remove sufixo de dispositivo multi-device ("5511999999999:12@s.whatsapp.net") antes do "@",
        # senão o ":12" entra na extração de dígitos e quebra a comparação com o número configurado.
        sender_number: str = ((msg.get("sender") or "").split("@")[0].split(":")[0]) or chat_id
        sender_digits = "".join(c for c in sender_number if c.isdigit())

        # wasSentByApi só é true quando o envio sai pela API (ex: via Teams). Uma resposta digitada
        # manualmente no WhatsApp pelo número conectado à instância vem com wasSentByApi=false, então
        # também comparamos com o número configurado para reconhecê-la como "nossa". Em grupos o
        # WhatsApp pode reportar o remetente como um ID anônimo "@lid" em vez do número de telefone
        # (feature de privacidade), quebrando essa comparação — por isso também confiamos em
        # "fromMe" quando presente no payload, que a uazapi calcula a partir da própria sessão
        # conectada e não depende do formato do JID do remetente.
        is_own_number = bool(
            msg.get("fromMe")
            or (settings.uazapi_own_number_digits and sender_digits == settings.uazapi_own_number_digits)
        )
        if msg.get("wasSentByApi"):
            # Eco de mensagem que já saiu pela API (ex: relay do Teams) — não reposta no Teams
            # para não duplicar algo que já está lá.
            await ai_watcher.on_our_response(chat_id)
            return

        message_id: str = msg.get("messageid") or msg.get("id", "")
        if not message_id:
            return

        is_group: bool = msg.get("isGroup") or chat_id.endswith("@g.us")
        sender_name: str = msg.get("senderName") or "Desconhecido"
        group_name: str = (
            msg.get("groupName")
            or (chat_id.replace("@g.us", "") if is_group else sender_name)
        )

        msg_type, media_url, mimetype, caption = _uazapi_media(msg)
        # Extrai thumbnail e corrige URL maiúscula do content (Uazapi usa "URL" não "url")
        _content = msg.get("content")
        if isinstance(_content, dict):
            thumbnail_b64 = _content.get("JPEGThumbnail") or ""
            media_key_b64 = _content.get("mediaKey") or ""
            if not mimetype:
                mimetype = (_content.get("mimetype") or "").lower()
            if not media_url:
                cand = _content.get("URL") or _content.get("url") or ""
                if isinstance(cand, str) and cand.startswith("http"):
                    media_url = cand
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
                for _key, _mtype in [
                    ("imageMessage", "imagemessage"),
                    ("videoMessage", "videomessage"),
                    ("audioMessage", "audiomessage"),
                    ("documentMessage", "documentmessage"),
                ]:
                    sub = inner.get(_key)
                    if isinstance(sub, dict):
                        # Usa apenas URL completa — directPath não é downloadável
                        cand = sub.get("url") or ""
                        if isinstance(cand, str) and cand.startswith("http"):
                            media_url = cand
                            msg_type = msg_type or _mtype
                            mimetype = mimetype or (sub.get("mimetype") or "").lower()
                            caption = caption or (sub.get("caption") or "")
                            print(f"[WA handler] URL de mídia encontrada no msg.message.{_key}: {media_url[:80]}")
                        break
        # Extrai nome do arquivo para documentos
        if "document" in (msg_type or ""):
            doc_filename = msg.get("filename") or msg.get("fileName") or ""
            if not doc_filename and isinstance(_content, dict):
                doc_filename = (
                    _content.get("filename") or _content.get("fileName") or
                    (_content.get("documentMessage") or {}).get("fileName") or
                    (_content.get("documentMessage") or {}).get("filename") or
                    ""
                )
            doc_filename = doc_filename or ""
        text = _extract_text_uazapi(msg)

        # Citação: a uazapi documenta só "quoted" (ID da mensagem citada). O texto citado
        # costuma vir no contextInfo do content bruto, mas isso não é documentado.
        quoted_id = msg.get("quoted") or ""
        context_info = _find_context_info(_content) or _find_context_info(msg.get("message"))
        if quoted_id or context_info.get("quotedMessage"):
            import json as _json
            print(
                f"[WA handler] Mensagem com citação | quoted={quoted_id!r} | "
                f"content={_json.dumps(_content, ensure_ascii=False, default=str)[:3000]}"
            )

    else:
        # Evolution API / generic format
        data = payload.get("data") or payload
        key = data.get("key") or {}

        chat_id = key.get("remoteJid", "")
        sender_jid: str = data.get("participant") or key.get("participant", "")
        sender_number = sender_jid.replace("@s.whatsapp.net", "") or chat_id
        sender_digits = "".join(c for c in sender_number if c.isdigit())
        is_own_number = bool(
            settings.uazapi_own_number_digits and sender_digits == settings.uazapi_own_number_digits
        )
        if key.get("fromMe"):
            # Formato Evolution não distingue envio via API de envio manual (fromMe cobre os dois) —
            # mantém o comportamento original de não repostar no Teams.
            await ai_watcher.on_our_response(chat_id)
            return

        message_id = key.get("id", "")
        if not message_id:
            return

        is_group = chat_id.endswith("@g.us")
        sender_name = data.get("pushName") or data.get("notifyName") or "Desconhecido"
        chat_obj = payload.get("chat") or {}
        group_name = (
            chat_obj.get("name")
            or chat_obj.get("subject")
            or (data.get("groupMetadata") or {}).get("subject")
            or (chat_id.replace("@g.us", "") if is_group else sender_name)
        )
        text = _extract_text(data.get("message"))
        context_info = _find_context_info(data.get("message"))

    is_image = "image" in msg_type
    is_audio = "audio" in msg_type
    is_video = "video" in msg_type
    is_document = "document" in msg_type and not is_image and not is_audio and not is_video

    if not text and not media_url and not is_image and not is_audio and not is_video and not is_document:
        print("[WA handler] sem texto nem mídia extraível")
        return

    display = text or caption or _media_label(msg_type, caption, msg if "chatid" in (msg or {}) else {})
    print(f'[WA→Teams] Chat: "{group_name}" | De: {sender_name} | Msg: "{display[:80]}"')

    teams_chat_id = settings.wa_to_teams.get(group_name)
    if not teams_chat_id:
        print(f"[WA→Teams] Grupo '{group_name}' sem mapeamento Teams, ignorado")
        return

    if is_group and settings.ai_enabled:
        # Diagnóstico: se uma mensagem nossa algum dia deixar de ser reconhecida como tal (ex:
        # WhatsApp reportando o remetente como "@lid" em vez do número real), esse log mostra o
        # formato bruto recebido para ajustar a detecção.
        print(
            f"[AI watcher] is_own_number={is_own_number} sender_digits={sender_digits!r} "
            f"fromMe={(msg.get('fromMe') if isinstance(msg, dict) else 'n/a')!r}"
        )
        if is_own_number:
            # Resposta digitada manualmente por nós no WhatsApp: fecha a janela de espera da IA,
            # mas a mensagem continua sendo postada no Teams normalmente (não é eco da API).
            await ai_watcher.on_our_response(chat_id)
        else:
            await ai_watcher.on_incoming_customer_message(
                wa_chat_id=chat_id,
                sender_number=sender_number,
                sender_name=sender_name,
                text=display,
            )

    is_uazapi_msg = isinstance(msg, dict) and "chatid" in msg
    media_ctx = msg if is_uazapi_msg else {}

    quote = _resolve_quote(quoted_id, context_info, teams_chat_id)
    if quote:
        modo = "nativa" if quote["teams_message_id"] else "bloco"
        print(f'[WA→Teams] Citação ({modo}) de {quote["sender"] or "?"}: "{quote["preview"][:60]}"')

    # IDs das mensagens criadas no Teams para esta mensagem do WA (para citações futuras).
    teams_msg_ids: list[str] = []

    async def _post_label_fallback() -> None:
        teams_msg_ids.append(await teams_api.post_to_chat(
            teams_chat_id,
            sender_name=sender_name,
            chat_name=group_name,
            text=_media_label(msg_type, caption, media_ctx),
            wa_chat_id=chat_id,
            wa_message_id=message_id,
            quote=quote,
        ))
        print("[WA→Teams] ✓ Texto (fallback) enviado ao chat")

    try:
        if text and is_image:
            # Texto + imagem: posta o texto primeiro (com ref [wa:] e citação) e depois a imagem
            teams_msg_ids.append(await teams_api.post_to_chat(
                teams_chat_id,
                sender_name=sender_name,
                chat_name=group_name,
                text=text,
                wa_chat_id=chat_id,
                wa_message_id=message_id,
                quote=quote,
            ))
            print("[WA→Teams] ✓ Texto enviado ao chat")
            try:
                image_bytes = await _download_image(media_url, message_id, chat_id, is_uazapi_msg, thumbnail_b64, media_key_b64, msg_type)
                if len(image_bytes) > 4 * 1024 * 1024:
                    raise Exception("imagem maior que 4 MB")
                teams_msg_ids.append(
                    await teams_api.post_image_only(teams_chat_id, image_bytes, mimetype or "image/jpeg")
                )
                print("[WA→Teams] ✓ Imagem enviada ao chat")
            except Exception as img_err:
                print(f"[WA→Teams] Falha ao enviar imagem ({img_err})")

        elif is_image:
            # Só imagem (sem texto): posta com cabeçalho de remetente e ref [wa:]
            try:
                image_bytes = await _download_image(media_url, message_id, chat_id, is_uazapi_msg, thumbnail_b64, media_key_b64, msg_type)
                if len(image_bytes) > 4 * 1024 * 1024:
                    raise Exception("imagem maior que 4 MB")
                teams_msg_ids.append(await teams_api.post_image_to_chat(
                    teams_chat_id,
                    sender_name=sender_name,
                    chat_name=group_name,
                    image_bytes=image_bytes,
                    content_type=mimetype or "image/jpeg",
                    wa_chat_id=chat_id,
                    wa_message_id=message_id,
                    caption=caption,
                    quote=quote,
                ))
                print("[WA→Teams] ✓ Imagem enviada ao chat")
            except Exception as img_err:
                print(f"[WA→Teams] Falha ao enviar imagem ({img_err}), enviando como texto")
                await _post_label_fallback()

        elif is_audio:
            try:
                print(f"[WA→Teams] Baixando áudio (url={media_url[:60] if media_url else 'vazio'}, key={'sim' if media_key_b64 else 'não'})")
                audio_bytes = await _download_image(
                    media_url, message_id, chat_id, is_uazapi_msg,
                    "", media_key_b64, msg_type
                )
                print(f"[WA→Teams] Áudio baixado: {len(audio_bytes)} bytes ({mimetype or 'audio/ogg'})")
                teams_msg_ids.append(await teams_api.post_audio_to_chat(
                    teams_chat_id,
                    sender_name=sender_name,
                    chat_name=group_name,
                    audio_bytes=audio_bytes,
                    mimetype=mimetype or "audio/ogg",
                    wa_chat_id=chat_id,
                    wa_message_id=message_id,
                    caption=caption,
                    quote=quote,
                ))
                print("[WA→Teams] ✓ Áudio enviado ao chat")
            except Exception as audio_err:
                print(f"[WA→Teams] Falha ao enviar áudio ({audio_err}), enviando como texto")
                await _post_label_fallback()

        elif is_video:
            try:
                print(f"[WA→Teams] Baixando vídeo (url={media_url[:60] if media_url else 'vazio'})")
                video_bytes = await _download_image(
                    media_url, message_id, chat_id, is_uazapi_msg,
                    "", media_key_b64, msg_type
                )
                print(f"[WA→Teams] Vídeo baixado: {len(video_bytes)} bytes ({mimetype or 'video/mp4'})")
                teams_msg_ids.append(await teams_api.post_video_to_chat(
                    teams_chat_id,
                    sender_name=sender_name,
                    chat_name=group_name,
                    video_bytes=video_bytes,
                    mimetype=mimetype or "video/mp4",
                    wa_chat_id=chat_id,
                    wa_message_id=message_id,
                    caption=caption,
                    quote=quote,
                ))
                print("[WA→Teams] ✓ Vídeo enviado ao chat")
            except Exception as video_err:
                print(f"[WA→Teams] Falha ao enviar vídeo ({video_err}), enviando como texto")
                await _post_label_fallback()

        elif is_document:
            try:
                print(f"[WA→Teams] Baixando documento (url={media_url[:60] if media_url else 'vazio'}, filename={doc_filename!r})")
                doc_bytes = await _download_image(
                    media_url, message_id, chat_id, is_uazapi_msg,
                    "", media_key_b64, msg_type
                )
                print(f"[WA→Teams] Documento baixado: {len(doc_bytes)} bytes ({mimetype or 'application/octet-stream'})")
                teams_msg_ids.append(await teams_api.post_document_to_chat(
                    teams_chat_id,
                    sender_name=sender_name,
                    chat_name=group_name,
                    doc_bytes=doc_bytes,
                    mimetype=mimetype or "application/octet-stream",
                    filename=doc_filename or "documento",
                    wa_chat_id=chat_id,
                    wa_message_id=message_id,
                    caption=caption,
                    quote=quote,
                ))
                print("[WA→Teams] ✓ Documento enviado ao chat")
            except Exception as doc_err:
                print(f"[WA→Teams] Falha ao enviar documento ({doc_err}), enviando como texto")
                await _post_label_fallback()

        else:
            # Texto ou label de mídia
            teams_msg_ids.append(await teams_api.post_to_chat(
                teams_chat_id,
                sender_name=sender_name,
                chat_name=group_name,
                text=text or _media_label(msg_type, caption, media_ctx),
                wa_chat_id=chat_id,
                wa_message_id=message_id,
                quote=quote,
            ))
            print("[WA→Teams] ✓ Nova mensagem no chat")

    except Exception as e:
        print(f"[WA→Teams] Erro ao postar no Teams: {e}")

    # Guarda o vínculo WA↔Teams para que respostas futuras (nos dois sentidos) possam citar
    # esta mensagem. Em texto + imagem, as duas mensagens do Teams apontam para a mesma do WA.
    for teams_msg_id in teams_msg_ids:
        try:
            db.save_message_map({
                "wa_group_id": chat_id,
                "wa_group_name": group_name,
                "wa_sender_name": sender_name,
                "wa_sender_number": sender_number,
                "wa_message_id": message_id,
                "wa_message_text": display,
                "teams_message_id": teams_msg_id,
                "teams_chat_id": teams_chat_id,
            })
        except Exception as e:
            print(f"[WA→Teams] Falha ao gravar mapa da mensagem: {e}")

    # Registra qual grupo do WA corresponde a este chat do Teams (usado para enviar mensagens
    # diretas Teams→WA). Antes isso era descoberto lendo o rodapé [wa:] no eco da mensagem.
    if teams_msg_ids:
        try:
            db.save_thread(chat_id, teams_msg_ids[0], teams_chat_id)
        except Exception as e:
            print(f"[WA→Teams] Falha ao gravar vínculo do grupo: {e}")
