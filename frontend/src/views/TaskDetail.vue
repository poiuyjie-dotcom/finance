<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import Inspector from '../components/Inspector.vue'
import RuleEditor from '../components/RuleEditor.vue'

const route = useRoute()
const router = useRouter()
const detail = ref(null)          // { task, current_rule, recent_logs, version_count }
const editRuleId = ref(null)      // 进入编辑模式
const loading = ref(true)

const STATUS = {
  ACTIVE: { cls: 'badge-green', txt: '监控中' },
  TRIGGERED: { cls: 'badge-red', txt: '已触发' },
  COOLDOWN: { cls: 'badge-blue', txt: '冷却中' },
  DEGRADED: { cls: 'badge-amber', txt: '降级运行' },
  PAUSED: { cls: 'badge-gray', txt: '已暂停' },
  ERROR_HALT: { cls: 'badge-red', txt: '熔断' },
}

async function load() {
  loading.value = true
  try {
    detail.value = await api.getTask(route.params.id)
  } catch (e) {
    router.replace('/')
    return
  } finally { loading.value = false }
}

const task = computed(() => detail.value?.task)

function fmtCd(sec) {
  if (sec <= 0) return ''
  return `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`
}

async function act(action) {
  await api.setStatus(task.value.id, action)
  load()
}

async function removeTask() {
  if (!confirm(`确认删除任务「${task.value.title}」？版本历史与巡检日志将一并删除。`)) return
  await api.deleteTask(task.value.id)
  router.push('/')
}

function startEdit() {
  editRuleId.value = route.params.id
}
function closeEdit() {
  editRuleId.value = null
}

function condCount(rule) {
  if (!rule?.rule_tree) return 0
  return (rule.rule_tree.conditions?.length || 0)
    + (rule.rule_tree.sub_groups || []).reduce((n, g) => n + g.conditions.length, 0)
}

onMounted(load)
</script>

<template>
  <main class="detail-wrap">
    <!-- 面包屑 + 任务头部 -->
    <div class="crumbs">
      <router-link to="/">‹ 工作台</router-link>
      <span style="color:var(--dim)">/</span>
      <span>{{ task?.title || '加载中…' }}</span>
    </div>

    <div class="panel detail-head" v-if="task">
      <div class="dh-main">
        <div class="dh-title">
          <span class="task-name" style="font-size:16px">{{ task.title }}</span>
          <span class="badge" :class="STATUS[task.status]?.cls">{{ STATUS[task.status]?.txt || task.status }}</span>
          <span class="badge badge-violet">v{{ task.current_version }}</span>
        </div>
        <div class="task-meta" style="font-size:12px">
          每 {{ task.interval_seconds }}s 巡检 · 版本数 {{ detail?.version_count }}
          <template v-if="task.status === 'COOLDOWN' && task.cooldown_remaining_seconds > 0">
            · 冷却剩余 <span class="mono">{{ fmtCd(task.cooldown_remaining_seconds) }}</span>
          </template>
          <template v-if="task.degraded_reason"> · <span style="color:var(--amber)">降级原因：{{ task.degraded_reason.slice(0, 60) }}</span></template>
        </div>
        <div class="task-outcome" v-if="task.latest_headline" style="font-size:12px">{{ task.latest_headline }}</div>
      </div>
      <div class="dh-actions">
        <button class="primary mini" @click="startEdit" v-if="!editRuleId">✏️ 编辑规则</button>
        <button class="mini" @click="act('PAUSE')" v-if="task.status !== 'PAUSED'">暂停</button>
        <button class="mini" @click="act('RESUME')" v-else>恢复</button>
        <button class="mini" v-if="task.status === 'COOLDOWN'" @click="act('CLEAR_COOLDOWN')">解除冷却</button>
        <button class="mini danger" @click="removeTask">🗑 删除</button>
      </div>
    </div>

    <!-- 主体：左归因 / 右当前规则 -->
    <div class="detail-grid" v-if="task">
      <div class="detail-left">
        <Inspector :selected-task="detail" @changed="load" @refresh-detail="load" />
      </div>
      <div class="detail-right">
        <!-- 编辑模式 -->
        <RuleEditor v-if="editRuleId" :edit-rule-id="editRuleId" :selected-task="detail" :show-nl="false"
                    @changed="load" @refresh-detail="load" @edit-closed="closeEdit" />
        <!-- 当前规则只读视图 -->
        <div class="panel" v-else>
          <div class="panel-title">当前规则 <span class="sub">v{{ task.current_version }} · {{ condCount(detail?.current_rule) }} 个原子条件</span>
            <button class="mini" style="margin-left:auto" @click="startEdit">✏️ 编辑</button>
          </div>
          <div v-if="detail?.current_rule?.ai_interpretation_summary" class="banner banner-info" style="margin-bottom:10px; font-size:11px">
            🤖 {{ detail.current_rule.ai_interpretation_summary }}
          </div>
          <div style="font-size:12px; color:var(--muted); margin-bottom:8px">
            顶层逻辑：<b>{{ detail?.current_rule?.rule_tree?.logical_op === 'OR' ? '任一满足 (OR)' : '全部满足 (AND)' }}</b>
            · 巡检 {{ detail?.current_rule?.schedule_config?.interval_seconds }}s
            · 冷却 {{ detail?.current_rule?.schedule_config?.cooldown_minutes }} 分钟
            · 去重窗口 {{ detail?.current_rule?.schedule_config?.dedup_window_minutes }} 分钟
          </div>
          <div v-for="c in detail?.current_rule?.rule_tree?.conditions || []" :key="c.condition_id" class="cond-row">
            <span class="cond-mark">▫</span>
            <div class="cond-body">
              <div class="cond-label">{{ c.condition_id }} · {{ c.label }}</div>
              <div class="cond-vals"><span>条件 <b>{{ c.operator }} {{ Array.isArray(c.threshold_value) ? c.threshold_value.join('/') : c.threshold_value }} {{ c.unit }}</b></span>
                <span>主源 <b>{{ c.primary_source }}</b></span></div>
              <div class="cond-reason">{{ c.statistical_caliber }}</div>
            </div>
          </div>
          <div v-if="detail?.current_rule?.rule_tree?.sub_groups?.length" class="group-box" style="margin-top:4px">
            <span class="group-label">以下全部满足 (AND)</span>
            <div v-for="c in detail.current_rule.rule_tree.sub_groups[0].conditions" :key="c.condition_id" class="cond-row" style="margin-bottom:6px">
              <span class="cond-mark">▫</span>
              <div class="cond-body">
                <div class="cond-label">{{ c.condition_id }} · {{ c.label }}</div>
                <div class="cond-vals"><span>条件 <b>{{ c.operator }} {{ Array.isArray(c.threshold_value) ? c.threshold_value.join('/') : c.threshold_value }} {{ c.unit }}</b></span>
                  <span>主源 <b>{{ c.primary_source }}</b></span></div>
                <div class="cond-reason">{{ c.statistical_caliber }}</div>
              </div>
            </div>
          </div>
          <div class="cond-reason" style="margin-top:6px">原始自然语言：「{{ detail?.current_rule?.original_nl_query }}」</div>
        </div>
      </div>
    </div>

    <div class="panel" v-if="loading && !task" style="text-align:center; color:var(--dim); padding:40px 0">
      <span class="spin"></span> 加载任务详情…
    </div>
  </main>
</template>
