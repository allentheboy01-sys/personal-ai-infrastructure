# PDI 当前开发上下文

**当前版本：** `v0.4.0`

**文档性质：** 当前真实实现状态，不是版本历史或永久架构规范。

## 1. 项目定位

PDI（Personal Digital Infrastructure）是项目本体，是个人数字生活的稳定基础设施。

Jarvis 是建立在 PDI 之上的第一个 AI Interface。Jarvis 是消费者，不定义 PDI Core，
也不是项目名称。

当前冻结依赖方向：

```text
Jarvis
  ↓
PDI Application Service
  ↓
Query Repository
  ↓
PostgreSQL Repository
```

必须保持：

- PDI 不依赖 Jarvis；
- Jarvis 只能通过 PDI 的公开 Application Service 读取数据；
- Tool 不直接访问 Repository、ORM、Session、Engine 或数据库；
- Write Pipeline 与 Read Pipeline 职责分离；
- Provider 和 AI 可以替换，PDI World Model 保持稳定。

## 2. 当前冻结架构

### Write Pipeline

```text
Provider
  ↓
Adapter
  ↓
ProviderFact
  ↓
SyncEngine
  ├── Identity / Matcher
  ├── Requirement
  └── Decision
        ↓
DecisionRepository
        ↓
PostgreSQLRepository
```

Write Pipeline 已冻结，不应因为消费者能力而重构。

### Read Pipeline

```text
QueryService
  ↓
QueryRepository
  ↓
PostgreSQLRepository
  ↓
SQLAlchemy ORM
  ↓
PostgreSQL
```

Read Pipeline 返回不可变 Read Model，不返回 ORM、Domain Model、Session 或 Engine。

当前公开读取能力：

- `QueryService.list_assets()`；
- `QueryService.get_asset(asset_id)`。

### Jarvis Tool Execution

```text
ToolCall
  ↓
JarvisApplication
  ↓
ToolRegistry
  ↓
Tool
  ↓
QueryService
```

`JarvisApplication` 只负责编排 Tool 执行。参数解析和业务错误由具体 Tool 负责。

Jarvis 与 PDI 位于同一仓库中的两个独立 Python 包：

```text
src/
├── pdi/
└── jarvis/
```

唯一正式 Jarvis 装配入口为：

```python
create_jarvis_application(settings)
```

## 3. 当前完成能力

### Provider 与 Write

- Nextcloud 与 Immich 两个真实 Provider；
- 统一 ProviderFact 输入；
- Identity、Requirement 和 Decision；
- SHA-256 内容身份验证；
- 增量同步和完整扫描 Reconcile；
- Source 软停用；
- 幂等同步；
- PostgreSQL Repository；
- Alembic Migration。

### Read

- `AssetSummary`；
- `AssetDetail`；
- `BlobView`；
- `SourceView`；
- 稳定排序；
- Metadata 递归不可变；
- Session 内完成 ORM 到 Read Model 映射。

### Jarvis Tool

当前支持：

- `list_assets`：返回 PDI 中可用的 Asset 摘要；
- `get_asset`：根据 Asset UUID 返回详细 Read Model。

当前执行边界还包括：

- 不可变 `ToolCall`、`ToolResult` 和 `ToolError`；
- 稳定且拒绝重复注册的 `ToolRegistry`；
- `unknown_tool`、`invalid_arguments`、`asset_not_found` 和
  `internal_error` 错误语义；
- 不记录参数值的 Tool 执行日志；
- 显式 Composition Root。

## 4. 测试状态

当前发布状态：

```text
81 passed
```

已通过真实 PostgreSQL Integration Test，覆盖：

- PostgreSQL → PostgreSQLRepository → QueryService → Tool →
  ToolRegistry → JarvisApplication；
- `list_assets` 的真实数据和确定性顺序；
- `get_asset` 的 Asset、Blob、Source 与 `blob_id` 关系；
- Session 关闭后的 Read Model 可用性；
- 不存在 Asset 的稳定 `asset_not_found` 结果。

现有 Write Pipeline、Provider、Migration 与数据库测试继续通过。

## 5. 当前未完成

以下能力不属于 `v0.4.0`：

- Jarvis HTTP API；
- Content Access；
- Search；
- Relation；
- Task System；
- LLM Integration；
- Agent Loop；
- Conversation 与 Chat History；
- RAG、Vector、Cache、Permission 与用户系统。

这些能力不能被当前代码或文档视为已经存在。

## 6. 下一阶段讨论

下一阶段首先讨论 `v0.5`。

当前方向是 Jarvis HTTP API，但在架构冻结前不提前定义 Transport、认证、请求模型、
部署方式或新的 Tool 能力。

默认流程仍然是：

```text
讨论问题
  ↓
冻结架构
  ↓
更新 Specification / ADR
  ↓
实现
  ↓
测试
```

不要提前实现 `v0.5`。
