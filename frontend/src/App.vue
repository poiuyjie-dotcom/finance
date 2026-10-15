<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from './api'
import SettingsModal from './components/SettingsModal.vue'

const health = ref(null)
const showSettings = ref(false)
let timer = null

const PHASE_CN = {
  CONTINUOUS_AUCTION: '盘中连续竞价', CALL_AUCTION: '集合竞价', LUNCH_BREAK: '午间休市',
  PRE_OPEN: '盘前', AFTER_CLOSE: '已收盘', NON_TRADING_DAY: '非交易日',
}

async function refreshHealth() {
  try { health.value = await api.health() } catch (e) { console.warn(e) }
}

onMounted(() => {
  refreshHealth()
  timer = setInterval(refreshHealth, 15000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <header class="topbar">
    <div>
      <router-link to="/" style="text-decoration:none; color:inherit">
        <div class="brand">Alpha<em>Radar</em> · 可配置投资监控与风险雷达</div>
      </router-link>
      <div class="brand-sub">自然语言 → 可检查可修改规则 AST · 逐条件触发/未触发归因 · 多源异常降级保护 · 不构成投资建议</div>
    </div>
    <div class="health">
      <span class="chip" v-if="health">
        <span class="dot" :class="health.fuyao.status === 'HEALTHY' ? 'dot-green' : health.fuyao.status === 'ERROR' ? 'dot-red' : 'dot-gray'"></span>
        扶摇 API · {{ health.fuyao.status === 'HEALTHY' ? '正常' : health.fuyao.status === 'ERROR' ? '异常' : '未知' }}
      </span>
      <span class="chip" v-if="health">
        <span class="dot" :class="health.ifind.status === 'HEALTHY' ? 'dot-green' : health.ifind.status === 'ERROR' ? 'dot-red' : 'dot-gray'"></span>
        iFinD MCP · {{ health.ifind.status === 'HEALTHY' ? '正常' : health.ifind.status === 'ERROR' ? '异常' : '未知' }}
      </span>
      <span class="chip" v-if="health?.jev?.enabled" title="Jev 系统一模型：结构化语义判断（合规护栏 + 公告情绪归因）">
        <span class="dot" :class="health.jev.status === 'HEALTHY' ? 'dot-green' : health.jev.status === 'ERROR' ? 'dot-red' : 'dot-gray'"></span>
        Jev 语义引擎 · {{ health.jev.status === 'HEALTHY' ? '正常' : health.jev.status === 'ERROR' ? '异常' : '待调用' }}
      </span>
      <span class="chip" v-if="health">
        <span class="dot" :class="health.trading_calendar.is_trading_day ? 'dot-green' : 'dot-gray'"></span>
        {{ health.trading_calendar.is_trading_day ? '交易日' : '非交易日' }} · {{ PHASE_CN[health.trading_calendar.market_phase] || health.trading_calendar.market_phase }}
      </span>
      <button class="mini" style="margin-left:6px" @click="showSettings = true" title="数据源密钥 / 调度配置 / 连通性测试">⚙️ 设置</button>
    </div>
  </header>

  <router-view />

  <footer class="footer-note">
    AI 仅承担「自然语言→规则编译」与「结构化归因解释」；所有数值比较由确定性引擎执行，关键数字可溯源至原始字段与时点。
  </footer>

  <SettingsModal :open="showSettings" @close="showSettings = false" />
</template>
