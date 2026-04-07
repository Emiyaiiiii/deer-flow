# 本地搜索与知识库检索工具集成指南

## 概述

本指南介绍如何在 DeerFlow 中集成和使用本地搜索工具 (`local_search`) 与知识库检索工具 (`knowledge_base_retrieve`)。

## 已创建的文件

### 1. 工具实现

- `backend/packages/harness/deerflow/community/local_search/tools.py` - 本地搜索工具
- `backend/packages/harness/deerflow/community/local_search/__init__.py` - 本地搜索模块初始化
- `backend/packages/harness/deerflow/community/knowledge_base/tools.py` - 知识库检索工具
- `backend/packages/harness/deerflow/community/knowledge_base/__init__.py` - 知识库模块初始化

### 2. 中间件更新

- `backend/packages/harness/deerflow/agents/middlewares/thread_data_middleware.py` - 支持提取前端参数
- `backend/packages/harness/deerflow/agents/thread_state.py` - 扩展 ThreadDataState 类型

## 配置步骤

### 1. 启用工具

在 `config.yaml` 中取消注释并配置工具：

```yaml
tools:
  # Local Search Tool - Search internal documents via API
  - name: local_search
    group: web
    use: deerflow.community.local_search.tools:local_search_tool
    api_url: http://your-api-server/api/search  # 替换为你的搜索API端点
    max_results: 5

  # Knowledge Base Retrieval Tool - Retrieve specific documents via API
  - name: knowledge_base_retrieve
    group: web
    use: deerflow.community.knowledge_base.tools:knowledge_base_retrieve_tool
    api_url: http://your-api-server/api/retrieve  # 替换为你的检索API端点
```

### 2. 前端参数传递

前端需要在调用 `/api/threads/{thread_id}/runs/stream` 时，在 `config.configurable` 中传递以下参数：

```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "搜索关于产品文档的信息"
      }
    ]
  },
  "config": {
    "configurable": {
      "thread_id": "thread_123",
      "authorization": "Bearer your_token_here",
      "knowledge_base_ids": ["kb_001", "kb_002", "kb_003"]
    }
  }
}
```

### 3. 前端调用示例

#### 方式一：使用 DeerFlowClient（Python SDK）

```python
from deerflow.client import DeerFlowClient

# 初始化客户端
client = DeerFlowClient()

# 示例 1：本地新闻检索（不需要 knowledge_base_ids）
response = client.chat(
    "搜索今天的新闻",
    thread_id="thread_123",
    authorization="Bearer your_token_here"
)
print(response)

# 示例 2：知识库检索（需要 knowledge_base_ids）
response = client.chat(
    "查找产品文档",
    thread_id="thread_123",
    authorization="Bearer your_token_here",
    knowledge_base_ids=["kb_001", "kb_002"]
)
print(response)

# 示例 3：流式输出
for event in client.stream(
    "搜索技术文档",
    thread_id="thread_123",
    authorization="Bearer your_token_here",
    knowledge_base_ids=["kb_001"]
):
    print(event.type, event.data)
```

#### 方式二：使用 JavaScript/TypeScript SDK

```typescript
import { useStream } from "@langchain/langgraph-sdk/react";

function ChatComponent() {
  const { submit, messages, isLoading } = useStream({
    apiUrl: "/api",
  });

  const handleSendMessage = async (userMessage: string) => {
    // 获取用户选择的知识库ID
    const selectedKnowledgeBases = ["kb_001", "kb_002"];
    
    // 获取用户的认证令牌
    const authToken = localStorage.getItem("auth_token");

    await submit(
      {
        messages: [
          {
            role: "user",
            content: userMessage,
          },
        ],
      },
      {
        configurable: {
          thread_id: "thread_123",
          authorization: `Bearer ${authToken}`,
          knowledge_base_ids: selectedKnowledgeBases,
        },
      }
    );
  };

  return (
    <div>
      {/* UI 组件 */}
    </div>
  );
}
```

#### 使用 Fetch API

```javascript
const response = await fetch('/api/threads/thread_123/runs/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    input: {
      messages: [{
        role: 'user',
        content: '搜索关于产品文档的信息'
      }]
    },
    config: {
      configurable: {
        thread_id: 'thread_123',
        authorization: 'Bearer your_token_here',
        knowledge_base_ids: ['kb_001', 'kb_002']
      }
    }
  })
});

// 处理 SSE 响应
const reader = response.body.getReader();
// ... 处理流式响应
```

## 系统提示词优化建议

### 基础提示词模板

