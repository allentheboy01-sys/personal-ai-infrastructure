# PDI 当前开发上下文

**更新时间：** 2026-07-21（PDI Core v0.2.0 完成）
**文档性质：** 当前实现状态，不是永久架构规范

## 1. 项目定位

PDI（Personal Digital Infrastructure）是项目本体。

Jarvis 是第一个 AI Interface。AI、Agent、LLM 和具体界面都是 PDI 的消费者，不定义 PDI 本身。

冻结原则：

- PDI 去掉 AI 后仍然必须有独立价值；
- Provider 和 AI 可以替换，World Model 应保持稳定；
- AI 消费 World Model，不定义核心 World Model；
- Architecture First；
- 新增抽象必须降低整体复杂度；
- 长期目标是一人可维护。

## 2. 当前真实闭环

```text
Nextcloud ──► Nextcloud Adapter ──┐
                                  │
Immich ─────► Immich Adapter ─────┤
                                  ▼
                             ProviderFact
                                  │
                                  ▼
                             Sync Engine
                       ┌──────────┼──────────┐
                       │          │          │
                       ▼          ▼          ▼
                Identity /   Requirement   Decision
                  Matcher     Adapter /        │
                              Capability       ▼
                                           Repository
                                               │
                                               ▼
                                    PostgreSQL World Model
```

Nextcloud 和 Immich 闭环均已真实运行，不是 Mock 或仅内存演示。

Immich 已验证：

- `connect()`、`scan()` 和 original-content `open()`；
- 进入统一 ProviderFact、Matcher、Requirement 和 Decision 流程；
- 由 SyncEngine 计算 SHA-256；
- 通过 PostgreSQLRepository 写入 PostgreSQL；
- 新上传资源首次同步会创建 Asset、Blob 和 AssetSource；
- 第二次同步保持 Source ID 和 Blob ID 不变，不重复创建数据。

## 3. 当前版本状态

PDI Core v0.2.0 已发布并合并到 `main`。

已验证：

- Nextcloud 与 Immich 通过同一套 PDI Core 顺序同步；
- 空的 `_test` 数据库会先通过 Alembic 升级至 `head`；
- 测试数据库 Guard 会拒绝正式数据库；
- Alembic 不再禁用已有 PDI logger；
- 全量测试：`52 passed`；
- 正式入口 `python -m pdi.main` 已在服务器运行；
- Immich 新资源首次同步产生 3 个 Action 和 1 次 SHA-256 计算；
- 再次同步不会重复创建实体。

## 4. 当前代码结构

项目采用 `src` layout，核心包位于：

```text
src/pdi/
├── adapters/
├── capability/
├── config/
├── database/
├── decision/
├── engine/
├── identity/
├── models/
└── repository/
```

统一运行入口：

```bash
python -m pdi.main
```

## 5. 基础设施状态

当前服务器环境包括：

- Debian Server；
- Docker / Docker Compose；
- PostgreSQL 16；
- Redis 7；
- Nextcloud；
- Immich；
- Tailscale；
- Python 虚拟环境。

Nextcloud、Immich、PostgreSQL 和 PDI Core 已经完成真实联通。

## 6. Provider 与 Adapter

当前已实现 Provider：

```text
Nextcloud
Immich
```

`NextcloudAdapter` 已具备：

- 连接 Provider；
- 扫描 Provider 对象；
- 输出统一 `ProviderFact`；
- 在 Requirement 需要时打开内容流；
- 隔离 WebDAV 和 Nextcloud 专属字段。

Adapter 不创建 Asset、Blob、AssetSource 或 Decision，也不直接访问 Repository。

`ImmichAdapter` 已具备：

- 使用 API Key 连接 Immich；
- 通过 metadata search 扫描 Asset；
- 输出相同的统一 `ProviderFact`；
- 按 Requirement 打开 original content；
- 保留 Immich SHA-1 作为 Provider metadata，不替代 PDI SHA-256；
- 隔离 EXIF、favorite、archive、visibility 等 Provider 专属字段。

正式入口共享一个 database engine、PostgreSQLRepository 和 Matcher，并为 Nextcloud、Immich 分别运行独立的 `SyncEngine.sync_once()`。当前是顺序同步，不是多 Provider 并行同步。

## 7. ProviderFact

`ProviderFact` 是 Adapter 与 PDI Core 之间的统一观察协议。

它表达 Provider 当前观察到的事实，例如：

- provider；
- external_id；
- path；
- name；
- version_tag；
- size；
- mime type；
- Provider metadata；
- 按需补充的 content hash。

ProviderFact 是临时观察，不是持久化 World Model 实体。

## 8. Identity V1

Identity V1 已完成完整的创建、更新、版本变化和停用生命周期。

当前支持：

### 新对象与新内容

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
```

### 新 Source 但内容已存在

```text
CREATE_SOURCE
```

Source 复用已有 Blob，不创建重复内容实体。

### Source 路径、名称、metadata 或 Provider version 变化

```text
UPDATE_SOURCE
```

### 已有 Source 内容变化

```text
CREATE_BLOB
UPDATE_SOURCE
```

旧 Blob 保留，新 Blob 表示新的不可变内容状态。

### 完整扫描后 Source 缺失

```text
DEACTIVATE_SOURCE
```

Source 使用软删除：

```text
is_active = false
deleted_at = timestamp
```

不会物理删除历史 Source。

## 9. Requirement 机制

当前 Requirement：

```text
CONTENT_HASH
```

处理流程：

```text
Identity 发现证据不足
        │
        ▼
