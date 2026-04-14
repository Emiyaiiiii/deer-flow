#!/usr/bin/env python3
"""
流式问答测试脚本 - 测试 DeerFlow 客户端与知识库工具的集成

使用方法:
    cd backend
    PYTHONPATH=. uv run python test_stream_qa.py "你的问题"

示例:
    PYTHONPATH=. uv run python test_stream_qa.py "防洪预案"
    PYTHONPATH=. uv run python test_stream_qa.py "防洪预案" "Bearer eyJhbGci..." "178,179"
"""

import sys
import os
import logging
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "packages", "harness"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """Stream event from DeerFlowClient."""
    type: str
    data: dict


def print_stream_events(events: list[StreamEvent]):
    """Print stream events in a formatted way."""
    for event in events:
        print(f"\n{'=' * 60}")
        print(f"Event Type: {event.type}")
        print(f"{'=' * 60}")

        if event.type == "values":
            print(f"Values: {event.data}")
        elif event.type == "messages-tuple":
            msg_type = event.data.get("type", "")
            content = event.data.get("content", "")
            name = event.data.get("name", "")
            tool_call_id = event.data.get("tool_call_id", "")
            msg_id = event.data.get("id", "")

            if msg_type == "ai":
                if content:
                    print(f"[AI Message] {content}")
                if event.data.get("tool_calls"):
                    print(f"[AI Tool Calls] {event.data['tool_calls']}")
                if event.data.get("usage_metadata"):
                    print(f"[Usage] {event.data['usage_metadata']}")
            elif msg_type == "tool":
                print(f"[Tool: {name}] (ID: {tool_call_id})")
                content_preview = content[:500] + "..." if len(content) > 500 else content
                print(f"Result: {content_preview}")
        elif event.type == "custom":
            print(f"Custom: {event.data}")
        elif event.type == "end":
            print(f"Stream ended. Usage: {event.data}")
        else:
            print(f"Unknown event: {event.data}")


def test_stream_qa(
    message: str,
    authorization: str | None = None,
    knowledge_base_ids: list[str] | None = None,
):
    """Test streaming Q&A with DeerFlow client."""
    try:
        from deerflow.client import DeerFlowClient
    except ImportError as e:
        print(f"\n导入 DeerFlowClient 失败: {e}")
        print("\n请确保在正确的环境中运行:")
        print("  cd backend")
        print("  PYTHONPATH=. uv run python test_stream_qa.py '你的问题'")
        return None

    print(f"\n{'#' * 60}")
    print(f"# 测试流式问答")
    print(f"#{'#' * 60}")
    print(f"# Message: {message}")
    print(f"# Authorization: {'Provided' if authorization else 'Not provided'}")
    print(f"# Knowledge Base IDs: {knowledge_base_ids}")
    print(f"{'#' * 60}\n")

    client = DeerFlowClient()

    events = []
    try:
        for event in client.stream(
            message=message,
            authorization=authorization,
            knowledge_base_ids=knowledge_base_ids,
        ):
            stream_event = StreamEvent(type=event.type, data=event.data)
            events.append(stream_event)
    except Exception as e:
        print(f"\nError during streaming: {e}")
        logger.exception("Error during streaming")
        return None

    return events


def main():
    if len(sys.argv) < 2:
        print("请提供问题作为参数")
        print(__doc__)
        sys.exit(1)

    message = sys.argv[1]

    authorization = None
    knowledge_base_ids = None

    if len(sys.argv) > 2:
        authorization = sys.argv[2]
    if len(sys.argv) > 3:
        knowledge_base_ids = sys.argv[3].split(",")

    events = test_stream_qa(
        message=message,
        authorization=authorization,
        knowledge_base_ids=knowledge_base_ids,
    )

    if events:
        print_stream_events(events)


if __name__ == "__main__":
    main()
