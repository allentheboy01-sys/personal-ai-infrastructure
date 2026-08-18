# PDI 当前开发上下文

**当前版本：** `v0.5.0`

**冻结日期：** 2026-08-18

**文档性质：** 当前真实实现状态，不是版本历史或永久架构规范。

## 1. 项目定位

PDI 是个人数字生活的稳定基础设施；Provider、LLM 与 AI Interface 都是可替换边缘。
Jarvis 是第一个经过服务器验证的 AI Interface，不定义 PDI Core。

当前依赖方向：

```text
Provider -> Adapter -> Write Pipeline -> PostgreSQL
                                      <- Query / Retrieval <- PDI MCP <- Consumer
                                      <- Resource Access

Provider metadata/content -> Observation Enrichment -> typed Statements
```

必须保持：

- PDI 不依赖 Jarvis、Hermes、DeepSeek 或 Codex；
- Consumer 只能使用公开 Application Service、MCP 或受控 Resource Access；
- ORM、Session、Engine、Repository 与 Provider credential 不越过公开边界；
- Observation 增强 Resource 的可理解性，但不改变 Resource identity；
- Write、Observation、Read/Retrieval 与 Resource Access 职责分离。

## 2. 已实现能力

### Write 与 Provider

- Nextcloud 与 Immich 真实 Adapter；
- 增量、幂等同步与完整扫描 reconcile；
- Asset、Blob、AssetSource identity 与 source lifecycle；
- Provider 选择和 Nextcloud 递归扫描；
- PostgreSQL Repository 与 Alembic migration。

### Resource Query

- 稳定 `pdi:resource:<uuid>` reference；
- recent、search、aggregate、detail 与 cursor page；
- Provider、MIME、Resource type 与时间范围过滤；
- captured time 与 file-modified time 语义；
- immutable Read Model 与 Session 内映射。

### Observation

- typed Statement、predicate registry、cardinality、Evidence、generator identity；
- current/superseded lifecycle、input fingerprint 与幂等 publish；
- Immich metadata、OCR 与 Provider geo label extractor；
- file modified metadata；
- Nextcloud plain text、PDF、DOCX 与 ODT extraction；
- Observation PostgreSQL Repository 与 MCP detail exposure。

### Retrieval 与 Resource Access

- Provider-semantic retrieval；
- rich retrieval：primary text 加 typed statement filters；
- captured/file-modified temporal statement matching；
- bounded streamed Resource representation；
- 独立 resource-access process、UDS/HTTP 边界与并发/大小限制。

### PDI MCP

当前正式 PDI MCP 提供八个 read-only Tool：

1. `pdi_list_recent_resources`
2. `pdi_search_resources`
3. `pdi_aggregate_resources`
4. `pdi_retrieve_resources`
5. `pdi_rich_retrieve_resources`
6. `pdi_get_resource`
7. `pdi_get_resource_observations`
8. `pdi_get_data_status`

Data Status V0.1 使用独立 `pipeline_runs` ledger、八项 static registry、
`DataStatusService` 与 formal `pdi.operational` runner。runner 是
`/run/lock/pdi-sync.lock` 的唯一 owner；裸 sync/enrichment CLI 不加锁、不写
ledger。Status 只派生 `last_success_at`、`success_age_seconds` 与 dependency
validation，不持久化 fresh/stale，也不返回 ResourceEnrichment coverage count。
Hermes/Jarvis 的三 Tool profile 本阶段保持不变。

### Server Runtime

- 正式主机：`pdi-server`；
- 正式 production checkout：`/srv/projects/PDI`；
- production PostgreSQL、Provider sync、enrichment timers 与 resource-access
  service 均在主机运行；
- Immich Geo Enrichment V0.1 已完成 production full enrichment、full
  idempotency、正式 unit 安装与每日 05:30 Asia/Shanghai timer 验证；
- 当前 Geo predicates 为 `geo.country`、`geo.admin1`、`geo.locality`；
- Jarvis/Hermes reference runtime 通过 SSH on-demand 启动；
- Hermes 仅启用三个冻结的 PDI MCP Tool，Memory 与 write capability 关闭；
- DeepSeek 是当前远程 inference Provider，PDI 不依赖它。

