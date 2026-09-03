# prova-backend-erp-ia-joaolehmkuhl

Prova prática de Back-end (IA/ERP) para a IPM Sistemas.

> Este README será completado progressivamente conforme cada parte da prova é
> implementada. Seções marcadas como `(TODO)` ainda não foram escritas.

## Sumário

- [Como rodar o projeto](#como-rodar-o-projeto)
- [Arquitetura e estrutura de pastas](#arquitetura-e-estrutura-de-pastas)
- [Parte 1 — Arquitetura e Organização (teórica)](#parte-1) `(TODO)`
- [Parte 2 — Assíncrono e Concorrência](#parte-2) `(TODO)`
- [Parte 3 — API RESTful (CRUD de Produtos)](#parte-3) `(TODO)`
- [Cache (Redis)](#cache-redis)
- [Autenticação (JWT)](#autenticação-jwt)
- [Parte 4 — Docker e Orquestração](#parte-4)
- [Parte 5 — Desafio de IA (agente baseado em regras)](#parte-5) `(TODO)`
- [Parte 6 — Pergunta de Perfil](#parte-6) `(TODO)`
- [Parte 7 — Portfólio](#parte-7) `(TODO)`
- [Uso de IA](#uso-de-ia) `(TODO)`

## Como rodar o projeto

### Opção 1: Docker Compose (recomendado — um único comando)

```bash
cp .env.example .env   # os valores default já funcionam com o compose
docker compose up --build
```

Isso sobe 3 containers: `postgres`, `redis` e `app` (a API). O `app` só inicia
depois que `postgres` e `redis` reportam `healthy`, e cria as tabelas
automaticamente no startup via `Base.metadata.create_all()` — não há
migração/seed manual necessária (ver "Schema do banco" abaixo).

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
resposta da [Parte 1 — Questão 2](#parte-1).

**Schema do banco:** as tabelas são criadas via `Base.metadata.create_all()` do
SQLAlchemy (sem ferramenta de migrations dedicada), suficiente para o escopo desta
prova. Ver seção [Parte 4](#parte-4) para detalhes de como isso roda no startup da
aplicação.

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

## Parte 2 — Assíncrono e Concorrência

### Questão 3 (teórica)

`(TODO — item 10 da ordem de prioridade; ver CLAUDE.md/PROGRESSO.md)`

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

## Uso de IA

Este projeto foi desenvolvido com apoio do Claude Code (Anthropic). Esta seção será
detalhada ao final do desenvolvimento, descrevendo especificamente o que foi
gerado/apoiado por IA e o que foi escrito/revisado manualmente, conforme pedido no
enunciado.
