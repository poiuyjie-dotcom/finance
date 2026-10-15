<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'

const props = defineProps({ selectedTask: Object })
const emit = defineEmits(['changed', 'refreshDetail'])

const citation = ref(null)   // 溯源弹层
const expandedId = ref(null) // 展开长解释的条件
const manualValue = ref('')  // 人工确认值输入
const resolving = ref(false)

const OUTCOME_CN = {
  TRIGGERED_ALERT: { cls: 'badge-red', txt: '已触发提醒' },
  NOT_TRIGGERED_NORMAL: { cls: 'badge-green', txt: '正常·未触发' },
  SUPPRESSED_BY_DEDUP: { cls: 'badge-violet', txt: '去重拦截' },
  SUPPRESSED_BY_COOLDOWN: { cls: 'badge-blue', txt: '冷却拦截' },
  DEGRADED_STALE_DATA: { cls: 'badge-amber', txt: '数据过期降级' },
  DEGRADED_CONFLICT_HOLD: { cls: 'badge-amber', txt: '双源冲突挂起' },
  DEGRADED_API_FALLBACK: { cls: 'badge-amber', txt: '接口异常降级' },
  RECOVERY: { cls: 'badge-green', txt: '已恢复' },
  SKIPPED_MARKET_CLOSED: { cls: 'badge-gray', txt: '休市静默' },
}

const latest = computed(() => props.selectedTask?.recent_logs?.[0] || null)
const logs = computed(() => props.selectedTask?.recent_logs || [])

const mark = (met) => met === true ? '✅' : met === false ? '❌' : '⚠️'

// 「有问题」= 无法判定 / 数据过期 / 双源冲突 / 降级数据源 —— 与业务上的未满足(❌)区分开
function isProblem(d) {
  const c = d.citation
  return d.is_met === null || c.is_stale || c.conflict_with
    || (c.source_name || '').includes('缓存回退') || (c.source_name || '').includes('离线')
}
const problemCount = computed(() => (latest.value?.condition_details || []).filter(isProblem).length)

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

// ---- 数据异常处理卡片 ----
const conflictConds = computed(() => (latest.value?.condition_details || [])
  .filter(d => d.citation.conflict_with && !d.citation.conflict_with.resolved_by))
const taskHalted = computed(() => props.selectedTask?.task?.status === 'ERROR_HALT')
const showIncident = computed(() => conflictConds.value.length > 0 || taskHalted.value)
const resolution = computed(() => props.selectedTask?.task?.conflict_resolution || null)

async function resolve(mode, conditionId = null, value = null) {
  if (!props.selectedTask) return
  resolving.value = true
  try {
    await api.resolveConflict(props.selectedTask.task.id,
      { mode, condition_id: conditionId, value })
    emit('changed'); emit('refreshDetail', props.selectedTask.task.id)
  } finally { resolving.value = false }
}

async function runNow() {
  if (!props.selectedTask) return
  await api.evaluateNow(props.selectedTask.task.id)
  emit('changed'); emit('refreshDetail', props.selectedTask.task.id)
}
</script>

