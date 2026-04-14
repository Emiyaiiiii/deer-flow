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
    """Extract authorization token from runtime context or thread_data.

    The token is expected to be passed from frontend via:
    1. runtime.context["authorization"]
    2. runtime.state["thread_data"]["authorization"]
    """
    if runtime is None:
        logger.debug("_get_auth_token: runtime is None")
        return None

    # Try to get from context first (direct pass from frontend)
    if runtime.context:
        auth = runtime.context.get("authorization")
        logger.debug(f"_get_auth_token: from runtime.context, auth present: {auth is not None}")
        if auth:
            # Log token preview (first 50 chars) for debugging
            token_preview = auth[:50] + "..." if len(auth) > 50 else auth
            logger.info(f"_get_auth_token: Found auth token in runtime.context: {token_preview}")
            return auth

    # Try to get from thread_data (stored in state)
    if runtime.state:
        thread_data = runtime.state.get("thread_data")
        if thread_data:
            auth = thread_data.get("authorization")
            logger.debug(f"_get_auth_token: from thread_data, auth present: {auth is not None}")
            if auth:
                # Log token preview (first 50 chars) for debugging
                token_preview = auth[:50] + "..." if len(auth) > 50 else auth
                logger.info(f"_get_auth_token: Found auth token in thread_data: {token_preview}")
                return auth

    logger.warning("_get_auth_token: No authorization token found in runtime.context or thread_data")
    return None


def _get_knowledge_base_ids(runtime: ToolRuntime[ContextT, ThreadState] | None) -> list[str]:
    """Extract knowledge base IDs from runtime context or thread_data.

    The IDs are expected to be passed from frontend via:
    1. runtime.context["knowledge_base_ids"]
    2. runtime.state["thread_data"]["knowledge_base_ids"]
    """
    if runtime is None:
        logger.debug("_get_knowledge_base_ids: runtime is None")
        return []

    # Try to get from context first
    if runtime.context:
        kb_ids = runtime.context.get("knowledge_base_ids")
        logger.debug(f"_get_knowledge_base_ids: from runtime.context, kb_ids present: {kb_ids is not None}")
        if kb_ids:
            logger.info(f"_get_knowledge_base_ids: Found knowledge_base_ids in runtime.context: {kb_ids}")
            return kb_ids if isinstance(kb_ids, list) else [kb_ids]

    # Try to get from thread_data
    if runtime.state:
        thread_data = runtime.state.get("thread_data")
        if thread_data:
            kb_ids = thread_data.get("knowledge_base_ids")
            logger.debug(f"_get_knowledge_base_ids: from thread_data, kb_ids present: {kb_ids is not None}")
            if kb_ids:
                logger.info(f"_get_knowledge_base_ids: Found knowledge_base_ids in thread_data: {kb_ids}")
                return kb_ids if isinstance(kb_ids, list) else [kb_ids]

    logger.warning("_get_knowledge_base_ids: No knowledge_base_ids found in runtime.context or thread_data")
    return []


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
    if config is not None:
        api_url = config.model_extra.get("api_url")

    if not api_url:
        return json.dumps(
            {"error": "Knowledge base search API URL not configured. Please set 'api_url' in config."},
            ensure_ascii=False,
            indent=2,
        )

    # Get auth token and knowledge base IDs from runtime
    auth_token = _get_auth_token(runtime)
    knowledge_base_ids = _get_knowledge_base_ids(runtime)

    if not auth_token:
        logger.warning("No authorization token found for knowledge_base_search tool")

    if not knowledge_base_ids:
        logger.warning("No knowledge_base_ids found for knowledge_base_search tool")

    logger.info(f"knowledge_base_search tool called with query: '{query}', api_url: {api_url}, auth_token present: {auth_token is not None}, knowledge_base_ids: {knowledge_base_ids}")

    # Call the API
    result = _search_kb_api(
        query=query,
        api_url=api_url,
        auth_token=auth_token,
        knowledge_base_ids=knowledge_base_ids,
        top_k=top_k,
    )

    # Format the result
    if "error" in result:
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Normalize the response format
    normalized_result = {
        "query": query,
        "knowledge_bases": knowledge_base_ids,
        "results": result.get("data", {}).get("results", []),
        "statistics": result.get("data", {}).get("statistics", {}),
    }

    return json.dumps(normalized_result, ensure_ascii=False, indent=2)
