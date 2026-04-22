"""Internal Search Tool - Unified search for internal news and knowledge bases via API.

This tool provides unified search across internal knowledge bases and news using the
enhanced search API. The source_type parameter determines whether to search documents or news.
"""

import json
import logging
from typing import Any

import httpx
from langchain.tools import ToolRuntime, tool
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState
from deerflow.config import get_app_config

logger = logging.getLogger(__name__)


def _get_auth_token(runtime: ToolRuntime[ContextT, ThreadState] | None) -> str | None:
    """Extract authorization token from runtime context."""
    if runtime is None:
        logger.debug("_get_auth_token: runtime is None")
        return None

    if runtime.context:
        auth = runtime.context.get("authorization")
        if auth:
            token_preview = auth[:50] + "..." if len(auth) > 50 else auth
            logger.info(f"_get_auth_token: Found auth token in runtime.context: {token_preview}")
            return auth

    logger.warning("_get_auth_token: No authorization token found in runtime.context")
    return None


def _get_knowledge_base_ids(runtime: ToolRuntime[ContextT, ThreadState] | None) -> list[str]:
    """Extract knowledge base IDs from runtime context."""
    if runtime is None:
        logger.debug("_get_knowledge_base_ids: runtime is None")
        return []

    if runtime.context:
        kb_ids = runtime.context.get("knowledge_base_ids")
        if kb_ids:
            logger.info(f"_get_knowledge_base_ids: Found knowledge_base_ids in runtime.context: {kb_ids}")
            return kb_ids if isinstance(kb_ids, list) else [kb_ids]

    logger.warning("_get_knowledge_base_ids: No knowledge_base_ids found in runtime.context")
    return []


def _get_category(runtime: ToolRuntime[ContextT, ThreadState] | None) -> str | None:
    """Extract category from runtime context."""
    if runtime is None:
        logger.debug("_get_category: runtime is None")
        return None

    if runtime.context:
        category = runtime.context.get("category")
        if category:
            logger.info(f"_get_category: Found category in runtime.context: {category}")
            return category

    logger.debug("_get_category: No category found in runtime.context")
    return None


