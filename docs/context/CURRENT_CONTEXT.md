# PDI Core 开发上下文（截至 PDI Core MVP V0.1 完成）

我们正在开发 **PDI（Personal Digital Infrastructure）**。

## 一、项目定位（冻结）

PDI 是整个项目本体。

Jarvis 只是第一个 AI Interface。

PDI 去掉 AI 后仍然应该有价值。

AI、Agent、LLM、Jarvis 都是 PDI 的消费者，而不是 PDI 本身。

PDI 的职责：

- 管理数字资产（Digital Assets）
- 提供统一数据模型（World Model）
- 保存数字历史
- 提供统一查询接口
- Adapter 连接各种 Provider

PDI 不负责：

- AI 推理
- 大模型 Memory
- 文件同步（由 Provider 完成）
- 文件管理 UI（Nextcloud 完成）
- 图片管理（Immich 完成）

Architecture First 是整个项目最高原则。

任何新增功能都必须保证：

> 可维护、可扩展、一人长期维护。

---

# 二、当前架构（已冻结）

```
Provider
        │
        ▼
Adapter
        │
        ▼
ProviderFact
        │
        ▼
Identity (Matcher)
        │
        ▼
Decision
        │
        ▼
Repository
        │
        ▼
PostgreSQL
```

目前整个闭环已经真实跑通。

---

# 三、已经完成（PDI Core MVP V0.1）

## 基础设施

完成：

- Debian Server
- Docker
- PostgreSQL
- Redis
- Nextcloud
- Tailscale

服务器稳定运行。

---

## Nextcloud Adapter

完成：

- connect()
- status()
- scan()
- open()

scan() 返回 ProviderFacts。

Provider 自己不做任何业务判断。

---

## ProviderFacts

Identity 输入统一使用：

ProviderFacts

而不是 Provider 自己的数据结构。

ProviderFacts 是 Adapter 与 Identity 的唯一协议。

---

## Identity（Matcher）

目前完成最小版本。

Matcher 输入：

```
ProviderFact
```

输出：

```
Decision
```

Decision 包含：

```
Action[]
Requirement[]
```

Requirement 已实现：

```
CONTENT_HASH
```

如果需要 hash：

SyncEngine 会：

```
adapter.open()

↓

calculate_sha256()

↓

重新 match()
```

Identity 不直接读取 Provider。

Identity 不计算 Hash。

---

## SyncEngine

职责：

仅负责调度。

流程：

```
adapter.connect()

↓

adapter.scan()

↓

matcher.match()

↓

如果需要 hash：

adapter.open()

↓

calculate_sha256()

↓

matcher.match()

↓

repository.execute()
```

SyncEngine 没有业务逻辑。

只是 Orchestrator。

---

## Repository

Repository 已完成 PostgreSQL 实现。

包括：

- Connection
- ORM Mapper
- Query
- Execute
- Transaction

---

### Repository 已实现

```
test_connection()

find_source()

find_blob_by_hash()

find_blob_by_hash_in_asset()

get_blob()

get_asset()

execute()
```

execute() 已支持：

```
CREATE_ASSET

CREATE_BLOB

CREATE_SOURCE
```

UPDATE_SOURCE 保留为：

```
NotImplementedError
```

等待 V0.2。

---

## ORM

已完成：

AssetORM

BlobORM

AssetSourceORM

使用：

SQLAlchemy 2.x Typed ORM

全部采用：

Mapped[]

mapped_column()

---

## 数据库 Schema（冻结）

三张表：

```
assets

blobs

asset_sources
```

关系：

```
Asset

↓

Blob

↓

AssetSource
```

ForeignKey 全部正常。

事务正常。

Integration Test 已验证。

---

## execute()

execute() 使用：

```
match ActionType

↓

_execute_create_asset()

_execute_create_blob()

_execute_create_source()
```

使用：

```
session.flush()
```

保证：

Asset

↓

Blob

↓

Source

按顺序满足 ForeignKey。

最后：

```
session.commit()
```

任何失败：

```
rollback()
```

保持事务原子性。

---

## Integration Test

已完成：

pytest

真实 PostgreSQL

不是 Mock。

Repository Integration Test 已通过。

测试：

```
Decision

↓

execute()

↓

PostgreSQL

↓

Repository Query

↓

Domain
```

全部成功。

---

## Database Layer

新增：

```
database/

    __init__.py

    postgres.py

    schema.sql
```

统一：

```
create_postgres_engine()
```

负责：

- load_dotenv()
- 创建 SQLAlchemy Engine

整个项目以后统一使用：

```
create_postgres_engine()
```

而不是直接：

```
sqlalchemy.create_engine()
```

---

## main.py

目前：

```
NextcloudAdapter

↓

SyncEngine

↓

Matcher

↓

PostgreSQLRepository
```

已经跑通。

运行：

```
python main.py
```

输出：

```
Sync finished.
```

数据库成功出现真实 Nextcloud 数据。

验证：

```
SELECT provider,path,name
FROM asset_sources;
```

结果：

```
provider = nextcloud
```

说明：

真正完成：

```
Nextcloud

↓

Adapter

↓

Identity

↓

Repository

↓

PostgreSQL
```

整个闭环。

---

# 四、目前技术栈

Python 3.13

SQLAlchemy 2.x

PostgreSQL 16

Docker

Nextcloud

pytest

python-dotenv

Redis

requests

psycopg3

---

# 五、目前项目目录

```
database/

repository/

repository/orm/

decision/

identity/

engine/

adapters/

models/

tests/

docs/
```

采用 Domain 驱动。

Repository Pattern。

ORM 与 Domain 完全分离。

---

# 六、已经踩过的重要坑（以后不要再踩）

① SQLAlchemy 没有 relationship 时：

session.commit() 不保证插入顺序。

解决：

每个 Action 后：

```
session.flush()
```

不是 commit。

flush 保证：

ForeignKey 正确。

---

② Repository 不应该检查业务。

例如：

不要：

```
if action.asset is None
```

Repository 信任：

Decision。

以后可使用：

assert。

---

③ 不直接访问 Repository 内部。

以前：

```
repository.assets
```

现在：

PostgreSQLRepository 没有：

assets/blobs/sources

统一使用：

Repository API。

---

④ Adapter 不做业务判断。

Identity 决定：

CREATE

MATCH

HASH

等等。

---

⑤ SyncEngine 不包含业务逻辑。

只是：

```
Adapter

↓

Identity

↓

Repository
```

调度。

---

⑥ Database Layer

统一：

create_postgres_engine()

不要：

项目里到处：

create_engine()

---

# 七、目前工程质量

已经完成：

- Integration Test
- Repository Pattern
- ORM
- Transaction
- Database Layer

目前缺少（属于 V0.2）：

- Settings 配置系统
- Logging
- Alembic Migration
- API
- Web UI
- 更多 Provider

---

# 八、下一阶段（PDI Core V0.2）

不再搭底层。

开始扩展能力。

优先讨论：

1.
Settings（统一配置）

2.
Logging

3.
Alembic

4.
API

5.
Immich Adapter

6.
WeChat Provider

7.
Email Provider

8.
Search

9.
Event Timeline

10.
Jarvis Interface

整个开发原则保持：

Architecture First

Small Commit

Integration Test

一步一步推进，不为了未来提前设计。