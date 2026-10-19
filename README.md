# BaseMgt · 业务底座

一套面向"持续开发管理系统"的业务底座：**用元数据描述业务，用可视化画布编排业务，用存储过程沉淀数据逻辑**。

核心价值：新增一个业务功能时，大部分工作变成「登记模块 → 写/改存储过程 → 画布里连线 → 发布接口 → 拖一个页面」，而不是从零写一套增删改查。

---

## 一、能力总览

| 能力 | 说明 | 落地位置 |
| --- | --- | --- |
| 业务模块 | 以模块为单位组织功能（菜单/功能包） | 前端「业务模块」 |
| 数据源 | 多库连接登记，编排节点按 key 引用 | 前端「数据源」+ SQL 控制台 |
| 存储过程开发 | 在线编写 DDL、版本管理、下发到库、在线调用测试 | 前端「存储过程」 |
| 服务/接口编排 | 节点连线编排，发布后即为一个 HTTP 接口 | 画布 kind=service |
| 业务流程编排 | 含人工任务节点，挂起→待办→处理→继续 | 画布 kind=flow + 「人工任务」 |
| 数据管道/定时任务 | cron 触发器 + SQL/存储过程节点跑批 | 画布 kind=pipeline + `run_schedules` |
| 页面与表单编排 | 字段/列可视化配置，绑定编排接口即成页面 | 前端「页面编排」 |
| 页面运行时 | 已发布页面自动生成 `/p/<key>` 页面并挂到侧边栏 | 前端动态菜单 |
| 权限（RBAC） | 角色、对象级授权（继承模块）、数据行级范围 | 前端「权限管理」 |
| 异步运行 | 入队 + worker 并发执行，可取消、可超时 | `run_worker` |
| 安全加固 | 数据源口令加密、SQL 控制台护栏 | `apps/catalog/crypto.py`、`sql_guard.py` |

---

## 二、架构

```
                ┌──────────────────────── Vue3 前端 ────────────────────────┐
                │ 画布(Vue Flow)  属性面板(按 schema 动态渲染)  运行日志      │
                └───────────────┬───────────────────────────────────────────┘
                                │ REST /api
┌───────────────────────────────▼───────────────────────────────────────────┐
│ Django 后端                                                                │
│  apps.catalog        模块/数据源/存储过程目录（元数据层）                   │
│  apps.orchestration  编排内核：Definition 图 + 引擎 + 节点插件（内核层）    │
│  apps.page           页面/表单 schema 与编排绑定（装配层）                  │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │ psycopg2
                      业务数据库（PostgreSQL）
```

**编排内核**的设计要点：

- 定义即数据：`Definition.graph` 存 `{nodes, edges}` JSON，画布自由编辑，运行前快照到 `Run.graph_snapshot`，改定义不影响历史运行。
- 节点即插件：新增节点 = 写一个 `BaseNode` 子类 + `register`，属性面板与校验自动生效（`/api/node-types` 下发 schema）。
- 解释执行：按「当前节点 → 决定出边 → 下一节点」推进，天然支持分支、循环、子流程、人工任务挂起/恢复。
- 表达式只做路径取值（`{{ vars.x }}`），不使用 `eval`，避免注入。

---

## 三、快速开始

```bash
# 0) 准备数据库（本机无可用 PG 账号时，用 home 目录下的私有实例，见下方说明）
scripts/pg.sh start          # 私有 PG：127.0.0.1:5433，超级用户 basemgt
#   或在 .env 里指向你自己的 PostgreSQL

# 1) 安装依赖
pip3 install --user -r backend/requirements.txt
cd frontend && npm install && cd ..

# 2) 初始化
cp .env.example .env         # 按需修改
cd backend && python3 manage.py migrate

# 3) 演示数据（可选，含一个"存储过程 → 接口"的示例）
python3 manage.py seed_demo

# 4) 启动
scripts/dev.sh all           # 后端 8000，前端 5173
```

验证示例接口：

```bash
curl -X POST http://127.0.0.1:8000/api/x/demo-calc \
  -H 'Content-Type: application/json' -d '{"qty":3,"price":12.5}'
# => {"code":0,"message":"success","data":{"run_id":1,"status":"success","output":{"amount":37.5}}}
```

后台账号：`admin / admin123`（`seed_demo` 创建）。

引擎自测（循环/分支/人工任务挂起恢复/子流程/错误继续）：

