<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import {
  Plus,
  RefreshCw,
  Search,
  ArrowUpRight,
  Radar,
  ShieldAlert,
  Bell,
  Pause,
  Play,
  ChevronRight,
  ChevronDown,
} from "lucide-vue-next";
import { api } from "../api";
import { statusInfo, formatTime } from "../presentation";
const tasks = ref([]);
const filter = ref("all");
const query = ref("");
const loading = ref(true);
const error = ref("");
const busy = ref(null);
const updated = ref("");
const taskSection = ref(null);
let timer;
const attention = (t) =>
  ["DEGRADED", "ERROR_HALT", "TRIGGERED"].includes(t.status) ||
  (t.status !== "PAUSED" && t.latest_outcome === "TRIGGERED_ALERT");
const stats = computed(() => [
  {
    key: "all",
    label: "全部任务",
    value: tasks.value.length,
    icon: Radar,
    color: "",
  },
  {
    key: "attention",
    label: "需要关注",
    value: tasks.value.filter(attention).length,
    icon: ShieldAlert,
    color: "amber",
  },
  {
    key: "running",
    label: "正常运行",
    value: tasks.value.filter((t) =>
      ["ACTIVE", "COOLDOWN", "TRIGGERED"].includes(t.status),
    ).length,
    icon: Bell,
    color: "green",
  },
  {
    key: "paused",
    label: "已暂停",
    value: tasks.value.filter((t) => t.status === "PAUSED").length,
    icon: Pause,
    color: "muted",
  },
]);
const filtered = computed(() => {
  const predicates = {
    all: () => true,
    attention,
    running: (t) => ["ACTIVE", "COOLDOWN", "TRIGGERED"].includes(t.status),
    paused: (t) => t.status === "PAUSED",
  };
  return tasks.value
    .filter(
      (t) =>
        t.title.toLowerCase().includes(query.value.toLowerCase()) &&
        predicates[filter.value](t),
    )
    .sort((a, b) => Number(attention(b)) - Number(attention(a)));
});
const priority = computed(() => tasks.value.filter(attention).slice(0, 3));
const listTitle = computed(() =>
  filter.value === "all"
    ? "监控任务"
    : stats.value.find((s) => s.key === filter.value)?.label + "任务",
);
async function showTasks(key) {
  filter.value = key;
  query.value = "";
  await nextTick();
  taskSection.value?.focus({ preventScroll: true });
  taskSection.value?.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
    block: "start",
  });
}
function headline(task) {
  if (task.status === "ERROR_HALT")
    return task.degraded_reason || "任务已熔断，等待恢复";
  return task.latest_headline || task.degraded_reason || "等待巡检";
}
async function refresh() {
  try {
    tasks.value = await api.listTasks();
    error.value = "";
    updated.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}
async function toggle(t) {
  busy.value = t.id;
  try {
    await api.setStatus(t.id, t.status === "PAUSED" ? "RESUME" : "PAUSE");
    await refresh();
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = null;
  }
}
onMounted(() => {
  refresh();
  timer = setInterval(refresh, 15000);
});
onUnmounted(() => clearInterval(timer));
</script>
<template>
  <main class="page dashboard-page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">MONITORING OVERVIEW</div>
        <h1>监控总览<span class="heading-dot"></span></h1>
        <p class="page-subtitle">
          {{
            priority.length
              ? "有任务需要关注，自动判定已按数据状态执行保护。"
              : "关注的市场变化，都在这里。"
          }}
        </p>
      </div>
      <router-link class="button primary" to="/new"
        ><Plus :size="17" />新建监控</router-link
      >
    </div>
    <div v-if="error" class="banner banner-bad" role="alert">
      数据更新失败：{{ error }} <button @click="refresh">重试</button>
    </div>
    <div class="overview-stats">
      <button
        v-for="s in stats"
        :key="s.key"
        class="overview-stat"
        :class="{ selected: filter === s.key }"
        :aria-pressed="filter === s.key"
        aria-controls="monitor-tasks"
        @click="showTasks(s.key)"
      >
        <span class="stat-label"
          >{{ s.label }}<component :is="s.icon" :size="18" /></span
        ><strong :class="s.color ? 'text-' + s.color : ''"
          >{{ loading ? "—" : s.value }}<small>个</small></strong
        ><span class="stat-selection"
          >查看{{
            s.label === "全部任务" ? "全部" : s.label
          }}任务列表<ChevronDown :size="13"
        /></span>
      </button>
    </div>
    <section v-if="priority.length" class="attention-section">
      <div class="section-heading">
        <h2><ShieldAlert :size="17" />优先关注</h2>
        <button class="text-button" @click="showTasks('attention')">
          查看全部<ChevronRight :size="14" />
        </button>
      </div>
      <div class="attention-grid">
        <router-link
          v-for="t in priority"
          :key="t.id"
          :to="`/task/${t.id}`"
          class="attention-item"
          ><span class="badge" :class="statusInfo(t.status).cls">{{
            statusInfo(t.status).txt
          }}</span>
          <h3>{{ t.title }}</h3>
          <p>{{ headline(t) }}</p>
          <span class="attention-link"
            >查看原因与证据<ArrowUpRight :size="15" /></span
        ></router-link>
      </div>
    </section>
    <section
      id="monitor-tasks"
      ref="taskSection"
      class="monitor-section"
      tabindex="-1"
      :aria-label="listTitle"
    >
      <div class="section-heading">
        <h2>
          {{ listTitle }}
          <span class="count" aria-live="polite">{{ filtered.length }}</span>
        </h2>
        <span class="update-time"
          >{{ updated ? updated + " 更新" : "正在加载"
          }}<button
            class="icon-button"
            title="刷新任务"
            aria-label="刷新任务"
            @click="refresh"
          >
            <RefreshCw :size="15" /></button
        ></span>
      </div>
      <div class="table-toolbar">
        <div class="tabs filter-tabs" aria-label="任务状态筛选">
          <button
            v-for="s in stats"
            :key="s.key"
            :class="{ active: filter === s.key }"
            @click="filter = s.key"
          >
            {{ s.key === "all" ? "全部" : s.label }}<span>{{ s.value }}</span>
          </button>
        </div>
        <label class="search-field"
          ><Search :size="16" /><input
            v-model="query"
            placeholder="搜索监控任务"
            aria-label="搜索监控任务"
        /></label>
      </div>
      <div class="task-table">
        <div class="table-header">
          <span>任务 / 最新结论</span><span>运行状态</span><span>最近巡检</span
          ><span>调度</span><span></span>
        </div>
        <div v-for="t in filtered" :key="t.id" class="task-table-row">
          <router-link :to="`/task/${t.id}`" class="task-primary"
            ><span class="task-monogram" :class="{ warning: attention(t) }"
              ><Radar :size="20" /></span
            ><span
              ><strong>{{ t.title }}</strong
              ><small>{{ headline(t) }}</small></span
            ></router-link
          ><span class="badge" :class="statusInfo(t.status).cls">{{
            statusInfo(t.status).txt
          }}</span
          ><span class="table-time"
            >{{ formatTime(t.last_executed_at, true)
            }}<small>规则 v{{ t.current_version }}</small></span
          ><span class="table-schedule"
            >{{ t.interval_seconds }}<small>秒 / 次</small></span
          >
          <div class="row-actions">
            <button
              class="icon-button"
              :disabled="busy === t.id"
              :title="t.status === 'PAUSED' ? '恢复监控' : '暂停监控'"
              :aria-label="t.status === 'PAUSED' ? '恢复监控' : '暂停监控'"
              @click="toggle(t)"
            >
              <component
                :is="t.status === 'PAUSED' ? Play : Pause"
                :size="16"
              /></button
            ><router-link
              :to="`/task/${t.id}`"
              class="icon-button"
              title="查看任务"
              aria-label="查看任务"
              ><ArrowUpRight :size="18"
            /></router-link>
          </div>
        </div>
        <div v-if="loading" class="empty-state">
          <span class="spin"></span>正在读取监控任务
        </div>
        <div v-else-if="!filtered.length" class="empty-state">
          <Radar :size="32" />
          <h3>{{ tasks.length ? "没有匹配的任务" : "还没有监控任务" }}</h3>
          <router-link v-if="!tasks.length" to="/new" class="button primary"
            ><Plus :size="16" />新建监控</router-link
          ><button
            v-else
            @click="
              query = '';
              filter = 'all';
            "
          >
            清除筛选
          </button>
        </div>
      </div>
      <div class="table-foot">
        <span>{{ filtered.length }} 个任务</span
        ><span><span class="dot dot-green"></span>每 15 秒同步状态</span>
      </div>
    </section>
  </main>
</template>
