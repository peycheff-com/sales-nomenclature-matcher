import json
import logging
from typing import Any

from duckduckgo_search import DDGS
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from matcher.config import settings
from matcher.indexing.search import hybrid_search

logger = logging.getLogger(__name__)


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
        results = DDGS().text(query, max_results=max_results)
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
    """Searches the local 1C catalog to find specific articles or product identifiers."""
    candidates = await hybrid_search(query_text=query, normalized_text=query, session=session, top_n=5)
    if not candidates:
        return "No catalog matches found for that query."
    
    snippets = []
    for c in candidates:
        snippets.append(f"ID: {c.product_id} | Name: {c.name} | Article: {c.article} | Brand: {c.brand}")
    return "\n".join(snippets)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Searches the internal 1C product catalog for specific brands, articles, or keywords. Use this when the initial candidates didn't contain the exact product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search keywords, model number, or brand."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the public internet for obscure product nomenclature, verifying manufacturer specifications, or checking what an SKU refers to.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The internet search query."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "final_decision",
            "description": "Submit your final confident matching decision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision_type": {
                        "type": "string",
                        "enum": ["exact_match", "no_match"],
                        "description": "If you are highly confident, emit exact_match. Otherwise no_match."
                    },
                    "product_id": {
                        "type": "string",
                        "description": "The ID of the candidate from the catalog if exact_match. Leave empty otherwise."
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "A short, one sentence explanation of why this product matches."
                    }
                },
                "required": ["decision_type", "reasoning"]
            }
        }
    }
]


async def resolve_agentically(
    raw_text: str,
    top_candidates: list[dict],
    session: AsyncSession
) -> dict | None:
    """
    Invokes the LLM in an agentic Tool Calling loop to resolve ambiguity.
    Returns:
       {"status": "auto_match" | "no_match", "product_id": str | None, "reasoning": str}
       Or None if the LLM failed to emit a valid output.
    """
    if not settings.active_llm_api_key or settings.active_llm_api_key == "none":
        return None  # Agent disabled for local without LLM
        
    client, model, extra_body = _make_llm_client()

    candidate_str = []
    for cd in top_candidates:
        c = cd.get("candidate")
        if c:
            candidate_str.append(f"ID: {c.product_id} | Name: {c.name} | Article: {c.article} | Brand: {c.brand}")
            
    initial_prompt = f"""You are the Advanced Resolution Agent for a B2B Nomenclature Matching System.
The standard pipeline failed to find a highly confident match for the following client request.

CLIENT REQUEST: "{raw_text}"

Current Top Catalog Candidates:
{chr(10).join(candidate_str) if candidate_str else "None"}

Your job is to determine if the CLIENT REQUEST perfectly matches any of our catalog candidates, or if you can find the correct one by searching the internal catalog using `search_catalog`.
If the CLIENT REQUEST is obscure (e.g., just an SKU or a weird abbreviation), use the `web_search` tool to figure out what the product is.

Once you have gathered enough context and are highly confident, call the `final_decision` tool.
Only return 'exact_match' if you are absolutely certain the product is identical (variants like 256GB vs 128GB or different colors must NOT be matched unless specified).
"""

    messages = [{"role": "system", "content": initial_prompt}]
    
    max_loops = 4
    loop_count = 0
    final_output = None
    
    while loop_count < max_loops:
        loop_count += 1
        logger.info(f"Agentic loop {loop_count} for request: {raw_text}")
        
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
            logger.error(f"Agentic resolution API call failed: {e}")
            return None

        msg = response.choices[0].message
        
        # Build the message for the history using standard OpenAI structures
        msg_dict = {"role": "assistant"}
        if msg.content:
            msg_dict["content"] = msg.content
            
        if msg.tool_calls:
            msg_dict["tool_calls"] = []
            for t in msg.tool_calls:
                msg_dict["tool_calls"].append({
                    "id": t.id,
                    "type": "function",
                    "function": {
                        "name": t.function.name,
                        "arguments": t.function.arguments
                    }
                })
            messages.append(msg_dict)
            
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                # Execute the tool
                if fn_name == "search_catalog":
                    query = args.get("query", raw_text)
                    result = await _catalog_search(query, session)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
                    
                elif fn_name == "web_search":
                    query = args.get("query", raw_text)
                    result = _web_search(query)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
                    
                elif fn_name == "final_decision":
                    decision_type = args.get("decision_type", "no_match")
                    pid = args.get("product_id")
                    reason = args.get("reasoning", "Agent completed review.")
                    
                    final_output = {
                        "status": "auto_match" if decision_type == "exact_match" and pid else "no_match",
                        "product_id": pid if decision_type == "exact_match" else None,
                        "reasoning": reason
                    }
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": "Decision received."})
                    return final_output
                else:
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": "Unknown tool."})
                    
        else:
            # Re-prompt if not confident enough to make a tool call but didn't finish.
            content = msg.content or ""
            msg_dict["content"] = content
            messages.append(msg_dict)
            messages.append({
                "role": "user", 
                "content": "Please invoke the `final_decision` tool to register your answer."
            })
            
    return final_output
