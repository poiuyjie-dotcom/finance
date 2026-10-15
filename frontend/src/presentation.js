const statuses = {
  ACTIVE: { cls: "badge-green", txt: "监控中" },
  TRIGGERED: { cls: "badge-red", txt: "已触发" },
  COOLDOWN: { cls: "badge-blue", txt: "冷却中" },
  DEGRADED: { cls: "badge-amber", txt: "数据降级" },
  PAUSED: { cls: "badge-gray", txt: "已暂停" },
  ERROR_HALT: { cls: "badge-red", txt: "已熔断" },
};
export const statusInfo = (status) =>
  statuses[status] || { cls: "badge-gray", txt: status };
export const outcomes = {
  TRIGGERED_ALERT: "已触发提醒",
  NOT_TRIGGERED_NORMAL: "条件未满足",
  SUPPRESSED_BY_DEDUP: "同一事件已提醒",
  SUPPRESSED_BY_COOLDOWN: "冷却静默中",
  DEGRADED_STALE_DATA: "数据已过期",
  DEGRADED_CONFLICT_HOLD: "数据冲突 · 暂停判定",
  DEGRADED_API_FALLBACK: "降级数据 · 仅供参考",
  RECOVERY: "数据已恢复",
  SKIPPED_MARKET_CLOSED: "休市静默",
};
export function formatTime(value, utc = false) {
  if (!value) return "尚未巡检";
  const normalized =
    utc && !/[Z+]|-\d\d:\d\d$/.test(value.slice(10)) ? value + "Z" : value;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleString("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
}
