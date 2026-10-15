<script setup>
import { ref } from 'vue'
import { api } from '../api'

const chaosMode = ref('NORMAL')
const injecting = ref(false)
const chaosHint = ref('')

async function inject(mode) {
  injecting.value = true
  try {
    const r = await api.faultInject(mode)
    chaosMode.value = mode
    chaosHint.value = r.hint
  } finally { injecting.value = false }
}
</script>

<template>
  <div class="panel">
    <div class="panel-title">异常模拟控制台 <span class="sub">演示降级与恢复（评分点）</span></div>
    <div style="display:flex; gap:6px; flex-wrap:wrap">
      <button class="mini" :class="{ primary: chaosMode === 'NORMAL' }" @click="inject('NORMAL')" :disabled="injecting">正常实时流</button>
      <button class="mini" :class="{ primary: chaosMode === 'STALE_DATA' }" @click="inject('STALE_DATA')" :disabled="injecting">模拟数据过期(+45min)</button>
      <button class="mini" :class="{ primary: chaosMode === 'SOURCE_CONFLICT' }" @click="inject('SOURCE_CONFLICT')" :disabled="injecting">模拟双源价格冲突</button>
      <button class="mini" :class="{ primary: chaosMode === 'API_TIMEOUT' }" @click="inject('API_TIMEOUT')" :disabled="injecting">模拟上游接口超时</button>
    </div>
    <div v-if="chaosHint" class="banner banner-info" style="margin:9px 0 0; font-size:11px">{{ chaosHint }}</div>
  </div>
</template>