def _search_internal_api(
    query: str,
    api_url: str,
    auth_token: str | None,
    source_type: str,
    knowledge_base_ids: list[str],
    top_k: int = 10,
    search_type: str = "unified",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Call the internal unified search API.

    Args:
        query: Search query string
        api_url: API endpoint URL
        auth_token: Authorization token (Bearer token)
        source_type: Search source type (document or news)
        knowledge_base_ids: List of knowledge base IDs to search
        top_k: Maximum number of results to return
        search_type: Search type (unified, keyword, vector, hybrid)
        start_date: Filter results from this date
        end_date: Filter results until this date

    Returns:
        API response as dictionary
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if auth_token:
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        headers["Authorization"] = auth_token

    filters: dict[str, Any] = {
        "source_type": source_type,
    }

    if source_type == "document" and knowledge_base_ids:
        filters["knowledge_base_ids"] = [int(id_) for id_ in knowledge_base_ids]

    if start_date or end_date:
        if start_date and end_date:
            filters["time_range"] = {"gte": start_date, "lte": end_date}
        elif start_date:
            filters["time_range"] = start_date
        elif end_date:
            filters["time_range"] = end_date

    payload = {
        "query": query,
        "filters": filters,
        "search_type": search_type,
        "top_k": top_k,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Internal search API HTTP error: {e.response.status_code} - {e.response.text}")
        return {
            "error": f"API error: {e.response.status_code}",
            "details": e.response.text,
        }
    except httpx.RequestError as e:
        logger.error(f"Internal search API request error: {e}")
        return {
            "error": f"Request failed: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Internal search API unexpected error: {e}")
        return {
            "error": f"Unexpected error: {str(e)}",
        }


def _get_kb_ids_by_category(
    api_url: str,
    category: str,
    auth_token: str | None,
) -> list[str]:
    """Fetch knowledge base IDs by category via API."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if auth_token:
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        headers["Authorization"] = auth_token

    url = api_url

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers, params={"category": category})
            response.raise_for_status()
            result = response.json()
            ids = result.get("data", {}).get("ids", [])
            logger.info(f"_get_kb_ids_by_category: Found {len(ids)} knowledge base IDs for category '{category}'")
            return [str(id_) for id_ in ids]
    except httpx.HTTPStatusError as e:
        logger.error(f"Category API HTTP error: {e.response.status_code} - {e.response.text}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Category API request error: {e}")
        return []
    except Exception as e:
        logger.error(f"Category API unexpected error: {e}")
        return []


@tool("web_search", parse_docstring=True)
def web_search(
    runtime: ToolRuntime[ContextT, ThreadState],
    query: str,
    source_type: str = "document",
    top_k: int = 10,
    search_type: str = "unified",
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Search internal knowledge bases and news.

    Use this tool when you need to find information from internal knowledge bases
    or company news. This tool calls the enhanced search API to retrieve relevant
    content.

    This tool is useful for:
    Finding documents from internal knowledge bases, searching company news and announcements, and retrieving relevant internal information.

    Required parameters from runtime context:
    authorization: Authentication token for API access
    knowledge_base_ids: List of knowledge base IDs to search (for document source)
    category: Category name to filter knowledge bases (optional)

    Args:
        query: The search query describing what you want to find.
        source_type: Content type to search. Can be document (for knowledge base search) or news (for news search). Default is document.
        top_k: Maximum number of results to return. Default is 10.
        search_type: Search algorithm type. Can be unified, keyword, vector, or hybrid. Default is unified.
        start_date: Filter results from this date (inclusive). Format: YYYY-MM-DD. Can also use relative format like last_7_days or year 2024 or year-month 2024-06.
        end_date: Filter results until this date (inclusive). Format: YYYY-MM-DD. Can also use relative format like year-month 2024-12 or date range dict.
    """
    if not query:
        return json.dumps(
            {"error": "No search query provided. Please provide a search query."},
            ensure_ascii=False,
            indent=2,
        )

    if source_type not in ("document", "news"):
        return json.dumps(
            {"error": f"Invalid source_type: {source_type}. Must be 'document' or 'news'."},
            ensure_ascii=False,
            indent=2,
        )

    config = get_app_config().get_tool_config("web_search")

    api_url = None
    category_api_url = None
    if config is not None:
        api_url = config.model_extra.get("api_url")
        category_api_url = config.model_extra.get("category_api_url")

    if not api_url:
        return json.dumps(
            {"error": "Internal search API URL not configured. Please set 'api_url' in config."},
            ensure_ascii=False,
            indent=2,
        )

    auth_token = _get_auth_token(runtime)
    knowledge_base_ids = _get_knowledge_base_ids(runtime)
    category = _get_category(runtime)

    if not auth_token:
        logger.warning("No authorization token found for web_search tool")

    combined_kb_ids: list[str] = list(knowledge_base_ids)

    if source_type == "document" and category and category_api_url:
        category_kb_ids = _get_kb_ids_by_category(category_api_url, category, auth_token)
        if category_kb_ids:
            combined_kb_ids = list(set(combined_kb_ids + category_kb_ids))
            logger.info(f"Combined knowledge_base_ids: {len(combined_kb_ids)} total (category: {category}, user_provided: {len(knowledge_base_ids)})")
        else:
            logger.warning(f"Failed to get knowledge base IDs for category '{category}', using user_provided IDs only")
    elif source_type == "document" and category and not category_api_url:
        logger.warning(f"Category '{category}' provided but category_api_url not configured")

    if not combined_kb_ids:
        logger.warning("No knowledge_base_ids found for web_search tool")

    logger.info(f"web_search tool called with query: '{query}', source_type: {source_type}, api_url: {api_url}, auth_token present: {auth_token is not None}, combined_kb_ids: {combined_kb_ids}, search_type: {search_type}, start_date: {start_date}, end_date: {end_date}")

    result = _search_internal_api(
        query=query,
        api_url=api_url,
        auth_token=auth_token,
        source_type=source_type,
        knowledge_base_ids=combined_kb_ids,
        top_k=top_k,
        search_type=search_type,
        start_date=start_date,
        end_date=end_date,
    )

    if "error" in result:
        return json.dumps(result, ensure_ascii=False, indent=2)

    normalized_result = {
        "query": query,
        "source_type": source_type,
        "processed_query": result.get("data", {}).get("processed_query", ""),
        "intent": result.get("data", {}).get("intent", ""),
        "intent_confidence": result.get("data", {}).get("intent_confidence", 0.0),
        "entities": result.get("data", {}).get("entities", []),
        "tags": result.get("data", {}).get("tags", []),
        "search_type": search_type,
        "start_date": start_date,
        "end_date": end_date,
        "knowledge_bases": combined_kb_ids,
        "results": result.get("data", {}).get("results", []),
        "statistics": result.get("data", {}).get("statistics", {}),
    }

    return json.dumps(normalized_result, ensure_ascii=False, indent=2)
