# prova-backend-erp-ia-joaolehmkuhl

Prova prática de Back-end (IA/ERP) para a IPM Sistemas.

> Este README será completado progressivamente conforme cada parte da prova é
> implementada. Seções marcadas como `(TODO)` ainda não foram escritas.

## Sumário

- [Como rodar o projeto](#como-rodar-o-projeto) `(TODO)`
- [Arquitetura e estrutura de pastas](#arquitetura-e-estrutura-de-pastas)
- [Parte 1 — Arquitetura e Organização (teórica)](#parte-1) `(TODO)`
- [Parte 2 — Assíncrono e Concorrência](#parte-2) `(TODO)`
- [Parte 3 — API RESTful (CRUD de Produtos)](#parte-3) `(TODO)`
- [Cache (Redis)](#cache-redis)
- [Parte 4 — Docker e Orquestração](#parte-4) `(TODO)`
- [Parte 5 — Desafio de IA (agente baseado em regras)](#parte-5) `(TODO)`
- [Parte 6 — Pergunta de Perfil](#parte-6) `(TODO)`
- [Parte 7 — Portfólio](#parte-7) `(TODO)`
- [Uso de IA](#uso-de-ia) `(TODO)`

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

## Uso de IA

Este projeto foi desenvolvido com apoio do Claude Code (Anthropic). Esta seção será
detalhada ao final do desenvolvimento, descrevendo especificamente o que foi
gerado/apoiado por IA e o que foi escrito/revisado manualmente, conforme pedido no
enunciado.
