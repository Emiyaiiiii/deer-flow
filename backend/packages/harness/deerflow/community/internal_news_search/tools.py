"""
Internal News Search Tool - Search internal news content via API.

This tool calls an external API to search internal news content.
Requires Authorization header from frontend.
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


def _search_internal_news_api(
    query: str,
    api_url: str,
    auth_token: str | None,
) -> dict[str, Any]:
    """Call the internal news search API.

    Args:
        query: Search query string
        api_url: API endpoint URL
        auth_token: Authorization token (Bearer token)

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
        "search_type": "hybrid",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Internal news search API HTTP error: {e.response.status_code} - {e.response.text}")
        return {
            "error": f"API error: {e.response.status_code}",
            "details": e.response.text,
        }
    except httpx.RequestError as e:
        logger.error(f"Internal news search API request error: {e}")
        return {
            "error": f"Request failed: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Internal news search API unexpected error: {e}")
        return {
            "error": f"Unexpected error: {str(e)}",
        }


@tool("internal_news_search", parse_docstring=True)
def internal_news_search(
    runtime: ToolRuntime[ContextT, ThreadState],
    query: str,
) -> str:
    """Search internal news content.

    Use this tool when you need to find information from:
    - Internal company news
    - Organization-specific news content
    - Internal news and information

    The search requires proper authorization and uses a hybrid search approach
    to find the most relevant news articles.

    Args:
        query: The search query describing what you want to find.
               Be specific and use relevant keywords for better results.
    """
    if not query:
        return json.dumps(
            {"error": "No search query provided. Please provide a search query."},
            ensure_ascii=False,
            indent=2,
        )

    # Get configuration
    config = get_app_config().get_tool_config("internal_news_search")

    # Get API URL from config
    api_url = None
    if config is not None:
        api_url = config.model_extra.get("api_url")

    if not api_url:
        return json.dumps(
            {"error": "Internal news search API URL not configured. Please set 'api_url' in config."},
            ensure_ascii=False,
            indent=2,
        )

    # Get auth token from runtime
    auth_token = _get_auth_token(runtime)

    if not auth_token:
        logger.warning("No authorization token found for internal_news_search tool")

    logger.info(f"internal_news_search tool called with query: '{query}', api_url: {api_url}, auth_token present: {auth_token is not None}")

    # Call the API
    result = _search_internal_news_api(
        query=query,
        api_url=api_url,
        auth_token=auth_token,
    )

    # Format the result
    if "error" in result:
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Normalize the response format
    normalized_result = {
        "query": query,
        "total_results": result.get("data", {}).get("metadata", {}).get("total_count", 0),
        "results": result.get("data", {}).get("results", []),
        "metadata": result.get("data", {}).get("metadata", {}),
    }

    return json.dumps(normalized_result, ensure_ascii=False, indent=2)
