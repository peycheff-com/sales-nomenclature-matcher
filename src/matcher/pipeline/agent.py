import json
import logging

from duckduckgo_search import DDGS
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.config import settings
from matcher.indexing.search import hybrid_search
from matcher.pipeline.token_tracker import TokenTracker

logger = logging.getLogger(__name__)

_token_tracker: TokenTracker | None = None


def set_token_tracker(tracker: TokenTracker | None) -> None:
    global _token_tracker
    _token_tracker = tracker


def _make_llm_client() -> tuple[AsyncOpenAI, str, dict]:
    """Create an OpenAI-compatible client configured for Agentic tool use."""
    llm_key = settings.active_llm_api_key
    model = settings.llm_model

    extra_headers = {}
    if settings.llm_provider == "openrouter":
        extra_headers["HTTP-Referer"] = "https://matcher.internal"
        extra_headers["X-Title"] = "Sales Nomenclature Matcher"

    client = AsyncOpenAI(
        api_key=llm_key,
        base_url=settings.active_llm_base_url,
        default_headers=extra_headers or None,
        timeout=60.0,
    )
    extra_body = {}

    # Provider-specific native web search enablement
    if settings.llm_provider == "openrouter":
        extra_body["plugins"] = [{"id": "web"}]
    elif settings.llm_provider == "dashscope":
        extra_body["enable_search"] = True
    elif "qwen" in model.lower():
        extra_body["no_thinking"] = True

    return client, model, extra_body


def _web_search(query: str, max_results: int = 4) -> str:
    """Fallback web search tool using DuckDuckGo."""
    try:
        results = DDGS(timeout=10).text(query, max_results=max_results)
        if not results:
            return "No web results found."

        snippets = []
        for r in results:
            snippets.append(f"Title: {r.get('title')}\nSnippet: {r.get('body')}")
        return "\n---\n".join(snippets)
    except Exception as e:
        logger.error(f"Web search failed for query '{query}': {e}")
        return f"Web search failed: {e}"


async def _catalog_search(query: str, session: AsyncSession) -> str:
    """Searches the local product catalog for specific articles or keywords."""
    candidates = await hybrid_search(
        query_text=query, normalized_text=query, session=session, top_n=10
    )
    if not candidates:
        return "No catalog matches found for that query."

    snippets = []
    for c in candidates:
        parts = [f"ID: {c.product_id}", f"Name: {c.name}"]
        if c.article:
            parts.append(f"Article: {c.article}")
        if c.brand:
            parts.append(f"Brand: {c.brand}")
        if c.category_path:
            parts.append(f"Category: {c.category_path}")
        if c.unit:
            parts.append(f"Unit: {c.unit}")
        snippets.append(" | ".join(parts))
    return "\n".join(snippets)


def _decompose_query(query: str) -> str:
    """Decompose a product query into structured components using the normalization pipeline."""
    from matcher.normalization.pipeline import run_pipeline
    from matcher.pipeline.features import extract_features

    ctx = run_pipeline(query)
    attrs = extract_features(ctx)

    result = {
        "normalized_text": ctx.text,
        "brand": attrs.brand,
        "article": attrs.article,
        "numbers": attrs.numbers,
        "dimensions": attrs.dimensions,
        "unit": attrs.unit,
        "packaging": attrs.packaging,
        "tokens": ctx.tokens[:20] if ctx.tokens else [],
    }
    # Identify the leading category word (first alpha token > 3 chars)
    for token in (ctx.tokens or []):
        if len(token) > 3 and token.isalpha():
            result["category_word"] = token
            break

    return json.dumps(result, ensure_ascii=False, indent=2)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "decompose_query",
            "description": (
                "Analyze a product query and break it into structured components: "
                "category word, brand, article, numbers/dimensions, unit, material. "
                "Use this FIRST to understand what the product is before searching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The product text to analyze.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": (
                "Search the internal product catalog by keywords. "
                "Try different queries: category word alone, brand + category, "
                "article number, or simplified product description. "
                "Returns up to 10 matches with IDs, names, articles, brands."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search keywords. Can be a single category word, "
                            "a brand name, an article number, or a combination."
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the public internet to understand obscure product "
                "nomenclature, decode abbreviations, verify manufacturer specs, "
                "or identify what a cryptic SKU refers to."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Internet search query.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "final_decision",
            "description": (
                "Submit your final matching decision after gathering enough context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "decision_type": {
                        "type": "string",
                        "enum": ["exact_match", "likely_match", "no_match"],
                        "description": (
                            "'exact_match' = identical product, confident. "
                            "'likely_match' = same product family, likely correct "
                            "but needs human verification. "
                            "'no_match' = no suitable match found."
                        ),
                    },
                    "product_id": {
                        "type": "string",
                        "description": (
                            "The catalog product ID if exact_match or likely_match."
                        ),
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of your decision.",
                    },
                },
                "required": ["decision_type", "reasoning"],
            },
        },
    },
]


