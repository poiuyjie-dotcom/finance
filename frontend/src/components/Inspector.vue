<script setup>
import { computed, ref, onMounted, onUnmounted } from "vue";
import {
  Check,
  Minus,
  TriangleAlert,
  ArrowUpRight,
  X,
  FileSearch,
  GitBranch,
} from "lucide-vue-next";
import { outcomes, formatTime } from "../presentation";
const props = defineProps({ selectedTask: Object });
const citation = ref(null);
const latest = computed(() => props.selectedTask?.recent_logs?.[0]);
const details = computed(() => latest.value?.condition_details || []);
const met = computed(
  () => details.value.filter((d) => d.is_met === true).length,
);
const problem = (d) =>
  d.is_met == null ||
  d.citation.is_stale ||
  (d.citation.conflict_with && !d.citation.conflict_with.resolved_by) ||
  /缓存回退|离线/.test(d.citation.source_name);
const problems = computed(() => details.value.filter(problem).length);
const verdictTitle = computed(() => {
  if (
    latest.value?.degradation_flag &&
    latest.value?.outcome_type === "NOT_TRIGGERED_NORMAL"
  ) {
    return "数据不完整 · 判定受限";
  }
  return outcomes[latest.value?.outcome_type] || latest.value?.outcome_type;
});
const tone = computed(() =>
  latest.value?.degradation_flag
    ? "amber"
    : latest.value?.outcome_type === "TRIGGERED_ALERT"
      ? "red"
      : "green",
);
function close(e) {
  if (e.key === "Escape") citation.value = null;
}
onMounted(() => window.addEventListener("keydown", close));
onUnmounted(() => window.removeEventListener("keydown", close));
</script>
<template>
  <section v-if="!latest" class="empty-state">
    <FileSearch :size="32" />
    <h3>等待首次巡检</h3>
    <p>尚无判定结果</p>
  </section>
  <template v-else>
    <div
      v-if="latest.rule_version !== selectedTask.task.current_version"
      class="banner banner-info"
    >
      规则已更新至 v{{ selectedTask.task.current_version }}；以下是 v{{
        latest.rule_version
      }}
      的巡检记录，等待按新规则重新巡检。
    </div>
    <section class="verdict" :class="'verdict-' + tone">
      <div class="verdict-icon">
        <component
          :is="
            tone === 'amber'
              ? TriangleAlert
              : tone === 'red'
                ? Check
                : GitBranch
          "
          :size="25"
        />
      </div>
      <div class="verdict-copy">
        <div class="eyebrow">
          最近一次判定 · {{ formatTime(latest.executed_at) }} · 规则 v{{
            latest.rule_version
          }}
        </div>
        <h2>{{ verdictTitle }}</h2>
        <p>{{ latest.headline }}</p>
      </div>
      <div class="verdict-count">
        <strong
          >{{ met }}<span>/{{ details.length }}</span></strong
        ><small>条件已满足</small>
      </div>
    </section>
    <div class="section-heading evidence-heading">
      <h2>
        条件与证据 <span class="count">{{ details.length }}</span>
      </h2>
      <span :class="problems ? 'text-amber' : 'muted'">{{
        problems ? `${problems} 个条件存在数据问题` : "按本次巡检规则逐项比较"
      }}</span>
    </div>
    <div class="evidence-grid">
      <article
        v-for="d in details"
        :key="d.condition_id"
        class="evidence-item"
        :class="{ 'evidence-problem': problem(d) }"
      >
        <div class="evidence-top">
          <span class="condition-id">{{ d.condition_id }}</span
          ><span
            class="condition-result"
            :class="
              problem(d) ? 'text-amber' : d.is_met ? 'text-green' : 'muted'
            "
            ><component
              :is="problem(d) ? TriangleAlert : d.is_met ? Check : Minus"
              :size="14"
            />{{
              problem(d) ? "数据待核查" : d.is_met ? "已满足" : "未满足"
            }}</span
          >
        </div>
        <h3>{{ d.label }}</h3>
        <div class="value-comparison">
          <div>
            <span>当前实测</span><strong>{{ d.actual_value_display }}</strong>
          </div>
          <div>
            <span>触发条件</span><b>{{ d.threshold_display }}</b>
          </div>
        </div>
        <div
          v-if="d.gap_pct != null && !d.is_met && !problem(d)"
          class="gap-indicator"
        >
          <div>
            <span
              :style="{
                width:
                  Math.max(4, 100 - Math.min(100, Math.abs(d.gap_pct))) + '%',
              }"
            ></span>
          </div>
          <small>距阈值 {{ Math.abs(d.gap_pct) }}%</small>
        </div>
        <details class="condition-explanation">
          <summary>判定依据</summary>
          <p>{{ d.reason_snippet }}</p>
          <p v-if="d.citation.conflict_with">
            对照源 {{ d.citation.conflict_with.source }}：{{
              d.citation.conflict_with.value
            }}
            · 偏差 {{ d.citation.conflict_with.diff_pct }}%
          </p>
        </details>
        <button class="evidence-source" @click="citation = d.citation">
          <FileSearch :size="14" /><span>{{ d.citation.source_name }}</span
          ><ArrowUpRight :size="15" />
        </button>
      </article>
    </div>
    <section class="explanation-section">
      <div class="section-heading"><h2>结论依据</h2></div>
      <details class="explanation-row">
        <summary>
          <span class="explanation-number">01</span>客观事实<span class="muted"
            >{{ latest.explanation.facts_list.length }} 条证据</span
          >
        </summary>
        <ul>
          <li v-for="(f, i) in latest.explanation.facts_list" :key="i">
            {{ f }}
          </li>
        </ul>
      </details>
      <details class="explanation-row">
        <summary>
          <span class="explanation-number">02</span>规则推导<span class="muted"
            >确定性判定</span
          >
        </summary>
        <ul>
          <li v-for="(f, i) in latest.explanation.inference_list" :key="i">
            {{ f }}
          </li>
        </ul>
      </details>
      <details class="explanation-row" :open="latest.degradation_flag">
        <summary>
          <span class="explanation-number">03</span>不确定性与数据边界<span
            class="badge"
            :class="latest.degradation_flag ? 'badge-amber' : 'badge-gray'"
            >{{ latest.degradation_flag ? "存在降级" : "数据说明" }}</span
          >
        </summary>
        <p>{{ latest.explanation.uncertainty_and_degradation_note }}</p>
      </details>
    </section>
  </template>
  <Teleport to="body"
    ><div v-if="citation" class="cite-pop" @click.self="citation = null">
      <section
        class="cite-card evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="原始证据"
      >
        <div class="section-heading">
          <div>
            <div class="eyebrow">SOURCE EVIDENCE</div>
            <h2>原始证据</h2>
          </div>
          <button
            class="icon-button"
            title="关闭证据"
            aria-label="关闭证据"
            autofocus
            @click="citation = null"
          >
            <X :size="20" />
          </button>
        </div>
        <span
          class="badge"
          :class="citation.is_stale ? 'badge-amber' : 'badge-green'"
          >{{ citation.is_stale ? "数据过期" : "来源记录" }}</span
        >
        <dl class="kv">
          <dt>数据源</dt>
          <dd>{{ citation.source_name }}</dd>
          <dt>接口 / 工具</dt>
          <dd>{{ citation.endpoint_or_tool }}</dd>
          <dt>原始字段</dt>
          <dd class="mono">{{ citation.raw_field_name }}</dd>
          <dt>原始值</dt>
          <dd class="raw-value">
            {{ JSON.stringify(citation.raw_value) }} {{ citation.unit }}
          </dd>
          <dt>统计口径</dt>
          <dd>{{ citation.statistical_caliber }}</dd>
          <dt>业务时点</dt>
          <dd>{{ citation.data_timestamp }}</dd>
          <dt>拉取时点</dt>
          <dd>{{ citation.fetch_timestamp }}</dd>
          <dt>数据延迟</dt>
          <dd>{{ citation.staleness_seconds }} 秒</dd>
        </dl>
        <details class="raw-details">
          <summary>完整原始记录</summary>
          <pre class="raw-box">{{ JSON.stringify(citation, null, 2) }}</pre>
        </details>
      </section>
    </div></Teleport
  >
</template>
