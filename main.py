import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import PlainTextResponse, Response

from config import settings
from storage.db import init_db
from teams.subscription import setup_subscription
import whatsapp.handler as wa_handler
import teams.handler as teams_handler


async def _setup_subscription_when_ready() -> None:
    # Aguarda o servidor estar aceitando conexões antes de registrar a subscription.
    # O Graph API valida o webhook imediatamente ao criar a subscription —
    # se o servidor ainda não estiver pronto, a validação falha com 400.
    await asyncio.sleep(2)
    try:
        await setup_subscription()
    except Exception as e:
        print(f"\n[AVISO] Falha ao criar subscription do Teams Graph API:")
        print(f"  {e}")
        print("  Mensagens do Teams NÃO serão recebidas.")
        print("  Verifique as credenciais no .env e as permissões do Azure AD.\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(_setup_subscription_when_ready())
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    from datetime import datetime
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    events = payload if isinstance(payload, list) else [payload]

    for event in events:
        data = event.get("data") or {}
        is_message = (
            event.get("event") in ("message", "messages.upsert")
            or event.get("type") == "message"
            or bool(data.get("key"))
        )
        print(f"[WA webhook] evento recebido | is_message={is_message} | event={str(event)[:120]}")
        if is_message:
            print("[WA webhook] agendando handle_incoming...")
            background_tasks.add_task(wa_handler.handle_incoming, event)

    return Response(content="OK", status_code=200)


@app.post("/webhook/teams")
async def teams_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    validationToken: str = None,
):
    if validationToken:
        print("[Teams→WA] Graph API validando subscription...")
        return PlainTextResponse(validationToken, status_code=200)

    body = await request.json()
    print(f"[Teams webhook] Recebido: {str(body)[:300]}")
    background_tasks.add_task(teams_handler.process_notifications, body)
    return Response(status_code=202)


if __name__ == "__main__":
    print()
    print("╔══════════════════════════════════════╗")
    print("║         Zap2Teams Iniciado           ║")
    print("╚══════════════════════════════════════╝")
    print(f"Porta        : {settings.port}")
    print(f"Webhook WA   : POST {settings.webhook_base}/webhook/whatsapp")
    print(f"Webhook Teams: POST {settings.webhook_base}/webhook/teams")
    print()
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=False)
