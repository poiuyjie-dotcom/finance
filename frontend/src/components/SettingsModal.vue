<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['close'])

const settings = ref(null)
const form = ref({})
const saving = ref(false)
const testing = ref(false)
const testResult = ref(null)
const saveMsg = ref('')

const SOURCES = [
  { key: 'FUYAO_API_KEY', name: '扶摇金融数据 API', hint: 'fuyao.aicubes.cn/admin 免费签发', health: 'fuyao' },
  { key: 'IFIND_API_KEY', name: 'iFinD MCP', hint: 'mcp.51ifind.com 个人中心-密钥（免费版 2 请求/秒）', health: 'ifind' },
  { key: 'JEV_API_KEY', name: 'Jev 语义引擎（TypeSafe）', hint: 'console.typesafe.ai/keys（可选）', health: null },
  { key: 'LLM_API_KEY', name: 'LLM 增强通道（可选）', hint: 'OpenAI 兼容协议；留空走确定性编译器', health: null },
]

watch(() => props.open, async (v) => {
  if (v) {
    saveMsg.value = ''; testResult.value = null
    settings.value = await api.getSettings()
    form.value = { FUYAO_API_KEY: '', IFIND_API_KEY: '', JEV_API_KEY: '', LLM_API_KEY: '',
                   LLM_BASE_URL: settings.value?.keys?.LLM_BASE_URL?.masked || '',
                   LLM_MODEL: settings.value?.keys?.LLM_MODEL?.masked || '',
                   SCHEDULER_TICK_SECONDS: settings.value?.scheduler_tick_seconds }
  }
}, { immediate: true })

async function save() {
  saving.value = true; saveMsg.value = ''
  try {
    const payload = {}
    for (const k of ['FUYAO_API_KEY', 'IFIND_API_KEY', 'JEV_API_KEY', 'LLM_API_KEY'])
      if (form.value[k]?.trim()) payload[k] = form.value[k].trim()
    for (const k of ['LLM_BASE_URL', 'LLM_MODEL'])
      if (form.value[k] !== undefined) payload[k] = form.value[k]
    if (form.value.SCHEDULER_TICK_SECONDS) payload.SCHEDULER_TICK_SECONDS = Number(form.value.SCHEDULER_TICK_SECONDS)
    const r = await api.updateKeys(payload)
    settings.value = { ...settings.value, ...r }
    saveMsg.value = `已保存并即时生效：${(r.applied || []).join('、') || '无变更'}`
    for (const k of ['FUYAO_API_KEY', 'IFIND_API_KEY', 'JEV_API_KEY', 'LLM_API_KEY']) form.value[k] = ''
  } catch (e) { saveMsg.value = '保存失败：' + e.message } finally { saving.value = false }
}

async function runTest() {
  testing.value = true; testResult.value = null
  try { testResult.value = await api.testConnections() }
  catch (e) { testResult.value = { error: e.message } }
  finally { testing.value = false }
}
</script>

<template>
  <div v-if="open" class="cite-pop" @click.self="emit('close')">
    <div class="cite-card" style="max-width: 640px">
      <h3>⚙️ 系统设置 · 数据源与调度</h3>

      <div v-for="s in SOURCES" :key="s.key" class="src-card">
        <div class="src-head">
          <span class="dot" :class="settings?.health?.[s.health]?.status === 'HEALTHY' ? 'dot-green'
            : settings?.health?.[s.health]?.status === 'ERROR' ? 'dot-red' : 'dot-gray'"></span>
          <b>{{ s.name }}</b>
          <span class="badge" v-if="settings?.keys?.[s.key]?.configured" class-="badge-green">已配置</span>
          <span class="badge badge-gray" v-else>未配置</span>
          <span style="margin-left:auto; font-size:10.5px; color:var(--dim)" class="mono">{{ settings?.keys?.[s.key]?.masked }}</span>
        </div>
        <div style="font-size:10.5px; color:var(--dim); margin: 2px 0 6px">
          {{ s.hint }}
          <template v-if="settings?.health?.[s.health]?.last_error">
            · 最近错误：{{ settings.health[s.health].last_error.slice(0, 60) }}
          </template>
        </div>
        <input :type="s.key.includes('KEY') ? 'password' : 'text'" v-model="form[s.key]"
               :placeholder="settings?.keys?.[s.key]?.configured ? '留空则保持不变' : '粘贴密钥…'" autocomplete="off" />
        <div v-if="testResult && testResult[s.health || 'jev'] && s.health" class="test-line"
             :style="{ color: testResult[s.health].ok ? 'var(--green)' : 'var(--red)' }">
          {{ testResult[s.health].ok ? '✓' : '✗' }} {{ testResult[s.health].detail }}（{{ testResult[s.health].latency_ms }}ms）
        </div>
      </div>

      <div v-if="testResult?.error" class="banner banner-bad" style="margin: 8px 0">测试失败：{{ testResult.error }}</div>
      <div v-else-if="testResult?.jev" class="test-line" :style="{ color: testResult.jev.ok ? 'var(--green)' : 'var(--amber)' }">
        Jev {{ testResult.jev.ok ? '✓' : '✗' }} {{ testResult.jev.detail }}（{{ testResult.jev.latency_ms }}ms）
      </div>

      <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 10px">
        <label style="font-size:11px;color:var(--dim)">LLM Base URL<input v-model="form.LLM_BASE_URL" placeholder="https://api.openai.com/v1" /></label>
        <label style="font-size:11px;color:var(--dim)">LLM Model<input v-model="form.LLM_MODEL" placeholder="gpt-4o-mini" /></label>
        <label style="font-size:11px;color:var(--dim)">全局巡检周期(秒)<input v-model.number="form.SCHEDULER_TICK_SECONDS" type="number" /></label>
      </div>

      <div style="display:flex; gap:8px; margin-top: 14px; align-items: center">
        <button class="primary" @click="save" :disabled="saving">保存配置</button>
        <button @click="runTest" :disabled="testing"><span v-if="testing" class="spin"></span> 测试全部连接</button>
        <span style="flex:1"></span>
        <button @click="emit('close')">关闭</button>
      </div>
      <div v-if="saveMsg" class="banner banner-good" style="margin-top:9px; font-size:11px">✅ {{ saveMsg }}</div>
      <div style="font-size:10px; color:var(--dim); margin-top: 8px">
        密钥保存到服务器 backend/.env（不进 Git 仓库）；展示仅掩码，修改后 iFinD 会话自动重置。配置文件：{{ settings?.env_file }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.src-card { border: 1px solid var(--border); border-radius: 9px; padding: 9px 11px; margin-bottom: 8px; background: var(--panel2); }
.src-head { display: flex; align-items: center; gap: 7px; font-size: 12.5px; }
.test-line { font-size: 11px; margin-top: 5px; }
</style>
