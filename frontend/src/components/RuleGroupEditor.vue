<script setup>
import { Plus, Trash2 } from "lucide-vue-next";
defineProps({ group: Object });
const metrics = [
  {
    value: "last_price",
    name: "最新价",
    unit: "元",
    source: "FUYAO_QUOTE",
    category: "PRICE_VALUATION",
    caliber: "不复权行情快照",
  },
  {
    value: "pct_chg",
    name: "当日涨跌幅",
    unit: "%",
    source: "FUYAO_QUOTE",
    category: "PRICE_VALUATION",
    caliber: "日内涨跌幅",
  },
  {
    value: "turnover_rate_pct",
    name: "换手率",
    unit: "%",
    source: "FUYAO_QUOTE",
    category: "PRICE_VALUATION",
    caliber: "个股日频换手率",
  },
  {
    value: "pe_ttm",
    name: "市盈率 PE",
    unit: "倍",
    source: "FUYAO_VALUATION",
    category: "PRICE_VALUATION",
    caliber: "TTM 估值快照",
  },
  {
    value: "hot_rank",
    name: "热榜排名",
    unit: "名",
    source: "FUYAO_HOTLIST",
    category: "SENTIMENT_HEAT",
    caliber: "盘中热榜排名",
  },
  {
    value: "announcement_keywords",
    name: "公告关键词",
    unit: "篇",
    source: "IFIND_ANNOUNCEMENT",
    category: "EVENT_ANNOUNCEMENT",
    caliber: "近 7 天公告",
  },
  {
    value: "days_to_earnings",
    name: "距财报披露",
    unit: "个交易日",
    source: "IFIND_EVENT_CAL",
    category: "CALENDAR_WINDOW",
    caliber: "财报预计披露日",
  },
  {
    value: "futures_pct_chg",
    name: "期货涨跌幅",
    unit: "%",
    source: "IFIND_COMMODITY",
    category: "PRICE_VALUATION",
    caliber: "主力合约日频",
  },
];
const ops = [
  { value: "<", name: "低于" },
  { value: "<=", name: "不高于" },
  { value: ">", name: "高于" },
  { value: ">=", name: "不低于" },
  { value: "==", name: "等于" },
  { value: "CONTAINS_ANY", name: "包含任一关键词" },
  { value: "NOT_CONTAINS", name: "不包含" },
  { value: "IN_WINDOW", name: "窗口内" },
  { value: "OUTSIDE_WINDOW", name: "窗口外" },
];
function changeMetric(c) {
  const metric = metrics.find((m) => m.value === c.metric_field);
  c.unit = metric.unit;
  c.primary_source = metric.source;
  c.category = metric.category;
  c.statistical_caliber = metric.caliber;
  c.backup_source = null;
  c.operator = metric.value === "announcement_keywords" ? "CONTAINS_ANY" : "<";
  c.threshold_value = metric.value === "announcement_keywords" ? ["减持"] : 0;
}
function threshold(c, value) {
  c.threshold_value = ["CONTAINS_ANY", "NOT_CONTAINS"].includes(c.operator)
    ? value
        .split(/[,，]/)
        .map((s) => s.trim())
        .filter(Boolean)
    : value === ""
      ? ""
      : Number.isFinite(Number(value))
        ? Number(value)
        : value;
}
function add(group) {
  group.conditions.push({
    condition_id: `cond_${crypto.randomUUID().slice(0, 8)}`,
    label: "价格监控",
    target_code: "300750.SZ",
    target_name: "宁德时代",
    metric_field: "last_price",
    operator: "<",
    threshold_value: 200,
    unit: "元",
    category: "PRICE_VALUATION",
    primary_source: "FUYAO_QUOTE",
    backup_source: null,
    statistical_caliber: "不复权行情快照",
    staleness_tolerance_seconds: 900,
  });
}
</script>
<template>
  <div class="rule-group">
    <div class="group-logic">
      <span>满足方式</span>
      <div class="segmented">
        <button
          type="button"
          :class="{ active: group.logical_op === 'AND' }"
          @click="group.logical_op = 'AND'"
        >
          全部满足 AND</button
        ><button
          type="button"
          :class="{ active: group.logical_op === 'OR' }"
          @click="group.logical_op = 'OR'"
        >
          任一满足 OR
        </button>
      </div>
    </div>
    <div
      v-for="(c, index) in group.conditions"
      :key="c.condition_id"
      class="condition-edit"
    >
      <div class="condition-edit-heading">
        <span class="condition-id">条件 {{ index + 1 }}</span
        ><input v-model="c.label" aria-label="条件名称" /><button
          type="button"
          class="icon-button danger"
          title="删除条件"
          aria-label="删除条件"
          :disabled="group.conditions.length <= 1"
          @click="group.conditions.splice(index, 1)"
        >
          <Trash2 :size="16" />
        </button>
      </div>
      <div class="condition-fields">
        <label>标的名称<input v-model="c.target_name" /></label
        ><label>标的代码<input v-model="c.target_code" /></label
        ><label
          >监控指标<select v-model="c.metric_field" @change="changeMetric(c)">
            <option v-for="m in metrics" :key="m.value" :value="m.value">
              {{ m.name }}
            </option>
          </select></label
        ><label
          >比较关系<select v-model="c.operator">
            <option v-for="o in ops" :key="o.value" :value="o.value">
              {{ o.name }}
            </option>
          </select></label
        ><label
          >阈值 · {{ c.unit
          }}<input
            :value="
              Array.isArray(c.threshold_value)
                ? c.threshold_value.join('，')
                : c.threshold_value
            "
            @input="threshold(c, $event.target.value)"
        /></label>
      </div>
      <details class="condition-advanced">
        <summary>数据口径与时效</summary>
        <label>统计口径<input v-model="c.statistical_caliber" /></label
        ><label
          >过期容忍（秒）<input
            v-model.number="c.staleness_tolerance_seconds"
            type="number"
            min="0"
        /></label>
        <p>数据源：{{ c.primary_source }}</p>
      </details>
    </div>
    <RuleGroupEditor
      v-for="(child, index) in group.sub_groups || []"
      :key="child.group_id || index"
      :group="child"
    />
    <button type="button" class="text-button" @click="add(group)">
      <Plus :size="15" />添加条件
    </button>
  </div>
</template>
