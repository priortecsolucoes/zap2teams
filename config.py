from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    port: int = 3000
    webhook_base_url: str

    uazapi_base_url: str
    uazapi_token: str
    uazapi_instance: str
    uazapi_webhook_secret: str = ""

    teams_tenant_id: str
    teams_client_id: str
    teams_client_secret: str
    teams_team_id: str
    teams_channel_id: str
    teams_notification_secret: str = "defaultsecret123"
    teams_chat_id: str
    teams_incoming_webhook_url: str = ""
    teams_reply_webhook_url: str = ""

    @property
    def uazapi_base(self) -> str:
        return self.uazapi_base_url.rstrip("/")

    @property
    def webhook_base(self) -> str:
        return self.webhook_base_url.rstrip("/")


settings = Settings()