def _build_system_prompt(
    raw_text: str,
    candidate_str: list[str],
    extracted_attrs: dict | None,
) -> str:
    """Build an adaptive system prompt based on the matching context."""
    attrs_block = ""
    if extracted_attrs:
        parts = []
        for k, v in extracted_attrs.items():
            if v and v != [] and v != {}:
                parts.append(f"  {k}: {v}")
        if parts:
            attrs_block = "\nExtracted attributes:\n" + "\n".join(parts)

    candidates_block = "\n".join(candidate_str) if candidate_str else "None found"
    has_candidates = bool(candidate_str)

    strategy_guidance = ""
    if not has_candidates:
        strategy_guidance = (
            "\nSTRATEGY: No candidates were found by the automated search. "
            "Follow this approach:\n"
            "1. Call `decompose_query` to understand the product structure\n"
            "2. Search the catalog using just the CATEGORY WORD "
            "(e.g., if the product is 'Воздуховод D250 оц.', search 'воздуховод')\n"
            "3. If catalog has products in the same category, compare specs "
            "to find the closest match\n"
            "4. If the query contains unknown abbreviations, use `web_search` "
            "to decode them\n"
            "5. Submit `final_decision` with your best judgment\n"
        )
    else:
        strategy_guidance = (
            "\nSTRATEGY: Some candidates were found but none scored high enough. "
            "Follow this approach:\n"
            "1. Review the candidates — do any match the request closely?\n"
            "2. If the product description is unclear, call `decompose_query` "
            "to identify key attributes\n"
            "3. If needed, `search_catalog` with different keywords "
            "(try article, brand, or category separately)\n"
            "4. Use `web_search` only for truly obscure terms or SKUs\n"
            "5. Submit `final_decision` — use 'likely_match' if the category "
            "matches but exact specs differ\n"
        )

    return (
        "You are a Product Matching Specialist for a B2B nomenclature system.\n"
        "Your task: determine if the client's product request matches any "
        "product in our catalog.\n"
        f'\nCLIENT REQUEST: "{raw_text}"\n'
        f"{attrs_block}\n"
        f"\nCurrent Catalog Candidates:\n{candidates_block}\n"
        f"{strategy_guidance}\n"
        "RULES:\n"
        "- 'exact_match': ONLY when you are certain it is the same product "
        "(same brand, model, specifications)\n"
        "- 'likely_match': Same product FAMILY/CATEGORY, specifications may "
        "differ — good enough for human review\n"
        "- 'no_match': Completely different product, or nothing in catalog "
        "is even close\n"
        "- Different sizes/dimensions within the same product type IS a "
        "'likely_match' (e.g., D250 vs D160 of the same duct type)\n"
        "- NEVER guess — if uncertain, prefer 'likely_match' over 'exact_match'\n"
    )


async def resolve_agentically(
    raw_text: str,
    top_candidates: list[dict],
    session: AsyncSession,
    extracted_attrs: dict | None = None,
) -> dict | None:
    """
    Adaptive agentic resolution with think-then-act strategy.

    Returns:
       {"status": "auto_match"|"review_needed"|"no_match",
        "product_id": str|None, "reasoning": str}
       Or None if the LLM failed.
    """
    if not settings.active_llm_api_key or settings.active_llm_api_key == "none":
        return None

    client, model, extra_body = _make_llm_client()

    candidate_str = []
    for cd in top_candidates:
        c = cd.get("candidate")
        if c:
            parts = [f"ID: {c.product_id}", f"Name: {c.name}"]
            if c.article:
                parts.append(f"Article: {c.article}")
            if c.brand:
                parts.append(f"Brand: {c.brand}")
            candidate_str.append(" | ".join(parts))

    system_prompt = _build_system_prompt(raw_text, candidate_str, extracted_attrs)
    messages = [{"role": "system", "content": system_prompt}]

    max_loops = 6
    loop_count = 0

    while loop_count < max_loops:
        loop_count += 1
        logger.info("Agentic loop %d for: %s", loop_count, raw_text[:80])

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.0,
                extra_body=extra_body or {},
            )
        except Exception as e:
            logger.error("Agentic resolution API call failed: %s", e)
            return None

        # Token tracking
        if hasattr(response, "usage") and response.usage and _token_tracker:
            _token_tracker.record(
                operation="agent",
                provider=settings.llm_provider,
                model=model,
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
            )

        msg = response.choices[0].message
        msg_dict: dict = {"role": "assistant"}
        if msg.content:
            msg_dict["content"] = msg.content

        if msg.tool_calls:
            msg_dict["tool_calls"] = [
                {
                    "id": t.id,
                    "type": "function",
                    "function": {
                        "name": t.function.name,
                        "arguments": t.function.arguments,
                    },
                }
                for t in msg.tool_calls
            ]
            messages.append(msg_dict)

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                if fn_name == "decompose_query":
                    query = args.get("query", raw_text)
                    result = _decompose_query(query)
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                    )

                elif fn_name == "search_catalog":
                    query = args.get("query", raw_text)
                    result = await _catalog_search(query, session)
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                    )

                elif fn_name == "web_search":
                    query = args.get("query", raw_text)
                    result = _web_search(query)
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                    )

                elif fn_name == "final_decision":
                    decision_type = args.get("decision_type", "no_match")
                    pid = args.get("product_id")
                    reason = args.get("reasoning", "Agent completed review.")

                    # Map decision types to pipeline statuses
                    if decision_type == "exact_match" and pid:
                        status = "auto_match"
                    elif decision_type == "likely_match" and pid:
                        status = "review_needed"
                    else:
                        status = "no_match"

                    return {
                        "status": status,
                        "product_id": pid if status != "no_match" else None,
                        "reasoning": reason,
                    }
                else:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "Unknown tool.",
                        }
                    )
        else:
            content = msg.content or ""
            msg_dict["content"] = content
            messages.append(msg_dict)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Please call `final_decision` with your verdict. "
                        "Use 'likely_match' if the category matches but "
                        "exact specs differ."
                    ),
                }
            )

    return None
