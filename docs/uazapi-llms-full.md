# uazapi API 2.6.9: guias consolidados

Escopo: conceitos e guias estáveis; endpoints completos disponíveis individualmente em llms.txt.

<!-- source: https://docs.uazapi.com/docs/collections/overview.md -->


# Integre seu sistema ao WhatsApp

A uazapi oferece uma API HTTP para gerenciar sessões do WhatsApp, enviar mensagens e acompanhar eventos.

## O caminho de uma integração

Seu sistema usa a **Server URL** para chegar ao servidor da API. O **token da instância** identifica a sessão do WhatsApp. Um **webhook** entrega eventos de volta ao seu sistema.

1. Confirme sua [Server URL](/docs/server-url).
2. Entenda [instâncias e sessões](/docs/instances) e [credenciais](/docs/authentication).
3. Siga o [início rápido](/docs/getting-started).
4. Configure [webhooks](/docs/integrations-webhooks) e leia sobre [recuperação de falhas](/docs/errors-and-retries).

## Escolha como integrar

Use a [referência da API](/api) e os exemplos HTTP de cada operação. O contrato OpenAPI também pode ser usado para gerar um cliente na linguagem da sua aplicação.

As credenciais de administração do servidor devem permanecer no backend da sua aplicação.

## Documentação para agentes e IA

- [`llms.txt`](/llms.txt): índice resumido com links para guias e referências.
- [`llms-full.txt`](/llms-full.txt): contexto consolidado dos guias públicos.

Use o arquivo resumido para descoberta e o consolidado quando precisar fornecer contexto documental completo a um agente.

---

<!-- source: https://docs.uazapi.com/docs/collections/server-url.md -->


# O que é Server URL?

A Server URL é o endereço base do servidor **da API** que hospeda suas instâncias. Cada chamada acrescenta uma rota a esse endereço.

```text
Server URL: https://seu-servidor.example
Rota:       /instance/status
Chamada:    https://seu-servidor.example/instance/status
```

O domínio acima é ilustrativo. Use o endereço fornecido na configuração do seu ambiente ou pelo administrador do servidor; não presuma que o servidor de demonstração hospeda sua instância.

## Endereços diferentes

| Endereço | Para que serve |
|---|---|
| Server URL | Seu sistema chama a API |
| Site da documentação | Você lê guias e consulta contratos |
| URL do webhook | A API chama seu sistema para entregar eventos |
| URL de proxy | A sessão usa o proxy configurado para sua conexão externa |

## Como conferir

Use o token da instância e consulte o estado:

```bash
curl "$BASE_URL/instance/status" -H "token: $INSTANCE_TOKEN"
```

`BASE_URL` deve conter protocolo e host corretos, normalmente HTTPS, sem duplicar a rota. Um token de outro servidor não deve ser tratado como válido nesse endereço. Em 401, confira a combinação servidor/credencial; em falhas de DNS ou TLS, confira primeiro o endereço e a conectividade.

Continue com [instância](/docs/instances) e [autenticação](/docs/authentication).

---

<!-- source: https://docs.uazapi.com/docs/collections/instances.md -->


# O que é uma instância?

Uma instância representa uma sessão do WhatsApp dentro do servidor da API. Um servidor pode hospedar várias instâncias. Cada instância possui token, configurações e dados associados à sua sessão.

## Servidor, instância e número

- **Servidor:** o ambiente acessado pela Server URL.
- **Instância:** o recurso que guarda e controla a sessão.
- **Número:** a conta do WhatsApp conectada à sessão.
- **Token:** a credencial usada nas operações daquela instância.

Criar uma instância não conclui o pareamento. É preciso iniciar a conexão e seguir o fluxo de QR Code ou código de pareamento.

## Estados

| Estado | Significado |
|---|---|
| disconnected | Sem conexão ativa |
| connecting | Conexão ou pareamento em andamento |
| connected | Sessão conectada |
| hibernated | Sessão pausada com credenciais preservadas |

Consulte a resposta de `/instance/status` antes de enviar. Uma sessão conectada não garante que toda operação será aceita pelo WhatsApp; trate a resposta específica da operação.

## Integração com vários clientes

No backend da sua aplicação, associe o usuário/cliente somente às instâncias que ele pode controlar. Nunca escolha um token apenas com base em um ID enviado pelo navegador. O `admintoken` possui alcance administrativo e não substitui essa autorização da aplicação.

Siga o [início rápido](/docs/getting-started). Para erros e reconexão, consulte [confiabilidade](/docs/errors-and-retries).

---

<!-- source: https://docs.uazapi.com/docs/collections/getting-started.md -->


# Início rápido

Este fluxo cria uma instância, inicia a conexão e envia uma mensagem. Os
comandos abaixo representam código de backend ou terminal. Substitua
`BASE_URL`, `ADMIN_TOKEN`, `INSTANCE_TOKEN` e o número de destino pelos valores
do seu ambiente.

## 1. Criar uma instância

Esta operação é administrativa e deve acontecer somente no servidor da sua aplicação.

```bash
curl -X POST "$BASE_URL/instance/create" \
  -H "Content-Type: application/json" \
  -H "admintoken: $ADMIN_TOKEN" \
  -d '{"name":"minha-instancia"}'
```

Guarde o campo `token` retornado. Ele autentica apenas a instância criada.

## 2. Conectar ao WhatsApp

Sem `phone`, a API inicia o fluxo por QR Code. Com `phone`, inicia o fluxo por código de pareamento.

```bash
curl -X POST "$BASE_URL/instance/connect" \
  -H "Content-Type: application/json" \
  -H "token: $INSTANCE_TOKEN" \
  -d '{}'
```

Consulte o estado até receber `connected`:

```bash
curl "$BASE_URL/instance/status" \
  -H "token: $INSTANCE_TOKEN"
```

Não faça polling agressivo. A interface também pode acompanhar mudanças pelo webhook de `connection` ou por SSE.

## 3. Enviar a primeira mensagem

Use o número internacional com código do país, sem `+`, espaços ou pontuação.

```bash
curl -X POST "$BASE_URL/send/text" \
  -H "Content-Type: application/json" \
  -H "token: $INSTANCE_TOKEN" \
  -d '{
    "number": "5511999999999",
    "text": "Olá! Esta mensagem foi enviada pela API."
  }'
```

## 4. Receber eventos

Configure um webhook da instância. O filtro `wasSentByApi` evita que uma automação responda às próprias mensagens e crie um loop.

```bash
curl -X POST "$BASE_URL/webhook" \
  -H "Content-Type: application/json" \
  -H "token: $INSTANCE_TOKEN" \
  -d '{
    "enabled": true,
    "url": "https://seu-sistema.example/webhooks/uazapi",
    "events": ["messages", "messages_update", "connection"],
    "excludeMessages": ["wasSentByApi"]
  }'
```

## Próximos passos

- Consulte **Autenticação e segurança** antes de expor a integração aos seus clientes.
- Use a referência OpenAPI para verificar o schema completo de cada operação.
- Leia **Webhooks e callbacks** para escolher entre webhook e SSE.
- Use `POST /chat/find` e `POST /message/find` para montar uma experiência de conversas.

---

<!-- source: https://docs.uazapi.com/docs/collections/authentication.md -->


# Autenticação e segurança

A API possui duas credenciais com alcances diferentes. Ambas são credenciais
bearer: quem obtiver o valor recebe as permissões correspondentes.

## Escolha antes de integrar

| Cenário | Credencial no navegador | Integração recomendada |
|---|---|---|
| Cliente administra somente a própria instância | `token` da instância | frontend chama a API da instância |
| Painel privado cujos usuários administram o servidor inteiro | `admintoken`, com exposição aceita explicitamente | frontend chama a API administrativa |
| SaaS multi-tenant ou painel entregue a clientes | Nenhuma credencial da API | frontend chama o backend; backend chama a API |

Tudo que chega ao navegador pode ser lido pelo usuário, DevTools, extensões e
scripts executados na página. Variáveis `NEXT_PUBLIC_*`, `VITE_*` e similares
não protegem segredos.

## `token` da instância

O header `token` autoriza operações de uma única instância: conexão, mensagens, chats, grupos, contatos, webhooks e demais recursos associados àquele número.

```http
token: INSTANCE_TOKEN
```

O token pode ser usado diretamente em um dashboard no navegador quando o
usuário autenticado é o dono daquela instância e já pode executar todas as
operações dela. O backend do seu SaaS deve validar o tenant antes de entregar o
token; não confie apenas no estado da interface.

Prefira manter o token em memória durante a sessão. Não o coloque no bundle,
em código versionado, logs ou analytics. Persistir em `localStorage` aumenta o
impacto de XSS e extensões maliciosas.

## `admintoken`

