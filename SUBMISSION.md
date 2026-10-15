# AlphaRadar 提交说明

题目：可配置投资监控与风险雷达。此项目对应题目截图和同名候选人附件，不对应另外两份参考题。

## 交付入口

| 必交内容 | 入口或文件 |
| --- | --- |
| 可访问、可操作的 Web 产品 | https://radar.poiuyjie.online/ |
| 源代码仓库 | https://github.com/poiuyjie-dotcom/finance |
| 启动、产品设计、AI 角色、数据与边界说明 | `README.md` |
| 60–180 秒演示视频 | `docs/demo/alpharadar-demo-180s.mp4`，精确 180 秒，无配音，1920×1080 |
| AI 使用与验证记录 | `AI_USAGE_AND_VERIFICATION.md` |
| 测试说明 | `TEST_SPECIFICATION.md`，最新后端自动化共 17 项通过 |

视频在线播放：https://radar.poiuyjie.online/demo/alpharadar-demo-180s.mp4

## 建议体验顺序

监控总览 → 新建监控 → 输入客观关注点 → 生成并检查组合规则 → 确认启动 → 立即巡检 → 查看逐条件归因及原始证据 → 查看规则版本与巡检记录。

异常验证入口为「运行验证」。模拟会影响该部署的全部任务；建议在本地独立环境验证，完成后恢复正常数据流。演示视频中的异常注入均在独立演示数据库中完成。

## 源码与复现

项目包含 `backend/`、`frontend/`、启动脚本、测试、当前截图及架构图制作材料。`frontend/dist/` 是随包提供的生产构建产物，需保留，使用 `bash start.sh` 可直接启动，无需先安装 Node。

未配置接口密钥时支持显式标注的离线回退数据；接入真实数据时，按 `backend/.env.example` 配置自己的密钥。Jev 与 LLM 为可选增强，数值判定由确定性规则引擎执行。

提交包不包含 `.env`、API 密钥、本地数据库、虚拟环境、`node_modules`、Git 历史及录制临时文件。项目外的其他题目 Markdown 和题目截图属于题目材料，无需作为答案上传。
