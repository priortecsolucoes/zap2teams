import asyncio
import time

import ai.service as ai_service
import whatsapp.api as wa_api
from config import settings
from storage import db

_CHECK_INTERVAL_SECONDS = 30


async def on_incoming_customer_message(
    wa_chat_id: str, sender_number: str, sender_name: str, text: str
) -> None:
    now = int(time.time())
    state = db.get_ai_state(wa_chat_id)
    last_activity = state["last_activity_at"] if state else 0
    window_already_open = bool(state and state["window_open"])

    if not window_already_open and (now - last_activity) >= settings.ai_inactivity_window_seconds:
        db.open_ai_window(wa_chat_id, now, sender_number, sender_name)
        print(f"[AI watcher] Janela de espera aberta em {wa_chat_id[:30]} (cliente: {sender_name})")

    if text:
        db.log_ai_customer_message(wa_chat_id, sender_number, sender_name, text, now)

    db.touch_ai_activity(wa_chat_id, now)


async def on_our_response(wa_chat_id: str) -> None:
    if not wa_chat_id:
        return
    db.mark_our_response(wa_chat_id, int(time.time()))


async def _handle_due_window(window: dict) -> None:
    wa_chat_id = window["wa_chat_id"]
    customer_number = window["window_customer_number"] or ""
    customer_name = window["window_customer_name"] or "Cliente"
    since_ts = window["window_opened_at"] or 0

    messages = db.get_ai_customer_messages_since(wa_chat_id, customer_number, since_ts)
    reply_text = await ai_service.generate_reply(customer_name, messages)

    if reply_text is None:
        # IA decidiu que as mensagens são só conversa social, sem bug/dúvida/pedido — não envia nada.
        db.close_ai_window(wa_chat_id)
        print(f"[AI watcher] Janela em {wa_chat_id[:30]} não exigia resposta, nada enviado")
        return

    full_text = f"*{settings.ai_assistant_name}*\n{reply_text}"

    # Só marca como notificado após o envio ter sucesso — se o envio falhar (ex: uazapi
    # fora do ar), a janela permanece aberta e será tentada de novo no próximo ciclo.
    await wa_api.send_text(wa_chat_id, full_text)
    print(f"[AI watcher] ✓ Mensagem de acolhimento enviada em {wa_chat_id[:30]}")
    db.mark_window_notified(wa_chat_id, int(time.time()))


async def _run_sweep() -> None:
    if not settings.ai_enabled or not settings.openai_api_key:
        return
    due = db.get_due_ai_windows(settings.ai_response_timeout_seconds)
    for window in due:
        try:
            await _handle_due_window(window)
        except Exception as e:
            print(f"[AI watcher] Erro ao processar janela {window.get('wa_chat_id', '')[:30]}: {e}")


async def sweep_loop() -> None:
    print(
        f"[AI watcher] Ativo | janela de silêncio: {settings.ai_inactivity_window_minutes}min "
        f"| timeout de resposta: {settings.ai_response_timeout_minutes}min "
        f"| nome: {settings.ai_assistant_name}"
    )
    while True:
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
        try:
            await _run_sweep()
        except Exception as e:
            print(f"[AI watcher] Erro no sweep: {e}")
