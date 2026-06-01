# Provider Capability Matrix / Матрица возможностей провайдеров

## English

The project is open-source and can run without paid hosted AI services. The
default provider set is `local`:

- embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- rerank: `BAAI/bge-reranker-v2-m3` via sentence-transformers CrossEncoder
- chat/LLM: any Ollama/OpenAI-compatible local server at `http://localhost:11434/v1`

Hosted providers are optional integrations for teams that already have API
keys or want managed inference.

| Provider | Chat | Embeddings | Rerank | Tool Calling | Structured Output | Web Search | Region | Beta | API Style |
|----------|------|------------|--------|--------------|-------------------|------------|--------|------|-----------|
| **OpenAI** | Y | Y | - | Y | Y | - | - | - | openai-compatible |
| **OpenRouter** | Y | Y | - | Y | Y | Y | - | - | openai-compatible |
| **Together** | Y | Y | Direct | Y | - | - | - | - | openai-compatible |
| **DashScope** | Y | Y | Direct | Y | Y | Y | CN | - | dashscope |
| **Jina** | - | Y | Direct | - | - | - | - | - | openai-compatible |
| **Cohere** | Y | Y | Direct | - | - | - | - | - | cohere-v2 |
| **Google** | Y | Y | - | Y | Y | - | - | - | google-native |
| **Local** | Y | Y | Local | - | - | - | - | - | openai-compatible |
| **Yandex** | Y | Y | - | Y | - | Y | RU | Y | openai-compatible |
| **GigaChat** | Y | Y | - | - | - | - | RU | Y | openai-compatible |
| **Moonshot** | Y | - | - | Y | - | Y | CN | Y | openai-compatible |

## Provider Roles

| Role | Primary | Fallback |
|------|---------|----------|
| **Embedding** | Local sentence-transformers | OpenAI, Together, DashScope, Jina, Google |
| **Rerank** | Local CrossEncoder | Cohere, Together, Jina, DashScope, LLM fallback |
| **LLM/Chat** | Local Ollama-compatible server | OpenAI, OpenRouter, Google, DashScope, Together |
| **Agentic** | OpenAI / OpenRouter / DashScope when enabled | Disabled by default |

## Configuration

Providers are configured via `PUT /api/v1/settings` with runtime validation:
- Provider must support assigned role (validated by `provider_supports()`)
- API keys stored in `system_settings` table (persisted across restarts)
- Circuit breaker opens after 5 consecutive failures (60s recovery)

## Русский

Проект является open-source и может работать без платных hosted AI services.
Provider set по умолчанию - `local`:

- embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- rerank: `BAAI/bge-reranker-v2-m3` через sentence-transformers CrossEncoder
- chat/LLM: любой локальный Ollama/OpenAI-compatible server на `http://localhost:11434/v1`

Hosted providers являются опциональными интеграциями для команд, у которых уже
есть API keys или которым нужен managed inference.

| Provider | Chat | Embeddings | Rerank | Tool Calling | Structured Output | Web Search | Region | Beta | API Style |
|----------|------|------------|--------|--------------|-------------------|------------|--------|------|-----------|
| **OpenAI** | Y | Y | - | Y | Y | - | - | - | openai-compatible |
| **OpenRouter** | Y | Y | - | Y | Y | Y | - | - | openai-compatible |
| **Together** | Y | Y | Direct | Y | - | - | - | - | openai-compatible |
| **DashScope** | Y | Y | Direct | Y | Y | Y | CN | - | dashscope |
| **Jina** | - | Y | Direct | - | - | - | - | - | openai-compatible |
| **Cohere** | Y | Y | Direct | - | - | - | - | - | cohere-v2 |
| **Google** | Y | Y | - | Y | Y | - | - | - | google-native |
| **Local** | Y | Y | Local | - | - | - | - | - | openai-compatible |
| **Yandex** | Y | Y | - | Y | - | Y | RU | Y | openai-compatible |
| **GigaChat** | Y | Y | - | - | - | - | RU | Y | openai-compatible |
| **Moonshot** | Y | - | - | Y | - | Y | CN | Y | openai-compatible |

### Роли провайдеров

| Role | Primary | Fallback |
|------|---------|----------|
| **Embedding** | Local sentence-transformers | OpenAI, Together, DashScope, Jina, Google |
| **Rerank** | Local CrossEncoder | Cohere, Together, Jina, DashScope, LLM fallback |
| **LLM/Chat** | Local Ollama-compatible server | OpenAI, OpenRouter, Google, DashScope, Together |
| **Agentic** | OpenAI / OpenRouter / DashScope when enabled | Disabled by default |

### Конфигурация

Providers настраиваются через `PUT /api/v1/settings` с runtime validation:

- Provider должен поддерживать назначенную роль (`provider_supports()`).
- API keys хранятся в таблице `system_settings` и переживают restart.
- Circuit breaker открывается после 5 consecutive failures, recovery - 60s.