<template>
  <div class="panel">
    <div class="panel-title">
      为什么触发 / 未触发 · 逐条件归因
      <span class="sub">v{{ selectedTask?.task?.current_version }} · 最近 {{ logs.length }} 次巡检</span>
      <button class="mini" style="margin-left:auto" @click="runNow" v-if="selectedTask">立即巡检</button>
    </div>

    <div v-if="!latest" style="color:var(--dim); font-size:12px; padding:26px 0; text-align:center">
      <span v-if="selectedTask" class="spin"></span>
      {{ selectedTask ? ' 首次巡检进行中…' : '加载任务详情…' }}
    </div>

    <template v-else>
      <!-- 顶部结论横幅 -->
      <div class="banner" :class="latest.outcome_type === 'TRIGGERED_ALERT' ? 'banner-bad' : latest.outcome_type === 'NOT_TRIGGERED_NORMAL' ? 'banner-good' : 'banner-warn'">
        <span class="badge" :class="OUTCOME_CN[latest.outcome_type]?.cls" style="margin-right:8px">
          {{ OUTCOME_CN[latest.outcome_type]?.txt || latest.outcome_type }}
        </span>
        {{ latest.headline }}
        <div style="font-size:10.5px; color:var(--dim); margin-top:4px">
          巡检时点 {{ (latest.executed_at || '').replace('T', ' ').slice(0, 19) }} · 规则 v{{ latest.rule_version }}
          · 状态流转 {{ latest.task_state_before }} → {{ latest.task_state_after }}
          <template v-if="latest.dedup_fingerprint"> · 去重指纹 <span class="mono">{{ latest.dedup_fingerprint }}</span></template>
          <template v-if="latest.cooldown_remaining_seconds > 0"> · 冷却剩余 {{ Math.floor(latest.cooldown_remaining_seconds / 60) }} 分 {{ latest.cooldown_remaining_seconds % 60 }} 秒</template>
        </div>
      </div>

      <!-- 双源冲突对照 -->
      <div v-for="d in latest.condition_details" :key="d.condition_id">
        <div v-if="d.citation.conflict_with" class="banner banner-warn" style="margin-bottom:8px">
          ⚖️ <b>{{ d.condition_id }} 多源冲突</b>：扶摇 {{ d.citation.raw_value }} vs {{ d.citation.conflict_with.source }}
          {{ d.citation.conflict_with.value }}（偏差 {{ d.citation.conflict_with.diff_pct }}%）——系统挂起自动判定，请核查数据源
        </div>
      </div>

      <!-- 数据异常处理卡片：供用户确认（选信任源 / 填确认值 / 撤销） -->
      <div v-if="showIncident" class="incident-card">
        <div class="incident-title">⚠️ 数据异常 · 待你确认
          <span style="font-weight:400; font-size:11px; color:var(--dim)">系统默认挂起不猜，由你裁决后立即按裁决重评估</span>
        </div>

        <!-- 当前裁决状态 -->
        <div v-if="resolution" class="incident-cur">
          当前裁决：<b>{{ {TRUST_PRIMARY: '以主源（扶摇）为准', TRUST_BACKUP: '以备源（iFinD）为准',
            MANUAL: `手工确认值 ${resolution.value}`}[resolution.mode] || resolution.mode }}</b>
          （{{ (resolution.set_at || '').replace('T', ' ').slice(5, 16) }} 设置）
          <button class="mini danger" :disabled="resolving" @click="resolve('CLEAR')">撤销裁决</button>
        </div>

        <!-- 双源冲突：选源 / 填值 -->
        <div v-for="d in conflictConds" :key="'ic' + d.condition_id" class="incident-body">
          <div style="margin-bottom:6px">
            <b>{{ d.condition_id }} · {{ d.label }}</b>：
            扶摇 <b>{{ d.citation.raw_value }}</b> vs {{ d.citation.conflict_with.source }}
            <b>{{ d.citation.conflict_with.value }}</b>（偏差 {{ d.citation.conflict_with.diff_pct }}%）
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center">
            <button class="mini primary" :disabled="resolving" @click="resolve('TRUST_PRIMARY')">以扶摇为准</button>
            <button class="mini primary" :disabled="resolving" @click="resolve('TRUST_BACKUP')">以 iFinD 为准</button>
            <input v-model="manualValue" type="number" step="0.01" :placeholder="`手工填入确认值（${d.citation.unit}）`"
                   style="width:170px; padding:3px 7px; font-size:12px" />
            <button class="mini" :disabled="resolving || manualValue === ''"
                    @click="resolve('MANUAL', d.condition_id, Number(manualValue))">用此值判定</button>
          </div>
        </div>

        <!-- 熔断恢复 -->
        <div v-if="taskHalted" class="incident-body">
          任务因连续数据失败熔断（ERROR_HALT）。确认数据源恢复后可解除：
          <button class="mini primary" :disabled="resolving" @click="resolve('CLEAR')">解除熔断并恢复</button>
        </div>
      </div>

      <!-- 条件状态速览条：一眼看出哪个条件有问题 -->
      <div class="cond-summary">
        <span v-for="d in latest.condition_details" :key="'s' + d.condition_id"
              class="badge" :class="isProblem(d) ? 'badge-amber' : d.is_met === true ? 'badge-green' : 'badge-gray'"
              :title="d.label">
          {{ d.condition_id }} {{ d.is_met === true ? '✓' : d.is_met === false ? '✗' : '⚠' }}
        </span>
        <span v-if="problemCount" class="prob-hint">{{ problemCount }} 个条件存在数据问题（琥珀色）</span>
      </div>

      <!-- 逐条件对比：问题条件高亮 + 长解释折叠，点击行展开 -->
      <div v-for="d in latest.condition_details" :key="'r' + d.condition_id"
           class="cond-row" :class="{ problem: isProblem(d), expanded: expandedId === d.condition_id }"
           @click="toggleExpand(d.condition_id)">
        <span class="cond-mark">{{ mark(d.is_met) }}</span>
        <div class="cond-body">
          <div class="cond-label">{{ d.condition_id }} · {{ d.label }}
            <span v-if="isProblem(d)" class="badge badge-amber" style="margin-left:4px">数据问题</span>
          </div>
          <div class="cond-vals">
            <span>实测 <b>{{ d.actual_value_display }}</b></span>
            <span>规则 <b>{{ d.threshold_display }}</b></span>
            <span v-if="d.gap_pct != null && d.is_met === false">距触发 <b>{{ d.gap_pct > 0 ? '+' : '' }}{{ d.gap_pct }}%</b></span>
            <span class="cite-tag" @click.stop="citation = d.citation" style="margin-top:0">
              溯源 · {{ d.citation.source_name.slice(0, 14) }}
            </span>
          </div>
          <div class="cond-reason" :title="d.reason_snippet">{{ d.reason_snippet }}</div>
        </div>
      </div>

      <!-- 三段式解释（默认折叠） -->
      <details style="margin-top:6px" class="sect-details">
        <summary style="cursor:pointer; color:var(--muted); font-size:12px; padding:4px 0">
          📋 【事实 / 推断 / 不确定性】三段式完整解释（点击展开）
        </summary>
        <div style="margin-top:6px">
          <div class="sect sect-fact">
            <h4>【客观事实 Fact】（可回溯至原始字段）</h4>
            <ul><li v-for="(f, i) in latest.explanation.facts_list" :key="i">{{ f }}</li></ul>
          </div>
          <div class="sect sect-infer">
            <h4>【规则逻辑推导 Inference】</h4>
            <ul><li v-for="(f, i) in latest.explanation.inference_list" :key="i">{{ f }}</li></ul>
          </div>
          <div class="sect sect-unc">
            <h4>【不确定性与降级说明 Uncertainty】</h4>
            {{ latest.explanation.uncertainty_and_degradation_note }}
          </div>
        </div>
      </details>

      <!-- 历史巡检时间轴 -->
      <details style="margin-top:6px">
        <summary style="cursor:pointer; color:var(--muted); font-size:12px">巡检历史（最近 {{ logs.length }} 次）</summary>
        <div v-for="lg in logs" :key="lg.log_id" style="display:flex; gap:8px; align-items:center; padding:4px 0; font-size:11px; border-bottom:1px dashed var(--border)">
          <span class="badge" :class="OUTCOME_CN[lg.outcome_type]?.cls">{{ OUTCOME_CN[lg.outcome_type]?.txt || lg.outcome_type }}</span>
          <span style="color:var(--dim)">{{ (lg.executed_at || '').replace('T', ' ').slice(5, 19) }}</span>
          <span style="color:var(--muted); flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">{{ lg.headline }}</span>
        </div>
      </details>
    </template>
  </div>

  <!-- 溯源弹层 -->
  <div v-if="citation" class="cite-pop" @click.self="citation = null">
    <div class="cite-card">
      <h3>字段级原始证据溯源</h3>
      <dl class="kv">
        <dt>数据源</dt><dd>{{ citation.source_name }}</dd>
        <dt>接口 / MCP Tool</dt><dd class="mono">{{ citation.endpoint_or_tool }}</dd>
        <dt>原始字段</dt><dd class="mono">{{ citation.raw_field_name }}</dd>
        <dt>原始值</dt><dd><b>{{ JSON.stringify(citation.raw_value) }}</b></dd>
        <dt>单位</dt><dd>{{ citation.unit }}</dd>
        <dt>统计口径</dt><dd>{{ citation.statistical_caliber }}</dd>
        <dt>数据业务时点</dt><dd class="mono">{{ citation.data_timestamp }}</dd>
        <dt>系统拉取时点</dt><dd class="mono">{{ citation.fetch_timestamp }}</dd>
        <dt v-if="citation.staleness_seconds > 0">数据延迟</dt>
        <dd v-if="citation.staleness_seconds > 0" :style="{ color: citation.is_stale ? 'var(--red)' : 'var(--amber)' }">
          {{ citation.staleness_seconds }} 秒{{ citation.is_stale ? '（超过容忍阈值，已标记过期）' : '' }}
        </dd>
      </dl>
      <div class="raw-box">{{ JSON.stringify(citation, null, 2) }}</div>
      <div style="margin-top:10px; text-align:right"><button @click="citation = null">关闭</button></div>
    </div>
  </div>
</template>