```bash
cd backend && python3 manage.py shell -c "exec(open('scripts/engine_selftest.py').read())"
```

---

## 四、典型工作流

### 1. 增加一个新模块

1. 「业务模块」新增模块（如 `finance`）。
2. 「数据源」确认业务库连接（新库在此登记，点「测试」验证）。
3. 「存储过程」新建存储过程，写 DDL →「下发到库」→「调用测试」。
4. 「编排定义」新建 `service` 编排，在画布里拖入：开始 → 存储过程 → 结束，填写参数表达式。
5. 发布后接口即 `POST /api/x/<key>`。
6. 「页面编排」建列表/表单页，绑定上面这个编排 key，一个模块页面就出来了。

### 2. 开发/迭代存储过程

- 每次保存生成一个版本，可回滚到任意版本「下发」。
- 「从库拉取」可把别人手工改过的定义同步回目录。
- 数据源详情页「同步存储过程」可批量把库里已有的过程纳入目录管理。

### 3. 跑批与定时任务

编排类型选「数据管道/定时」，触发设置里选 cron（如 `*/5 * * * *`），后台常驻调度：

```bash
cd backend && python3 manage.py run_schedules --interval 30
```

### 4. 新增一种节点类型

```python
# backend/apps/orchestration/nodes/my_node.py
from ..registry import register
from .base import BaseNode, NodeResult

@register
class MyNode(BaseNode):
    type = "my_node"
    label = "我的节点"
    category = "集成"
    config_schema = [{"key": "url", "label": "地址", "type": "text", "default": ""}]

    def execute(self, ctx, config):
        value = ctx.render(config.get("url"))     # 支持 {{ vars.x }} 表达式
        ctx.log(f"处理 {value}")                   # 日志进入节点运行记录
        ctx.set_var("result", value)               # 写入上下文变量
        return NodeResult(output={"value": value})
```

在 `nodes/__init__.py` 里 import 即可。前端画布左侧自动出现该节点，右侧属性面板按 `config_schema` 自动渲染。

---

## 五、目录结构

```
BaseMgt/
├── backend/
│   ├── config/                 Django 配置
│   └── apps/
│       ├── core/               公共基类与统一响应
│       ├── catalog/            模块 / 数据源 / 存储过程目录
│       ├── orchestration/      编排内核
│       │   ├── models.py       Definition / Run / NodeRun / HumanTask
│       │   ├── engine.py       执行引擎（分支/循环/挂起恢复/子流程）
│       │   ├── context.py      上下文与表达式解析（无 eval）
│       │   ├── registry.py     节点类型注册表
│       │   ├── nodes/          节点插件
│       │   └── management/commands/  seed_demo、run_schedules
│       └── page/               页面与表单编排
├── frontend/                   Vue3 + Vite + Element Plus + Vue Flow
├── scripts/                    pg.sh（私有 PG）、dev.sh（一键启动）
└── deploy/                     docker-compose（仅依赖服务）
```

## 六、内置节点

| 类型 | 分类 | 说明 |
| --- | --- | --- |
| `start` / `end` | 流程控制 | 入口与输出映射 |
| `branch` | 流程控制 | 条件分支（eq/gt/contains/is_empty…） |
| `loop` | 流程控制 | 遍历数组，body 出边循环、done 出边结束 |
| `transform` | 流程控制 | 变量赋值/数据映射 |
| `subflow` | 流程控制 | 调用另一个已发布编排 |
| `human_task` | 流程控制 | 生成待办并挂起，处理动作决定出边 |
| `sql` | 数据 | 执行 SQL，结果赋给变量 |
| `procedure` | 数据 | 调用存储过程/函数（支持从目录选择） |
| `http` | 集成 | 调用外部接口 |
| `script` | 集成 | Python 脚本（可通过 `BM_ENABLE_SCRIPT_NODE=0` 关闭） |

## 七、配置

参见 `.env.example`：

- `BM_DB_*` 平台元数据库
- `BM_AUTH_DISABLED=1` 关闭接口鉴权（仅建议本地开发）
- `BM_ENABLE_SCRIPT_NODE=1` 是否允许脚本节点
- `BM_MAX_RUN_STEPS` 单次运行步数上限（防死循环）

## 八、权限（RBAC）

动作：`read` / `write` / `run` / `admin`（admin 隐含其它三个）。

