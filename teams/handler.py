import json
import re

import ai.watcher as ai_watcher
import whatsapp.api as wa_api
import teams.api as teams_api
from config import settings
from storage import db

# Referência oculta que toda mensagem vinda do WhatsApp carrega no Teams: [wa:chatId|msgId|remetente]
_WA_REF_RE = re.compile(r'\[wa:([^|\]]+)\|([^|\]]+)\|([^\]]+)\]')


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

    # Resposta em thread: responde no WA citando a mensagem-pai (que veio do WhatsApp).
    if message.get("messageType") != "message":
        return

    content: str = (message.get("body") or {}).get("content", "")
    if "📱" in content:
        return

    reply_text = _strip_html(content).strip()
    images = await _extract_images(message, teams_chat_id)
    if not reply_text and not images:
        return

    parent_message = await teams_api.get_chat_message(teams_chat_id, parent_message_id)
    parent_content: str = (parent_message.get("body") or {}).get("content", "")
    wa_match = _WA_REF_RE.search(parent_content)
    if not wa_match:
        print(f"[Teams→WA] Ref WA não encontrada na msg pai {parent_message_id}")
        return

    wa_chat_id = wa_match.group(1).strip()
    parent_wa_message_id = wa_match.group(2).strip()

    # Uma citação explícita dentro da thread tem prioridade sobre a mensagem-pai.
    quoted_wa_id = await _resolve_quoted_wa_id(message, teams_chat_id) or parent_wa_message_id
    await _relay_to_wa(message, teams_chat_id, wa_chat_id, reply_text, images, quoted_wa_id)


async def _route_direct_message(message: dict, teams_chat_id: str) -> None:
    """Mensagem solta no chat do Teams (fora de thread). Se o atendente usou "Responder"
    citando uma mensagem, a resposta sai no WhatsApp com citação nativa."""
    if message.get("messageType") != "message":
        return

    content: str = (message.get("body") or {}).get("content", "")
    reply_text = _strip_html(content).strip()
    images = await _extract_images(message, teams_chat_id)

    if not reply_text and not images:
        return

    wa_jid = db.find_wa_jid_by_teams_chat(teams_chat_id)
    if not wa_jid:
        wa_group_name = settings.chat_mappings.get(teams_chat_id, teams_chat_id[:30])
        print(f"[Teams→WA] JID WA não encontrado para '{wa_group_name}' — aguardando primeira msg WA")
        return

    quoted_wa_id = await _resolve_quoted_wa_id(message, teams_chat_id)
    await _relay_to_wa(message, teams_chat_id, wa_jid, reply_text, images, quoted_wa_id)


async def _relay_to_wa(
    message: dict,
    teams_chat_id: str,
    wa_jid: str,
    reply_text: str,
    images: list[tuple[bytes, str]],
    quoted_wa_id: str | None,
) -> None:
    """Envia texto/imagens do Teams para o WhatsApp, citando quoted_wa_id quando houver."""
    from_info = message.get("from") or {}
    sender_name: str = (from_info.get("user") or {}).get("displayName") or "Colaborador"
    quote_log = f" (citando {quoted_wa_id[:20]})" if quoted_wa_id else ""

    first_response: dict | None = None

    if reply_text:
        message_text = f"*{sender_name}:*\n{reply_text}"
        print(f'[Teams→WA] "{sender_name}"{quote_log} → {wa_jid[:30]} | "{reply_text[:80]}"')
        if quoted_wa_id:
            first_response = await wa_api.send_reply(wa_jid, quoted_wa_id, message_text)
        else:
            first_response = await wa_api.send_text(wa_jid, message_text)

    for img_bytes, mimetype in images:
        caption = f"*{sender_name}*" if not reply_text else ""
        # Sem texto, a primeira imagem leva a citação.
        reply_id = quoted_wa_id if (quoted_wa_id and first_response is None) else ""
        print(f'[Teams→WA] "{sender_name}" → imagem {mimetype} ({len(img_bytes)} bytes) → {wa_jid[:30]}')
        resp = await wa_api.send_image(wa_jid, img_bytes, mimetype, caption, reply_id=reply_id)
        if first_response is None:
            first_response = resp

    # Guarda o vínculo para que, se o cliente citar esta resposta no WhatsApp, o Teams
    # consiga apontar para a mensagem original do atendente.
    wa_message_id = wa_api.get_message_id(first_response or {})
    if wa_message_id and message.get("id"):
        try:
            db.save_message_map({
                "wa_group_id": wa_jid,
                "wa_group_name": settings.chat_mappings.get(teams_chat_id, ""),
                "wa_sender_name": sender_name,
                "wa_sender_number": "",
                "wa_message_id": wa_message_id,
                "wa_message_text": reply_text or "📷 [Foto]",
                "teams_message_id": message["id"],
                "teams_chat_id": teams_chat_id,
            })
        except Exception as e:
            print(f"[Teams→WA] Falha ao gravar mapa da mensagem: {e}")

    db.update_thread_timestamp(wa_jid)
    await ai_watcher.on_our_response(wa_jid)
    print(f"[Teams→WA] ✓ Enviado para {wa_jid[:30]}")


