# AlphaRadar 架构主图

图中模块及连线来自本仓库实现，布局为本项目原创。动态图中的流动数据包与日志为流程示意，不是实时行情或生产遥测数据。

- `overview.gif`：GitHub README 首屏主图。
- `overview.png`：无动画的高清图。
- `index.html`：无需后端即可打开的独立动态页面；线上路径 `/architecture`。
- `build_config.py` / `config.json`：可编辑布局与生成的配置。

使用 [ythx-101/live-panel-skill](https://github.com/ythx-101/live-panel-skill) 的渲染引擎生成，未复刻其示例图。引擎及其内嵌 Lucide 代码的许可保留在本目录。

复现（先取得 live-panel-skill 源码，设置其目录为 `LIVE_PANEL_DIR`，Chrome 和 ffmpeg 需在 PATH）：

```bash
python3 docs/live-panel/build_config.py
python3 "$LIVE_PANEL_DIR/scripts/check_frames.py" --config docs/live-panel/config.json --out-dir /tmp/radar-frames --repeat
python3 "$LIVE_PANEL_DIR/scripts/render.py" --config docs/live-panel/config.json --out /tmp/radar-overview.mp4 --html-out docs/live-panel/index.html
ffmpeg -i /tmp/radar-overview.mp4 -vf 'fps=10,scale=1200:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer' -loop 0 docs/live-panel/overview.gif
ffmpeg -ss 4.5 -i /tmp/radar-overview.mp4 -frames:v 1 docs/live-panel/overview.png
```

可用 `--chrome /path/to/chrome` 指定浏览器。主图验证采样 124 个时点，并检查文字溢出、重叠与回放确定性。
