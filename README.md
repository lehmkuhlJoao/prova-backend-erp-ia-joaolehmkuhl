# prova-backend-erp-ia-joaolehmkuhl

Prova prática de Back-end (IA/ERP) para a IPM Sistemas.

## Sumário

- [Como rodar o projeto](#como-rodar-o-projeto)
- [Arquitetura e estrutura de pastas](#arquitetura-e-estrutura-de-pastas)
- [Parte 1 — Arquitetura e Organização (teórica)](#parte-1--arquitetura-e-organização-teórica)
- [Parte 2 — Assíncrono e Concorrência](#parte-2--assíncrono-e-concorrência)
- [Parte 3 — API RESTful (CRUD real de ERP)](#parte-3--api-restful-crud-real-de-erp)
- [Cache (Redis)](#cache-redis)
- [Worker de fila (arq)](#worker-de-fila-arq)
- [Autenticação (JWT)](#autenticação-jwt)
- [Testes](#testes)
- [Parte 4 — Docker e Orquestração](#parte-4--docker-e-orquestração)
- [Parte 5 — Desafio de IA (agente baseado em regras)](#parte-5--desafio-de-ia-agente-baseado-em-regras)
- [Parte 6 — Pergunta de Perfil](#parte-6--pergunta-de-perfil)
- [Parte 7 — Portfólio](#parte-7--portfólio)
- [Uso de IA](#uso-de-ia)

## Como rodar o projeto

### Opção 1: Docker Compose (recomendado — um único comando)

```bash
cp .env.example .env   # os valores default já funcionam com o compose
docker compose up --build
```

Isso sobe 4 containers: `postgres`, `redis`, `app` (a API) e `worker` (fila em
background — ver [Worker de fila (arq)](#worker-de-fila-arq)). O `app` e o
`worker` só iniciam depois que `postgres` e `redis` reportam `healthy`, e o
`app` cria as tabelas automaticamente no startup via
`Base.metadata.create_all()` — não há migração/seed manual necessária (ver
"Schema do banco" abaixo).

API em `http://localhost:8000`, docs interativos em `http://localhost:8000/docs`.

Para derrubar: `docker compose down` (os dados do Postgres persistem no volume
nomeado `postgres_data`; `docker compose down -v` também apaga os dados).

### Opção 2: local, sem Docker (uvicorn direto)

Útil durante o desenvolvimento, para iterar sem rebuildar a imagem a cada
mudança (`--reload`). Requer Postgres e Redis já rodando localmente (containers
standalone ou instalação nativa).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ajuste host/porta/credenciais conforme seu Postgres/Redis
python -c "from app.core.database import init_db; init_db()"   # cria as tabelas
uvicorn app.main:app --reload
```

Pra também processar a fila em background (ver [Worker de fila (arq)](#worker-de-fila-arq)), rode o worker num segundo terminal, com o mesmo venv ativo:

```bash
arq app.workers.tasks.WorkerSettings
```

Sem o worker rodando, os jobs enfileirados (ex: pelo `PATCH /produtos/{id}`)
ficam parados no Redis até algum worker os consumir — a API continua
funcionando normalmente, só o processamento em background não acontece.

### `localhost` vs. nome do serviço: por que `DATABASE_URL`/`REDIS_URL` diferem

O `.env` (usado pela Opção 2) aponta `DATABASE_URL`/`REDIS_URL` para `localhost`,
porque nesse modo a aplicação roda no host, na mesma rede que o Postgres/Redis
expostos via porta mapeada.

Dentro da rede do Docker Compose (Opção 1), porém, `localhost` **de dentro do
container da app aponta para o próprio container**, não para os containers de
Postgres/Redis. Por isso o `docker-compose.yml` **sobrescreve**
`DATABASE_URL`/`REDIS_URL` no `environment:` do serviço `app`, usando o nome dos
serviços (`postgres`, `redis`) como host — assim que o Compose resolve DNS
interno entre containers da mesma rede. As credenciais (`POSTGRES_USER`/
`PASSWORD`/`DB`) continuam vindas do mesmo `.env` nos dois modos; só o host de
conexão muda.

### Sobre os containers `postgres-dev`/`redis-dev` usados durante o desenvolvimento

Os blocos anteriores deste projeto (model/schema, CRUD, cache) foram
desenvolvidos e testados contra containers Postgres/Redis standalone, subidos
manualmente fora do Compose, para iterar rápido sem rebuildar a imagem a cada
mudança de código (Opção 2 acima). O Docker Compose criado agora **não depende
deles** — sobe seu próprio Postgres/Redis do zero, com seus próprios dados. As
duas formas não rodam ao mesmo tempo por padrão (ambas usam as portas 5432/6379
do host); a partir de agora, `docker compose up` pode substituir esse fluxo
manual para quem só quer rodar o projeto, enquanto o fluxo manual + `--reload`
continua sendo o mais rápido para iterar em cima do código.

## Arquitetura e estrutura de pastas

```
app/
├── main.py            # FastAPI app entrypoint, router registration
├── core/               # settings, database session, security (JWT), redis client
├── models/             # SQLAlchemy ORM models
├── schemas/             # Pydantic request/response schemas
├── repositories/        # data access layer (DB queries only, no business rules)
├── services/             # business logic, orchestration, caching decisions
├── routers/              # FastAPI routers (HTTP layer only)
└── workers/               # background task definitions (arq)
tests/                        # unit tests
```

Separação em camadas: `routers` (HTTP) → `services` (regras de negócio) →
`repositories` (acesso a dados) → `models`/`schemas`. Cada camada depende apenas da
camada abaixo dela, o que facilita testar `services` com repositórios mockados, sem
precisar de banco de dados real, e mantém regra de negócio fora dos endpoints.

A justificativa completa (princípios que inspiraram essa escolha, trade-offs) está na
resposta da [Parte 1 — Questão 2](#questão-2).

**Schema do banco:** as tabelas são criadas via `Base.metadata.create_all()` do
SQLAlchemy (sem ferramenta de migrations dedicada), suficiente para o escopo desta
prova. Ver seção [Parte 4](#parte-4--docker-e-orquestração) para detalhes de como isso roda no startup da
aplicação.

## Parte 1 — Arquitetura e Organização (teórica)

### Questão 1

Organizaria os microsserviços por área de responsabilidade de negócio: um serviço para Pedidos/Estoque, outro para Financeiro, outro para Clientes, cada um com seu próprio banco de dados. A principal motivação para essa separação é evitar um single point of failure: se o serviço de Financeiro tiver instabilidade, isso não deve necessariamente derrubar a capacidade de criar pedidos ou consultar estoque. Além disso, essa separação permite que os serviços evoluam de forma independente, sejam implantados separadamente, e até utilizem tecnologias diferentes internamente, se fizer sentido para o problema de cada um.

Usaria comunicação síncrona (REST) quando a resposta é necessária imediatamente para decidir o próximo passo do fluxo, como verificar se um cliente existe antes de permitir a criação de um pedido. Usaria comunicação assíncrona (via fila) quando a ação seguinte não precisa bloquear a resposta ao usuário, como notificar o serviço Financeiro sobre um novo pedido para gerar uma cobrança. Isso também torna o sistema mais resiliente: se o Financeiro estiver temporariamente indisponível, a mensagem permanece na fila até ser processada, sem impedir a criação do pedido.

Cada microsserviço teria seu próprio banco PostgreSQL, isolado dos demais, mantendo a independência entre os serviços: o serviço de Pedidos/Estoque não deveria acessar diretamente o banco do Financeiro, por exemplo, e sim se comunicar via API ou fila quando precisasse de dados de outro domínio. O Redis entraria com pelo menos dois papéis práticos, que utilizei nesta própria prova: cache de leituras (evitando consultas repetidas ao Postgres para dados que não mudam com frequência, como fiz na listagem de produtos) e fila de mensagens para comunicação assíncrona entre serviços (como fiz com o worker usando arq para processar tarefas em segundo plano). Além desses dois usos, o Redis também poderia atuar como mecanismo de pub/sub, permitindo que um serviço notifique múltiplos outros sobre um evento, e como lock distribuído, garantindo que múltiplas instâncias de um mesmo serviço não executem uma mesma ação concorrentemente.

Um API Gateway funcionaria como ponto único de entrada para todas as requisições externas, direcionando cada uma para o microsserviço correto (Pedidos/Estoque, Financeiro ou Clientes), sem que o cliente precise conhecer os endereços internos de cada serviço. Além do roteamento, o Gateway centralizaria responsabilidades transversais como autenticação (validando o JWT uma única vez, antes de rotear a requisição), rate limiting, e logging de todas as requisições que entram no sistema. Ferramentas como Kong ou Nginx são exemplos comuns usados para essa função.

Para observabilidade, utilizaria os três pilares principais: logs, métricas e tracing.

Para métricas, utilizaria Prometheus fazendo scraping periódico das aplicações, com painéis no Grafana. Priorizaria monitorar: taxa de erros por código HTTP (4xx e 5xx, separando erros de cliente dos de servidor), latência das requisições (p50/p95/p99), e disponibilidade de cada microsserviço individualmente, já que num ERP é importante identificar rapidamente se um serviço específico está degradado sem afetar a visão geral do sistema.

Para logs, centralizaria os registros de todos os microsserviços em um local único (ex: ELK Stack ou Loki), facilitando investigação de problemas sem precisar acessar cada serviço individualmente.

Para tracing, utilizaria uma ferramenta como Jaeger ou OpenTelemetry, permitindo acompanhar uma requisição específica conforme ela atravessa múltiplos microsserviços (por exemplo, uma criação de pedido que passa por Pedidos, Clientes e Financeiro), identificando em qual etapa específica ocorreu lentidão ou falha.

Como prioridade de monitoramento em um ERP, focaria primeiro em: disponibilidade dos serviços críticos (como o de Pedidos, que impacta diretamente a operação), taxa de erros nas integrações entre serviços, e tempo de resposta das operações mais usadas pelos usuários finais.

### Questão 2

Organizei o projeto em camadas separadas (`routers`, `services`, `repositories`, `schemas`, `models`, `core`) com o objetivo principal de manter cada parte do código com uma única responsabilidade, facilitando manutenção, testabilidade e desacoplamento entre as partes.

`routers`: contém os endpoints da API, os caminhos que o cliente acessa (`POST /produtos`, `GET /produtos`, etc). Essa camada só recebe a requisição, repassa para o `service` correspondente, e devolve a resposta. Não contém lógica de negócio nem acesso direto ao banco.

`services`: contém a lógica de negócio e as decisões do sistema. É aqui que ficam as regras sobre o que fazer com os dados. Por exemplo, no cache de listagem de produtos, foi o `service` que decidiu a lógica: primeiro verifica se existe no Redis; se não existir, busca no banco via `repository` e depois guarda no cache. Da mesma forma, no endpoint de dashboard (Parte 2, Q4), foi o `service` que orquestrou as chamadas em paralelo às três fontes simuladas, com timeout e retry.

`repositories`: responsável exclusivamente pelo acesso a dados, executando queries no banco (via SQLAlchemy), sem tomar nenhuma decisão de negócio. Ele só executa o que é pedido (buscar, criar, atualizar, deletar), sem saber, por exemplo, que existe cache envolvido no fluxo.

`schemas`: define os formatos de entrada e saída da API, usando Pydantic. Aqui ficam as validações dos dados recebidos (preço não pode ser negativo, nome não pode ser vazio) e o formato dos dados devolvidos ao cliente. Existem schemas diferentes para cada momento (criação, atualização parcial, resposta), já que os campos exigidos mudam conforme o contexto. Por exemplo, ao criar um produto, o cliente não deve enviar `id` nem as datas, que são geradas pelo banco.

`models`: define a estrutura das tabelas do banco de dados via SQLAlchemy (ORM). Os atributos de cada classe representam as colunas da tabela correspondente no PostgreSQL.

`core`: contém configurações e integrações transversais do projeto, usadas por várias camadas: conexão com o banco de dados, configurações lidas do `.env`, cliente Redis, autenticação (JWT), fila de tarefas (arq).

Essa separação garante que cada camada só conhece a camada imediatamente abaixo dela (o `router` não fala diretamente com o banco, por exemplo), o que permite trocar detalhes de implementação, como adicionar cache com Redis ou trocar a estratégia de autenticação, sem impactar as demais camadas. Foi o que aconteceu, por exemplo, ao adicionar cache no endpoint de listagem: toda a lógica ficou concentrada no `service`, e o `router` não precisou de nenhuma alteração.

Quanto aos princípios que inspiraram essa escolha: a separação de responsabilidades segue uma ideia próxima ao princípio de responsabilidade única (do SOLID) e a uma versão simplificada de Clean Architecture, sem a intenção de aplicar um framework arquitetural completo. O objetivo foi manter o código organizado e testável dentro do escopo desta prova.

## Parte 3 — API RESTful (CRUD real de ERP)

### Questão 6 (prática)

Implementada em `app/models/produto.py`, `app/schemas/produto.py`,
`app/repositories/produto.py`, `app/services/produto.py` e
`app/routers/produto.py`: CRUD completo de Produtos (`id`, `nome`, `preco`,
`quantidade_em_estoque`, `data_criacao`, `data_atualizacao`), validação via
Pydantic (preço não negativo, nome não vazio nem numérico), persistência em
PostgreSQL via SQLAlchemy, e paginação/filtros (`nome`, faixa de preço,
`estoque_abaixo_de`) em `GET /produtos`.

Cada aspecto já está detalhado em sua própria seção — esta apenas resume e
aponta pra elas, sem duplicar o conteúdo técnico:

- **Estrutura em camadas** (por que `routers`/`services`/`repositories`/
  `schemas`/`models` existem, e por que SQLAlchemy síncrono foi a escolha):
  [Arquitetura e estrutura de pastas](#arquitetura-e-estrutura-de-pastas) e
  [Parte 1 — Questão 2](#questão-2).
- **Cache Redis** no `GET /produtos` (estratégia de chave, TTL, por que sem
  invalidação ativa por ora): [Cache (Redis)](#cache-redis).
- **Worker de fila** disparado pelo `PATCH /produtos/{id}` (alerta de estoque
  baixo processado em background, sem bloquear a resposta):
  [Worker de fila (arq)](#worker-de-fila-arq).
- **Autenticação JWT** protegendo os endpoints de escrita
  (`POST`/`PATCH`/`DELETE`), com `GET` público (leitura de catálogo, não
  sensível): [Autenticação (JWT)](#autenticação-jwt).
- **Testes de validação dos schemas** (`ProdutoCreate`): [Testes](#testes).
- **Dockerização** da aplicação e do banco: [Parte 4 — Docker e
  Orquestração](#parte-4--docker-e-orquestração).

## Cache (Redis)

O endpoint `GET /produtos` (listagem paginada) é cacheado no Redis.

**Estratégia de chave**: a chave reflete todos os parâmetros da consulta (`page`,
`page_size`, e os filtros `nome`, `preco_min`, `preco_max`, `estoque_abaixo_de`), no
formato `produtos:list:page=1:page_size=20:nome=:preco_min=:preco_max=:estoque_abaixo_de=`.
Isso significa que cada combinação de página/filtros tem sua própria entrada de
cache — uma busca por `nome=caneta` não interfere na listagem sem filtro, por
exemplo.

**Estratégia de expiração (TTL)**: cada entrada expira em **30 segundos**
(`redis_client.setex`), sem invalidação ativa nas rotas de escrita
(`POST`/`PATCH`/`DELETE`). Foi a estratégia escolhida para este escopo porque:

- É simples de implementar e de explicar — não exige rastrear quais chaves de
  listagem podem ter sido afetadas por uma escrita (o que fica mais complexo
  justamente por causa da combinação de filtros/paginação na chave: uma escrita
  em um produto pode afetar múltiplas chaves de listagem diferentes, ex:
  `estoque_abaixo_de=10` e `estoque_abaixo_de=20` ao mesmo tempo);
- Um TTL curto limita a janela de inconsistência a um valor previsível e pequeno,
  o que é aceitável para uma listagem de produtos (não é um dado que precisa ser
  100% em tempo real, diferente de, por exemplo, saldo financeiro).

**O que eu faria diferente com mais tempo**: implementar invalidação ativa —
deletar (ou usar `SCAN` + `DEL` nas chaves com prefixo `produtos:list:*`) as
entradas de cache relevantes sempre que um produto for criado, atualizado ou
deletado. Isso eliminaria a janela de inconsistência do TTL às custas de mais
complexidade (rastrear/varrer chaves afetadas). Também consideraria cachear
`GET /produtos/{id}` individualmente, com invalidação pontual da chave daquele id
específico no update/delete (mais simples de invalidar corretamente do que a
listagem, já que não depende de filtros).

## Worker de fila (arq)

**A tarefa**: `verificar_estoque_baixo` (`app/workers/tasks.py`) recebe um
`produto_id`, consulta a quantidade em estoque **atual** desse produto no banco
e loga um alerta estruturado (`logger.warning`) se estiver abaixo de 10 unidades
(`ESTOQUE_BAIXO_THRESHOLD`). Não há sistema de notificação — o log já demonstra
o padrão pedido (enfileirar → processar em background); um passo natural com
mais tempo seria trocar o log por um evento publicado (email, Slack, outra fila).

**Por que consulta o estoque atual em vez de usar o valor de quando o job foi
enfileirado**: se dois `PATCH` no mesmo produto acontecerem em sequência rápida
(antes do worker processar o primeiro job), o job só teria sentido checando o
estado mais recente — checar um valor already-stale seria enganoso. Efeito
colateral aceitável: se dois updates enfileirarem dois jobs próximos, os dois
podem acabar checando o mesmo valor final (idempotente, sem problema aqui).

**Como é disparado**: `PATCH /produtos/{id}` (`app/routers/produto.py`) compara
a quantidade antes/depois do update; se a quantidade **diminuiu**, enfileira o
job via `BackgroundTasks.add_task(...)`, que roda **depois** da resposta HTTP já
ter sido enviada — a chamada `pool.enqueue_job(...)` em si só publica a
mensagem no Redis (rápido), então na prática o cliente da API não percebe
diferença de latência entre um `PATCH` que enfileira e um que não enfileira
(medido: ~13ms de resposta, contra ~400-500ms até o worker sequer pegar o job).

**Broker**: o mesmo Redis já usado pelo cache (`REDIS_URL`) — `arq` guarda a
fila e o resultado dos jobs lá, sem precisar de outro serviço.

### Rodando o worker

- **Local** (com o venv ativo, Postgres/Redis já rodando):
  `arq app.workers.tasks.WorkerSettings`
- **Docker**: já sobe automaticamente com `docker compose up` — é o serviço
  `worker` no `docker-compose.yml`, mesma imagem do `app`, só trocando o
  comando (`arq app.workers.tasks.WorkerSettings` em vez de `uvicorn`).

**Sobre o healthcheck do `worker`**: a imagem herda o `HEALTHCHECK` do
Dockerfile, que testa `http://localhost:8000/health` — isso só existe no
serviço `app` (o worker não serve HTTP nenhum), então esse healthcheck foi
**desabilitado explicitamente** (`healthcheck: disable: true`) só pro serviço
`worker` no compose, pra não ficar marcado como "unhealthy" por engano.

### Como ver a tarefa funcionando

1. Suba o worker (local ou via `docker compose up`).
2. Faça login (ver [Autenticação (JWT)](#autenticação-jwt)) e crie um produto
   com `quantidade_em_estoque` alto (ex: 20).
3. `PATCH` esse produto reduzindo a quantidade pra abaixo de 10 (ex:
   `{"quantidade_em_estoque": 3}`).
4. No log do worker (terminal local, ou `docker compose logs worker`), aparece:
   `ALERTA DE ESTOQUE BAIXO: produto_id=... nome='...' quantidade_em_estoque=3 limite=10`

Qualquer redução de estoque enfileira o job, mesmo que o valor final continue
acima de 10 — nesse caso o log final é só informativo
(`verificar_estoque_baixo: produto_id=... ok`), sem o alerta. Um `PATCH` que só
**aumenta** o estoque (ou que não toca em `quantidade_em_estoque`) não enfileira
nada — um aumento nunca faz um produto cruzar o limite de estoque baixo pra
baixo, então não há o que verificar.

## Parte 2 — Assíncrono e Concorrência

### Questão 3 (teórica)

`asyncio` é indicado para operações que passam a maior parte do tempo esperando (I/O), como chamadas de rede, consultas a serviços externos ou operações de banco de dados. Ele funciona com um único processo e uma única thread, mas de forma inteligente: enquanto uma tarefa está esperando uma resposta, o programa aproveita esse tempo ocioso para avançar em outras tarefas, em vez de ficar bloqueado esperando uma de cada vez. Utilizei esse conceito no endpoint de dashboard (Parte 2, Q4), consultando três serviços simulados simultaneamente com `asyncio.gather`.

`threading` também é voltado para operações de espera (I/O), de forma semelhante ao `asyncio`, mas utiliza múltiplas threads reais do sistema operacional em vez de um único fluxo controlado. É útil principalmente quando se trabalha com bibliotecas que não têm suporte nativo a `async`/`await`.

`multiprocessing` é indicado para tarefas que exigem processamento pesado de CPU, e não espera de rede, como processar um arquivo grande realizando cálculos linha a linha. Diferente das duas abordagens anteriores, o `multiprocessing` cria processos Python totalmente separados, permitindo paralelismo real utilizando múltiplos núcleos do processador.

Uma diferença importante entre essas abordagens está relacionada ao GIL (Global Interpreter Lock) do Python, que permite que apenas uma thread execute código Python por vez dentro de um mesmo processo. Isso significa que `threading` não traz ganho de performance em tarefas de CPU intensiva (o GIL continua limitando a execução a uma thread por vez), sendo útil apenas para tarefas de espera. Já o `multiprocessing`, por criar processos separados (cada um com seu próprio interpretador Python), consegue contornar essa limitação e realizar processamento paralelo de verdade.

Exemplos de uso em um cenário de ERP:

- **asyncio**: consultar simultaneamente APIs de estoque, financeiro e clientes para montar um dashboard, como implementado na Parte 2, Questão 4.
- **multiprocessing**: processar um arquivo CSV grande com milhares de linhas, aplicando cálculos em cada uma.
- **threading**: realizar operações de I/O utilizando bibliotecas mais antigas que não possuem suporte nativo a `async`/`await`.

### Questão 4 (prática) — `GET /dashboard`

Endpoint isolado (não depende do CRUD de Produtos, sem autenticação) que consulta
3 fontes simuladas — `estoque-service`, `financeiro-service`, `cliente-service`
— em paralelo, cada uma como uma função `async` com sua própria latência
(`app/services/external_services.py`), orquestradas em
`app/services/dashboard_service.py`.

**Paralelismo com `asyncio.gather`**: as 3 chamadas são disparadas de uma vez com
`asyncio.gather`. Prova disso: `estoque-service` leva 0.3s, `financeiro-service`
(com retry) leva ~0.8s, e `cliente-service` estoura o timeout de 2s — se fossem
sequenciais, a resposta demoraria pelo menos `0.3 + 0.8 + 2.0 = 3.1s` (ou até
`6.1s` se o timeout não cortasse o `cliente-service` mais cedo); o endpoint
responde em **~2.0s** (medido com `TestClient`), tempo dominado só pela fonte
mais lenta, não pela soma de todas.

**Timeout individual**: cada chamada é envolvida em
`asyncio.wait_for(chamada(), timeout=2.0)`. `cliente-service` simula uma
latência de 5s de propósito — o `wait_for` cancela e considera "erro" aos 2s,
sem esperar os 5s completos e sem que isso afete as outras duas chamadas, que
continuam seu curso normalmente dentro do mesmo `gather`.

**Retry**: `financeiro-service` está propositalmente configurado pra falhar na
primeira chamada de cada processo (`RuntimeError` simulando indisponibilidade
temporária) e funcionar normalmente a partir da segunda — `_call_with_timeout`
tenta 1 vez extra (`retries=1`) antes de desistir, e nesse caso o retry recupera
a falha automaticamente (fica registrado como sucesso na resposta final, sem o
cliente da API perceber que houve uma falha por trás).

**Graceful degradation**: `_call_with_timeout` nunca propaga exceção — sempre
devolve um dicionário com `status: "ok"` ou `status: "erro"`. Isso significa que
`asyncio.gather` nunca precisa de `return_exceptions=True`: uma fonte falhando
(timeout ou exceção) não derruba a requisição inteira nem as outras chamadas em
andamento. A resposta final sempre retorna `200`, com `fontes_com_sucesso`,
`fontes_com_falha` e `completo` (`false` quando pelo menos uma fonte falhou),
para o cliente da API decidir o que fazer com uma resposta parcial.

**Exemplo de resposta** (com a falha do `cliente-service` propositalmente
provocada, e o retry do `financeiro-service` já recuperado):

```json
{
  "fontes": [
    {"fonte": "estoque-service", "status": "ok", "dados": {"produtos_em_estoque": 842, "produtos_estoque_baixo": 5}, "erro": null},
    {"fonte": "financeiro-service", "status": "ok", "dados": {"faturamento_mes": 125430.5, "pedidos_pendentes_pagamento": 7}, "erro": null},
    {"fonte": "cliente-service", "status": "erro", "dados": null, "erro": "timeout after 2.0s"}
  ],
  "fontes_com_sucesso": ["estoque-service", "financeiro-service"],
  "fontes_com_falha": ["cliente-service"],
  "completo": false
}
```

**Por que `async def` aqui e `def` no CRUD de Produtos**: este endpoint não tem
nenhuma chamada bloqueante/síncrona no caminho — é `asyncio.gather`/`wait_for`
sobre mocks `async` do início ao fim, o caso de uso exato pra `async def`. Já os
endpoints de Produtos usam uma `Session` síncrona do SQLAlchemy, por isso são
`def` (ver `app/routers/produto.py`).

## Autenticação (JWT)

Os endpoints de escrita de Produtos (`POST`, `PATCH`, `DELETE /produtos`) exigem um
token JWT válido. Os endpoints de leitura (`GET /produtos`, `GET /produtos/{id}`)
são públicos.

**Por que GET ficou público**: tratei a listagem/consulta de produtos como dado de
catálogo, não sensível — uma escolha razoável pra esse domínio (não é o mesmo que
expor saldo financeiro ou dado de cliente, por exemplo). O que precisa de proteção
é a capacidade de *alterar* o estoque/catálogo, daí a escrita exigir autenticação.
Numa API real de produção, dependendo do caso de uso (ex: catálogo interno, não
público), eu protegeria o GET também — é só adicionar o mesmo
`Depends(get_current_user)` nos routers de leitura.

**Usuário fixo, sem cadastro/tabela de usuários**: o enunciado permite
explicitamente usuário/senha fixos via `.env` para o escopo da prova, e não há
necessidade real de múltiplos usuários, roles ou refresh token aqui — só demonstrar
o mecanismo de autenticação JWT funcionando. Um usuário fixo (`AUTH_USERNAME` +
`AUTH_PASSWORD_HASH` no `.env`) é a opção mais simples que atende ao requisito, sem
introduzir uma tabela `users`, endpoint de cadastro, etc. — que seriam escopo de um
sistema de auth de produção, fora do que foi pedido.

A senha não fica em texto puro no `.env`: `AUTH_PASSWORD_HASH` guarda o hash bcrypt
(gerado uma vez com `passlib`), e o login compara a senha recebida contra o hash
(`passlib.context.CryptContext.verify`) — mesmo sendo um único usuário de teste,
evitar comparar/guardar senha em texto puro é hábito que vale manter.

### Como obter e usar um token

**Usuário de teste**: `admin` / senha `admin123` (o `.env.example` já vem com o
hash bcrypt dessa senha em `AUTH_PASSWORD_HASH`).

**Via Swagger (`/docs`)**: clique no cadeado "Authorize" no canto superior direito,
preencha `username=admin` e `password=admin123` (os outros campos ficam em
branco) e confirme. O Swagger guarda o token e passa automaticamente
`Authorization: Bearer <token>` em todas as chamadas seguintes feitas por ali —
inclusive nos botões "Try it out" dos endpoints protegidos.

**Via linha de comando**:

```bash
# 1. login (o endpoint espera form-urlencoded, não JSON, por isso -d ao invés de --json)
curl -X POST http://localhost:8000/auth/login -d "username=admin&password=admin123"
# -> {"access_token": "<token>", "token_type": "bearer"}

# 2. usar o token num endpoint protegido
curl -X POST http://localhost:8000/produtos \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"nome": "Caneta Azul", "preco": "2.50", "quantidade_em_estoque": 100}'
```

Sem o header `Authorization`, ou com um token inválido/expirado/malformado, os
endpoints protegidos retornam `401 Unauthorized` (`{"detail": "Not authenticated"}`
quando o header está ausente, `{"detail": "Could not validate credentials"}` quando
o token é inválido/expirado). O token expira em 60 minutos por padrão
(`JWT_ACCESS_TOKEN_EXPIRE_MINUTES` no `.env`).

**O que eu faria diferente com mais tempo/em produção**: tabela de usuários real
com senha hasheada por usuário (não uma fixa via env), refresh tokens (hoje é só
access token de vida curta, sem forma de renovar sem logar de novo), roles/escopos
(hoje é tudo-ou-nada: autenticado ou não, sem diferenciar quem pode fazer o quê),
e rate limiting no `/auth/login` (hoje não há proteção contra força bruta).

## Testes

```bash
source .venv/bin/activate   # ou o venv que preferir, com requirements.txt instalado
pytest -v
```

23 testes, todos unitários — **nenhum precisa de Postgres/Redis rodando** (rodam
em ~0.4s). Cobrem, em ordem de prioridade:

1. **`tests/test_schemas_produto.py`** — validação do `ProdutoCreate`: preço
   negativo falha, preço zero é aceito (o enunciado só proíbe negativo), nome
   vazio/só espaço falha, nome ausente/`None` falha, nome puramente numérico
   falha (`"12345"`, `"99.90"`, `"-5"`), dados válidos passam.
2. **`tests/test_agente_service.py`** — o agente da Parte 5 (Q8): as 3
   intenções reconhecidas (`estoque_baixo`, `preco_produto`, `total_produtos`)
   retornam a resposta estruturada esperada, uma pergunta reconhecida mas sem
   resultado (`sucesso: true`, lista vazia) é diferenciada de uma pergunta não
   reconhecida (`sucesso: false`, erro claro). `produto_service.list_produtos`
   é mockado (`monkeypatch`) — o teste cobre a lógica do agente (interpretação
   + montagem da resposta), não a query em si.
3. **`tests/test_dashboard_service.py`** — `_call_with_timeout` da Parte 2
   (Q4): sucesso direto, timeout gera `status: erro` (com `TIMEOUT_SECONDS`
   reduzido via `monkeypatch` pra rodar rápido), retry recupera uma falha
   transitória, e falha persistente esgota as tentativas e retorna erro.

**Por que não há testes de repository/integração com banco real ainda**: dado o
tempo disponível, priorizei testes unitários de validação (schemas) e lógica de
negócio isolada (agente, retry/timeout do dashboard) — código que é barato de
testar sem infraestrutura e que já cobre as partes com mais regra explícita do
enunciado (validação de dados, interpretação de linguagem natural, graceful
degradation). Testes de repository/integração (rodar contra um Postgres/Redis
real, de teste, provavelmente via um container efêmero ou um banco SQLite
in-memory para os casos que permitem) seriam o próximo passo natural com mais
tempo — cobririam coisas que os testes unitários atuais não alcançam, como a
tradução correta dos filtros (`nome`, faixa de preço, `estoque_abaixo_de`) em
SQL de verdade, o comportamento do cache Redis (hit/miss/TTL) e o fluxo
completo do worker `arq` ponta a ponta.

## Parte 4 — Docker e Orquestração

- **Dockerfile em estágio único** (não multi-stage): todas as dependências do
  projeto (`fastapi`, `sqlalchemy`, `psycopg2-binary`, `python-jose[cryptography]`,
  `passlib[bcrypt]`, `redis`) têm wheel pré-compilada para a plataforma da imagem
  — não há nenhum passo de compilação a isolar num estágio "builder". Um
  multi-stage aqui adicionaria complexidade sem reduzir o tamanho final da
  imagem nem a superfície de dependências, então optei por simplicidade. A
  imagem roda como usuário não-root (`appuser`), e `requirements.txt` é copiado
  e instalado antes do código da aplicação para aproveitar o cache de camadas do
  Docker (mudanças no código não invalidam a camada de instalação de deps).
- **Healthcheck da app**: endpoint dedicado `GET /health`, que não consulta banco
  nem Redis — só confirma que o processo está de pé (ver `app/main.py`). O
  `HEALTHCHECK` do Dockerfile chama esse endpoint via
  `python -c "urllib.request.urlopen(...)"`, evitando instalar `curl` só para
  isso (a imagem `python:3.12-slim` não traz `curl` por padrão).
- **Healthcheck de `postgres`/`redis`**: `pg_isready` e `redis-cli ping`,
  respectivamente — ambos já disponíveis nas imagens oficiais, sem necessidade de
  ferramentas extras.
- **`depends_on: condition: service_healthy`**: o serviço `app` só é iniciado
  depois que `postgres` e `redis` estão de fato prontos para aceitar conexões
  (não apenas "o container iniciou") — evita que `init_db()`, chamado no startup
  da aplicação, tente conectar a um Postgres ainda inicializando.
- **Variáveis sensíveis via `.env`**: nenhum segredo é commitado — `.env` está no
  `.gitignore`; `.env.example` documenta o formato esperado. Dentro do
  `docker-compose.yml`, as credenciais do Postgres (`POSTGRES_USER/PASSWORD/DB`)
  vêm do `.env` por substituição automática do Compose; `DATABASE_URL`/
  `REDIS_URL` do serviço `app` são montadas explicitamente ali (não herdadas do
  `.env`) porque precisam apontar para os hosts internos `postgres`/`redis`, não
  `localhost` — ver [Como rodar o projeto](#como-rodar-o-projeto) para a
  explicação completa dessa diferença.
- Instruções completas de execução (Docker e local) estão em
  [Como rodar o projeto](#como-rodar-o-projeto).

## Parte 5 — Desafio de IA (agente baseado em regras)

### Questão 8 (prática) — `POST /agente/perguntar`

Endpoint que recebe uma pergunta em linguagem natural (português) sobre dados de
Produtos e devolve uma resposta estruturada. **Não usa nenhuma API de LLM
externa** (OpenAI, Anthropic, etc.) — a "interpretação" é feita por regex e
casamento de palavras-chave (`app/services/agente_service.py`), conforme
exigido pelo enunciado (a prova não integra com IA de terceiros em produção).

**Como funciona**: `interpretar_pergunta()` testa a pergunta contra 3 padrões de
regex, cada um mapeado numa "intenção":

| Intenção | Exemplo de pergunta | Parâmetro extraído |
|---|---|---|
| `estoque_baixo` | "quais produtos estão com estoque abaixo de 10 unidades?" | `estoque_abaixo_de: 10` |
| `preco_produto` | "qual o preço do produto Caneta Azul?" | `nome: "Caneta Azul"` |
| `total_produtos` | "quantos produtos existem no total?" | *(nenhum)* |

Se nenhum padrão bater, a resposta vem com `sucesso: false` e um `erro`
explicando que a pergunta não foi entendida (nunca um erro 500 — o endpoint
sempre responde `200`, com o "sucesso"/"erro" no corpo, não no status HTTP,
igual um serviço de busca que pode simplesmente não ter resultado).

**Reaproveitamento, sem duplicar lógica de consulta**: as 3 intenções são
resolvidas chamando `produto_service.list_produtos(...)` — a mesma função usada
por `GET /produtos`. `estoque_baixo` usa o filtro `estoque_abaixo_de` (o mesmo
da Parte 3); `preco_produto` usa o filtro `nome` (busca parcial,
case-insensitive, a mesma da listagem — por isso pode retornar mais de um
produto, ou nenhum); `total_produtos` só lê o `total` já calculado pela
paginação (`page_size=1`, sem trazer todos os registros). Nenhuma query nova
foi escrita para o agente.

**Formato da resposta**:

```json
{
  "pergunta": "Quais produtos estão com estoque abaixo de 10 unidades?",
  "intencao": "estoque_baixo",
  "parametros": {"estoque_abaixo_de": 10},
  "sucesso": true,
  "resultado": {"produtos": [...], "total": 2},
  "erro": null
}
```

**Limitações (é regex, não NLP de verdade)**:

- Só reconhece as 3 frases-padrão acima (com alguma variação de palavras
  permitida pelo regex) — qualquer reformulação fora desses padrões
  (sinônimos, ordem diferente das palavras, erros de digitação) cai em "não
  entendi", mesmo que um humano entendesse facilmente.
- Não faz nenhuma forma de correção ortográfica, sinônimos, ou entendimento de
  contexto entre perguntas (cada chamada é isolada, sem memória de conversa).
- `preco_produto` depende de o nome do produto aparecer quase literalmente na
  pergunta (é passado direto como filtro `ILIKE %nome%` — funciona bem para
  "Caneta Azul", mas não entende uma descrição indireta do produto).
- Endpoint público (sem JWT), como `GET /produtos` — só lê dados, não expõe
  nada que a listagem pública já não expusesse.

Como desenhar isso de forma plugável para um LLM real no futuro (tool/function
calling, MCP, guardrails, custo/latência/observabilidade) é a resposta da
Questão 9, abaixo.

### Questão 9 (teórica)

Tool/Function Calling: em vez de utilizar regras fixas como fiz na Questão 8, exporia ao LLM um conjunto de "ferramentas" descritas com nome, propósito e parâmetros esperados, por exemplo, uma ferramenta consultar_estoque recebendo um parâmetro limite (número), ou criar_pedido recebendo os dados necessários para criar um pedido. O próprio LLM, ao receber a pergunta em linguagem natural do usuário, decidiria qual ferramenta chamar e com quais parâmetros, de forma estruturada, substituindo a lógica de regex/palavras-chave por uma decisão feita pelo modelo.

MCP (Model Context Protocol): utilizaria o padrão MCP para expor essas ferramentas ao agente. O MCP padroniza a forma como ferramentas são descritas e disponibilizadas a um LLM, evitando que cada integração precise ser feita de forma proprietária para cada modelo. Na arquitetura de microsserviços descrita na Parte 1, um servidor MCP se encaixaria como um serviço adicional, atuando como intermediário entre o LLM e os microsserviços já existentes (Pedidos/Estoque, Financeiro, Clientes). Esse servidor exporia ferramentas como consultar_estoque ou criar_pedido, e cada uma delas, internamente, faria uma chamada REST comum ao microsserviço responsável, exatamente como já ocorre na comunicação síncrona descrita anteriormente. Dessa forma, o LLM nunca acessaria diretamente o banco de dados ou os microsserviços; ele decide o que fazer, enquanto o servidor MCP e os microsserviços decidem como fazer, mantendo a mesma separação de responsabilidades já utilizada no restante do sistema.

Guardrails: classificaria as ferramentas disponíveis ao agente por nível de risco. Ferramentas de leitura (consultar estoque, consultar pedido) poderiam ser executadas diretamente, já que o impacto de um erro de interpretação é baixo. Já ferramentas de escrita ou destrutivas (deletar um pedido, cancelar uma compra) exigiriam uma etapa de confirmação explícita do usuário antes da execução, evitando que uma interpretação equivocada do LLM cause uma ação irreversível sem consentimento humano. Para lidar com alucinação ou erro de interpretação, todos os parâmetros extraídos pelo LLM passariam pela mesma validação já utilizada no restante da API (Pydantic), rejeitando parâmetros inválidos antes de qualquer execução; além disso, restringiria o conjunto de ferramentas disponíveis ao mínimo necessário, reduzindo a superfície de erro possível, e garantiria que toda resposta do agente fosse baseada exclusivamente em dados reais retornados pelas ferramentas, nunca inventados pelo próprio modelo.

Custo, latência e observabilidade: diferente de chamadas tradicionais de API, chamadas a LLMs costumam ter custo variável por volume de texto processado, o que exige monitorar não apenas disponibilidade, mas também gasto ao longo do tempo; uma estratégia comum para mitigar isso é cachear respostas para perguntas repetidas ou muito similares, reaproveitando a mesma infraestrutura de cache com Redis já utilizada no projeto. Quanto à latência, LLMs tendem a responder mais lentamente que uma consulta tradicional de banco, o que pode justificar o uso de comunicação assíncrona (como o worker com arq implementado neste projeto) em cenários onde não é necessário bloquear o usuário esperando a resposta do modelo. Por fim, a observabilidade de um sistema com LLM deveria incluir logging estruturado de prompts e respostas, tanto para depuração quanto para eventual auditoria de decisões tomadas pelo agente, além de uma estratégia de fallback para quando o provedor de IA estiver indisponível, devolvendo uma mensagem de erro clara ao invés de comprometer o funcionamento do restante da aplicação.

## Parte 6 — Pergunta de Perfil

### Questão 10

Reagiria de forma positiva a essa decisão. Considero minha capacidade de adaptação a novas tecnologias, sejam elas mais modernas ou mais legadas, um dos meus pontos fortes. Já precisei me virar tanto em situações envolvendo tecnologias mais antigas, recorrendo à documentação e resolvendo problemas com pouco suporte direto, quanto aprendendo ferramentas novas rapidamente quando o contexto exigiu. Encararia aprender Go como mais um desafio desse tipo, independente de ser algo totalmente novo pra mim.

Nunca trabalhei com Go, então não tenho experiência prática para avaliar profundamente seus pontos fortes e fracos frente a outras linguagens. Mas, pelo que conheço conceitualmente, Go é uma escolha comum e tecnicamente razoável para esse tipo de cenário: possui concorrência nativa leve (goroutines), baixo overhead de execução por ser compilado, e gera um binário único sem dependências externas, o que facilita o deploy. Essas características se alinham diretamente com o que foi descrito no cenário (alta performance, baixa latência, alto throughput).

Caso eu discordasse tecnicamente da escolha em uma situação real, argumentaria de forma aberta e respeitosa, trazendo dados concretos: pesquisaria alternativas, apresentaria vantagens e desvantagens de cada opção com clareza, e proporia uma conversa técnica com o time para decidir juntos, sempre buscando entender o contexto e as razões por trás da decisão original antes de simplesmente discordar.

Concordando com a escolha, mas sem experiência prévia em Go, me organizaria estudando a linguagem de forma dedicada, buscando documentação oficial, cursos e projetos práticos pequenos antes de atuar diretamente na frente de produção. Buscaria também apoio do time, perguntando sobre padrões e convenções já utilizados internamente, e seria transparente sobre minha curva de aprendizado, priorizando entregar com qualidade mesmo que isso exigisse mais tempo de estudo inicial.

## Parte 7 — Portfólio

### Questão 11

Escolhi este projeto por ser público; a maior parte do meu trabalho mais recente está em repositórios privados da empresa onde atuo atualmente (https://github.com/lehmkuhlJoao/a3-ingressos).

Qual problema ele resolve: é um sistema de venda de ingressos para eventos, desenvolvido como projeto acadêmico (A3 da faculdade). O foco real do projeto não é ser um produto completo de ticketing, mas demonstrar uma arquitetura distribuída: decomposição em microsserviços, comunicação síncrona e assíncrona, controle de concorrência sobre um recurso escasso (estoque de ingressos), API Gateway, e observabilidade com métricas e dashboards.

Principais decisões técnicas:

Arquitetura com três microsserviços em Python/FastAPI (eventos, compras, notificacoes), Nginx como API Gateway fazendo roteamento por path, PostgreSQL como banco relacional, RabbitMQ como broker de mensagens, e Prometheus + Grafana para observabilidade, tudo orquestrado via Docker Compose.

A decisão técnica mais relevante do projeto está no serviço de compras: usei SELECT ... FOR UPDATE dentro de uma transação para evitar overselling (vender mais ingressos do que o estoque disponível) quando múltiplas compras concorrentes acontecem ao mesmo tempo. Também implementei idempotência via um transaction_id único, evitando que requisições repetidas dupliquem uma compra.

Para comunicação assíncrona, o serviço de compras publica um evento no RabbitMQ após confirmar uma compra, e um worker separado (notificacoes) consome essa fila para simular o envio de confirmação, desacoplando essa responsabilidade do fluxo principal de compra.

Implementei observabilidade desde o início do projeto, não como algo adicionado depois: métricas Prometheus em cada serviço FastAPI e logging estruturado em JSON.

Também cheguei a rodar este projeto na AWS (via AWS Academy Lab), em contato prático com a nuvem, mapeando os conceitos equivalentes entre containers Docker e serviços AWS, como EC2 no lugar de instâncias locais e SQS como alternativa ao RabbitMQ.

O que eu faria diferente hoje:

O ponto mais importante: o serviço de compras acessa diretamente a tabela de eventos no banco compartilhado, em vez de consultar o serviço de eventos via API. Isso quebra o princípio de que cada microsserviço deveria ser dono exclusivo dos seus próprios dados (o mesmo princípio que descrevi na Parte 1 desta prova). O correto seria o serviço de compras chamar um endpoint de reserva/decremento de estoque exposto pelo serviço de eventos, possivelmente usando um padrão de saga para lidar com falhas parciais.

Adicionaria autenticação e hash de senha (hoje não há nenhuma camada de segurança implementada), já que o projeto foi focado deliberadamente nos aspectos de arquitetura distribuída, deixando de lado a camada de segurança.

Adicionaria testes automatizados, especialmente cobrindo o endpoint de compra, que é o trecho crítico de concorrência do sistema e hoje não tem nenhuma cobertura.

Configuraria uma dead-letter queue no RabbitMQ; atualmente, uma mensagem que falha ao ser processada pelo worker de notificações é simplesmente descartada, sem reprocessamento.

Adicionaria versionamento de schema com Alembic, em vez de criar as tabelas via create_all() no boot da aplicação, permitindo evolução controlada do banco.

## Uso de IA

Utilizei o Claude (via Claude Code) como ferramenta de apoio ao longo de todo o desenvolvimento desta prova, mas de forma ativa e supervisionada, não apenas aceitando o que era gerado.

Código: a maior parte do código foi gerada com apoio de IA, mas segui um processo de compreensão antes de aceitar cada parte: pedi explicações detalhadas sobre a sintaxe e as decisões técnicas de cada bloco (SQLAlchemy, Pydantic, Redis, Docker, JWT, arq, etc.) antes de avançar para o próximo, e evitei prosseguir com trechos que eu não conseguia entender ou justificar. Um exemplo concreto de intervenção ativa: em um primeiro momento, o código foi gerado utilizando Alembic para migrations, mas ao perceber que isso não era exigido pelo enunciado e adicionava complexidade desnecessária dado o prazo, pedi a reversão para uma abordagem mais simples (`Base.metadata.create_all()`), documentando essa decisão no histórico de commits.

Optei deliberadamente por uma implementação mais simples em alguns pontos (como a cobertura de testes unitários, focada em validação e lógica de negócio isolada, sem cobertura completa) mesmo sabendo que uma abordagem mais completa seria possível com mais tempo, priorizando entregar algo que eu realmente compreendesse a fundo.

Respostas teóricas (Partes 1, 2 Q3, 5 Q9, 6 e 7): essas respostas não foram geradas pela IA. Na maior parte dos casos eu já tinha uma noção inicial do conteúdo (por experiência prática construída durante esta própria prova, ou por conhecimento prévio, como observabilidade), e utilizei a IA como apoio para organizar, estruturar e complementar tecnicamente minhas respostas, mas o raciocínio, as decisões e o conteúdo central partiram de mim.
