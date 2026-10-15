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
    <div class="panel-title">异常模拟控制台 <span class="sub">全局注入 · 演示降级与恢复</span></div>
    <div style="font-size:10.5px; color:var(--dim); margin-bottom:8px">
      注入作用于<b>数据通道层</b>，对<b>所有任务</b>的下一次巡检生效（点「立即巡检」立即观察）：
      双源冲突仅影响<b>股票行情快照</b>类条件；数据过期仅影响<b>行情时点</b>；接口超时影响<b>扶摇+iFinD 全部接口</b>（热榜/期货也会中招）。
    </div>
    <div style="display:flex; gap:6px; flex-wrap:wrap">
      <button class="mini" :class="{ primary: chaosMode === 'NORMAL' }" @click="inject('NORMAL')" :disabled="injecting">正常实时流</button>
      <button class="mini" :class="{ primary: chaosMode === 'STALE_DATA' }" @click="inject('STALE_DATA')" :disabled="injecting">模拟数据过期(+45min)</button>
      <button class="mini" :class="{ primary: chaosMode === 'SOURCE_CONFLICT' }" @click="inject('SOURCE_CONFLICT')" :disabled="injecting">模拟双源价格冲突</button>
      <button class="mini" :class="{ primary: chaosMode === 'API_TIMEOUT' }" @click="inject('API_TIMEOUT')" :disabled="injecting">模拟上游接口超时</button>
    </div>
    <div v-if="chaosHint" class="banner banner-info" style="margin:9px 0 0; font-size:11px">{{ chaosHint }}</div>
  </div>
</template>
