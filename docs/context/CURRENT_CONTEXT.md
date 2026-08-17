# PDI 当前开发上下文

**当前版本：** `v0.5.0`

**冻结日期：** 2026-08-17

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

当前提供七个 read-only Tool：

1. `pdi_list_recent_resources`
2. `pdi_search_resources`
3. `pdi_aggregate_resources`
4. `pdi_retrieve_resources`
5. `pdi_rich_retrieve_resources`
6. `pdi_get_resource`
7. `pdi_get_resource_observations`

### Server Runtime

- 正式主机：`pdi-server`；
- 正式 production checkout：`/srv/projects/PDI`；
- production PostgreSQL、Provider sync、enrichment timers 与 resource-access
  service 均在主机运行；
- Jarvis/Hermes reference runtime 通过 SSH on-demand 启动；
- Hermes 仅启用三个冻结的 PDI MCP Tool，Memory 与 write capability 关闭；
- DeepSeek 是当前远程 inference Provider，PDI 不依赖它。

## 3. 开发工作流

主机开发采用独立 checkout：

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

2026-08-17 本地完整测试：

```text
414 passed, 66 skipped
```

66 个 skip 是显式的数据库/真实 Provider integration gate。本轮没有让 pytest 连接
production `pdi` 数据库。服务器 Runtime 与 Jarvis E2E 的已冻结证据记录在对应
deployment/design 文档中。

## 6. 当前限制

- 没有通用 Jarvis/PDI long-term memory；
- 没有 write Tool、任务系统或 proactive agent loop；
- 没有正式 HTTP/Web UI；
- Codex CLI 是开发工具，不进入 production data path；
- Immich geo extractor 与独立 05:30 systemd scheduling artifacts 已实现；production
  安装、首次运行与 timer enable 仍需按 deployment gate 完成；
- production integration validation 必须使用隔离数据库，不能复用 production secret。

## 7. 下一阶段

下一阶段是 v0.6 operational retrieval hardening：生产规模验证并启用 geo scheduling、
改进 retrieval UX 与可重复 release/development automation。任何关系推理、Memory、
写操作或 Web transport 都必须先冻结 trust boundary 与架构，再实现。
