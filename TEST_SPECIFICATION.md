# 测试说明

## 1. 测试体系总览

| 层级 | 工具 | 位置 | 覆盖 |
| :--- | :--- | :--- | :--- |
| 自动化测试 | pytest + FastAPI TestClient + pytest-asyncio | `backend/tests/`（11 用例） | 主链路、状态机抑制、异常降级、合规边界 |
| 可视化故障注入 | 前端「异常模拟控制台」+ `/api/v1/simulator/*` | Web 工作台 | 数据过期/双源冲突/接口超时的一键演示 |
| 双源交叉验证 | 真实接口实测 | 开发期验证 | 扶摇 vs iFinD 同标的价格一致性 |

运行方式：

```bash
cd backend
pytest -v tests/
```

测试环境自动隔离：清空密钥环境变量（全部走显式标注的高仿真回退数据）、独立临时 SQLite、禁用调度器——**无网络、无密钥也可完整回归**。

## 2. 核心用例矩阵

| 用例 | 分类 | 场景 | 预期 | 结果 |
| :--- | :--- | :--- | :--- | :--- |
| TC-01 | 主链路 | 自然语言转复合规则树 | OR(公告, AND(价格, 换手率)) 结构、代码/单位/口径/主源字段完整 | PASS |
| TC-02 | 主链路 | 评估 + Why/Why-Not 归因 | 逐条件明细含实测值/阈值/理由/溯源（源名、接口、字段、双时点、单位、口径）+ 三段式解释 | PASS |
| TC-03 | 主链路 | 修改阈值 → v2 Diff → 回滚 v1 | 字段级 `threshold_value 290→295`；版本钩子清空冷却与去重；回滚恢复原值（v3） | PASS |
| TC-04 | 状态抑制 | 触发 → 冷却 → 去重 | ①`TRIGGERED_ALERT` 入冷却 ②`SUPPRESSED_BY_COOLDOWN`（剩余>3500s）③清冷却后同指纹 `SUPPRESSED_BY_DEDUP` | PASS |
| TC-05 | 异常降级 | 数据过期（-45min） | `DEGRADED_STALE_DATA`，`is_stale=true`、`staleness_seconds>900`，不正式触发 | PASS |
| TC-06 | 异常降级 | 双源价格冲突（+1.36%） | `DEGRADED_CONFLICT_HOLD`，`is_met=None`，`conflict_with` 完整记录双源值与偏差 | PASS |
| TC-07 | 异常降级+恢复 | 接口超时 → 恢复 | 超时：`DEGRADED_API_FALLBACK` 且**禁止** `NOT_TRIGGERED_NORMAL`；恢复：`TRIGGERED_ALERT` + `[RECOVERY]` 日志 | PASS |
| TC-08 | 合规边界 | 纯荐股/预测/稳赚诉求 | 前置拦截，拒绝创建并给出合规引导话术 | PASS |
| TC-09 | 合规边界 | 混合意图（含"满仓抄底"） | 剥离主观词保留 `002594.SZ last_price < 240`，客观规则可创建 | PASS |
| TC-10 | 合规边界 | 后置输出清洗 | 「建议买入/必涨/稳赚/满仓」等词被替换，不外泄 | PASS |
| TC-11 | 合规边界 | `/simulator/compliance-test` | 返回拦截结果 + 审计日志 | PASS |

## 3. 极端与合规边界场景（前端 Fault Console 手动演示路径）

1. **数据过期**：在「运行验证」选择「数据过期」并启用模拟，再进入股票任务立即巡检。任务转 `DEGRADED`，证据显示 `data_timestamp` 回拨 45 分钟、`staleness_seconds≈2700 > 900`，本次不生成正式提醒。
2. **双源冲突**：在「运行验证」选择「双源价格冲突」并启用模拟。巡检后出现 `DEGRADED_CONFLICT_HOLD`，任务详情的异常处理区并列展示双源数值与偏差，条件卡标记数据待核查。
3. **接口超时与恢复**：选择「上游接口超时」并启用模拟，巡检出现缓存/离线回退。验证后点「恢复正常数据流」；上游正常后再次巡检，检查恢复说明与状态。
4. **合规反例**：在「运行验证」检查"推荐几只明天必涨的牛股"，应出现拦截结果；在「新建监控」输入"当比亚迪跌破240元时提醒我满仓抄底"，检查剥离提示及客观规则草稿。
5. **休市静默**：交易日历校验非交易日时巡检记录 `SKIPPED_MARKET_CLOSED`，解释面板说明价格指标采用收盘快照口径。

## 4. 关键数字可追溯性验证

每个巡检日志的每个实测数字点击「溯源」标签展开卡片，包含：数据源名称、接口/MCP Tool 名、原始 JSON 字段路径（如 `item[0].last_price`）、原始值、单位、统计口径、数据业务时点、系统拉取时点、延迟秒数与冲突对照——满足赛题"核心结论必须能回到原始字段或原文"的要求。自动化层面由 TC-02 断言以上字段非空。

## 5. 已知测试局限

- 测试环境不依赖外网：真实数据源行为（限流、波动、公告命中）在开发期以真实密钥实测验证并记录于 `AI_USAGE_AND_VERIFICATION.md`，不纳入 CI 回归。
- 双源冲突/数据过期在测试中以受控注入（构造 `DataFetchResult`）复现，保证确定性；前端 Fault Console 提供同样的注入路径供评委现场验证。

## 6. 2026-10-15 页面改版验收

新增 `backend/tests/test_model_health.py`：覆盖模型未配置、已配置待调用、成功、请求失败、结构校验失败、配置变化重置与错误脱敏。全套后端共 17 项。

架构动画使用 live-panel-skill，124 个采样检查无问题，4 个重复帧一致；动画为流程示意，不代表生产实时遥测。

后端：`backend/.venv/bin/python -m pytest -q backend/tests`，11 项通过。

前端：`cd frontend && npm run build`，生产构建通过。

浏览器验收脚本：`frontend/scripts/ui-smoke.mjs`（需要可导入的 Playwright 和 Chromium，默认访问本地 8011 端口）。

```bash
cd frontend
# 已安装 playwright 时直接运行；也可用 PLAYWRIGHT_MODULE 指定现有模块的绝对路径
node scripts/ui-smoke.mjs
```

覆盖任务搜索、空结果恢复、三条件嵌套规则编辑、创建后跳转、立即巡检、证据侧栏、编辑生成 v2、回滚生成 v3、删除 204 响应处理、移动端设置、合规拦截，以及 1440px / 390px 下横向溢出和浏览器运行时异常。脚本只删除自己创建的临时任务；异常模拟未在生产站点启用。

默认截图目录 `/tmp/alpharadar-ui`。可用 `BASE_URL` 和 `SCREENSHOT_DIR` 更改站点和截图输出目录。脚本会创建并修改临时任务，验收生产环境时应明确这一点。
