# PDI 当前开发上下文

**当前版本：** `v0.5.0`

**冻结日期：** 2026-08-19

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

Data Status V0.1 使用独立 `pipeline_runs` ledger、十项 static registry、
`DataStatusService` 与 formal `pdi.operational` runner。runner 是
`/run/lock/pdi-sync.lock` 的唯一 owner；裸 sync/enrichment CLI 不加锁、不写
ledger。Status 只派生 `last_success_at`、`success_age_seconds` 与 dependency
validation，不持久化 fresh/stale，也不返回 ResourceEnrichment coverage count。
Hermes/Jarvis 的三 Tool profile 本阶段保持不变。

### Gmail Provider production freeze

Gmail Provider V0.1 已于 2026-08-19 完成功能与 production data-plane freeze。
V0.1 仅支持一个配置的 Gmail account；Provider identity
`(gmail, message.id)` 只在该单账号边界内成立，多账号 namespace 明确 deferred。

完整 `users.messages.list(includeSpamTrash=true)` 同步创建 283 个
`resource_type=message` Resources、283 个 active Gmail AssetSources，并实现
283/283 `message/rfc822` RAW RFC 2822 Blob coverage。四个 deterministic
predicates `gmail.subject`、`gmail.from`、`gmail.to`、`gmail.internal_date`
共产生 1,132 条 current observations。第二轮正式 sync actions=0；第二轮
enrichment processed=0、skipped=283、writes=0。duplicate Message Resources=0，
Gmail API writes=0。

`provider.gmail.sync` 与依赖它的 `enrichment.gmail_metadata` 复用现有 formal
runner、shared lock、PipelineRun、DataStatusService 与 `pdi_get_data_status`；
registry 共十项，MCP 仍为八个 read-only Tools。没有 Gmail systemd unit、timer
或 scheduler。OAuth application 仍处于 Testing：bounded/manual execution 已支持，
long-lived unattended operation 尚未 ready。

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
shared flock owner。历史没有回填；初次 freeze 按 dependency 顺序执行当时八个 pipeline，随后
额外执行一次 Immich Geo no-op 验证，共形成九条真实 `completed` PipelineRun，零
`running`、零 `failed`。

当前 production StatusSnapshot 返回十个 registry pipeline；三个 Provider pipeline 的
dependency validation 为 `null`，七个 enrichment pipeline 可按各自最新 upstream
success 派生 validation。初次 freeze 时六个 enrichment pipeline 均为 `true`。本地正式
stdio MCP 已验证八个 read-only Tool。Jarvis Web UI V0.1 的当前正式
Hermes/PDI read allowlist 已单独冻结为七项：recent、search、Resource detail、
aggregation、Observations、Provider-semantic retrieval 与 rich retrieval；本阶段
不增删 Tool。

### Person Identity production freeze

Person Identity V0.1 已在 production 启用。它只同步 Immich standard
`/api/people` enumerable inventory；Provider total 仅是诊断信号，不定义同步完整性。
首次完整同步创建 417 个 `Person` 与 417 个 active `PersonSource`，第二次完整同步
创建、恢复和 inactive 均为零，全部 417 个 mapping 保持不变。

Person 只包含 UUID identity 与 `created_at`；PersonSource 使用
`(provider, external_id)` composite primary key，并只用 nullable `inactive_at` 表达
enumerable membership lifecycle。display name、metadata、face/vector、cross-provider
matching、public reference、MCP 与 operational schedule 均未引入。Person
Identity 本身仍不保存 Relation；Resource-Person Relation 由后续独立专用表承载。

### Resource-Person Relation production freeze

Resource-Person Relation V0.1 已在 production 启用，只表达 Provider-derived
`Resource depicts Person`。专用 `resource_person_relations` 表仅包含
`resource_id`、`person_id`、`provider`、`inactive_at`，并以三者 identity columns
作为 composite primary key；没有 Relation UUID、predicate、confidence、face、
bounding box、embedding 或 generic graph。