O header `admintoken` administra o servidor e todas as instâncias. Ele permite operações como criar/listar instâncias, atualizar campos administrativos e rotacionar credenciais.

```http
admintoken: ADMIN_TOKEN
```

Por padrão, mantenha o `admintoken` no backend. Um painel administrativo pode
usá-lo diretamente no navegador somente quando **todo usuário desse painel já
é administrador do servidor inteiro** e a exposição do token é uma decisão
aceita explicitamente.

Nunca use esse modo em SaaS multi-tenant, painel entregue a clientes,
dispositivo compartilhado ou aplicação com scripts de terceiros. Nesses casos,
a interface chama o backend do SaaS, que valida usuário, tenant e permissão
antes de usar a credencial.

## SSE

O endpoint `/sse` aceita o token da instância na query string porque a API nativa `EventSource` não permite definir headers arbitrários:

```text
/sse?token=INSTANCE_TOKEN&events=chats,messages
```

URLs podem aparecer em logs, histórico e ferramentas de observabilidade. Use HTTPS, evite registrar a query completa e prefira um proxy autenticado do seu backend quando o stream for aberto pelo navegador.

## Armazenamento e rotação

- Armazene credenciais criptografadas ou em um secret manager.
- Não use `NEXT_PUBLIC_*`, `VITE_*` ou equivalentes para tokens.
- Redija `token`, `admintoken` e URLs SSE antes de registrar requests.
- Rotacione o token de instância por `POST /instance/token/rotate` quando houver exposição.
- Rotacione o token administrativo por `POST /admin/token/rotate` seguindo o intervalo aceito pela API.
- Depois da rotação, atualize consumidores e invalide caches imediatamente.

## Matriz rápida

| Operação | Credencial |
|---|---|
| Criar e listar instâncias | `admintoken` |
| Enviar mensagens | `token` |
| Consultar chats e contatos | `token` |
| Webhook por instância | `token` |
| Webhook global | `admintoken` |
| Administração do servidor | `admintoken` |

O OpenAPI é a fonte final para a segurança de cada rota; uma operação pode sobrescrever o requisito global.

---

<!-- source: https://docs.uazapi.com/docs/collections/concepts.md -->


# Conceitos e identificadores

## Servidor e instância

Um servidor pode hospedar várias instâncias. Cada instância representa uma sessão do WhatsApp, possui seu próprio `token` e mantém chats, mensagens, contatos e configurações isolados.

Estados principais:

- `disconnected`: não há conexão ativa;
- `connecting`: QR Code ou pareamento em andamento;
- `connected`: sessão autenticada e pronta;
- `hibernated`: sessão pausada, com credenciais preservadas;
- `registering`: registro nativo em andamento;
- `registration_conflict`: registro concluído com conflito de número ativo.

Antes de enviar, verifique o estado retornado por `/instance/status`.

## Identificadores de conversa

O campo `number` de várias operações aceita mais de um formato:

| Formato | Uso |
|---|---|
| `5511999999999` | contato por número internacional |
| `5511999999999@s.whatsapp.net` | JID de contato |
| `...@lid` | identificador alternativo de usuário |
| `...@g.us` | grupo |
| `...@newsletter` | canal/newsletter |

Não remova o sufixo de JIDs de grupo, LID ou newsletter. Quando a resposta fornecer um identificador completo, preserve-o como valor opaco.

## Mensagens e histórico

Depois da conexão, mensagens enviadas e recebidas são persistidas e podem ser consultadas por `/message/find` e `/chat/find`. Durante a conexão inicial, o histórico sincronizado também pode chegar pelo evento `history`.

IDs de mensagem devem ser tratados como strings. Algumas operações aceitam tanto o ID curto quanto o identificador completo retornado pela API; reutilize preferencialmente o valor recebido.

## Paginação

Listas grandes vêm em páginas. A maioria das rotas usa `limit` (itens por página) e `offset` (quantos itens pular) e devolve o objeto `pagination`:

```json
"pagination": { "totalRecords": 230, "limit": 100, "offset": 100, "hasMore": true, "nextOffset": 200 }
```

Para ler a lista inteira, comece com `offset: 0` e repita a chamada com `offset` igual ao `nextOffset` enquanto `hasMore` for `true`.

| Rotas | Como paginar |
|---|---|
| [`POST /chat/find`](/endpoint/post/chat~find), [`POST /contacts/list`](/endpoint/post/contacts~list), [`POST /group/list`](/endpoint/post/group~list), [`POST /sender/listmessages`](/endpoint/post/sender~listmessages), [`POST /message/status`](/endpoint/post/message~status) | `limit` e `offset`, com `pagination` e o total em `totalRecords` |
| [`POST /message/find`](/endpoint/post/message~find) | `limit` e `offset`, com `pagination` sem o total |
| [`POST /newsletter/search`](/endpoint/post/newsletter~search), [`POST /business/catalog/list`](/endpoint/post/business~catalog~list), [`GET /business/catalog/collection/list`](/endpoint/get/business~catalog~collection~list) | `after` com o valor que a página anterior devolveu (`response.after` ou `response.next`), copiado sem alterar; quando ele não vem, acabou |
| [`POST /message/history-sync`](/endpoint/post/message~history-sync) | `count` pede um lote ao celular; `has_more` diz se o celular declarou mensagens mais antigas, e `next_request` traz o pedido seguinte |

Mensagens e conversas novas podem chegar enquanto você pagina e deslocar a lista: um item pode se repetir entre duas páginas. Descarte repetidos pelo ID.

## Tempo real

- **Webhook:** melhor para integração servidor a servidor e processamento durável.
- **SSE:** melhor para atualizar uma interface enquanto ela está aberta.

Uma aplicação estilo WhatsApp Web normalmente usa endpoints de consulta para o estado inicial e SSE para mudanças incrementais. Webhooks continuam recomendados para automações que não podem depender de uma aba aberta.

---

<!-- source: https://docs.uazapi.com/docs/collections/proxy.md -->


# Proxy da instância

Um proxy é um intermediário na conexão de rede. Na configuração da instância, ele controla como a sessão acessa o serviço externo. Ele não é a Server URL usada pelo seu sistema para chamar a API.

## Preciso configurar?

Configure um proxy quando seu ambiente ou sua operação exigir uma saída de rede específica. Confirme as opções disponíveis no servidor; não preencha um proxy aleatório para tentar resolver um erro de autenticação da API.

## Diferentes usos da palavra proxy

- **Proxy da sessão:** configurado na instância para sua conexão externa.
- **Reverse proxy:** infraestrutura na frente do servidor da API, por exemplo para HTTPS.
- **Backend intermediário do seu SaaS:** valida o usuário e chama a API sem expor credenciais administrativas.

## Consultar e alterar

Use a referência de `GET /instance/proxy` e `POST /instance/proxy` em [API](/api). Confira os campos e opções do contrato da API antes de alterar; disponibilidade de proxy interno depende da configuração do servidor.

Para escolher uma região já na [criação da instância](/endpoint/post/instance~create),
consulte [países](/endpoint/get/proxy-managed~countries) e
[cidades](/endpoint/get/proxy-managed~cities). Envie os valores retornados em
`proxy_managed_country`, `proxy_managed_state` (quando houver) e
`proxy_managed_city`.

Alterar a configuração pode afetar a conexão. Confira o estado antes e depois. Proteja usuário, senha e endereço do proxy; não os inclua em exemplos compartilhados ou logs públicos.

## Diagnóstico

Confira endereço, porta, credenciais e disponibilidade do proxy. Diferencie falha de conexão da sessão de uma resposta 401 ao chamar a API. Um proxy não garante entrega de mensagens nem elimina limites aplicados pelo provedor.

---

<!-- source: https://docs.uazapi.com/docs/collections/integrations.md -->


# Integrações

A API pode alimentar CRMs, plataformas de atendimento, automações, painéis de
campanhas e interfaces próprias. Cada instância mantém uma sessão e uma
credencial separadas, permitindo atender vários clientes com isolamento.

## Fluxo recomendado

1. Seu sistema autentica o usuário e identifica a conta correta.
2. Recupera somente o token da instância autorizada.
3. A aplicação chama a API HTTP.
4. Webhooks alimentam automações e persistência durável.
5. SSE atualiza interfaces em tempo real enquanto estão abertas.

## Responsabilidades da integração

- guardar tokens fora do navegador e dos logs;
- validar a permissão do usuário antes de cada operação;
- prevenir loops de webhook;
- tratar eventos duplicados ou fora de ordem;
- aplicar retry apenas quando a operação permitir;
- respeitar limites e o header `Retry-After`;
- manter correlação entre requests, mensagens e eventos.

Comece pelo [início rápido](/docs/getting-started) e depois configure
[Webhooks e SSE](/docs/integrations-webhooks).

---

