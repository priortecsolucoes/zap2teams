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
    teams_team_id: str = ""
    teams_channel_id: str = ""
    teams_notification_secret: str = "defaultsecret123"
    # Formato: "19:chatid1@thread.v2=Nome Grupo WA;19:chatid2@thread.v2=Outro Grupo"
    teams_chat_mappings: str = ""
    teams_incoming_webhook_url: str = ""
    teams_reply_webhook_url: str = ""

    @property
    def uazapi_base(self) -> str:
        return self.uazapi_base_url.rstrip("/")

    @property
    def webhook_base(self) -> str:
        return self.webhook_base_url.rstrip("/")

    @property
    def chat_mappings(self) -> dict[str, str]:
        """Retorna {teams_chat_id: wa_group_name}"""
        result: dict[str, str] = {}
        for pair in self.teams_chat_mappings.split(";"):
            pair = pair.strip()
            if "=" in pair:
                chat_id, name = pair.split("=", 1)
                result[chat_id.strip()] = name.strip()
        return result

    @property
    def wa_to_teams(self) -> dict[str, str]:
        """Retorna {wa_group_name: teams_chat_id}"""
        return {v: k for k, v in self.chat_mappings.items()}


settings = Settings()
