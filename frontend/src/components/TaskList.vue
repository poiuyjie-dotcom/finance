<script setup>
import { computed } from 'vue'
import { api } from '../api'

const props = defineProps({ tasks: Array, selectedId: String, refreshKey: Number, collapsed: Boolean })
const emit = defineEmits(['select', 'changed', 'editRule', 'toggleCollapse'])

const STATUS = {
  ACTIVE: { cls: 'badge-green', txt: '监控中' },
  TRIGGERED: { cls: 'badge-red', txt: '已触发' },
  COOLDOWN: { cls: 'badge-blue', txt: '冷却中' },
  DEGRADED: { cls: 'badge-amber', txt: '降级运行' },
  PAUSED: { cls: 'badge-gray', txt: '已暂停' },
  ERROR_HALT: { cls: 'badge-red', txt: '熔断' },
}

const stats = computed(() => ({
  total: props.tasks.length,
  triggered: props.tasks.filter(t => t.status === 'TRIGGERED' || (t.latest_outcome === 'TRIGGERED_ALERT')).length,
  cooldown: props.tasks.filter(t => t.status === 'COOLDOWN').length,
  degraded: props.tasks.filter(t => t.status === 'DEGRADED').length,
}))

function fmtCd(sec) {
  if (sec <= 0) return ''
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`
}

async function runNow(id) {
  await api.evaluateNow(id)
  emit('changed')
  emit('select', id)
}

async function togglePause(t) {
  await api.setStatus(t.id, t.status === 'PAUSED' ? 'RESUME' : 'PAUSE')
  emit('changed')
}

async function clearCooldown(t) {
  await api.setStatus(t.id, 'CLEAR_COOLDOWN')
  emit('changed')
  emit('select', t.id)
}
</script>

<template>
  <!-- 折叠态：窄条 -->
  <div class="panel side-strip" v-if="collapsed" @click="emit('toggleCollapse')" title="展开任务雷达">
    <div class="strip-btn">»</div>
    <div class="strip-label">任务雷达</div>
    <div class="strip-stats">
      <span title="运行任务">{{ stats.total }}</span>
      <span style="color:var(--red)" title="已触发">{{ stats.triggered }}</span>
      <span style="color:var(--blue)" title="冷却中">{{ stats.cooldown }}</span>
      <span style="color:var(--amber)" title="降级">{{ stats.degraded }}</span>
    </div>
  </div>

  <!-- 展开态 -->
  <div class="panel" v-else>
    <div class="panel-title">
      监控任务雷达 <span class="sub">点击查看归因</span>
      <button class="mini" style="margin-left:auto" @click="emit('toggleCollapse')" title="折叠侧栏">«</button>
    </div>
    <div class="stat-row">
      <div class="stat"><b style="color:var(--text)">{{ stats.total }}</b><span>运行任务</span></div>
      <div class="stat"><b style="color:var(--red)">{{ stats.triggered }}</b><span>已触发</span></div>
      <div class="stat"><b style="color:var(--blue)">{{ stats.cooldown }}</b><span>冷却中</span></div>
      <div class="stat"><b style="color:var(--amber)">{{ stats.degraded }}</b><span>降级</span></div>
    </div>

    <div v-for="t in tasks" :key="t.id"
         class="task-card" :class="{ active: t.id === selectedId, triggered: t.status === 'TRIGGERED' }"
         @click="emit('select', t.id)">
      <div class="task-head">
        <span class="task-name">{{ t.title }}</span>
        <span class="badge" :class="STATUS[t.status]?.cls">{{ STATUS[t.status]?.txt || t.status }}</span>
      </div>
      <div class="task-meta">
        v{{ t.current_version }} · 每 {{ t.interval_seconds }}s 巡检
        <template v-if="t.status === 'COOLDOWN' && t.cooldown_remaining_seconds > 0">
          · 冷却剩余 <span class="mono">{{ fmtCd(t.cooldown_remaining_seconds) }}</span>
        </template>
      </div>
      <div class="task-outcome" v-if="t.latest_headline">{{ t.latest_headline }}</div>
      <div class="task-actions" @click.stop>
        <button class="mini" @click="runNow(t.id)">立即巡检</button>
        <button class="mini" @click="emit('editRule', t.id)">编辑规则</button>
        <button class="mini" v-if="t.status === 'COOLDOWN'" @click="clearCooldown(t)">解除冷却</button>
        <button class="mini" @click="togglePause(t)">{{ t.status === 'PAUSED' ? '恢复' : '暂停' }}</button>
      </div>
    </div>
  </div>
</template>