Requirement(CONTENT_HASH)
        │
        ▼
Sync Engine 调用 Adapter.open()
        │
        ▼
SHA-256 Capability
        │
        ▼
补充 ProviderFact.content_hash
        │
        ▼
再次进入 Identity
```

Identity 不读取文件，也不计算 Hash。

## 10. Sync Engine 与完整扫描

Sync Engine 当前负责一个同步会话的生命周期：

- 连接 Adapter；
- 开始并消费 Provider 扫描；
- 将 Fact 交给 Identity；
- 满足 Requirement；
- 将可执行 Decision 交给 Repository；
- 记录本次扫描出现的 external_id；
- 在完整扫描成功后执行 Reconcile；
- 对缺失 Source 触发停用 Decision；
- 输出结构化同步日志。

冻结安全规则：

> 只有成功完成的完整扫描才能推断 Source 缺失。

连接失败、扫描中断或部分扫描不得触发批量停用。

## 11. World Model

当前核心实体：

```text
Asset
  │
  ├── Blob
  │
  └── AssetSource
```

### Asset

长期稳定的语义身份。Asset 可以跨越重命名、移动和内容变化。

### Blob

不可变内容状态。内容变化创建新 Blob，不覆盖旧 Blob。

### AssetSource

Provider 中一个对象的存在形式。

Source 身份由以下组合定义：

```text
provider + external_id
```

路径和名称只是可变属性。

## 12. Repository

当前 Repository 实现：

- `InMemoryRepository`；
- `PostgreSQLRepository`。

当前支持的主要查询和操作：

```text
find_source()
list_active_sources()
find_blob_by_hash()
find_blob_by_hash_in_asset()
get_blob()
get_asset()
execute()
```

`execute()` 当前支持：

```text
CREATE_ASSET
CREATE_BLOB
CREATE_SOURCE
UPDATE_SOURCE
DEACTIVATE_SOURCE
```

PostgreSQL Repository 使用事务执行 Decision，并通过有序 flush 满足 Asset → Blob → Source 的外键依赖。

失败时回滚，避免部分 Decision 被写入。

## 13. 数据库与 ORM

当前持久化技术：

- PostgreSQL 16；
- SQLAlchemy 2.x Typed ORM；
- psycopg；
- Domain Model 与 ORM Model 分离。

当前主要表：

```text
assets
blobs
asset_sources
```

`asset_sources` 已包含：

```text
is_active
deleted_at
```

统一数据库入口由配置和 database 模块提供，业务模块不应自行创建 Engine。

## 14. 测试与可观测性

已完成：

- Matcher 单元测试；
- Repository 测试；
- 真实 PostgreSQL Integration Test；
- 可按环境安全跳过的真实 Immich + PostgreSQL Integration Test；
- 空测试数据库自动执行 Alembic Migration；
- `_test` 数据库安全 Guard；
- Alembic logger 隔离回归测试；
- 同步过程结构化日志；
- Provider 连接、扫描、Requirement、Action、缺失 Source 和停用过程日志；
- 服务器全量测试 `52 passed`；
- 正式环境增量同步与幂等验证。

日志目标是让一次同步的每个关键阶段都可以被定位和诊断。

当前唯一已知测试 warning 是 Alembic 对 `prepend_sys_path` 缺少 `path_separator` 的 deprecation warning，不影响当前功能。

## 15. 当前已冻结边界

当前不属于 Identity V1 的内容：

- Source reactivation；
- Relation；
- Tag；
- Evidence；
- Collection；
- 完整事件日志；
- 完整 Source-to-Blob 时间线；
- AI 语义合并；
- 多 Provider 并行同步；
- 自动 Retry / Resume；
- Scheduler；
- 对外 API；
- Jarvis Interface。

这些功能不能被当前代码或文档默认视为已经存在。

## 16. 当前文档结构

```text
docs/
├── README.md
├── architecture/
│   ├── 01-overview.md
│   ├── 02-provider.md
│   ├── 03-provider-adapter.md
│   ├── 04-provider-fact.md
│   ├── 05-sync-engine.md
│   ├── 06-identity.md
│   ├── 07-decision.md
│   ├── 08-repository.md
│   ├── 09-world-model.md
│   ├── 10-capability.md
│   └── 11-sync-lifecycle.md
├── context/
│   └── CURRENT_CONTEXT.md
└── decisions/
    └── README.md
```

职责区分：

- `architecture/`：当前有效的架构规范；
- `context/`：当前真实实现进度；
- `decisions/`：重大架构决策及其原因；
- Git 历史：过去版本和演进记录。

## 17. 下一阶段建议

PDI Core v0.2.0 已验证多 Provider 写入闭环。下一阶段不应继续无边界扩展 Provider 或底层抽象，而应建立 PDI 的读取与消费边界。

优先顺序：

1. 定义最小 Read / Query Contract；
2. 为 Repository 增加面向消费者的查询能力；
3. 建立 Jarvis CLI 或最小 Interface；
4. 验证 User → Jarvis → PDI → World Model 的第一条读取闭环；
5. 在出现明确需求前，不继续扩展 Provider、Relation 或 Source reactivation。

下一版本目标应是让 Jarvis 成为 PDI 的第一个真实消费者，而不是继续增加第三个 Provider。

## 18. 开发规则

后续开发默认遵循：

```text
讨论问题
    │
    ▼
冻结架构
    │
    ▼
更新 Specification / ADR
    │
    ▼
实现代码
    │
    ▼
测试
    │
    ▼
提交
```

文档不是代码的事后解释。

> Code implements the specification.
