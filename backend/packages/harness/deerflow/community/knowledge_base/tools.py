"""
Knowledge Base Retrieval Tool - Retrieve specific documents from knowledge bases via API.

This tool calls an external API to retrieve documents from specific knowledge bases.
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


def _retrieve_from_kb_api(
    document_ids: list[str],
    api_url: str,
    auth_token: str | None,
    knowledge_base_ids: list[str],
) -> dict[str, Any]:
    """Call the knowledge base retrieval API.

    Args:
        document_ids: List of document IDs to retrieve
        api_url: API endpoint URL
        auth_token: Authorization token (Bearer token)
        knowledge_base_ids: List of knowledge base IDs to search

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
        "document_ids": document_ids,
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
        logger.error(f"Knowledge base API HTTP error: {e.response.status_code} - {e.response.text}")
        return {
            "error": f"API error: {e.response.status_code}",
            "details": e.response.text,
        }
    except httpx.RequestError as e:
        logger.error(f"Knowledge base API request error: {e}")
        return {
            "error": f"Request failed: {str(e)}",
        }
    except Exception as e:
        logger.error(f"Knowledge base API unexpected error: {e}")
        return {
            "error": f"Unexpected error: {str(e)}",
        }


@tool("knowledge_base_retrieve", parse_docstring=True)
def knowledge_base_retrieve_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    document_ids: str,
) -> str:
    """Retrieve specific documents from knowledge bases by their document IDs.

    Use this tool when you need to fetch the full content of specific documents
    that have been identified (e.g., from a previous local_search result).

    This tool is useful for:
    - Getting full document content after finding document IDs via search
    - Retrieving specific documents by their unique identifiers
    - Accessing detailed content from internal knowledge bases

    The retrieval requires proper authorization and targets specific knowledge bases
    that have been configured for this conversation.

    Args:
        document_ids: Comma-separated list of document IDs to retrieve.
    """
    # Parse document IDs
    doc_id_list = [doc_id.strip() for doc_id in document_ids.split(",") if doc_id.strip()]

    if not doc_id_list:
        return json.dumps(
            {"error": "No document IDs provided. Please provide at least one document ID."},
            ensure_ascii=False,
            indent=2,
        )

    # Get configuration
    config = get_app_config().get_tool_config("knowledge_base_retrieve")

    # Get API URL from config
    api_url = None
    if config is not None:
        api_url = config.model_extra.get("api_url")

    if not api_url:
        return json.dumps(
            {"error": "Knowledge base API URL not configured. Please set 'api_url' in config."},
            ensure_ascii=False,
            indent=2,
        )

    # Get auth token and knowledge base IDs from runtime
    auth_token = _get_auth_token(runtime)
    knowledge_base_ids = _get_knowledge_base_ids(runtime)

    if not auth_token:
        logger.warning("No authorization token found for knowledge_base_retrieve tool")

    if not knowledge_base_ids:
        logger.warning("No knowledge_base_ids found for knowledge_base_retrieve tool")

    # Call the API
    result = _retrieve_from_kb_api(
        document_ids=doc_id_list,
        api_url=api_url,
        auth_token=auth_token,
        knowledge_base_ids=knowledge_base_ids,
    )

    # Format the result
    if "error" in result:
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Normalize the response format
    normalized_result = {
        "document_ids": doc_id_list,
        "knowledge_bases": knowledge_base_ids,
        "total_documents": result.get("total", len(doc_id_list)),
        "documents": result.get("documents", []),
    }

    return json.dumps(normalized_result, ensure_ascii=False, indent=2)