<!-- source: https://docs.uazapi.com/docs/collections/integrations-webhooks.md -->


# Webhooks

Receba eventos da sua instância do WhatsApp no backend do seu sistema. Você configura uma URL de destino; a API envia um **POST com JSON** para essa URL quando ocorre um evento selecionado.

## Fluxo de uma integração

1. Disponibilize um receptor HTTP acessível ao servidor da API.
2. Configure a URL e a lista de eventos na instância.
3. Valide e registre cada recebimento, responda rapidamente com `2xx` e processe a regra da aplicação.
4. Consulte os erros e reconcilie dados quando houver falhas de entrega.

A URL de destino é do **seu sistema**. Ela é diferente da [Server URL](/docs/server-url), usada para chamar a API.

## Configurar o webhook da instância

```bash
curl -X POST "$BASE_URL/webhook" \
  -H "token: $INSTANCE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "url": "https://seu-sistema.example/hooks/whatsapp",
    "events": ["messages", "messages_update", "connection"],
    "excludeMessages": ["wasSentByApi"],
    "addUrlEvents": false,
    "addUrlTypesMessages": false
  }'
```

O modo simples configura o webhook principal. Para gerenciar mais de um destino, consulte as ações `add`, `update` e `delete` e os IDs retornados em [GET /webhook](/endpoint/get/webhook). Confira o contrato completo de [POST /webhook](/endpoint/post/webhook) antes de alterar um destino existente.

### Filtros de mensagens

`excludeMessages` contém os casos que você deseja **excluir** da entrega:

| Valor | Exclui |
|---|---|
| `wasSentByApi` | Mensagens classificadas como enviadas pela API |
| `wasNotSentByApi` | Mensagens que não foram classificadas como enviadas pela API |
| `fromMeYes` | Mensagens originadas pela conta conectada |
| `fromMeNo` | Mensagens que não são da conta conectada |
| `isGroupYes` | Mensagens de grupo |
| `isGroupNo` | Mensagens fora de grupos |

Os filtros valem para `messages`, `messages_update`, `status_posts` e `newsletter_messages`. `isGroupYes` e `isGroupNo` não valem para `status_posts` e `newsletter_messages`: quem assina esses eventos recebe todos, e separa os Status de grupo pelo campo `isGroup` do payload.

`wasSentByApi` e `fromMeYes` são critérios diferentes. Uma mensagem enviada pelo celular pode ser da própria conta sem ter sido enviada pela API. Escolha os filtros conforme a automação para evitar loops de resposta.

### Como a URL final é formada

`addUrlEvents` acrescenta o `EventType` como **segmento do caminho**. `addUrlTypesMessages` acrescenta o tipo da mensagem quando ele está disponível. Não são parâmetros de query string.

| Configuração | Exemplo de destino |
|---|---|
| Ambos desativados | `/hooks/whatsapp` |
| Apenas `addUrlEvents` | `/hooks/whatsapp/messages` |
| Ambos ativados, mensagem de texto | `/hooks/whatsapp/messages/text` |

Se ativar essas opções, seu receptor precisa aceitar os caminhos derivados. Um endpoint que aceita apenas a URL base pode passar a responder 404.

## Catálogo de eventos

Use exatamente os valores da coluna `EventType` em `events`. Cada página apresenta finalidade, campos e exemplos específicos.

`All` ou uma lista vazia assinam todos os eventos, menos `status_posts` e `newsletter_messages`: esses dois só chegam a quem os inclui pelo nome.

Os Status dos contatos ficam guardados por 24 horas mesmo sem `status_posts`: liste com [`/message/find`](/endpoint/post/message~find) e `chatid: status@broadcast`. Os Status de grupo ficam na conversa de cada grupo, também por 24 horas: liste com `messageType: GroupStatusMessage`.

| EventType | O que acompanhar |
|---|---|
| [`connection`](/webhook/connection) | Conexão da instância |
| [`history`](/webhook/history) | Sincronização de histórico |
| [`messages`](/webhook/messages) | Mensagens |
| [`messages_update`](/webhook/messages_update) | Entrega e leitura |
| [`newsletter_messages`](/webhook/newsletter_messages) | Mensagens de canais (só com inscrição pelo nome) |
| [`status_posts`](/webhook/status_posts) | Publicações de Status dos contatos e de grupos (só com inscrição pelo nome) |
| [`call`](/webhook/call) | Chamadas |
| [`contacts`](/webhook/contacts) | Contatos |
| [`presence`](/webhook/presence) | Digitação e gravação |
| [`groups`](/webhook/groups) | Alterações de grupos |
| [`labels`](/webhook/labels) | Definição de etiquetas |
| [`chats`](/webhook/chats) | Atualizações de chats |
| [`chat_labels`](/webhook/chat_labels) | Etiquetas de um chat |
| [`sender`](/webhook/sender) | Processamento de campanhas |

## Envelope comum

| Campo | Uso |
|---|---|
| `EventType` | Identifica o evento recebido |
| `owner` | Identidade da conta associada à instância |
| `token` | Credencial da instância; deve ser protegida |
| `BaseUrl` | Endereço base informado pela API |
| `instanceName` | Nome da instância, quando disponível |

Os campos específicos ficam na raiz: por exemplo `message`, `chat`, `event` ou dados de uma campanha. Não presuma que todo evento tenha `{ event, instance, data }`. Nem todos possuem um `event_id` universal; use a estratégia de correlação da página de cada evento.

O token no payload é sensível. Faça a validação e o vínculo com a instância autorizada no seu backend; não use apenas `owner` ou `instanceName` como permissão. Não registre o payload completo em logs públicos.

## Webhook global

[GET /globalwebhook](/endpoint/get/globalwebhook) e [POST /globalwebhook](/endpoint/post/globalwebhook) usam `admintoken` para configuração administrativa. No `POST /globalwebhook`, mande sempre `enabled: true`: sem o campo, o global é salvo desligado. O destino global pode receber eventos de várias instâncias: faça o roteamento correto antes de processar a mensagem.

## Sempre responda 200 imediatamente

Não mantenha a requisição do webhook aberta. Para cada evento recebido, responda `200` imediatamente e coloque o trabalho na fila interna da sua aplicação. Validação, deduplicação, chamadas a CRM, respostas automáticas, download de mídia, transcrição e outras regras devem acontecer **depois**, de forma assíncrona.

Fluxo recomendado:

1. Receba o payload e preserve o objeto necessário para o processamento.
2. Responda `200` imediatamente.
3. Coloque o evento em uma fila ou caixa de entrada durável sem aguardar o processamento.
4. Valide, deduplique e processe o evento separadamente.
5. Registre sucesso ou falha para reconciliação.

```js
app.post('/hooks/whatsapp', (req, res) => {
  const event = req.body;

  res.sendStatus(200);

  webhookInbox.enqueue(event).catch(reportWebhookFailure);
});

webhookInbox.process(async (event) => {
  if (!isValidWebhook(event)) return;
  await processBusinessRules(event);
});
```

Não aguarde `enqueue`, validações externas nem `processBusinessRules` antes de responder. Isso aumenta a latência, pode causar timeout e atrasa a fila de webhooks. Monitore falhas da sua fila interna e reconcilie dados pela API quando necessário.

### Evite atrasar a fila de webhooks

Um webhook lento, indisponível ou apontando para uma URL que não existe mais ocupa a capacidade de entrega e faz os próximos eventos aguardarem. Com volume alto, a fila pode acumular e eventos podem ser descartados.

- Desative webhooks de testes assim que eles deixarem de ser usados.
- Desative o webhook durante uma manutenção em que o receptor ficará indisponível.
- Remova destinos antigos ou duplicados que não possuem mais consumidor.
- Antes de reativar, confirme que a URL está acessível e responde `200` rapidamente.
- Consulte [erros do webhook da instância](/endpoint/get/webhook~errors) para identificar timeout, conexão recusada e respostas HTTP de erro.

Use [POST /webhook](/endpoint/post/webhook) para desativar ou atualizar um destino. Não deixe um webhook quebrado ativo esperando que ele volte sozinho: isso atrasa a fila da instância.

## Diagnóstico

1. Confira `enabled`, a instância/servidor e os nomes em `events`.
2. Verifique se os filtros excluem o evento esperado.
3. Confira a URL final, especialmente quando os segmentos automáticos estão ativados.
4. Valide conectividade, HTTPS e a resposta do seu receptor.
5. Consulte [erros da instância](/endpoint/get/webhook~errors) ou [erros do webhook global](/endpoint/get/globalwebhook~errors).

O header `X-Webhook-Error-Capture-Started-At` ajuda a identificar a janela de captura disponível. Use essa consulta como diagnóstico operacional, não como armazenamento permanente de auditoria.

## Webhooks ou SSE?