Immich 显式同步只查询 active enumerable PersonSources，并通过 metadata search
的 `personIds` 完整分页获取资产；normal sync 不调用 Faces API。production 当前有
10,460 条 active relations，覆盖 5,267 个 Resources 与 417 个 Persons。完整只读
审计另发现 84 个 Person V0.1 inventory 外 Provider identities、114 个 pairs；它们
不创建隐藏 Person/PersonSource，也不持久化 relation。

首次同步创建 10,460 行；立即第二次同步全部 unchanged，created、reactivated、
inactivated 均为零，mapping digest 不变。MCP 仍为八个 read-only Tools，且没有
Relation/Person query、systemd、timer 或 PipelineRun registry entry。

### Typed Resource production freeze

Typed Resource V0.1 已在 production 启用。`assets.id` 继续作为 canonical PDI
Resource identity，公开 reference 仍为 `pdi:resource:<uuid>`；物理 `assets`、
`Asset` 与 `AssetSource` 名称不变。`assets.resource_type` 是必填 Core
discriminator，V0.1 仅允许 `file` 与 `message`。

迁移 `3b1e6f8a4c20` 将当时既有 15,325 个 production Resources 全部确定性标记为
`file`；迁移验证时 `message=0`、NULL=0，最终 schema 没有 server default。Blob 与
AssetSource schema 不变，Message 仍必须拥有 Blob。File 保留原有 global
content-hash dedup；不同 Provider Message identity 即使 raw content hash 相同也
不得自动合并。

Observation、Resource-Person Relation 与 `pdi:resource` reference 均未改变。
现有 Immich retrieval、Rich Retrieval 与 Resource Access 继续显式 file-only。
Gmail 已在上述独立 freeze 中实现，但没有 Gmail Resource Access、专用 MCP Tool
或 schedule。上线前暴露的旧 PDI PostgreSQL credential 已确认失效，Compose/container
配置已协调，live reference 为零。

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

2026-08-19 当前 host-safe 与 Stage 2 Jarvis validation：

```text
host-safe/default: 491 passed, 98 skipped
Jarvis isolated PostgreSQL migration: 1 passed
prior PDI isolated PostgreSQL suite: 99 passed, 2 skipped
```

skip 均来自显式 database、live Provider 或 integration gate；isolated suite 使用
一次性 PostgreSQL 16 测试容器；Jarvis migration 使用独立的
`jarvis_stage2_test`，本轮没有让 pytest 连接 production `pdi` 或 production
Jarvis database。
Codex 默认 command sandbox 会阻塞 MCP SDK `Client.call_tool` worker path；相同
standalone/minimal pytest 在 host-native execution 正常通过，因此正式回归使用
host-native execution 完成。

## 6. 当前限制

- 没有通用 Jarvis/PDI long-term memory；
- 没有 write Tool、任务系统或 proactive agent loop；
- Jarvis Web UI V0.1 Stage 1 的视觉与 Beacon / Guide identity 保持冻结；Stage 2
  已通过 human architecture review 并冻结 FastAPI product skeleton、独立 Jarvis
  state/migration、MockRuntimeAdapter、SSE 与 persistent Chat API boundary；仍没有
  Hermes/PDI integration、production Jarvis database 或 production Web service；
- Codex CLI 是开发工具，不进入 production data path；
- production integration validation 必须使用隔离数据库，不能复用 production secret。

## 7. 下一阶段

Server-first Codex migration、Geo、Data Status V0.1、Person Identity V0.1 与
Resource-Person Relation V0.1、Typed Resource V0.1 与单账号 Gmail Provider V0.1
production freeze 已完成。Jarvis Web UI V0.1 Stage 1 static frontend 与
Beacon / Guide identity 也已通过 human visual/brand review 并冻结；Stage 2 skeleton
也已通过 human architecture review 并冻结；真实 Hermes/PDI/production deployment
分别保持 Stage 3/Stage 4/Stage 5 deferred。
任何关系推理、Memory、写操作或 Web backend/deployment 都必须遵守各自已批准或后续
单独冻结的 trust boundary 与架构。
