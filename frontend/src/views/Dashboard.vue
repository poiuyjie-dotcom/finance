<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import TaskList from '../components/TaskList.vue'
import RuleEditor from '../components/RuleEditor.vue'
import ChaosConsole from '../components/ChaosConsole.vue'

const router = useRouter()
const tasks = ref([])
const leftCollapsed = ref(false)
let timer = null

async function refreshTasks() {
  try { tasks.value = await api.listTasks() } catch (e) { console.warn(e) }
}

function navigate(id) {
  router.push(`/task/${id}`)
}

onMounted(() => {
  refreshTasks()
  timer = setInterval(refreshTasks, 15000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <main class="layout" :class="{ 'left-collapsed': leftCollapsed }">
    <div class="col-left">
      <TaskList :tasks="tasks" :collapsed="leftCollapsed"
                @navigate="navigate" @changed="refreshTasks"
                @toggle-collapse="leftCollapsed = !leftCollapsed" />
    </div>
    <div class="col-mid">
      <RuleEditor @changed="refreshTasks" @created="navigate" />
    </div>
    <div class="col-right">
      <ChaosConsole />
      <div class="panel">
        <div class="panel-title">使用指引 <span class="sub">两级页面：工作台 → 任务详情</span></div>
        <div class="empty-guide">
          <div class="empty-step">💬 <b>创建监控</b>：在中间输入关注点（如「宁德时代跌破 290 元且换手率大于 3%」），解析后检查/修改规则树，创建任务</div>
          <div class="empty-step">📊 <b>进入详情</b>：点击左侧任意任务卡片，进入该任务的详情页——逐条件归因、溯源、巡检历史、版本管理与规则编辑都在那里</div>
          <div class="empty-step">⚡ <b>快速操作</b>：任务卡上的「立即巡检 / 解除冷却 / 暂停」无需进详情页</div>
          <div class="empty-step">🧪 <b>演示降级</b>：上方异常模拟控制台一键注入 数据过期 / 双源冲突 / 接口超时，观察任务如何显式降级与自动恢复</div>
        </div>
      </div>
    </div>
  </main>
</template>