Use webhooks para integração entre servidores. Use [SSE](/endpoint/get/sse) para manter uma interface atualizada durante uma conexão aberta. Eles podem coexistir; receber SSE não comprova que o seu receptor de webhook aceitou o evento.

```js
const params = new URLSearchParams({
  token: instanceToken,
  events: 'chats,messages,messages_update,connection',
});
const stream = new EventSource(`${baseUrl}/sse?${params}`);
stream.onmessage = ({ data }) => {
  const update = JSON.parse(data);
  // Atualize o estado da aplicação sem registrar credenciais.
};
// Ao desmontar a tela:
// stream.close();
```

O token fica na URL do SSE. Proteja a URL e evite incluí-la em logs e analytics. A sessão, os filtros e as permissões do seu backend continuam valendo.

---

<!-- source: https://docs.uazapi.com/docs/collections/web-embed.md -->


# uazapi web no seu site

O uazapi web (o painel de conversas em `web.uazapi.com`) pode abrir dentro do
seu site, com o seu nome e o seu logo. Você cola um script, e as atualizações
do painel chegam sozinhas, sem mudar nada do seu lado.

O painel abre num iframe. O token da instância chega até ele por
`postMessage`, sem passar pela URL nem pelo histórico do navegador.

## Veja funcionando

Dois sites de exemplo, num domínio separado do painel, como o site de um
cliente. Entre com o servidor e o token de uma instância sua:

- **[Laboratório do embed](https://uazapi-embed-exemplo.vercel.app):** marca,
  tema, modo e as opções desta página num formulário. Mostra os eventos ao
  vivo e o código da configuração que você montou.
- **[Réplica com outra marca](https://uazapi-white-label-exemplo.vercel.app):**
  o uazapi web inteiro como "Whatsapp Web Api", feito só com o `embed.js`. O
  código está mais abaixo, em "Com a sua marca".

## Começar com uma tag

Cole no `<body>` da página:

```html
<script src="https://web.uazapi.com/embed.js" async
  data-server="minha-api" data-token="<token da instância>"
  data-name="Revenda Chat" data-theme="ocean"></script>
```

O painel ocupa a janela inteira. `data-server` é o subdomínio do seu servidor
(`minha-api` para `minha-api.uazapi.com`) ou a URL completa dele. Com
`data-server-domain="seudominio.com"`, o subdomínio completa com o seu domínio:
`minha-api.seudominio.com`.

| Atributo | Para quê |
|---|---|
| `data-server` | Servidor da instância (obrigatório). |
| `data-token` | Token da instância (obrigatório). |
| `data-name` | Nome que aparece no painel (os primeiros 40 caracteres). |
| `data-logo` | Logo ao lado do nome: endereço `https` ou `data:image` (PNG, JPEG, GIF, WebP ou SVG). O `data:image` inteiro, já em base64, cabe em 32 KB: uma imagem de até uns 24 KB. |
| `data-theme` | Cores iniciais: `whatsapp`, `petroleo`, `ocean`, `amethyst`, `graphite` ou `sunset`. |
| `data-server-domain` | Domínio que completa o subdomínio do `data-server`, no lugar de `uazapi.com`. |
| `data-target` | Seletor de um elemento da página: o painel abre dentro dele, e não na janela inteira. O elemento precisa existir quando a página termina de carregar. |
| `data-chat` | Número ou id da conversa que já abre junto com o painel. |
| `data-lazy` | Com `data-target`, `false` carrega o painel na hora, mesmo longe da tela. |

Nome, logo ou tema inválido é ignorado, e fica o padrão da uazapi. Quem usa o
painel ainda pode trocar as cores em Perfil → Cores, e essa escolha vale mais
que a `data-theme`.

## Num espaço da página, com eventos

Para pôr o painel num pedaço da página e saber o que acontece nele:

```html
<div id="chat" style="height: 640px"></div>
<script src="https://web.uazapi.com/embed.js"></script>
<script>
  const painel = UazapiWeb.mount("#chat", {
    server: "minha-api",
    token: "<token da instância>",
    brand: { name: "Revenda Chat", logoUrl: "https://exemplo.com/logo.png", theme: "ocean" },
    onReady: () => {},
    onConnect: ({ instanceName }) => {},
    onDisconnect: ({ instanceName }) => {},
    onUnread: (conversas) => { /* contador no seu menu */ },
    onNotification: ({ chatId, title, body }) => {},
    onError: (mensagem) => {},
    onLogout: () => {},
  });
</script>
```

O elemento precisa de altura. Sem ela, o painel fica com 480 px. Num espaço
da página, o painel ganha um botão de tela cheia.

`UazapiWeb.mount(opções)`, sem o seletor, abre na janela inteira, como o
script com `data-`.

### Eventos

| Evento | Quando |
|---|---|
| `onReady` | O painel carregou (antes de entrar na instância). |
| `onConnect`, `onDisconnect` | O WhatsApp da instância conectou ou desconectou. Recebe `{ instanceName }`. |
| `onUnread` | Mudou o número de conversas com mensagem não lida. Recebe esse número. |
| `onNotification` | Chegou mensagem nova. Recebe `{ chatId, title, body }`, com ou sem permissão de aviso. |
| `onError` | O acesso falhou (token inválido, servidor não encontrado). Recebe o texto do erro. |
| `onLogout` | A pessoa clicou em "Sair do painel". O botão só aparece com este evento: o painel apaga o que guardou da instância, e a sua página decide o que vem depois. Chame `painel.unmount()` ou mostre a sua tela de entrada: o painel fica em "Você saiu do painel" até um `mount` ou `update` com o acesso. |

### Opções

| Opção | Para quê |
|---|---|
| `server`, `token` | Servidor e token da instância. |
| `serverDomain` | Domínio que completa o subdomínio do `server` (`minha-api` vira `minha-api.seudominio.com`). Sem ele, `uazapi.com`. Só o domínio, sem `https://`, porta ou barra: com um valor inválido, o painel não entra e chama o `onError`. |
| `brand` | `{ name, logoUrl, theme }`, com as mesmas regras dos atributos `data-`. Sem `brand`, fica a marca uazapi. |
| `chat` | Conversa que abre junto com o painel. |
| `fullscreen` | `true` abre cobrindo a janela inteira. |
| `lazy` | Num espaço da página, um painel fora da tela só carrega quando a página chega perto dele, e até lá não manda contador nem aviso. `false` carrega na hora. |
| `notifications` | `false` desliga os avisos do navegador. |

### O que o `mount` devolve

| Método | Para quê |
|---|---|
| `painel.openChat(id)` | Abre uma conversa pelo número ou pelo id. |
| `painel.fullscreen(true)` | Num espaço da página, cobre a janela inteira. `false` devolve o painel ao lugar dele. |
| `painel.update({ token, server, serverDomain, brand })` | Troca token, servidor, domínio ou marca sem recarregar. `brand` troca a marca inteira: mande nome, logo e tema juntos. |
| `painel.unmount()` | Remove o painel. |

`UazapiWeb.unmount()` remove todos os painéis da página.

## Com a sua marca

A [réplica](https://uazapi-white-label-exemplo.vercel.app) é uma página só:
a sua tela de entrada e o painel na janela inteira. O essencial dela:

```html
<form id="entrada">
  <input id="server" placeholder="minha-api ou https://minha-api.seudominio.com">
  <input id="token" placeholder="Seu token de acesso">
  <p id="erro"></p>
  <button>Conectar</button>
</form>
<script src="https://web.uazapi.com/embed.js"></script>
<script>
  const NOME = "Whatsapp Web Api";
  const LOGO = "data:image/png;base64,..."; // ou https://seusite.com/logo.svg
  let painel = null;

  function entrada(erro) {
    painel?.unmount();
    painel = null;
    document.title = NOME;
    document.getElementById("entrada").hidden = false;
    document.getElementById("erro").textContent = erro || "";
  }

  function abrir(acesso) {
    document.getElementById("entrada").hidden = true;
    painel = UazapiWeb.mount({
      ...acesso,
      serverDomain: "seudominio.com",
      brand: { name: NOME, logoUrl: LOGO },
      onUnread: (n) => (document.title = (n ? `(${n}) ` : "") + NOME),
      onError: entrada,
      onLogout: () => {
        localStorage.removeItem("acesso");
        entrada();
      },
    });
  }

  document.getElementById("entrada").onsubmit = (e) => {
    e.preventDefault();
    const acesso = {
      server: document.getElementById("server").value.trim(),
      token: document.getElementById("token").value.trim(),
    };
    localStorage.setItem("acesso", JSON.stringify(acesso));
    abrir(acesso);
  };

  const salvo = JSON.parse(localStorage.getItem("acesso") || "null");
  if (salvo) abrir(salvo);
</script>
```

O que muda em relação ao `web.uazapi.com`:

- **Dados por site.** O navegador guarda o cache das conversas e as
  preferências (como as cores escolhidas) separados por site. No primeiro
  acesso ao seu site, a lista carrega do zero.
- **Microfone.** O pedido de permissão do navegador mostra o domínio do seu
  site, e a permissão fica com ele.
- **Avisos no celular.** Com a tela apagada ou em outro app, o navegador
  congela a página, e nenhum aviso chega até a pessoa voltar.
- **O endereço do script.** O `embed.js` e o painel continuam vindo de
  `web.uazapi.com`. Quem abre as ferramentas do navegador vê esse endereço.

Guardar o token no `localStorage`, como nesse exemplo, só serve para a pessoa
entrar com o token dela. Para um token que vem do seu sistema, veja os
cuidados no fim desta página.

## Avisos do navegador

O navegador não deixa um iframe de outro site pedir permissão de aviso. Por
isso, quem mostra o aviso é a sua página. Quando a pessoa ativa os avisos dentro
do painel, a sua página pede a permissão. Também dá para pedir num botão seu:

```js
botao.onclick = () => UazapiWeb.enableNotifications();
```

Clicar no aviso abre a conversa no painel. O aviso sai sem som (o som é do
painel). No Chrome do Android, o navegador não mostra esse aviso: use o
`onNotification` para avisar do seu jeito.

## Cuidados

- **O token fica visível no código da página.** Ele dá acesso completo à
  instância: ler as conversas e enviar mensagens. Mostre a página só depois do
  login no seu sistema, com o token da instância daquela pessoa, e nunca numa
  página pública. Use só o token da instância, nunca o `admintoken`.
- **Abra a página por `http` ou `https`.** Um arquivo aberto direto do disco
  (`file://`) não carrega o painel.
- **No celular, use a meta viewport:**
  `<meta name="viewport" content="width=device-width,initial-scale=1">`. Na
  janela inteira, o script já põe essa meta se ela faltar.
- O painel pede o microfone para gravar áudio e a área de transferência para o
  botão de copiar.

---

<!-- source: https://docs.uazapi.com/docs/collections/groups.md -->


# Listar e consultar grupos

Use o token da instância e preserve o JID do grupo, terminado em `@g.us`.

## Listagem paginada

```bash
curl -X POST "$BASE_URL/group/list" -H "token: $INSTANCE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit":50,"offset":0,"noParticipants":true}'
```

Leia `groups` e a paginação retornada. Para consultar os participantes, use `POST /group/info` com `groupjid`. Evite atualizar toda a lista continuamente; solicite as páginas necessárias.

Consulte os detalhes somente depois de o usuário escolher o grupo:

```bash
curl -X POST "$BASE_URL/group/info" -H "token: $INSTANCE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"groupjid":"120363153742561022@g.us"}'
```

## Criar grupo

Use [`POST /group/create`](/endpoint/post/group~create) com `name` e, se quiser, `participants`. Lista vazia, omitida ou só com o seu número cria o grupo só com você. A resposta traz `group` e `failed`: em `failed` ficam os números que não entraram.

Quem ficou em `failed` por causa da privacidade não recebe convite automático. Para chamar essa pessoa, envie o link do grupo (veja [Convidar pessoas](#convidar-pessoas)).

## Convidar pessoas

Pegue o link `https://chat.whatsapp.com/<código>` com [`GET /group/invitelink/{groupJID}`](/endpoint/get/group~invitelink~:groupJID) e envie como texto em [`POST /send/text`](/endpoint/post/send~text). Qualquer pessoa com o link pode entrar, e ele vale até alguém gerar um novo.

Para invalidar o link atual, use [`POST /group/resetInviteCode`](/endpoint/post/group~resetInviteCode).

Convites recebidos chegam no webhook `messages` com `messageType: "GroupInviteMessage"`.

Consulte a [referência](/api) para o contrato completo.

---

<!-- source: https://docs.uazapi.com/docs/collections/newsletters.md -->


# Canais e newsletters

Canais usam identificadores terminados em `@newsletter`. Preserve o JID completo: ele não equivale ao número de um contato nem ao JID de um grupo.

## Enviar e consultar

A operação [Enviar texto](/endpoint/post/send~text) documenta o destino newsletter no campo `number`. Confira permissões da sessão e os campos aceitos antes de enviar.

Para conteúdo de canais, use as operações específicas de newsletter disponíveis na [referência](/api), como [Buscar mensagens do canal](/endpoint/post/newsletter~messages). Não presuma que `/message/find` seja um histórico completo dos canais.

Fluxo recomendado:

1. Liste os canais seguidos ou resolva uma chave de convite.
2. Consulte os detalhes e confirme o `jid` completo.
3. Siga o canal quando necessário.
4. Consulte posts e atualizações usando as rotas próprias de newsletter.
5. Use as operações administrativas apenas em canais que a conta pode gerenciar.

## Edição e remoção

As operações de newsletter possuem seus próprios identificadores e regras para mídia. Reutilize o ID devolvido pela operação correspondente; não adapte automaticamente um payload de edição de mensagem de contato para canal.

A disponibilidade do conteúdo e as permissões dependem do canal e do WhatsApp. Confira o erro retornado e evite retries automáticos de alterações. Para os formatos de destino, veja [conceitos e identificadores](/docs/concepts).

## Por que usar as rotas de newsletter

Elas preservam IDs, permissões e métricas específicas de canais. Isso permite
criar painéis editoriais, acompanhar publicações e administrar canais sem tratar
um post como se fosse uma mensagem comum de chat.

---

<!-- source: https://docs.uazapi.com/docs/collections/business-catalog.md -->


# Catálogo comercial

Use estas operações com uma instância WhatsApp Business conectada.

## Produtos

1. [Liste os produtos](/endpoint/post/business~catalog~list) para obter os IDs e o cursor da próxima página.
2. [Crie ou edite um produto](/endpoint/post/business~catalog~save). Omita o ID para criar; informe-o para editar.
3. Para retirar um item da vitrine sem apagá-lo, use [ocultar](/endpoint/post/business~catalog~hide). Para apagar de vez, use [excluir](/endpoint/post/business~catalog~delete).

O preço é uma string em milésimos da moeda: 19990 representa R$ 19,99.
Envie uma imagem nova em image_data (base64 ou Data URL) ou image_url
(HTTPS público). Para preservar imagens cadastradas, use as URLs devolvidas
pelo catálogo em image_urls.

```json
{
  "name": "Camiseta básica",
  "currency": "BRL",
  "price": "19990",
  "image_url": "https://exemplo.com/camiseta.jpg"
}
```

## Coleções

[Liste as coleções](/endpoint/get/business~catalog~collection~list) sem corpo.
Para a próxima página, copie response.next para o parâmetro de consulta after. Use os IDs
dos produtos para [criar](/endpoint/post/business~catalog~collection~create)
uma coleção. Você pode [editar nome e produtos](/endpoint/patch/business~catalog~collection~:id)
ou [apagar a coleção](/endpoint/delete/business~catalog~collection~:id);
apagar a coleção não apaga seus produtos.

---

<!-- source: https://docs.uazapi.com/docs/collections/chats-and-contacts.md -->


# Chats e contatos

Um contato e um chat representam coisas diferentes. O contato descreve uma identidade/entrada da agenda; o chat é uma conversa. A existência de um chat não garante que o número esteja salvo na agenda.

## Consultar

- [Buscar chats](/endpoint/post/chat~find): filtros, ordenação e paginação dos chats locais.
- [Listar contatos](/endpoint/post/contacts~list): contatos conforme o escopo e filtros documentados.
- [Verificar número](/endpoint/get/contacts): verificação de números conforme a operação.
- [Consultar detalhes do chat](/endpoint/post/chat~details): detalhes do contato, conversa ou grupo selecionado.
- [Consultar foto do chat](/endpoint/post/chat~avatar): imagem da conversa sem carregar todos os detalhes.

Em `/chat/details`, `is_business` e `business_name` ajudam a identificar
contatos comerciais quando a instância conhece o nome da empresa.

`/chat/find` usa limite padrão 2000 quando não há limite positivo. Para uma interface, informe páginas menores explicitamente.

```json
{ "limit": 50, "offset": 0 }
```

## Paginação

Leia os metadados retornados, preserve os filtros entre páginas e encerre quando não houver mais resultados. Uma lista vazia é um resultado possível; não conclua que o token é inválido apenas porque a consulta não encontrou contatos.

## Atualização de interface

Carregue o estado inicial por HTTP e aplique eventos incrementais de [SSE ou webhook](/docs/integrations-webhooks). Preserve JIDs e IDs retornados; não remova sufixos para tentar unificar contato, grupo e newsletter.

Os dados disponíveis dependem da sessão e do histórico sincronizado. Não prometa que uma consulta local contém todas as mensagens já existentes no WhatsApp.

## Atendimento e CRM

Chats podem receber nome do lead, responsável, observações, campos
personalizados e etiquetas. Use `POST /chat/editLead` para atualizar os dados
comerciais e `POST /chat/labels` para organizar a conversa. Essas informações
servem para construir funis, filas de atendimento e Kanban sem alterar o contato
salvo no WhatsApp.

---

<!-- source: https://docs.uazapi.com/docs/collections/messages-and-media.md -->


# Mensagens e mídias

Antes de enviar, confirme [Server URL](/docs/server-url), [token](/docs/authentication) e [estado da instância](/docs/instances).

## Escolha a operação

| Objetivo | Referência |
|---|---|
| Texto | [Enviar texto](/endpoint/post/send~text) |
| Arquivo, imagem, vídeo ou áudio | [Enviar mídia](/endpoint/post/send~media) |
| Baixar mídia recebida | [Download de mídias](/docs/media-downloads) |
| Transcrever mensagem de áudio | [Transcrever áudio](/docs/media-downloads#transcrever-audio) |
| Enfileirar um envio direto | [Filas de mensagem](/docs/message-queues) |
| Enviar para vários destinatários | [Mensagem em massa](/docs/bulk-messaging) |
| Botões, listas, enquete ou carrossel | [Enviar menu interativo](/endpoint/post/send~menu) |
| Convite de evento | [Enviar evento](/endpoint/post/send~event) |
| Cobrança de um pedido | [Solicitar pagamento](/endpoint/post/send~request-payment) |
| Atualizar pagamento ou pedido | [Atualizar pedido](/endpoint/post/message~payment~status) |
| Responder enquete, lista ou botão | [Responder interação](/endpoint/post/send~text#responder-enquete-lista-ou-botao) |
| Consultar mensagens locais | [Buscar mensagens](/endpoint/post/message~find) |
| Recuperar mensagens anteriores | [Histórico de mensagens](/docs/message-history-retention) |
| Marcar como lida | [Marcar mensagem como lida](/endpoint/post/message~markread) |
| Apagar mensagem | [Apagar mensagem](/endpoint/post/message~delete) |

Em mídia, confira os tipos aceitos e o campo `file` no schema. Não presuma que qualquer URL seja acessível ao servidor: ele precisa conseguir obter o conteúdo e processar o formato. Limites externos e permissões do destinatário também podem impedir o envio.

Para atendimento interativo, envie o menu primeiro e preserve o ID retornado.
Ao responder uma opção programaticamente, use esse ID em `replyid` e a seleção
documentada em `POST /send/text`.

## Identificador e resultado

Preserve os IDs retornados como strings. O formato do destino distingue contato, grupo e newsletter; veja [identificadores](/docs/concepts). Uma resposta de enfileiramento não significa entrega ao destinatário. Consulte [Entrega e status](/docs/message-delivery) para interpretar cada confirmação.

## Evite duplicações

Um timeout deixa o resultado incerto: o envio pode ter sido processado. Não faça retry automático de envio. Campos de rastreamento ajudam na correlação, mas `track_id` aceita duplicados e não é uma chave de idempotência. Veja [erros e recuperação](/docs/errors-and-retries).

Para automações, processe [webhooks](/docs/integrations-webhooks) sem responder aos próprios envios indefinidamente.

---

<!-- source: https://docs.uazapi.com/docs/collections/media-downloads.md -->


# Download de mídias

Use [POST /message/download](/endpoint/post/message~download) para baixar imagens, vídeos, áudios, documentos e stickers recebidos em uma mensagem. Na mensagem de botão com imagem, vídeo ou documento no topo, use o id da mensagem do botão: o download traz essa mídia.

## Prefira receber a URL

Envie o `id` da mensagem. A resposta inclui `fileURL`, uma URL pública para acessar o arquivo:

```json
{
  "id": "ID_DA_MENSAGEM"
}
```

```json
{
  "fileURL": "https://seu-servidor.exemplo/files/arquivo.jpg",
  "mimetype": "image/jpeg"
}
```

Prefira consumir `fileURL` em vez de solicitar o arquivo em base64. A URL reduz o tamanho da resposta e evita transportar todo o conteúdo dentro do JSON.

## Disponibilidade por 2 dias

O arquivo fica disponível no nosso CDN por **2 dias**. Depois desse período, a URL deixa de funcionar.

Se precisar acessar a mídia novamente, chame o endpoint de download outra vez para gerar uma nova URL, enquanto a mensagem e a mídia original ainda estiverem disponíveis. A disponibilidade da mensagem também depende das regras explicadas em [Histórico de mensagens](/docs/message-history-retention).

## Guardar por mais tempo

Se a sua aplicação precisar manter o arquivo por mais de 2 dias, baixe o conteúdo pela `fileURL` e salve-o em um armazenamento próprio. Guardar somente a URL não aumenta o prazo de retenção.

## Quando usar base64

Evite `return_base64: true`. Codificar o arquivo em base64 aumenta o uso de memória e processamento no servidor, além de produzir uma resposta maior e mais lenta. Prefira baixar o conteúdo pela `fileURL`.

Use base64 somente quando a integração realmente exigir o arquivo embutido no JSON. Mesmo nesse caso, a resposta também inclui `fileURL`.

> **Compatibilidade futura:** o retorno em base64 poderá ser limitado para arquivos maiores que **5 MB** em versões futuras. Não dependa de base64 para arquivos grandes.

```json
{
  "id": "ID_DA_MENSAGEM",
  "return_base64": true
}
```

## Transcrever áudio

Para baixar e transcrever uma mensagem de áudio na mesma operação, envie `transcribe: true`:

```json
{
  "id": "ID_DA_MENSAGEM_DE_AUDIO",
  "transcribe": true
}
```

Quando a transcrição for concluída, a resposta inclui `transcription` junto com `fileURL` e `mimetype`:

```json
{
  "fileURL": "https://seu-servidor.exemplo/files/audio.mp3",
  "mimetype": "audio/mpeg",
  "transcription": "Olá, gostaria de saber mais sobre o pedido."
}
```

A transcrição requer uma credencial válida configurada para a instância ou enviada pelo campo aceito no contrato da operação. O texto transcrito passa a fazer parte da mensagem e também pode ser acompanhado pelo evento `messages_update`.

Para áudios, `generate_mp3` controla o formato retornado. Para baixar a mídia original citada por uma resposta, use `download_quoted: true`. Consulte o schema da [operação de download](/endpoint/post/message~download) para os campos completos.

---

<!-- source: https://docs.uazapi.com/docs/collections/message-queues.md -->


# Filas de mensagem

Use `async: true` para aceitar rapidamente um envio direto e processá-lo pela fila da instância. A resposta confirma que a mensagem entrou na fila — não que chegou ao destinatário.

## Envio direto ou assíncrono?

| Fluxo | Quando usar | O que a resposta informa |
|---|---|---|
| Direto | Quando você precisa aguardar a tentativa de envio | Resultado daquela tentativa |
| `async: true` | Para absorver picos e não manter a requisição aberta durante o envio | Aceite na fila e posição aproximada |

O campo `async` está disponível nas operações de envio que o exibem no schema, como [Enviar texto](/endpoint/post/send~text) e [Enviar mídia](/endpoint/post/send~media).

```json
{
  "number": "5511999999999",
  "text": "Olá! Sua solicitação foi recebida.",
  "async": true,
  "track_source": "meu-sistema",
  "track_id": "pedido-123"
}
```

Uma resposta aceita contém `status: "Queued"`, `async: true`, os identificadores da mensagem e `queuePosition`. Preserve o campo `id`; a posição é uma fotografia do momento e não uma previsão de horário.

## Acompanhar a fila

Consulte [GET /message/async](/endpoint/get/message~async) para obter a situação geral da fila da instância.

| Status | Significado |
|---|---|
| `idle` | Não há mensagens pendentes |
| `queued` | Há mensagens aguardando processamento |
| `processing` | Uma mensagem está sendo processada agora |
| `waiting_connection` | A fila aguarda a sessão ficar pronta |
| `waiting_warmup` | A fila aguarda a preparação da sessão |
| `waiting_history` | A fila aguarda a preparação do histórico |
| `resetting` | A fila está temporariamente indisponível durante uma limpeza ou reinicialização |

Use `pending` para acompanhar o volume restante, `processingNow` para saber se há trabalho em andamento e `acceptingNewMessages` antes de adicionar novos envios. `sessionReady: false` explica por que uma fila pode permanecer pendente.

## Acompanhar uma mensagem

O estado geral da fila não substitui o acompanhamento individual. Busque a mensagem pelo `id` em [POST /message/find](/endpoint/post/message~find) ou acompanhe o evento `messages_update`.

| Estado | Significado |
|---|---|
| `Queued` | Aceita e aguardando processamento |
| `Sent` | Enviada pela sessão; ainda não significa entrega ou leitura |
| `Failed` | O envio terminou com falha |
| `Expired` | A mensagem não pôde ser enviada dentro da janela disponível |
| `Canceled` | A mensagem pendente foi cancelada pela limpeza da fila |

Antes de repetir um envio após timeout ou desconexão, consulte a mensagem pelo ID ou pelos campos de rastreamento. Reenviar sem essa conferência pode gerar duplicidade.

## Intervalo entre mensagens

[Configure o intervalo da fila](/endpoint/post/instance~updateDelaySettings) para controlar o tempo entre envios assíncronos. Essa configuração pertence à fila de mensagens diretas e não altera campanhas.

## Limpar a fila

[DELETE /message/async](/endpoint/delete/message~async) cancela todas as mensagens ainda pendentes da instância. Mensagens já enviadas não são desfeitas. Use a limpeza somente quando a intenção for cancelar todo o trabalho pendente.

## O que não entra nesta fila

- [Mensagem em massa](/docs/bulk-messaging) possui acompanhamento e controle próprios.
- Publicações em canais/newsletters não usam esta fila, mesmo que `async: true` seja informado.
- `Queued` não comprova entrega, leitura nem sucesso da regra de negócio do destinatário.

---

<!-- source: https://docs.uazapi.com/docs/collections/bulk-messaging.md -->


# Mensagem em massa

Campanhas organizam vários envios sob um mesmo identificador, com agendamento, intervalo e controle próprios. Use esse fluxo quando o trabalho precisa ser acompanhado como um lote — ele é separado da fila de mensagens diretas com `async: true`.

## Escolha o tipo de campanha

| Operação | Quando usar |
|---|---|
| [Criar campanha simples](/endpoint/post/sender~simple) | Enviar o mesmo conteúdo para vários destinatários |
| [Criar campanha avançada](/endpoint/post/sender~advanced) | Definir conteúdo ou tipo de mensagem individualmente para cada destinatário |

Configure os intervalos de envio e, quando necessário, `scheduled_for`. Preserve o `folder_id` retornado: ele identifica a campanha nas consultas e ações seguintes.

Para publicar no status dos grupos em vez de mandar no chat, use `groupStatus: true` (na campanha simples, para todos; na avançada, por mensagem). Só vale para grupos (`@g.us`) e para texto, imagem ou vídeo.

## Acompanhar a execução

- [Consultar campanhas](/endpoint/get/sender~listfolders) mostra os lotes e seus estados.
- [Listar mensagens da campanha](/endpoint/post/sender~listmessages) detalha o que pertence a um `folder_id`.
- [Consultar estado e métricas](/endpoint/get/sender~stats) apresenta o ritmo atual e o próximo envio agendado.

Mensagens processadas não significam necessariamente entregues ou lidas. Para confirmação por destinatário, acompanhe os eventos e estados das mensagens.

## Pausar, continuar ou excluir

Use [Controlar campanha](/endpoint/post/sender~edit) com o `folder_id`:

- `stop` pausa os envios ainda não realizados;
- `continue` retoma uma campanha pausada;
- `delete` remove a campanha e seus envios ainda não realizados, preservando o histórico do que já foi enviado.

Consulte o estado novamente depois da ação. Não recrie a campanha apenas porque uma resposta demorou: primeiro verifique se o lote já existe.

## Limpeza

[Limpar campanhas concluídas](/endpoint/post/sender~cleardone) e [limpar todas as campanhas](/endpoint/delete/sender~clearall) têm escopos diferentes. Confira a operação e a instância antes de usar qualquer limpeza.

Para envios pontuais que apenas precisam sair da requisição principal, use [Filas de mensagem](/docs/message-queues).

---

<!-- source: https://docs.uazapi.com/docs/collections/message-history-retention.md -->


# Histórico de mensagens

A API mantém mensagens em um banco de dados local para consultas, respostas e
outras ações. A janela de retenção é de até **7 dias**; em instâncias com
volume muito alto de mensagens, a manutenção diária pode manter menos.

Esse histórico facilita o atendimento, mas não deve ser tratado como arquivo
permanente, backup ou fonte exclusiva para auditoria. Se sua operação precisa
reter conversas por mais tempo, salve no seu sistema os eventos e dados
necessários conforme sua política de privacidade.

## Por que a mensagem original é necessária

Várias ações precisam recuperar o contexto da mensagem original:

| Ação | Dependência do histórico local |
|---|---|
| Responder com `replyid` | Usa chat, remetente e conteúdo citado |
| Responder enquete, lista ou botão | Usa as opções e identificadores da mensagem interativa |
| Reagir | Usa chat, remetente e ID da mensagem |
| Editar ou apagar | Confirma a mensagem enviada e a conversa correta |
| Fixar ou desafixar | Usa o contexto da mensagem e as permissões da conversa |
| Baixar mídia novamente | Depende dos dados ainda disponíveis para recuperação |

Quando a mensagem já saiu da janela local, essas operações podem retornar que a
mensagem não foi encontrada ou que não foi possível reconstruir seu contexto.
Repetir a mesma chamada não recupera a mensagem automaticamente.

## Solicitar mensagens mais antigas

Use `POST /message/history-sync` para pedir mensagens anteriores de um chat:

```bash
curl -X POST "$BASE_URL/message/history-sync" \
  -H "token: $INSTANCE_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "number": "5511999999999@s.whatsapp.net",
    "count": 50
  }'
```

A API envia o pedido ao **aparelho principal** da conta. O retorno não é
imediato nem garantido pelo WhatsApp. Para aumentar a chance de resposta:

- mantenha o celular com internet;
- abra o WhatsApp no aparelho ou deixe-o ativo em segundo plano;
- evite encerrar o aplicativo enquanto a recuperação estiver pendente;
- aguarde os eventos antes de repetir o pedido.

As mensagens recuperadas chegam pelo evento `history` em webhook/SSE, com o
`request_id` devolvido na resposta, e passam a ficar disponíveis em
`POST /message/find`. O recebimento pode acontecer em mais de um lote.

Cada pedido aceito termina com um único lote `event: "status"` com o mesmo
`request_id`. Ele informa se o celular declarou mais mensagens (`has_more`) e traz em
`next_request` o corpo pronto para pedir as mensagens anteriores.
`status: "completed"` encerra o pedido; só `has_more: false` confirma o início
da conversa. `has_more: null` significa informação inconclusiva, inclusive
quando o resultado é `status: "timeout"` após 2 minutos.

`has_more` é o que o celular declarou. Alguns aparelhos declaram mais mensagens
em toda resposta, inclusive na que vem vazia: com eles, a paginação nunca
termina em `has_more: false`, e sim em `status: "blocked"` com
`error: "pagination_no_progress"`.

Uma âncora apagada pode ser substituída pela próxima mensagem válida do chat
(`details.anchor_replaced`). Sem alternativa, `anchor_unavailable` pede uma
nova referência; omitir `messageid` usa a mensagem mais antiga salva.

## Fluxo recomendado na interface

1. Carregue a página atual com `POST /message/find`.
2. Quando o usuário pedir mensagens anteriores, chame
   `POST /message/history-sync` com `count` limitado e guarde o `request_id`.
3. Mostre que a solicitação foi enviada, sem prometer conclusão imediata.
4. Exiba as mensagens do evento `history` com esse `request_id`.
5. Quando chegar o `status` desse `request_id`:
   - com `next_request`, permita carregar mais reenviando esse corpo, após
     o resultado do pedido anterior. Se a página não avançou (veio vazia ou sem
     mensagem que sirva de referência), ele repete a mesma referência com o
     dobro do `count`, até 100;
   - com `has_more: false`, mostre que a conversa chegou ao início;
   - com `history_access: "unavailable"`, explique que o restante não está
     acessível;
   - com `status: "timeout"`, oriente o usuário a abrir o WhatsApp no celular e
     tentar novamente.
   - com `status: "blocked"`, o celular indica mais mensagens mas não entregou
     uma página que avance: mostre o motivo de `error` e não ofereça "carregar
     mais" com o mesmo pedido (`anchor_unavailable` aceita pedir com outra
     mensagem de referência). `pagination_no_progress` vem quando nem com
     `count` 100 a página avançou: encerre a paginação do chat sem repetir
     automaticamente. É o fim do que o celular entrega a partir daquela
     referência, mesmo que ele continue declarando `has_more: true`, mas não
     confirma o início da conversa.

Mantenha um pedido por vez em cada chat: repetir a mesma referência devolve o
pedido em andamento, e outra referência encerra o anterior. Mensagens atrasadas podem chegar com o mesmo id
por cerca de 5 minutos após o pedido, sem um segundo status final.
`next_request: null` sem `has_more: false` não comprova o início da conversa.

Não mantenha um carregamento infinito: o aparelho pode estar offline, o
WhatsApp pode não responder ou o trecho solicitado pode não estar mais
disponível.

## Recuperar uma mensagem que não abriu

Uma mensagem que chegou sem abrir aparece em `POST /message/find` com
`messageType: "error"`. Para pedir de novo ao celular só essa mensagem, use
[`POST /message/reload`](/endpoint/post/message~reload) com o `id` dela. Se o
celular tiver a mensagem, ela chega pelo webhook `messages` e substitui a linha
de erro.

## Limites importantes

- Solicitar histórico não aumenta permanentemente a janela de retenção.
- A recuperação não garante que toda a conversa existente no celular será
  entregue.
- Mensagens recuperadas mais antigas que a janela são salvas, mas ficam em
  `POST /message/find` só até a manutenção diária seguinte, que aplica a mesma
  janela. Para guardá-las, salve-as no seu sistema a partir do evento `history`.
- Para responder ou editar depois da recuperação, aguarde a mensagem aparecer em
  `POST /message/find`.
- Evite polling agressivo e solicitações repetidas para o mesmo trecho.

Consulte também [Mensagens e mídias](/docs/messages-and-media),
[Webhooks e SSE](/docs/integrations-webhooks) e
[Erros e confiabilidade](/docs/errors-and-retries).

---

<!-- source: https://docs.uazapi.com/docs/collections/message-delivery.md -->


# Entrega e status de mensagens

Uma resposta bem-sucedida da API não significa, por si só, que a mensagem chegou ou foi lida. Cada confirmação representa uma etapa diferente.

## O que cada confirmação significa

| Confirmação | Significado |
|---|---|
| Resposta HTTP `2xx` | A API aceitou e processou a requisição conforme o contrato da operação |
| `Queued` | A mensagem entrou na [fila assíncrona](/docs/message-queues) |
| `Sent` | A sessão enviou a mensagem; ainda não confirma entrega ao aparelho do destinatário |
| `Delivered` | Houve confirmação de entrega |
| `Read` | Houve confirmação de leitura, quando esse recibo está disponível |
| `Played` | Houve confirmação de reprodução para um tipo de mídia compatível |
| `Failed` | O envio terminou com falha |
| `Expired` | O envio pendente não pôde ser concluído dentro da janela disponível |
| `Canceled` | O envio pendente foi cancelado |
| `Deleted` | A mensagem foi marcada como apagada |

A ausência de `Read` não comprova que a pessoa não leu: recibos de leitura podem estar indisponíveis conforme privacidade, tipo de conversa ou estado da sessão.

## Identificadores que devem ser preservados

- `id`: identificador consolidado usado nas consultas da API;
- `messageid`: identificador original da mensagem;
- `track_source` e `track_id`: correlação com o seu sistema.

Trate todos como strings. `track_id` aceita valores repetidos e não funciona como chave de idempotência.

## Como acompanhar

1. Preserve os identificadores retornados no envio.
2. Assine o evento [`messages_update`](/webhook/messages_update) para receber mudanças de estado.
3. Reconcilie uma mensagem pelo `id` ou pelos campos de rastreamento em [POST /message/find](/endpoint/post/message~find).
4. Se houver timeout, consulte o estado existente antes de repetir o envio.

Eventos podem chegar repetidos ou fora de ordem. Atualize o estado de forma idempotente e não faça uma mensagem regredir de `Read` para `Sent`, por exemplo.

## Mensagens em grupo

Em grupos, cada participante confirma separadamente. Em vez de um evento por participante, a API junta as confirmações de cada mensagem durante 60 segundos e envia um único `messages_update` com `type: "GroupReceipts"`. A lista `event.Receipts` traz quem recebeu, leu ou reproduziu e quando. Confirmações que chegam depois saem num próximo evento da mesma mensagem.

O status de uma mensagem de grupo segue o participante mais adiantado e muda junto com o `GroupReceipts`: `Delivered` quando pelo menos um recebeu, `Read` quando pelo menos um leu e `Played` quando pelo menos um ouviu. Ele não diz que o grupo todo leu. Para ver as confirmações de cada participante, use [POST /message/status](/endpoint/post/message~status): as mensagens que a API acompanha em memória respondem na hora; a primeira consulta das demais pergunta ao celular da conta, que precisa estar ligado e com internet (sem resposta em 40 segundos, a rota retorna `504`).

A API não grava as confirmações em banco: o `GroupReceipts` é a fonte ao vivo. Num reinício do servidor dentro dos 60 segundos de agrupamento, o webhook daquele lote pode não sair; o celular continua com elas. Se precisar do histórico das confirmações, guarde os eventos do seu lado.

## Entrega não é resultado de negócio

`Delivered` confirma transporte, não que o destinatário entendeu, respondeu ou concluiu uma ação. Para fluxos comerciais, acompanhe também respostas recebidas e o estado da sua própria aplicação.

Consulte [Erros e confiabilidade](/docs/errors-and-retries) para definir retries e [Webhooks e SSE](/docs/integrations-webhooks) para processar eventos.

---

<!-- source: https://docs.uazapi.com/docs/collections/errors-and-retries.md -->


# Erros e confiabilidade

## Status HTTP

| Status | Significado típico | Ação recomendada |
|---|---|---|
| `400` | payload ou parâmetro inválido | corrija o request; não repita igual |
| `401` | credencial ausente ou inválida | interrompa e revise/rotacione o token |
| `403` | operação não permitida | revise escopo, papel ou permissão no WhatsApp |
| `404` | recurso ou instância não encontrado | confirme identificadores e ownership |
| `409` | conflito ou operação já em andamento | consulte o estado antes de repetir |
| `429` | limite temporário | respeite `Retry-After` quando presente |
| `5xx` | falha temporária ou do provedor | registre contexto e tente novamente com limite |

Sempre leia o schema e o corpo documentado da operação: alguns erros incluem `error_key`, mensagem do provedor ou endpoint de diagnóstico.

## Política de retry

- Pode repetir automaticamente leituras (`GET`) após falhas temporárias.
- Em `429` e `503`, respeite `Retry-After` quando retornado.
- Use atraso exponencial com jitter e limite de tentativas.
- Não repita cegamente um envio de mensagem após timeout: o primeiro request pode ter sido processado.
- Antes de repetir uma mutação, consulte o estado ou reconcilie pelo ID retornado, webhook ou campo de rastreamento.

Exemplo de sequência de espera: `1s`, `2s`, `4s`, `8s`, sempre com pequena variação aleatória.

## Limite de chamadas

Todas as rotas chamadas com o `token` de uma instância dividem a mesma cota:

| Quem | Limite padrão |
|---|---|
| Instância (`token`) | 10 chamadas por segundo, com rajada de até 20 |
| Administração (`admintoken`) | 10 chamadas por segundo por servidor, com rajada de até 20 |
| [`POST /chat/details`](/endpoint/post/chat~details) | também até 4 consultas ao mesmo tempo por instância; a seguinte espera até 2 segundos por uma vaga |

Acima do limite, a API responde `429` com `{"error": "rate limit exceeded"}` e o header `Retry-After`, com os segundos até a próxima chamada ser aceita. Espere esse tempo antes de repetir.

- No navegador, o `Retry-After` não fica legível, porque não é exposto no CORS: espere cerca de 1 segundo e tente de novo.
- Para enviar muitas mensagens, use [Mensagem em massa](/docs/bulk-messaging) ou `async: true`, em vez de muitas chamadas seguidas.
- Para mostrar fotos numa lista de conversas, use [`POST /chat/avatar`](/endpoint/post/chat~avatar), mais leve que `/chat/details`.

## Webhooks

Seu receptor deve:

1. autenticar e validar o destino configurado;
2. rejeitar payloads maiores que o limite esperado;
3. responder rapidamente;
4. colocar processamento demorado em fila;
5. tolerar eventos repetidos e fora de ordem;
6. deduplicar por identificadores de evento/mensagem quando disponíveis.

Consulte `/webhook/errors` com o token da instância para diagnosticar falhas recentes. Para o webhook global, use `/globalwebhook/errors` com `admintoken`. O campo `stage` diz onde a entrega parou: `http` quando o seu receptor respondeu com erro ou não respondeu; `config` ou um `*_queue_full` (com `attempts: 0`) quando o evento nem chegou a ser enviado. Muitos `*_queue_full` indicam receptor lento: responda antes de processar.

## Observabilidade mínima

Registre operação, status HTTP, duração, instância interna/tenant e um correlation ID. Nunca registre tokens, conteúdo sensível de mensagens ou a query completa do SSE.