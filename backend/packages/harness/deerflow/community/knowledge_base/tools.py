"""
Knowledge Base Search Tool - Search knowledge bases for documents matching a query via API.

This tool calls an external API to search documents from specific knowledge bases.
Requires Authorization header and knowledge_base_ids from frontend.
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
    """Extract authorization token from runtime context.

    The token is expected to be passed from frontend via runtime.context["authorization"].
    """
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
    """Extract knowledge base IDs from runtime context.

    The IDs are expected to be passed from frontend via runtime.context["knowledge_base_ids"].
    """
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
    """Extract category from runtime context.

    The category is expected to be passed from frontend via runtime.context["category"].
    """
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


def _search_kb_api(
    query: str,
    api_url: str,
    auth_token: str | None,
    knowledge_base_ids: list[str],
    top_k: int = 10,
) -> dict[str, Any]:
    """Call the knowledge base search API.

    Args:
        query: Search query string
        api_url: API endpoint URL
        auth_token: Authorization token (Bearer token)
        knowledge_base_ids: List of knowledge base IDs to search
        top_k: Maximum number of results to return

    Returns:
        API response as dictionary
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if auth_token:
        # Ensure Bearer prefix
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        headers["Authorization"] = auth_token

    payload = {
        "query": query,
        "knowledge_base_ids": knowledge_base_ids,
        "top_k": top_k,
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Knowledge base search API HTTP error: {e.response.status_code} - {e.response.text}")
        return {
            "error": f"API error: {e.response.status_code}",
            "details": e.response.text,
        }
    except httpx.RequestError as e:
        logger.error(f"Knowledge base search API request error: {e}")
        return {
            "error": f"Request failed: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Knowledge base search API unexpected error: {e}")
        return {
            "error": f"Unexpected error: {str(e)}",
        }


def _get_kb_ids_by_category(
    api_url: str,
    category: str,
    auth_token: str | None,
) -> list[str]:
    """Fetch knowledge base IDs by category via API.

    Args:
        api_url: Base API URL (will append /accessible-ids/)
        category: Category name to query
        auth_token: Authorization token (Bearer token)

    Returns:
        List of knowledge base IDs from the category
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if auth_token:
        if not auth_token.startswith("Bearer "):
            auth_token = f"Bearer {auth_token}"
        headers["Authorization"] = auth_token

    url = api_url.rstrip("/") + "/accessible-ids/"

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


@tool("knowledge_base_search", parse_docstring=True)
def knowledge_base_search_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    query: str,
    top_k: int = 10,
) -> str:
    """Search knowledge bases for documents matching a query.

    Use this tool when you need to find relevant documents from knowledge bases
    based on a search query. This tool calls the enhanced search API to retrieve
    documents that match the given query.

    This tool is useful for:
    - Finding documents related to a specific topic
    - Searching for information across multiple knowledge bases
    - Getting relevant documents with metadata and highlights

    The search requires proper authorization and specific knowledge bases
    that have been configured for this conversation.

    Args:
        query: The search query describing what you want to find.
        top_k: Maximum number of results to return. Default is 10.
    """
    if not query:
        return json.dumps(
            {"error": "No search query provided. Please provide a search query."},
            ensure_ascii=False,
            indent=2,
        )

    # Get configuration
    config = get_app_config().get_tool_config("knowledge_base_search")

    # Get API URL from config
    api_url = None
    category_api_url = None
    if config is not None:
        api_url = config.model_extra.get("api_url")
        category_api_url = config.model_extra.get("category_api_url")

    if not api_url:
        return json.dumps(
            {"error": "Knowledge base search API URL not configured. Please set 'api_url' in config."},
            ensure_ascii=False,
            indent=2,
        )

    # Get auth token and knowledge base IDs from runtime
    auth_token = _get_auth_token(runtime)
    knowledge_base_ids = _get_knowledge_base_ids(runtime)
    category = _get_category(runtime)

    if not auth_token:
        logger.warning("No authorization token found for knowledge_base_search tool")

    combined_kb_ids: list[str] = list(knowledge_base_ids)

    if category and category_api_url:
        category_kb_ids = _get_kb_ids_by_category(category_api_url, category, auth_token)
        if category_kb_ids:
            combined_kb_ids = list(set(combined_kb_ids + category_kb_ids))
            logger.info(f"Combined knowledge_base_ids: {len(combined_kb_ids)} total (category: {category}, user_provided: {len(knowledge_base_ids)})")
        else:
            logger.warning(f"Failed to get knowledge base IDs for category '{category}', using user_provided IDs only")
    elif category and not category_api_url:
        logger.warning(f"Category '{category}' provided but category_api_url not configured")

    if not combined_kb_ids:
        logger.warning("No knowledge_base_ids found for knowledge_base_search tool")

    logger.info(f"knowledge_base_search tool called with query: '{query}', api_url: {api_url}, auth_token present: {auth_token is not None}, combined_kb_ids: {combined_kb_ids}")

    # Call the API
    result = _search_kb_api(
        query=query,
        api_url=api_url,
        auth_token=auth_token,
        knowledge_base_ids=combined_kb_ids,
        top_k=top_k,
    )

    # Format the result
    if "error" in result:
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Normalize the response format
    normalized_result = {
        "query": query,
        "knowledge_bases": combined_kb_ids,
        "results": result.get("data", {}).get("results", []),
        "statistics": result.get("data", {}).get("statistics", {}),
    }

    return json.dumps(normalized_result, ensure_ascii=False, indent=2)
