"""Generate the technical deployment diagram from the project's implementation."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
elements = []
config = {
    "meta": {"title": "AlphaRadar · 前后端分离技术架构", "lang": "zh"},
    "canvas": {"width": 1600, "height": 1320, "duration": 12, "fps": 15},
    "theme": {
        "preset": "light-pastel", "fontSize": 20, "lineHeight": 32,
        "radius": 6, "glow": False,
        "colors": {"bg": "#f7f9fa", "ink": "#243632", "dim": "#72817e",
                   "green": "#167b63", "greenfill": "#edf7f2", "blue": "#3a719b",
                   "bluefill": "#eef4fa", "amber": "#a87723", "amberfill": "#fff7e8",
                   "line": "#b9c9c3", "paper": "#ffffff"},
    },
    "clock": {"start": "09:30:00", "rate": 1},
    "machines": {
        "request": {"type": "cycle", "period": 3, "values": [
            {"t": "规则编译", "m": "前端提交自然语言，后端校验并返回规则草稿", "g": "示意"},
            {"t": "用户确认", "m": "用户检查后保存任务与规则版本", "g": "示意"},
            {"t": "后台巡检", "m": "调度触发取数，确定性引擎判定并保存证据", "g": "示意"},
            {"t": "结果查询", "m": "前端通过 API 查询状态、执行日志与原始证据", "g": "示意"},
        ], "log": {"who": "调用链路", "c": "green"}},
    },
    "elements": elements,
    "credit": {"text": "依据本项目源码与部署配置绘制 · 动画引擎：ythx-101 https://github.com/ythx-101/live-panel-skill", "y": 1295, "size": 14},
}


def text(x, y, value, size=19, color="dim", bold=False):
    elements.append({"type": "text", "x": x, "y": y, "w": 1480,
                     "t": value, "size": size, "c": color, "b": bold})


def box(x, y, title, lines, color="green", fill="greenfill", height=180):
    elements.append({"type": "box", "x": x, "y": y, "w": 420, "h": height,
                     "color": color, "fill": fill, "pad": [20, 20],
                     "lines": [{"t": title, "b": 1, "size": 25, "c": color},
                               {"t": "", "h": .3},
                               *[{"t": line, "c": "ink", "size": 19} for line in lines]]})


def wire(points, color="green", period=2.8, dash=None):
    path = {"type": "path", "points": points, "color": color, "width": 2,
            "r": 8, "flow": {"period": period, "offsets": [0, .5], "color": color, "tail": 12}}
    if dash:
        path["dash"] = dash
    elements.append(path)


text(60, 60, "AlphaRadar · 前后端分离技术架构", 40, "ink", True)
text(60, 112, "独立前端与 API 后端，确定性判定与可追溯存储。", 25, "green")
text(60, 170, "01 / 页面与接口", 17)
box(60, 205, "Vue 3 + Vite 前端", ["Vue Router · 页面与交互", "组合规则编辑 / 状态 / 证据", "开发端口 5173"], "blue", "bluefill")
box(590, 205, "REST API /api/v1", ["JSON 请求与响应", "任务 / 编译 / 巡检 / 版本", "开发时由 Vite 代理 /api"])
box(1120, 205, "FastAPI 后端入口", ["路由与 Pydantic 校验", "业务处理与接口健康状态", "开发端口 8000"])
wire([[480, 270], [590, 270]], "blue")
wire([[590, 330], [480, 330]], "blue", 3.4)
wire([[1010, 270], [1120, 270]])
wire([[1120, 330], [1010, 330]], "green", 3.4)

text(60, 440, "02 / 后端服务与可选模型", 17)
box(60, 480, "APScheduler 调度", ["按任务周期发起后台巡检", "结合交易日历与市场时段", "单实例进程内运行"], "amber", "amberfill")
box(590, 480, "任务管理与规则编译", ["自然语言 → 规则草稿", "用户确认 / 版本 / 恢复", "内置解析器作为回退通道"])
box(1120, 480, "Jev / LLM · 可选增强", ["Jev：合规意图 / 公告情绪", "LLM：自然语言规则编译", "不承担数值触发判定"], "amber", "amberfill")
wire([[1330, 385], [1330, 410], [800, 410], [800, 480]])
wire([[1010, 545], [1120, 545]], "amber", 4, "6 5")
wire([[1120, 605], [1010, 605]], "amber", 4, "6 5")

text(60, 730, "03 / 取数、判定与持久化", 17)
box(60, 770, "数据适配与外部接口", ["扶摇 REST / iFinD MCP", "取数 / 双源核查 / 缓存回退", "来源、业务时点、单位与口径"], "blue", "bluefill")
box(590, 770, "确定性引擎与状态机", ["条件比较 / AND / OR", "冷却 / 去重 / 降级 / 恢复", "原始证据绑定到执行日志"])
box(1120, 770, "SQLAlchemy / SQLite", ["MonitorTask · 监控任务", "TaskRuleVersion · 规则版本", "TaskExecutionLog · 巡检日志"], "blue", "bluefill")
wire([[270, 660], [270, 700], [800, 700], [800, 770]], "amber", 3.8)
wire([[590, 595], [530, 595], [530, 745], [270, 745], [270, 770]], "blue", 3.2)
wire([[800, 660], [800, 770]])
wire([[480, 850], [590, 850]], "blue")
wire([[1010, 850], [1120, 850]], "blue")
wire([[1330, 770], [1330, 720], [1070, 720], [1070, 450], [910, 450], [910, 480]], "blue", 4)

text(60, 1000, "生产同域：Cloudflare → Nginx → FastAPI，提供 API 与 frontend/dist 静态页面。", 22, "green")
text(60, 1040, "源码与职责分离；也可独立部署前端静态站点，并将 /api 反向代理到后端。", 19)
elements.append({"type": "log", "x": 60, "y": 1090, "w": 1480, "rows": 3,
                 "padTop": 20, "padBottom": 20, "padLeft": 22,
                 "title": "请求与调度回放 · 示意", "titleX": 22, "titleW": 320,
                 "cols": [{"key": "time", "x": 0}, {"key": "who", "x": 160},
                          {"key": "m", "x": 340}, {"key": "g", "x": 1380}]})
text(60, 1250, "流动数据包与日志仅示意调用关系，不代表真实请求、在线状态或性能指标。", 17)
(ROOT / "technical-config.json").write_text(
    json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