- **角色**：内置 `admin`/`developer`/`operator`/`viewer`，可自建（`python manage.py seed_demo` 会初始化）
- **对象级授权**：给具体对象（模块/编排/存储过程/页面/数据源）授予动作；**编排、页面、存储过程自动继承所属模块的授权**
- **接口鉴权**：所有业务 ViewSet 统一走 `apps.iam.permissions`，列表按授权过滤、详情/发布/运行按动作校验
- **数据行级**：`DataScope` 定义「角色 → 某类数据的过滤条件」；SQL 节点填写同样的「数据范围」标识后，引擎会在结果外层追加 `WHERE`（特权用户不限制）
- **登录**：`/api/auth/login`（Session），前端未登录时自动显示登录页

开发便利：`BM_AUTH_DISABLED=1`（默认）时未登录按管理员处理，前台顶栏会显示「未鉴权(开发模式)」提示。上线前务必置 0。

## 九、异步运行

```bash
scripts/dev.sh worker        # 或 all，worker 已随 all 启动
python manage.py run_worker --workers 2 --interval 2
```

- `POST /api/definitions/{id}/run/` 默认入队，立即返回 `status=pending` 的 run；前端自动轮询至结束
- 需要同步等待：`?sync=1`
- 对外接口 `/api/x/<key>` 默认同步返回结果；加 `?async=1` 改为入队并返回 202 + `run_id`
- 取消：`POST /api/runs/{id}/cancel/` —— 等待中直接取消，运行中在下一个节点处协作式终止
- 超时：`BM_RUN_TIMEOUT`（整次运行）、`BM_SQL_TIMEOUT_MS`（单条 SQL，通过 `statement_timeout` 下发）
- worker 用 PG 行锁 `FOR UPDATE SKIP LOCKED` 领取任务，可多进程/多机并发

## 十、安全

- 数据源口令用 Fernet 加密存储（`enc:` 前缀），历史明文仍可读；改密后执行 `python manage.py encrypt_passwords`
  注意：密钥由 `SECRET_KEY` 派生，更换 `SECRET_KEY` 后需重新录入口令
- SQL 控制台默认只读：仅 SELECT/WITH/EXPLAIN 等，禁止多语句与 DROP/ALTER/TRUNCATE 等 DDL；
  DDL 请走存储过程版本下发，写操作需 `BM_SQL_CONSOLE_WRITE=1`
- 脚本节点可用 `BM_ENABLE_SCRIPT_NODE=0` 关闭

## 十一、自测脚本

```bash
cd backend
python manage.py shell -c "exec(open('scripts/engine_selftest.py').read())"   # 循环/分支/人工任务/子流程
python manage.py shell -c "exec(open('scripts/iam_selftest.py').read())"      # 授权/继承/过滤/行级/鉴权
python manage.py shell -c "exec(open('scripts/async_selftest.py').read())"    # 入队/取消/超时/接口
```

## 十二、企业主数据（MDM）

底座内置企业通用主数据，**元数据驱动 + 生成真实物理表**（不是通用宽表），
所以历史/新写的存储过程、报表、JOIN 都能直接作用在这些表上。

```bash
cd backend && python manage.py init_master_data
```

### 预置的 7 类主数据

| 标识 | 名称 | 物理表 | 特有字段示例 |
| --- | --- | --- | --- |
| `department` | 部门信息 | `mdm_department` | parent_id(上级部门)、leader、phone、location |
| `employee` | 人员信息 | `mdm_employee` | dept_id(所属部门)、job_status、position、phone、email、id_no、entry_date |
| `supplier` | 供应商信息 | `mdm_supplier` | short_name、category、level、contact、tax_no、bank_account、payment_term |
| `customer` | 客户信息 | `mdm_customer` | category、level、contact、credit_limit、sales_owner(负责业务员) |
| `product` | 产品信息 | `mdm_product` | spec、unit、category、brand、barcode、sale_price、cost_price |
| `material` | 原材料信息 | `mdm_material` | spec、unit、purchase_price、safety_stock、shelf_life、warehouse |
| `asset` | 资产信息 | `mdm_asset` | category、asset_status、buy_amount、depreciation_rate、dept_id、custodian、warranty_date |

**每类都自带标准基础字段**：`id / code(编号) / name(名称) / status / remark / is_deleted / created_by / updated_by / created_at / updated_at`。

