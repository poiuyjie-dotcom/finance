<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'

const props = defineProps({ detail: Object })
const emit = defineEmits(['changed', 'refreshDetail'])

const manualValue = ref('')
const resolving = ref(false)

const latest = computed(() => props.detail?.recent_logs?.[0] || null)
const conflictConds = computed(() => (latest.value?.condition_details || [])
  .filter(d => d.citation.conflict_with && !d.citation.conflict_with.resolved_by))
const taskHalted = computed(() => props.detail?.task?.status === 'ERROR_HALT')
const show = computed(() => conflictConds.value.length > 0 || taskHalted.value
  || props.detail?.task?.conflict_resolution)
const resolution = computed(() => props.detail?.task?.conflict_resolution || null)

async function resolve(mode, conditionId = null, value = null) {
  if (!props.detail) return
  resolving.value = true
  try {
    await api.resolveConflict(props.detail.task.id, { mode, condition_id: conditionId, value })
    emit('changed'); emit('refreshDetail', props.detail.task.id)
  } finally { resolving.value = false }
}
</script>

<template>
  <div class="panel incident-panel" v-if="show">
    <div class="incident-title">⚠️ 数据异常处理
      <span style="font-weight:400; font-size:11px; color:var(--dim)">系统默认挂起不猜 · 你的裁决将被记录并立即重评估</span>
    </div>

    <div v-if="resolution" class="incident-cur">
      当前裁决：<b>{{ {TRUST_PRIMARY: '以主源（扶摇）为准', TRUST_BACKUP: '以备源（iFinD）为准',
        MANUAL: `手工确认值 ${resolution.value}`}[resolution.mode] || resolution.mode }}</b>
      （{{ (resolution.set_at || '').replace('T', ' ').slice(5, 16) }} 设置）
      <button class="mini danger" :disabled="resolving" @click="resolve('CLEAR')">撤销裁决</button>
    </div>

    <div v-for="d in conflictConds" :key="'ic' + d.condition_id" class="incident-body">
      <div style="margin-bottom:6px">
        <b>{{ d.condition_id }} · {{ d.label }}</b>：
        扶摇 <b>{{ d.citation.raw_value }}</b> vs {{ d.citation.conflict_with.source }}
        <b>{{ d.citation.conflict_with.value }}</b>（偏差 {{ d.citation.conflict_with.diff_pct }}%）
      </div>
      <div style="display:flex; gap:6px; flex-wrap:wrap; align-items:center">
        <button class="mini primary" :disabled="resolving" @click="resolve('TRUST_PRIMARY')">以扶摇为准</button>
        <button class="mini primary" :disabled="resolving" @click="resolve('TRUST_BACKUP')">以 iFinD 为准</button>
        <input v-model="manualValue" type="number" step="0.01" :placeholder="`手工确认值（${d.citation.unit}）`"
               style="width:150px; padding:3px 7px; font-size:12px" />
        <button class="mini" :disabled="resolving || manualValue === ''"
                @click="resolve('MANUAL', d.condition_id, Number(manualValue))">用此值判定</button>
      </div>
    </div>

    <div v-if="taskHalted" class="incident-body">
      任务因连续数据失败熔断（ERROR_HALT）。确认数据源恢复后可解除：
      <button class="mini primary" :disabled="resolving" @click="resolve('CLEAR')">解除熔断并恢复</button>
    </div>
  </div>
</template>