### Data Status production freeze

Data Status & Freshness V0.1 已于 2026-08-18 在 production 启用。Alembic head
为 `4d8a2c6e9f10`，八个正式 batch service 均通过 `pdi.operational` 进入唯一
shared flock owner。历史没有回填；首轮按 dependency 顺序执行八个 pipeline，随后
额外执行一次 Immich Geo no-op 验证，共形成九条真实 `completed` PipelineRun，零
`running`、零 `failed`。

production StatusSnapshot 返回八个 registry pipeline；两个 Provider pipeline 的
dependency validation 为 `null`，六个 enrichment pipeline 均为 `true`。本地正式
stdio MCP 已验证八个 read-only Tool。Hermes/Jarvis allowlist 未随本次上线扩展。

### Person Identity production freeze

Person Identity V0.1 已在 production 启用。它只同步 Immich standard
`/api/people` enumerable inventory；Provider total 仅是诊断信号，不定义同步完整性。
首次完整同步创建 417 个 `Person` 与 417 个 active `PersonSource`，第二次完整同步
创建、恢复和 inactive 均为零，全部 417 个 mapping 保持不变。

Person 只包含 UUID identity 与 `created_at`；PersonSource 使用
`(provider, external_id)` composite primary key，并只用 nullable `inactive_at` 表达
enumerable membership lifecycle。display name、metadata、face/vector、cross-provider
matching、Relation、public reference、MCP 与 operational schedule 均未引入。

## 3. 开发工作流

主机独立 development checkout 是 PDI 的主要 Codex 开发环境：

```text
/home/harry/projects/personal-ai-infrastructure  # development
/srv/projects/PDI                               # production only
```

Codex CLI 可以在开发 checkout 中读取 `AGENTS.md`、本文件与 release 文档。
生产 checkout 只接受从 `origin/main` 的 clean fast-forward promotion，不用于日常开发或
pytest。完整操作见 `docs/development/codex-cli-on-pdi-server.md`。

主机 Codex CLI 已使用独立常驻 Xray user service，通过仅监听
`127.0.0.1:10808` 的本机代理访问 ChatGPT 与 GitHub。ChatGPT 登录已完成，Xray
service、user lingering 与 Git HTTPS proxy 均已验证，不依赖 Mac 在线。

## 4. Chat 与 Memory 边界

- Codex chat transcript 是运行 Codex 的 host-local session state；
- 新主机上的 chat 可用 `codex resume` 恢复，但现有 Mac-only chat 不视为已迁移；
- Codex local memory 与 ChatGPT web memory 分离；主机 local memory 当前已启用；
- 必须长期保留的架构、命令、测试与安全规则写进 Git 中的 `AGENTS.md` 和文档；
- 不复制整个 `~/.codex`，也不提交 `auth.json`、sessions 或 memories。

## 5. 验证状态

2026-08-18 Data Status freeze validation：

```text
host-safe/default: 435 passed, 82 skipped
isolated PostgreSQL: 515 passed, 2 skipped
```

skip 均来自显式 database、live Provider 或 integration gate；isolated suite 使用
独立测试数据库，本轮没有让 pytest 连接 production `pdi` 数据库。runner 的
SIGTERM、SIGINT、child reap 与第二运行互斥已在隔离集成测试中验证。

## 6. 当前限制

- 没有通用 Jarvis/PDI long-term memory；
- 没有 write Tool、任务系统或 proactive agent loop；
- 没有正式 HTTP/Web UI；
- Codex CLI 是开发工具，不进入 production data path；
- production integration validation 必须使用隔离数据库，不能复用 production secret。

## 7. 下一阶段

Server-first Codex migration、Geo、Data Status V0.1 与 Person Identity V0.1
production freeze 已完成。下一正式 PDI
architecture stage 由人工讨论后决定；本上下文不预选新功能。任何关系推理、Memory、
写操作或 Web transport 都必须先冻结 trust boundary 与架构，再实现。
