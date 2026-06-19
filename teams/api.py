import asyncio
import time

import httpx

from config import settings

_token_cache: dict = {"token": None, "expiry": 0.0}
_token_lock = asyncio.Lock()


async def _get_access_token() -> str:
    async with _token_lock:
        if _token_cache["token"] and time.time() < _token_cache["expiry"] - 60:
            return _token_cache["token"]

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"https://login.microsoftonline.com/{settings.teams_tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.teams_client_id,
                    "client_secret": settings.teams_client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

        _token_cache["token"] = data["access_token"]
        _token_cache["expiry"] = time.time() + data["expires_in"]
        return _token_cache["token"]


async def graph_request(method: str, path: str, body: dict | None = None) -> dict:
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(
            method,
            f"https://graph.microsoft.com/v1.0{path}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body,
        )
        if not resp.is_success:
            raise Exception(f"Graph API {resp.status_code} em {method} {path}: {resp.text}")
        return resp.json() if resp.content else {}


async def post_to_channel(
    group_id: str,
    group_name: str,
    sender_name: str,
    sender_number: str,
    message_text: str,
    wa_message_id: str,
) -> None:
    clean_number = sender_number.replace("@s.whatsapp.net", "").replace("@g.us", "")
    safe_sender = sender_name.replace("|", "").replace("[", "").replace("]", "")
    ref = f"[wa:{group_id}|{wa_message_id}|{safe_sender}]"
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"📱 Mensagem WhatsApp — {group_name}",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "FactSet",
                "facts": [{"title": "De:", "value": f"{sender_name} (+{clean_number})"}],
            },
            {
                "type": "TextBlock",
                "text": message_text,
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": "↩ Responda nesta thread para responder ao cliente.",
                "wrap": True,
                "isSubtle": True,
            },
            {
                "type": "TextBlock",
                "text": ref,
                "wrap": False,
                "isSubtle": True,
                "size": "Small",
            },
        ],
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            settings.teams_incoming_webhook_url,
            json=card,
        )
        if not resp.is_success:
            raise Exception(f"Incoming Webhook {resp.status_code}: {resp.text}")


async def post_reply_to_thread(parent_message_id: str, sender_name: str, text: str) -> None:
    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    await graph_request(
        "POST",
        f"/teams/{settings.teams_team_id}/channels/{settings.teams_channel_id}"
        f"/messages/{parent_message_id}/replies",
        {
            "body": {
                "contentType": "html",
                "content": f"<p><strong>📱 {esc(sender_name)}:</strong> {esc(text)}</p>",
            }
        },
    )


async def get_message(message_id: str) -> dict:
    return await graph_request(
        "GET",
        f"/teams/{settings.teams_team_id}/channels/{settings.teams_channel_id}"
        f"/messages/{message_id}",
    )


async def get_reply(parent_message_id: str, reply_id: str) -> dict:
    return await graph_request(
        "GET",
        f"/teams/{settings.teams_team_id}/channels/{settings.teams_channel_id}"
        f"/messages/{parent_message_id}/replies/{reply_id}",
    )


async def create_subscription(notification_url: str) -> dict:
    from datetime import datetime, timezone, timedelta

    expiration = (datetime.now(timezone.utc) + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return await graph_request(
        "POST",
        "/subscriptions",
        {
            "changeType": "created",
            "notificationUrl": notification_url,
            "lifecycleNotificationUrl": notification_url,
            "resource": f"teams/{settings.teams_team_id}/channels/{settings.teams_channel_id}/messages",
            "expirationDateTime": expiration,
            "clientState": settings.teams_notification_secret,
        },
    )


async def list_subscriptions() -> list[dict]:
    result = await graph_request("GET", "/subscriptions")
    return result.get("value", [])


async def renew_subscription(subscription_id: str) -> dict:
    from datetime import datetime, timezone, timedelta

    expiration = (datetime.now(timezone.utc) + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return await graph_request(
        "PATCH",
        f"/subscriptions/{subscription_id}",
        {"expirationDateTime": expiration},
    )


async def update_subscription_url(subscription_id: str, notification_url: str) -> dict:
    from datetime import datetime, timezone, timedelta

    expiration = (datetime.now(timezone.utc) + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return await graph_request(
        "PATCH",
        f"/subscriptions/{subscription_id}",
        {
            "expirationDateTime": expiration,
            "notificationUrl": notification_url,
            "lifecycleNotificationUrl": notification_url,
        },
    )


async def delete_subscription(subscription_id: str) -> None:
    try:
        await graph_request("DELETE", f"/subscriptions/{subscription_id}")
    except Exception:
        pass