### 每个主数据对象自动产出

| 产物 | 说明 |
| --- | --- |
| 物理表 | 按字段定义建表、建索引、加列注释 |
| 存储过程 | `sp_<key>_search`(分页查询) `_count`(总数) `_get`(单条) `_save`(新增/更新) `_delete`(软删除) |
| 编排 | `<key>-list` / `<key>-save` / `<key>-delete`，已发布为 HTTP 接口 |
| 页面 | `/p/<key>-list`(列表，带查询框与分页) `/p/<key>-form`(登记表单) |

```bash
# 直接使用
curl -X POST http://127.0.0.1:8000/api/x/employee-save -H 'Content-Type: application/json' \
  -d '{"code":"E001","name":"张三","dept_id":1,"position":"后端工程师","operator":"admin"}'
curl -X POST http://127.0.0.1:8000/api/x/employee-list -H 'Content-Type: application/json' \
  -d '{"keyword":"张","limit":20,"offset":0}'
```

### 配套能力

**统一字典**（`/dict`）：枚举值集中维护（记录状态、性别、在职状态、资产类别、供应类别、客户类别、
合作伙伴等级、产品/物料分类、计量单位，共 11 个预置字典）。字段引用字典后，页面下拉与查询条件
自动取自字典项，**改字典不用改表结构、不用改存储过程**，只需重新生成页面：

```bash
# 例：给资产类别加一个值
curl -X POST http://127.0.0.1:8000/api/mdm/dict-items/ -H 'Content-Type: application/json' \
  -d '{"dictionary":1,"value":"无形资产","label":"无形资产"}'
cd backend && python manage.py init_master_data   # 重新生成页面，下拉立即多一项
```

字典项支持父子层级，可做多级分类。

**字段级变更审计**：所有主数据共用 `mdm_data_change_log` 表，生成的保存/删除存储过程写入
`谁(operator) 在什么时候 把哪条记录的哪个字段 从什么改成什么`；更新只记录真正变化的字段。

```bash
curl http://127.0.0.1:8000/api/mdm/entities/2/changes/?record_id=9
```

**层级树**：实体配置 `options.tree_parent`（部门已配 `parent_id`）后，
`GET /api/mdm/entities/{id}/tree/` 返回嵌套结构；部门列表页左侧以树形过滤，
人员/资产的「所属部门」字段在表单里是树形下拉（`el-tree-select`）。

**Excel 导入导出**：表头支持中文名或列名；导入按 **编码** 定位已有记录（有则更新、无则新增），
逐行调用保存存储过程并返回成功/失败明细。

```bash
curl -o tpl.xlsx "http://127.0.0.1:8000/api/mdm/entities/3/template/"        # 下载模板
curl -o out.xlsx "http://127.0.0.1:8000/api/mdm/entities/3/export/?keyword=S10"  # 导出
curl -X POST "http://127.0.0.1:8000/api/mdm/entities/3/import/" -F "file=@tpl.xlsx"  # 导入
```

### 字段可扩展

前端「企业主数据」页 → 选对象 → **字段** → 新增字段（类型支持文本/整数/金额/日期/布尔/枚举/JSON/关联主数据）→
**结构差异**（预览将要执行的 DDL）→ **同步表**（`ALTER TABLE ADD COLUMN`）→ **一条龙重建**
（重建 CRUD 存储过程 + 编排 + 页面）。全程零代码，已有数据不受影响。

规则：
- **只增不改不删**：已有列的类型不会被改写；删除字段定义不会自动 DROP COLUMN（会在「结构差异」里提示，手工确认后再删）
- 每次结构变更写入 `EntityDdlLog`，可在「变更记录」里追溯
- 重建存储过程时先 `DROP ROUTINE`，因此返回列变化（加字段）也能安全重建
- 字段默认值在**新增**时生效：`COALESCE(传入值, 默认值)`；**更新**时未传的字段保持原值
  （`COALESCE(传入值, 当前列值)`），只改一个字段不会把其它字段清空。
  代价是无法通过保存接口把字段改回 NULL

### 功能可扩展

- **加接口**：在画布里引用这些存储过程/编排，或给主数据对象再挂 `subflow` 组合多个对象的操作
- **加业务规则**：写自定义存储过程 + 编排（如「员工离职流程」：人员状态改离职 + 资产归还 + 待办）
- **加字段关联**：字段类型选「关联主数据」，页面表单自动变成下拉，列表显示关联对象的名称
- **加数据范围**：权限管理 → 数据范围 + SQL 节点 scope_key，实现「销售只能看自己的客户」

