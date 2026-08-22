import re
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from config import settings

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_NO_REPLY_TOKEN = "SEM_RESPOSTA"

# Casa e remove uma saudação que o modelo eventualmente tenha escrito sozinho (ele não sabe a
# hora real do relógio) — sempre substituída pela saudação calculada em código, que é correta.
_LEADING_GREETING_RE = re.compile(
    r"^(bom dia|boa tarde|boa noite)[,!.]?\s*(pessoal[,!.]?\s*)?", re.IGNORECASE
)


def _saudacao() -> str:
    try:
        hour = datetime.now(ZoneInfo("America/Sao_Paulo")).hour
    except Exception:
        hour = datetime.now().hour
    if hour < 12:
        return "Bom dia"
    if hour < 18:
        return "Boa tarde"
    return "Boa noite"


def _greeting_fallback() -> str:
    return f"{_saudacao()} pessoal, já estamos analisando e assim que possível retornamos."


def _ensure_greeting(text: str) -> str:
    """Garante que a mensagem comece com a saudação correta do horário atual — é sempre a
    1ª mensagem da IA na janela. Não confia na saudação que o modelo possa ter escrito, pois
    o modelo não tem acesso ao horário real."""
    stripped = text.strip()
    body = _LEADING_GREETING_RE.sub("", stripped, count=1).strip() or stripped
    if body and body[0].islower():
        body = body[0].upper() + body[1:]
    return f"{_saudacao()} pessoal! {body}"


def _build_prompt(customer_name: str, messages: list[str]) -> tuple[str, str]:
    fallback = _greeting_fallback()
    context_block = f"\nContexto do negócio:\n{settings.ai_context}\n" if settings.ai_context else ""
    system = (
        f"Você é {settings.ai_assistant_name}, atendente de suporte via WhatsApp. "
        "Um cliente enviou mensagens em um grupo de suporte e ainda não foi respondido por um atendente humano.\n"
        f"{context_block}\n"
        "Sua tarefa: analisar as mensagens do cliente e escolher UMA destas 3 ações:\n\n"
        "AÇÃO 1 — PERGUNTA DE TRIAGEM (ação padrão sempre que houver qualquer indício de problema técnico, "
        "dúvida sobre o sistema ou pedido): mencionar um bug, erro, travamento, dúvida de uso ou solicitação "
        "já é informação suficiente para agir — não espere uma descrição completa. Comece com a saudação do "
        "horário atual (ex: \"Bom dia pessoal!\") seguida de 1 ou 2 perguntas breves e objetivas para levantar "
        "o que falta (desde quando, qual erro exato aparece, em qual tela/processo, para qual cliente/pedido, etc.).\n"
        "AÇÃO 2 — SAUDAÇÃO PADRÃO: use SOMENTE quando a mensagem claramente pede ajuda/suporte mas é vaga demais "
        'para até formular uma pergunta (ex: "alguém pode ajudar?" sem nenhum outro contexto). '
        f'Nesse caso retorne exatamente: "{fallback}"\n'
        "AÇÃO 3 — NÃO RESPONDER: use quando as mensagens forem só conversa social — cumprimento, agradecimento, "
        "figurinha, teste — sem qualquer menção a problema técnico, dúvida ou pedido. "
        f'Nesse caso retorne exatamente e apenas: "{_NO_REPLY_TOKEN}"\n\n'
        "Exemplos (a saudação exata do horário atual deve ser usada, não necessariamente a do exemplo):\n"
        '- "o robô de faturamento parou de rodar hoje de manhã" → AÇÃO 1: "Bom dia pessoal! Desde que horário '
        'o robô parou de rodar? Aparece alguma mensagem de erro?"\n'
        '- "sistema dando erro 500 ao gerar boleto do cliente XPTO" → AÇÃO 1: "Boa tarde! Esse erro acontece '
        'com outros clientes também ou só com o XPTO? Desde quando está acontecendo?"\n'
        '- "gente o robô travou de novo" → AÇÃO 1: "Boa noite pessoal! Em qual etapa o robô travou dessa vez? '
        'Apareceu alguma mensagem de erro?"\n'
        '- "alguém pode ajudar?" (sem mais contexto) → AÇÃO 2\n'
        '- "oi pessoal" / "bom dia" / "muito obrigado!" → AÇÃO 3\n\n'
        "Regras:\n"
        "- Responda em português do Brasil.\n"
        "- Seja breve, cordial e profissional, seguindo o contexto do negócio acima quando fornecido.\n"
        "- Toda mensagem enviada (ações 1 e 2) deve começar com a saudação do horário atual (\"Bom dia\"/\"Boa "
        "tarde\"/\"Boa noite\" + \"pessoal\"), pois é a primeira mensagem da conversa hoje.\n"
        "- Não invente soluções, prazos ou promessas — você está apenas triando/acolhendo; um atendente humano vai continuar depois.\n"
        "- Não repita literalmente as mensagens do cliente.\n"
        "- Não assine a mensagem nem inclua nome antes da saudação (o nome já é adicionado separadamente).\n"
        f'- Retorne APENAS o texto da mensagem (ou "{_NO_REPLY_TOKEN}", quando aplicável), sem aspas e sem markdown.'
    )
    if messages:
        listed = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(messages))
        user = f"Mensagens do cliente ({customer_name}), em ordem cronológica:\n{listed}"
    else:
        user = f"O cliente ({customer_name}) enviou mensagem(ns) sem texto extraível (mídia)."
    return system, user


async def generate_reply(customer_name: str, messages: list[str]) -> str | None:
    """Retorna o texto da mensagem a enviar, ou None se a IA decidir que nada precisa ser enviado."""
    fallback = _greeting_fallback()

    if not settings.openai_api_key:
        return fallback

    system, user = _build_prompt(customer_name, messages)

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _OPENAI_URL,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 200,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = (data["choices"][0]["message"]["content"] or "").strip()
        if not text:
            return fallback
        if text.strip('"').strip().upper() == _NO_REPLY_TOKEN:
            return None
        return _ensure_greeting(text)
    except Exception as e:
        print(f"[AI service] Falha ao gerar resposta via OpenAI ({e}), usando saudação padrão")
        return fallback
