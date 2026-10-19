# PR 合并顺序与冲突处理

针对当前待合并的特性分支，说明**先合谁、为什么、冲突在哪、怎么解、合完怎么验证**。

> 状态（2026-10-19）：
> ① `docs/pr-merge-order`、**② `feat/purchase-inbound`**、**③ `feat/dashboard-report` 均已合入 `develop`**；
> ④ `develop → main` 发版已执行。下文保留完整流程，供后续多分支协作参考。
流程背景见 README「分支与 PR 流程」（`main` 稳定 / `develop` 集成 / `feat/*` 特性）。

## 1. 当前分支与 PR

| 顺序 | 分支 | HEAD | 内容 | 依赖 |
| --- | --- | --- | --- | --- |
| ① | `docs/pr-merge-order` | 本文档 | 合并顺序与冲突说明 | 无 | ✅ 已合 |
| ② | `feat/purchase-inbound` | `d6a4fe1` | 采购入库示例（多主数据联动、事务边界、审计）+ Excel 导入的枚举校验与关联校验 | 无 | ✅ 已合 |
| ③ | `feat/dashboard-report` | `d5e2864` | 页面渲染器新增看板(dashboard)与报表(report) + 报表导出 + 3 个示例页面 | 依赖 ②（见下） | ✅ 已合 |
| ④ | `develop` → `main` | — | 发版 | ②③ 合完且验证通过 | ✅ 已发 |

### 为什么 ② 必须在 ③ 之前

`feat/dashboard-report` 生成的 `/p/inventory-report`（库存台账报表）绑定的取数编排是
`inventory-list`，而该编排由 `feat/purchase-inbound` 的 `init_purchase_demo` 创建。

- 正序（②→③）：报表直接有数据
- 反序（③→②）：不会报错——`init_dashboard_demo` 检测到编排缺失会打印
  `跳过 inventory-report：缺少已发布编排 inventory-list` 并跳过；补跑 `init_purchase_demo`
  后再跑一次 `init_dashboard_demo` 即可补上

所以反序不会弄坏仓库，但会让报表暂时缺数据，**建议仍按 ②→③**。

## 2. 预期冲突：只有 `README.md`

两个特性分支的改动范围（已核对）：

```
feat/purchase-inbound:
  README.md                                                  （改）
  backend/apps/mdm/presets.py                                （改）
  backend/apps/mdm/views.py                                  （改）
  backend/apps/orchestration/management/commands/init_purchase_demo.py   （增）
  backend/scripts/mdm_import_selftest.py                     （增）

feat/dashboard-report:
  README.md                                                  （改）
  backend/apps/orchestration/management/commands/init_dashboard_demo.py  （增）
  backend/apps/page/models.py、views.py                      （改）
  frontend/package.json、package-lock.json                   （改，新增 echarts）
  frontend/src/api/index.js、components/ChartView.vue、views/PageList.vue、views/PageRuntime.vue
```

**唯一重叠文件是 `README.md`**，且冲突集中在「章节编号」：

- ② 把「十三、示例模块：员工报销管理」改成「十三、示例模块」并新增「采购入库」子节，
  在「十一、自测脚本」里加了一行 `mdm_import_selftest.py`
- ③ 新增「十四、看板与报表」，并把「十四、当前边界」→「十五」、「十五、分支与 PR 流程」→「十六」

## 3. 冲突怎么解

### 网页（推荐）

1. 打开 ③ 的 PR 页面 → 出现 `This branch has conflicts` → **Resolve conflicts**
2. 找到 `<<<<<<< feat/dashboard-report` / `=======` / `>>>>>>> develop` 标记
3. **两边内容都保留**（② 的采购入库子节 + ③ 的看板报表章节），只把章节编号重排成最终顺序
4. Mark as resolved → Commit merge → Merge pull request

### 命令行

```bash
git checkout develop && git pull
git checkout feat/dashboard-report && git pull
git merge develop                  # 把已合入 ② 的 develop 合进来
# 编辑 README.md：删除冲突标记，保留双方章节，重排编号
git add README.md && git commit    # （不用 -m 也行，merge 提交信息会自动生成）
git push
```

### 最终章节顺序（重排目标）

```
…
十一、自测脚本
十二、企业主数据（MDM）
十三、示例模块
    ├─ 员工报销管理
    └─ 采购入库（多主数据联动）      ← 来自 ②
十四、看板与报表                    ← 来自 ③
十五、当前边界
十六、分支与 PR 流程
```

## 4. 合并后验证（在 `develop` 上）—— 2026-10-19 已执行，结果：

```
迁移      page.0002（page_type 新增 report）已应用；check 无问题
示例数据  seed_demo / init_master_data(12 字典) / init_expense_demo /
          init_purchase_demo / init_dashboard_demo 全部成功
自测      engine ✅  iam ✅  async ✅  mdm_import ✅
前端      vite build 通过
冒烟      入库过账 ok；看板取数正常；库存/报销报表导出正常
```

```bash
cd backend
python manage.py migrate

# 建全部示例数据（幂等，可重复执行）
python manage.py seed_demo
python manage.py init_master_data
python manage.py init_expense_demo
python manage.py init_purchase_demo      # ② 提供：仓库/库存/入库单
python manage.py init_dashboard_demo     # ③ 提供：看板与报表

# 自测（四个都应输出 ✅）
for s in engine iam async mdm_import; do
  python manage.py shell -c "exec(open('scripts/${s}_selftest.py').read())"
done

cd ../frontend && npm install && npx vite build
cd .. && scripts/dev.sh all              # 后端 8000 + worker + 前端 5173
```

冒烟检查：

```bash
# 入库过账（②）
curl -X POST http://127.0.0.1:8000/api/x/purchase-inbound -H 'Content-Type: application/json' \
  -d '{"supplier_id":2,"material_id":1,"warehouse_id":1,"qty":100,"price":5.2,"operator":"admin"}'
# 报表导出（③）
curl -o rep.xlsx "http://127.0.0.1:8000/api/pages/<report-page-id>/export/"
# 页面
#   /p/mdm-overview   /p/inventory-report   /p/expense-report
```

## 5. 发版（④）

`develop` 验证通过后开 `develop → main` 的 PR（本机 `gh` 不可用时，用本地快进合并 + SSH 推送，
不要 force push）：

🔗 https://github.com/yanyinghua/BaseMgt/compare/main...develop

## 6. 操作注意事项（都是踩过的坑）

- **不要用 `pkill -f <关键字>` 停服务**：它会匹配到执行命令的 shell 自身，曾导致会话被杀、
  worktree 丢失、git 仓库损坏。改用按端口 kill：
  ```bash
  (lsof -ti:8000 2>/dev/null | xargs -r kill)   # 后端
  (lsof -ti:5173 2>/dev/null | xargs -r kill)   # 前端
  ```
- **`gh` 的 token 已失效**（`gh auth status` 报 invalid）：`gh pr create` 用不了，
  PR 走网页创建；git 推送改走 SSH：`git remote set-url origin git@github.com:yanyinghua/BaseMgt.git`
- **未推送的改动在会话结束可能丢失**：及时 commit + push，或先备份到
  `/home/yanyinghua/BaseMgt-backup-2026-10-19/`
- **数据库内容不在 git 里**：主数据对象、编排、页面这些实例都在 PostgreSQL 中。
  换环境时用上面的 `init_*` 命令重建，或恢复备份里的 `basemgt-db.dump`