```markdown
# 智能助手系统提示词

## 角色定义
你是一位专业的智能助手，能够帮助用户搜索和检索内部知识库中的信息。

## 可用工具

### 1. local_search - 本地文档搜索
- **用途**: 在内部知识库中搜索文档
- **使用场景**: 
  - 用户询问公司内部政策、流程文档
  - 需要查找产品规格、技术文档
  - 搜索历史项目资料

### 2. knowledge_base_retrieve - 知识库文档检索
- **用途**: 根据文档ID获取完整文档内容
- **使用场景**:
  - 已经通过 local_search 找到相关文档ID
  - 需要获取文档的完整内容
  - 用户提供了具体的文档编号

## 工作流程

1. **理解用户意图**: 分析用户问题，判断是否需要搜索内部知识库
2. **选择工具**:
   - 如果是开放式问题 → 使用 `local_search`
   - 如果用户提供了文档ID → 使用 `knowledge_base_retrieve`
3. **执行搜索**: 调用相应工具获取信息
4. **综合分析**: 整合搜索结果，提供完整回答
5. **引用来源**: 明确标注信息来源的知识库和文档

## 使用指南

### 何时使用本地搜索
- 用户问："公司的请假流程是什么？"
- 用户问："查找关于API网关的技术文档"
- 用户问："去年项目的总结报告在哪里？"

### 何时使用文档检索
- 用户问："请打开文档 doc_12345 的完整内容"
- 用户提供了具体的文档编号
- 搜索结果显示相关文档，需要获取详情

## 回答格式

1. **直接回答**: 首先给出简洁直接的答案
2. **详细说明**: 提供相关背景和细节
3. **来源引用**: 列出引用的知识库和文档ID
4. **相关推荐**: 如有相关文档，建议用户查看

## 注意事项

- 如果搜索结果为空，告知用户并建议调整关键词
- 如果涉及多个知识库，说明搜索范围
- 保护敏感信息，不泄露未授权的内容
- 如果用户问题不明确，先进行搜索再回答
```

### 高级提示词优化

#### 1. 添加上下文感知

```markdown
## 上下文感知策略

### 对话历史分析
- 检查之前的对话是否已有相关搜索结果
- 避免重复搜索相同内容
- 基于已有结果进行深度检索

### 多轮搜索策略
1. 第一轮：广泛搜索获取相关文档列表
2. 第二轮：根据第一轮结果，检索关键文档详情
3. 第三轮：如有必要，针对特定细节再次搜索

### 示例对话流程
用户："查找API文档"
→ 使用 local_search 搜索 "API"
→ 返回多个相关文档ID

用户："第一个文档的详细内容"
→ 使用 knowledge_base_retrieve 获取 doc_xxx 详情
→ 展示完整文档内容
```

#### 2. 错误处理提示

```markdown
## 错误处理与恢复

### 搜索无结果时
"我在知识库中没有找到与 '关键词' 相关的内容。建议：
1. 尝试使用更通用的关键词
2. 检查是否有拼写错误
3. 确认您有访问相关知识库的权限"

### API 调用失败时
"暂时无法访问知识库服务，请稍后重试。如果问题持续，请联系管理员。"

### 权限不足时
"您当前没有访问该知识库的权限。如需访问，请联系管理员开通权限。"
```

#### 3. 结果优化提示

```markdown
## 搜索结果优化

### 相关性排序
- 优先展示与用户问题最相关的结果
- 按时间排序（最新的文档优先）
- 按来源可信度排序

### 结果摘要生成
对于每个搜索结果，生成简洁摘要：
- 文档标题
- 关键信息点（2-3条）
- 相关性评分

### 智能推荐
根据当前搜索结果，推荐：
- 相关文档
- 可能感兴趣的其他知识库
- 热门或常用文档
```

## API 接口规范

### 本地搜索 API

**Endpoint**: `POST /api/search`

**Request**:
```json
{
  "query": "搜索关键词",
  "knowledge_base_ids": ["kb_001", "kb_002"],
  "max_results": 5
}
```

**Response**:
```json
{
  "total": 10,
  "results": [
    {
      "document_id": "doc_123",
      "title": "文档标题",
      "snippet": "文档摘要...",
      "knowledge_base_id": "kb_001",
      "score": 0.95
    }
  ]
}
```

### 文档检索 API

**Endpoint**: `POST /api/retrieve`

**Request**:
```json
{
  "document_ids": ["doc_123", "doc_456"],
  "knowledge_base_ids": ["kb_001"]
}
```

**Response**:
```json
{
  "total": 2,
  "documents": [
    {
      "document_id": "doc_123",
      "title": "文档标题",
      "content": "完整文档内容...",
      "knowledge_base_id": "kb_001",
      "metadata": {
        "created_at": "2024-01-01",
        "author": "张三"
      }
    }
  ]
}
```

## 安全注意事项

1. **认证令牌**: 确保 `authorization` 参数安全传递，不要在前端暴露敏感信息
2. **权限控制**: 后端 API 应该验证用户是否有权访问指定的知识库
3. **数据脱敏**: 返回的文档内容应进行必要的脱敏处理
4. **访问日志**: 记录知识库访问日志，便于审计

## 故障排查

### 工具调用失败

1. **检查配置**: 确认 `config.yaml` 中的 `api_url` 配置正确
2. **验证网络**: 确保 DeerFlow 后端可以访问搜索 API 服务器
3. **查看日志**: 检查后端日志中的错误信息
4. **验证参数**: 确认前端正确传递了 `authorization` 和 `knowledge_base_ids`

### 搜索结果为空

1. **检查知识库ID**: 确认 `knowledge_base_ids` 是否正确
2. **验证权限**: 确认用户有权限访问指定的知识库
3. **调整关键词**: 尝试使用不同的搜索关键词
4. **检查API**: 直接调用搜索 API 验证是否正常工作