def _find_message_reference(message: dict) -> str | None:
    """Retorna o ID da mensagem do Teams citada via "Responder" (attachment messageReference)."""
    for att in message.get("attachments") or []:
        if att.get("contentType") != "messageReference":
            continue
        ref_id = att.get("id")
        if not ref_id:
            try:
                ref_id = json.loads(att.get("content") or "{}").get("messageId")
            except ValueError:
                ref_id = None
        if ref_id:
            return ref_id
    return None


async def _resolve_quoted_wa_id(message: dict, teams_chat_id: str) -> str | None:
    """Traduz a mensagem citada no Teams para o ID dela no WhatsApp.
    Ordem: nosso mapa WA↔Teams → referência [wa:...] escondida na própria mensagem citada."""
    quoted_teams_id = _find_message_reference(message)
    if not quoted_teams_id:
        return None

    row = db.find_by_teams_message_id(quoted_teams_id)
    if row:
        return row["wa_message_id"]

    try:
        quoted = await teams_api.get_chat_message(teams_chat_id, quoted_teams_id)
        wa_match = _WA_REF_RE.search((quoted.get("body") or {}).get("content", ""))
        if wa_match:
            return wa_match.group(2).strip()
    except Exception as e:
        print(f"[Teams→WA] Não foi possível ler a mensagem citada {quoted_teams_id}: {e}")

    print(f"[Teams→WA] Mensagem citada {quoted_teams_id} sem correspondente no WhatsApp, enviando sem citar")
    return None


async def _extract_images(message: dict, teams_chat_id: str) -> list[tuple[bytes, str]]:
    """Extrai imagens de uma mensagem do Teams. Retorna lista de (bytes, mimetype)."""
    results = []
    msg_id = message.get("id", "")
    content = (message.get("body") or {}).get("content", "")

    # Imagens inline coladas ou arrastadas (hostedContents)
    for hc_id in re.findall(r'hostedContents/([^/\s"\']+)/\$value', content):
        try:
            img_bytes, ct = await teams_api.download_graph_binary(
                f"/chats/{teams_chat_id}/messages/{msg_id}/hostedContents/{hc_id}/$value"
            )
            if img_bytes:
                results.append((img_bytes, ct.split(";")[0] or "image/jpeg"))
                print(f"[Teams→WA] Hosted content baixado: {len(img_bytes)} bytes ({ct.split(';')[0]})")
        except Exception as e:
            print(f"[Teams→WA] Hosted content {hc_id[:30]} falhou: {e}")

    # Imagens enviadas como arquivo anexo
    for att in message.get("attachments") or []:
        if att.get("contentType") != "reference":
            continue
        name = att.get("name", "").lower()
        if not any(name.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            continue
        ct_url = att.get("contentUrl", "")
        if not ct_url:
            continue
        try:
            img_bytes = await wa_api.download_media(ct_url)
            mime = "image/png" if name.endswith(".png") else "image/gif" if name.endswith(".gif") else "image/jpeg"
            results.append((img_bytes, mime))
            print(f"[Teams→WA] Anexo '{name}' baixado: {len(img_bytes)} bytes")
        except Exception as e:
            print(f"[Teams→WA] Anexo '{name}' falhou: {e}")

    return results


def _maybe_save_thread(message_id: str, message: dict, teams_chat_id: str = "") -> None:
    content: str = (message.get("body") or {}).get("content", "")
    wa_match = _WA_REF_RE.search(content)
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
