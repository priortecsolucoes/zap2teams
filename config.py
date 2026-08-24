from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    port: int = 3000
    webhook_base_url: str

    uazapi_base_url: str
    uazapi_token: str
    uazapi_instance: str
    uazapi_webhook_secret: str = ""
    # Número conectado à instância uazapi (só dígitos, ex: 5511999999999). Usado para reconhecer
    # como "nossa" uma mensagem enviada manualmente pelo app/celular (não via API) — a uazapi só
    # marca wasSentByApi=true quando o envio sai pela API (ex: via Teams).
    uazapi_own_number: str = ""

    teams_tenant_id: str
    teams_client_id: str
    teams_client_secret: str
    teams_team_id: str = ""
    teams_channel_id: str = ""
    teams_notification_secret: str = "defaultsecret123"
    # Formato: "19:chatid1@thread.v2=Nome Grupo WA;19:chatid2@thread.v2=Outro Grupo"
    teams_chat_mappings: str = ""
    # Formato: "19:chatid1@thread.v2=120363@g.us;19:chatid2@thread.v2=120364@g.us"
    teams_wa_jids: str = ""
    teams_incoming_webhook_url: str = ""
    teams_reply_webhook_url: str = ""

    # ─────────────────────────────────────────────
    # Camada de IA (acolhimento automático no WhatsApp)
    # ─────────────────────────────────────────────
    ai_enabled: bool = True
    # X: minutos de silêncio no grupo exigidos para uma msg de cliente abrir uma "janela de espera"
    ai_inactivity_window_minutes: int = 30
    # Y: minutos após a abertura da janela sem resposta nossa até a IA intervir
    ai_response_timeout_minutes: int = 15
    # Nome exibido em negrito antes da mensagem da IA
    ai_assistant_name: str = "Assistente"
    # Contexto de negócio injetado no prompt: quem é a empresa, produtos, tom de voz, regras etc.
    ai_context: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @property
    def ai_inactivity_window_seconds(self) -> int:
        return self.ai_inactivity_window_minutes * 60

    @property
    def ai_response_timeout_seconds(self) -> int:
        return self.ai_response_timeout_minutes * 60

    @property
    def uazapi_own_number_digits(self) -> str:
        return "".join(c for c in self.uazapi_own_number if c.isdigit())

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

    @property
    def wa_jid_mappings(self) -> dict[str, str]:
        """Retorna {teams_chat_id: wa_jid} para seed do banco."""
        result: dict[str, str] = {}
        for pair in self.teams_wa_jids.split(";"):
            pair = pair.strip()
            if "=" in pair:
                chat_id, jid = pair.split("=", 1)
                result[chat_id.strip()] = jid.strip()
        return result


settings = Settings()
