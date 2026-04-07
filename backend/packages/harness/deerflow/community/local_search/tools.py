"""
Local Search Tool - Search local documents and content via API.

This tool calls an external API to search local documents.
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
        return None

    # Try to get from context first (direct pass from frontend)
    if runtime.context:
        auth = runtime.context.get("authorization")
        if auth:
            return auth

    # Try to get from thread_data (stored in state)
    if runtime.state:
        thread_data = runtime.state.get("thread_data")
        if thread_data:
            auth = thread_data.get("authorization")
            if auth:
                return auth

    return None


def _get_knowledge_base_ids(runtime: ToolRuntime[ContextT, ThreadState] | None) -> list[str]:
    """Extract knowledge base IDs from runtime context or thread_data.

    The IDs are expected to be passed from frontend via:
    1. runtime.context["knowledge_base_ids"]
    2. runtime.state["thread_data"]["knowledge_base_ids"]
    """
    if runtime is None:
        return []

    # Try to get from context first
    if runtime.context:
        kb_ids = runtime.context.get("knowledge_base_ids")
        if kb_ids:
            return kb_ids if isinstance(kb_ids, list) else [kb_ids]

    # Try to get from thread_data
    if runtime.state:
        thread_data = runtime.state.get("thread_data")
        if thread_data:
            kb_ids = thread_data.get("knowledge_base_ids")
            if kb_ids:
                return kb_ids if isinstance(kb_ids, list) else [kb_ids]

    return []


def _search_local_api(
    query: str,
    api_url: str,
    auth_token: str | None,
    knowledge_base_ids: list[str],
    max_results: int = 5,
) -> dict[str, Any]:
    """Call the local search API.

    Args:
        query: Search query string
        api_url: API endpoint URL
        auth_token: Authorization token (Bearer token)
        knowledge_base_ids: List of knowledge base IDs to search
        max_results: Maximum number of results to return

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
        "max_results": max_results,
    }

    # Only include knowledge_base_ids if provided
    if knowledge_base_ids:
        payload["knowledge_base_ids"] = knowledge_base_ids

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Local search API HTTP error: {e.response.status_code} - {e.response.text}")
        return {
            "error": f"API error: {e.response.status_code}",
            "details": e.response.text,
        }
    except httpx.RequestError as e:
        logger.error(f"Local search API request error: {e}")
        return {
            "error": f"Request failed: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Local search API unexpected error: {e}")
        return {
            "error": f"Unexpected error: {str(e)}",
        }


@tool("local_search", parse_docstring=True)
def local_search_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    query: str,
    max_results: int = 5,
) -> str:
    """Search local documents and content.

    Use this tool when you need to find information from:
    - Internal company documents
    - Local knowledge bases
    - Private document repositories
    - Organization-specific content
    - Local news and information

    The search requires proper authorization. For knowledge base searches,
    specific knowledge bases should be configured for this conversation.
    For general local searches (e.g., news), knowledge_base_ids is optional.

    Args:
        query: The search query describing what you want to find.
               Be specific and use relevant keywords for better results.
        max_results: Maximum number of results to return. Default is 5.
    """
    # Get configuration
    config = get_app_config().get_tool_config("local_search")

    # Get API URL from config
    api_url = None
    if config is not None:
        api_url = config.model_extra.get("api_url")

    if not api_url:
        return json.dumps(
            {"error": "Local search API URL not configured. Please set 'api_url' in config."},
            ensure_ascii=False,
            indent=2,
        )

    # Get auth token and knowledge base IDs from runtime
    auth_token = _get_auth_token(runtime)
    knowledge_base_ids = _get_knowledge_base_ids(runtime)

    if not auth_token:
        logger.warning("No authorization token found for local_search tool")
        # Optionally return error or proceed without auth
        # return json.dumps(
        #     {"error": "Authorization required. Please provide authentication token."},
        #     ensure_ascii=False,
        #     indent=2,
        # )

    # Note: knowledge_base_ids is optional for local_search
    # - For knowledge base search: should provide knowledge_base_ids
    # - For local news search: knowledge_base_ids is not required
    if not knowledge_base_ids:
        logger.debug("No knowledge_base_ids found for local_search tool, searching without KB filter")

    # Call the API
    result = _search_local_api(
        query=query,
        api_url=api_url,
        auth_token=auth_token,
        knowledge_base_ids=knowledge_base_ids,
        max_results=max_results,
    )

    # Format the result
    if "error" in result:
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Normalize the response format
    normalized_result = {
        "query": query,
        "knowledge_bases": knowledge_base_ids if knowledge_base_ids else None,
        "total_results": result.get("total", 0),
        "results": result.get("results", []),
    }

    return json.dumps(normalized_result, ensure_ascii=False, indent=2)
