<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft,
  Play,
  Pause,
  Pencil,
  Trash2,
  RefreshCw,
  Clock,
  GitBranch,
  ShieldCheck,
  RotateCcw,
} from "lucide-vue-next";
import { api } from "../api";
import { statusInfo, formatTime, outcomes } from "../presentation";
import Inspector from "../components/Inspector.vue";
import RuleEditor from "../components/RuleEditor.vue";
import IncidentCard from "../components/IncidentCard.vue";
const route = useRoute();
const router = useRouter();
const detail = ref(null);
const tab = ref("result");
const editing = ref(false);
const versions = ref([]);
const error = ref("");
const busy = ref(false);
let timer;
const task = computed(() => detail.value?.task);
const schedule = computed(
  () => detail.value?.current_rule?.schedule_config || {},
);
const latest = computed(() => detail.value?.recent_logs?.[0]);
const conditions = computed(() => {
  const flatten = (g) => [
    ...(g?.conditions || []),
    ...(g?.sub_groups || []).flatMap(flatten),
  ];
  return flatten(detail.value?.current_rule?.rule_tree);
});
async function load() {
  try {
    detail.value = await api.getTask(route.params.id);
    error.value = "";
  } catch (e) {
    error.value = e.message;
  }
}
async function execute(fn) {
  busy.value = true;
  error.value = "";
  try {
    await fn();
    await load();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function removeTask() {
  if (confirm(`删除「${task.value.title}」及其全部巡检和版本记录？`))
    await execute(async () => {
      await api.deleteTask(task.value.id);
      await router.push("/");
    });
}
async function showVersions() {
  try {
    versions.value = await api.versions(route.params.id);
  } catch (e) {
    error.value = e.message;
  }
}
async function rollback(v) {
  if (confirm(`将 v${v} 的规则恢复为一个新版本？冷却与去重状态将重置。`))
    await execute(async () => {
      await api.rollback(task.value.id, v);
      await showVersions();
    });
}
watch(tab, (v) => {
  if (v === "versions") showVersions();
});
watch(() => route.params.id, load);
onMounted(() => {
  load();
  timer = setInterval(() => {
    if (!busy.value && !editing.value) load();
  }, 15000);
});
onUnmounted(() => clearInterval(timer));
</script>
<template>
  <main class="page detail-page">
    <router-link to="/" class="back-link"
      ><ArrowLeft :size="15" />监控总览</router-link
    >
    <div v-if="error" class="banner banner-bad" role="alert">
      {{ error }}<button @click="load">重新加载</button>
    </div>
    <template v-if="task">
      <div class="page-heading detail-heading">
        <div>
          <div class="eyebrow">MONITOR / v{{ task.current_version }}</div>
          <h1>{{ task.title }}</h1>
          <div class="detail-status">
            <span class="badge" :class="statusInfo(task.status).cls">{{
              statusInfo(task.status).txt
            }}</span
            ><span
              >{{ conditions.length }} 个条件 ·
              {{
                detail.current_rule.rule_tree.logical_op === "OR"
                  ? "任一满足"
                  : "全部满足"
              }}</span
            >
          </div>
        </div>
        <div class="head-actions">
          <button
            class="icon-button"
            title="编辑规则"
            aria-label="编辑规则"
            @click="
              tab = 'rule';
              editing = true;
            "
          >
            <Pencil :size="17" /></button
          ><button
            :disabled="busy"
            @click="
              execute(() =>
                api.setStatus(
                  task.id,
                  task.status === 'PAUSED' ? 'RESUME' : 'PAUSE',
                ),
              )
            "
          >
            <component
              :is="task.status === 'PAUSED' ? Play : Pause"
              :size="16"
            />{{ task.status === "PAUSED" ? "恢复" : "暂停" }}</button
          ><button
            class="primary"
            :disabled="busy"
            @click="execute(() => api.evaluateNow(task.id))"
          >
            <RefreshCw :size="16" :class="{ rotating: busy }" />{{
              busy ? "处理中…" : "立即巡检"
            }}</button
          ><button
            class="icon-button danger"
            title="删除任务"
            aria-label="删除任务"
            :disabled="busy"
            @click="removeTask"
          >
            <Trash2 :size="17" />
          </button>
        </div>
      </div>
      <div class="detail-metrics">
        <div>
          <Clock :size="17" /><span
            >巡检频率<strong>每 {{ task.interval_seconds }} 秒</strong></span
          >
        </div>
        <div>
          <ShieldCheck :size="17" /><span
            >冷却 / 去重<strong
              >{{ schedule.cooldown_minutes }} /
              {{ schedule.dedup_window_minutes }} 分钟</strong
            ></span
          >
        </div>
        <div>
          <GitBranch :size="17" /><span
            >规则版本<strong
              >v{{ task.current_version }} ·
              {{ detail.version_count }} 个版本</strong
            ></span
          >
        </div>
        <div>
          <RefreshCw :size="17" /><span
            >最近巡检<strong>{{
              formatTime(task.last_executed_at, true)
            }}</strong></span
          >
        </div>
      </div>
      <div v-if="task.cooldown_remaining_seconds > 0" class="cooldown-notice">
        <Clock :size="16" />冷却静默还剩
        {{ Math.ceil(task.cooldown_remaining_seconds / 60) }} 分钟<button
          class="text-button"
          :disabled="busy"
          @click="execute(() => api.setStatus(task.id, 'CLEAR_COOLDOWN'))"
        >
          解除冷却
        </button>
      </div>
      <IncidentCard :detail="detail" @changed="load" />
      <div class="tabs detail-tabs" role="tablist" aria-label="任务详情">
        <button
          v-for="item in [
            { id: 'result', name: '当前判定' },
            { id: 'rule', name: '监控规则' },
            { id: 'history', name: '巡检记录' },
            { id: 'versions', name: '版本变化' },
          ]"
          :key="item.id"
          role="tab"
          :aria-selected="tab === item.id"
          :class="{ active: tab === item.id }"
          @click="tab = item.id"
        >
          {{ item.name
          }}<span v-if="item.id === 'history'">{{
            detail.recent_logs.length
          }}</span>
        </button>
      </div>
      <Inspector v-if="tab === 'result'" :selected-task="detail" />
      <section v-if="tab === 'rule'" class="rule-section">
        <RuleEditor
          v-if="editing"
          :edit-rule-id="task.id"
          :selected-task="detail"
          :show-nl="false"
          @changed="load"
          @edit-closed="editing = false"
        /><template v-else
          ><div class="section-heading">
            <h2>当前规则</h2>
            <button @click="editing = true">
              <Pencil :size="15" />编辑规则
            </button>
          </div>
          <blockquote class="original-query">
            {{ detail.current_rule.original_nl_query }}
          </blockquote>
          <div class="rule-logic-label">
            {{
              detail.current_rule.rule_tree.logical_op === "OR"
                ? "任一分支满足时触发"
                : "全部条件满足时触发"
            }}
          </div>
          <div
            v-for="c in conditions"
            :key="c.condition_id"
            class="rule-read-row"
          >
            <span class="condition-id">{{ c.condition_id }}</span>
            <div>
              <strong>{{ c.label }}</strong>
              <p>
                {{ c.target_name }} · {{ c.target_code }} ·
                {{ c.statistical_caliber }}
              </p>
            </div>
            <b
              >{{ c.operator }}
              {{
                Array.isArray(c.threshold_value)
                  ? c.threshold_value.join(" / ")
                  : c.threshold_value
              }}
              {{ c.unit }}</b
            >
          </div>
          <details class="raw-details">
            <summary>完整规则结构</summary>
            <pre class="raw-box">{{
              JSON.stringify(detail.current_rule.rule_tree, null, 2)
            }}</pre>
          </details></template
        >
      </section>
      <section v-if="tab === 'history'" class="history-section">
        <div class="section-heading">
          <h2>最近巡检</h2>
          <span class="muted">保留展示最近 20 次</span>
        </div>
        <div v-if="!detail.recent_logs.length" class="empty-state">
          尚无巡检记录
        </div>
        <details
          v-for="log in detail.recent_logs"
          :key="log.log_id"
          class="history-row"
        >
          <summary>
            <span
              class="timeline-dot"
              :class="log.degradation_flag ? 'dot-amber' : 'dot-green'"
            ></span
            ><time>{{ formatTime(log.executed_at) }}</time
            ><strong>{{
              outcomes[log.outcome_type] || log.outcome_type
            }}</strong
            ><span class="muted">v{{ log.rule_version }}</span>
          </summary>
          <p>{{ log.headline }}</p>
          <p class="muted">
            {{ statusInfo(log.task_state_before).txt }} →
            {{ statusInfo(log.task_state_after).txt
            }}<template v-if="log.dedup_fingerprint">
              · 去重指纹 {{ log.dedup_fingerprint }}</template
            >
          </p>
          <p v-for="d in log.condition_details" :key="d.condition_id">
            {{ d.label }}：{{ d.actual_value_display }} /
            {{ d.threshold_display }}
          </p>
        </details>
      </section>
      <section v-if="tab === 'versions'" class="versions-section">
        <div class="section-heading"><h2>规则版本变化</h2></div>
        <div v-for="v in versions" :key="v.version_num" class="version-row">
          <div class="section-heading">
            <h3>
              v{{ v.version_num
              }}<span
                v-if="v.version_num === task.current_version"
                class="badge badge-green"
                >当前版本</span
              >
            </h3>
            <button
              v-if="v.version_num !== task.current_version"
              :disabled="busy"
              @click="rollback(v.version_num)"
            >
              <RotateCcw :size="14" />恢复此版本
            </button>
          </div>
          <p class="muted">
            {{
              v.change_reason ||
              (v.change_type === "NL_INIT" ? "自然语言创建" : v.change_type)
            }}
          </p>
          <div
            v-for="(c, i) in v.diff_summary?.changes || []"
            :key="i"
            class="diff-item"
          >
            <span class="diff-path">{{ c.path }}</span
            ><span class="diff-old">{{ c.old_value }}</span
            ><span>→</span><span class="diff-new">{{ c.new_value }}</span>
          </div>
        </div>
      </section>
    </template>
    <div v-else-if="!error" class="empty-state">
      <span class="spin"></span>加载任务详情
    </div>
  </main>
</template>
