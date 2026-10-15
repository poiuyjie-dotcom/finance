"""Generate AlphaRadar's original architecture layout for live-panel."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
elements = []
config = {
    "meta": {"title": "AlphaRadar · 投资监控与风险雷达", "lang": "zh"},
    "canvas": {"width": 1600, "height": 1060, "duration": 12, "fps": 15},
    "theme": {
        "preset": "light-pastel", "fontSize": 21, "lineHeight": 33,
        "radius": 6, "glow": False,
        "colors": {"bg": "#f7f9fa", "ink": "#243632", "dim": "#72817e",
                   "green": "#167b63", "greenfill": "#edf7f2", "blue": "#3a719b",
                   "bluefill": "#eef4fa", "amber": "#a87723", "amberfill": "#fff7e8",
                   "line": "#b9c9c3", "paper": "#ffffff"},
    },
    "clock": {"start": "09:30:00", "rate": 1},
    "machines": {
        "flow": {"type": "cycle", "period": 3, "values": [
            {"t": "检查规则", "m": "自然语言编译草稿，等待用户确认", "g": "示意"},
            {"t": "采集证据", "m": "按任务周期巡检，保留来源与业务时点", "g": "示意"},
            {"t": "执行判定", "m": "代码比较条件，冷却与去重抑制重复提醒", "g": "示意"},
            {"t": "异常降级", "m": "数据异常显式标记，恢复后重新评估", "g": "示意"},
        ], "log": {"who": "AlphaRadar", "c": "green"}},
    },
    "elements": elements,
    "credit": {"text": "图示来源：本项目代码 · 动画引擎：ythx-101 https://github.com/ythx-101/live-panel-skill", "y": 1034, "size": 14},
}


def text(x, y, value, size=19, color="dim", width=1510, bold=False):
    elements.append({"type": "text", "x": x, "y": y, "w": width,
                     "t": value, "size": size, "c": color, "b": bold})


def box(x, y, title, lines, color="green", fill="greenfill", height=160):
    elements.append({"type": "box", "x": x, "y": y, "w": 330, "h": height,
                     "color": color, "fill": fill, "pad": [22, 22],
                     "lines": [{"t": title, "b": 1, "size": 25, "c": color},
                               {"t": "", "h": .35},
                               *[{"t": line, "c": "ink", "size": 19} for line in lines]]})


def wire(points, color="green", period=2.4):
    elements.append({"type": "path", "points": points, "color": color,
                     "width": 2, "r": 8, "flow": {"period": period, "offsets": [0, .5], "color": color, "tail": 12}})


text(45, 58, "AlphaRadar", 44, "ink", bold=True)
text(45, 110, "把关注点变成持续运行的监控，让每一次判定都有证据。", 25, "green")
text(45, 170, "01 / 建立监控", 17, "dim")
for x, title, lines in [
    (45, "自然语言关注点", ["价格 · 事件 · 日历 · 热度", "客观条件，不生成买卖建议"]),
    (435, "规则编译与合规", ["Jev / LLM 可选增强", "不可用时走确定性解析器"]),
    (825, "用户检查与确认", ["修改阈值与 AND / OR 分支", "确认后创建版本化监控规则"]),
    (1215, "长期调度", ["交易日历 · 任务巡检周期", "单实例 APScheduler"]),
]:
    box(x, 205, title, lines)
for left in [375, 765, 1155]:
    wire([[left, 285], [left + 60, 285]])
text(45, 450, "02 / 执行、判定与追溯", 17, "dim")
for x, title, lines, color, fill in [
    (45, "扶摇 + iFinD", ["行情 / 估值 / 公告 / 日历", "双源核查 · 缓存与回退", "来源、时点、单位和口径"], "blue", "bluefill"),
    (435, "确定性规则引擎", ["逐条件实测值 vs 阈值", "布尔组合与数据健康检查", "AI 不承担数值触发判定"], "green", "greenfill"),
    (825, "状态机与执行日志", ["运行 / 触发 / 冷却 / 去重", "降级 / 暂停 / 熔断 / 恢复", "版本变化与回滚"], "amber", "amberfill"),
    (1215, "监控工作台", ["总览 → 详情 → 原始证据", "为什么触发 / 为什么未触发", "事实、推导、不确定性"], "green", "greenfill"),
]:
    box(x, 505, title, lines, color, fill, 185)
wire([[1380, 365], [1380, 405], [25, 405], [25, 480], [210, 480], [210, 505]], "blue", 3)
wire([[375, 595], [435, 595]], "blue")
wire([[765, 595], [825, 595]])
wire([[1155, 595], [1215, 595]])
text(45, 750, "数据过期 / 双源冲突 / 接口失败 → 显式降级与核查 → 数据恢复后重新评估", 23, "amber")
elements.append({"type": "log", "x": 45, "y": 810, "w": 1515, "rows": 3,
                 "padTop": 20, "padBottom": 25, "padLeft": 24,
                 "title": "流程回放 · 示意", "titleX": 24, "titleW": 230,
                 "cols": [{"key": "time", "x": 0}, {"key": "who", "x": 155},
                          {"key": "m", "x": 345}, {"key": "g", "x": 1370}]})
text(45, 996, "流程动画为示意，并非实时行情、在线状态或生产运行日志。", 17)
(ROOT / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
