# Provider Capability Matrix

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
| **Embedding** | OpenAI (text-embedding-3-small) | Together, DashScope, Jina |
| **Rerank** | Cohere / Together / Jina (direct) | LLM-based reranking via OpenAI/OpenRouter |
| **LLM/Chat** | OpenAI / OpenRouter | Any provider with chat support |
| **Agentic** | OpenAI / OpenRouter (tool_calling) | - |

## Configuration

Providers are configured via `PUT /api/v1/settings` with runtime validation:
- Provider must support assigned role (validated by `provider_supports()`)
- API keys stored in `system_settings` table (persisted across restarts)
- Circuit breaker opens after 5 consecutive failures (60s recovery)
