import asyncio
from datetime import datetime, timezone, timedelta

import teams.api as teams_api
from storage import db
from config import settings


async def setup_subscription() -> None:
    notification_url = f"{settings.webhook_base}/webhook/teams"
    existing = db.get_subscription()

    if existing:
        expires_at = datetime.fromisoformat(existing["expiration_datetime"].replace("Z", "+00:00"))
        thirty_min_from_now = datetime.now(timezone.utc) + timedelta(minutes=30)

        if expires_at > thirty_min_from_now:
            try:
                renewed = await teams_api.renew_subscription(existing["subscription_id"])
                db.save_subscription(
                    {
                        "subscription_id": renewed["id"],
                        "expiration_datetime": renewed["expirationDateTime"],
                        "resource": renewed["resource"],
                    }
                )
                print(f"[Subscription] Renovada | Expira: {renewed['expirationDateTime']}")
                asyncio.create_task(_renewal_loop(renewed["expirationDateTime"]))
                return
            except Exception as e:
                print(f"[Subscription] Falha ao renovar, recriando: {e}")

        await teams_api.delete_subscription(existing["subscription_id"])
        db.delete_subscription(existing["subscription_id"])

    sub = await teams_api.create_subscription(notification_url)
    db.save_subscription(
        {
            "subscription_id": sub["id"],
            "expiration_datetime": sub["expirationDateTime"],
            "resource": sub["resource"],
        }
    )
    print(f"[Subscription] Criada | ID: {sub['id']} | Expira: {sub['expirationDateTime']}")
    asyncio.create_task(_renewal_loop(sub["expirationDateTime"]))


async def _renewal_loop(expiration_datetime: str) -> None:
    expires_at = datetime.fromisoformat(expiration_datetime.replace("Z", "+00:00"))
    renew_at = expires_at - timedelta(minutes=30)
    delay = max((renew_at - datetime.now(timezone.utc)).total_seconds(), 300)

    print(f"[Subscription] Próxima renovação em {int(delay / 60)} minutos")
    await asyncio.sleep(delay)

    print("[Subscription] Renovando automaticamente...")
    try:
        await setup_subscription()
    except Exception as e:
        print(f"[Subscription] Erro na renovação automática: {e}")