## 十三、示例模块：员工报销管理

一条命令搭出完整链路（建表 + 4 个存储过程 + 4 个编排 + 2 个页面）：

```bash
cd backend && python manage.py init_expense_demo
```

产出：

| 层 | 内容 |
| --- | --- |
| 表 | `public.expense_claim`（单号/申请人/部门/类别/金额/事由/状态/审批信息），含 5 条示例数据 |
| 存储过程 | `sp_expense_search`(查询) `sp_expense_save`(新增/更新) `sp_expense_set_status`(置状态) `sp_expense_summary`(汇总) |
| 编排 | `expense-list`、`expense-save`、`expense-summary`(service)，`expense-approve`(**flow**：金额 >5000 走人工待办，否则自动通过) |
| 页面 | `/p/expense-list` 列表、`/p/expense-form` 填单，侧边栏「员工报销管理」自动出现 |

手工验证：

```bash
# 查询
curl -X POST http://127.0.0.1:8000/api/x/expense-list -H 'Content-Type: application/json' -d '{"applicant":"张三"}'
# 新增（单号自动生成）
curl -X POST http://127.0.0.1:8000/api/x/expense-save -H 'Content-Type: application/json' \
  -d '{"applicant":"孙七","dept":"市场部","category":"餐饮","amount":6800,"reason":"客户招待"}'
# 审批：小额自动通过
curl -X POST http://127.0.0.1:8000/api/x/expense-approve -H 'Content-Type: application/json' -d '{"id":2,"operator":"admin"}'
# 审批：大额挂起 -> 返回 202 与待办 id -> 前端「人工任务」处理，或：
curl -X POST http://127.0.0.1:8000/api/x/expense-approve -H 'Content-Type: application/json' -d '{"id":16,"operator":"admin"}'
curl -X POST http://127.0.0.1:8000/api/human-tasks/1/complete/ -H 'Content-Type: application/json' \
  -d '{"action":"approve","result":{"comment":"同意报销"}}'
# 汇总（按状态+类别统计金额）
curl -X POST http://127.0.0.1:8000/api/x/expense-summary -H 'Content-Type: application/json' -d '{}'
```

照这个套路换自己的表与存储过程，就是一个新模块。

## 十四、当前边界

- 并行分支按"顺序执行各分支、汇聚节点由主流程执行"处理，未做真正并发与事务边界
- 异步 worker 为内置线程实现（无外部依赖）；规模更大时可替换为 Celery/RQ，只需替换 `run_worker` 的执行入口
- 页面渲染器目前支持列表（查询表单 + 表格）与表单（字段 + 提交），尚未支持看板与复杂控件
- 未做运行历史的清理策略与审计日志归档

## 十五、分支与 PR 流程

仓库：<https://github.com/yanyinghua/BaseMgt>

| 分支 | 用途 | 谁往里合 |
| --- | --- | --- |
| `main` | 稳定版，可运行、已验证 | 只从 `develop` 合入 |
| `develop` | 集成分支，日常开发往这里合 | 各 `feat/*` 特性分支 |
| `feat/<主题>` | 单个特性/修复 | 开发完成后 PR 到 `develop` |
| `fix/<主题>` | 紧急修复 | PR 到 `develop`（紧急时可直接到 `main`） |

日常流程：

```bash
git checkout develop && git pull
git checkout -b feat/xxx
# ... 改动 + 自测 ...
git add -A && git commit -m "feat: xxx"
git push -u origin feat/xxx
# 创建 PR：base=develop
```

自测通过后（`backend/scripts/` 下三个 selftest）再合入；`develop` 跑通一轮端到端验证后，
再开 PR 从 `develop` → `main`。

PR 创建方式（本机 `gh` 的 token 已失效，任选其一）：
- 网页：<https://github.com/yanyinghua/BaseMgt/compare/develop> 选 compare 分支后点 Create pull request
- 命令行：先 `gh auth refresh -h github.com`，再 `gh pr create --base develop --fill`

分支保护建议在 GitHub → Settings → Branches 里给 `main` 加上「需经 PR 合入」，
`develop` 可按需设置（当前凭据下无法用 API 代劳）。
