<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  Radar,
  LayoutDashboard,
  Plus,
  FlaskConical,
  Settings,
  ArrowUpRight,
} from "lucide-vue-next";
import { api } from "./api";
import SettingsModal from "./components/SettingsModal.vue";
const health = ref(null);
const showSettings = ref(false);
let timer;
const connectionGroups = computed(() => [
  {
    name: "数据接口",
    sources: [
      { key: "fuyao", name: "扶摇金融", ...health.value?.fuyao },
      { key: "ifind", name: "iFinD", ...health.value?.ifind },
    ],
  },
  {
    name: "AI 接口",
    sources: [
      { key: "jev", name: "Jev 语义引擎", ...health.value?.jev },
      { key: "llm", name: "规则编译模型", ...health.value?.llm },
    ],
  },
]);
function connectionStatus(source) {
  if (!health.value) return { label: "待确认", color: "gray" };
  if (source.enabled === false) return { label: "未配置", color: "gray" };
  if (source.status === "HEALTHY") return { label: "调用正常", color: "green" };
  if (source.status === "ERROR")
    return {
      label: source.key === "jev" || source.key === "llm" ? "异常回退" : "异常",
      color: "amber",
    };
  return { label: source.enabled ? "待调用" : "待确认", color: "gray" };
}
function connectionHint(source) {
  if (source.enabled === false)
    return source.key === "llm"
      ? "未启用模型增强，使用确定性规则解析器"
      : "未启用 Jev，使用规则合规护栏";
  const parts = [
    source.model,
    source.last_sync && `最近调用：${source.last_sync}`,
    source.latency_ms != null && `耗时：${source.latency_ms} ms`,
  ];
  if (source.status === "ERROR") parts.push("最近调用失败，主流程使用回退通道");
  return parts.filter(Boolean).join(" · ") || "等待实际调用验证连接";
}
const phases = {
  CONTINUOUS_AUCTION: "盘中",
  CALL_AUCTION: "集合竞价",
  LUNCH_BREAK: "午间休市",
  PRE_OPEN: "盘前",
  AFTER_CLOSE: "已收盘",
  NON_TRADING_DAY: "非交易日",
};
async function refreshHealth() {
  try {
    health.value = await api.health();
  } catch {
    health.value = null;
  }
}
onMounted(() => {
  refreshHealth();
  timer = setInterval(refreshHealth, 15000);
});
onUnmounted(() => clearInterval(timer));
</script>
<template>
  <div class="app-shell">
    <aside class="sidebar">
      <router-link to="/" class="brand"
        ><Radar :size="27" /><span
          >AlphaRadar<small>投资监控与风险雷达</small></span
        ></router-link
      >
      <div class="nav-label">工作空间</div>
      <nav class="main-nav" aria-label="主导航">
        <router-link
          to="/"
          :class="{
            active:
              $route.name === 'dashboard' || $route.name === 'task-detail',
          }"
          ><LayoutDashboard :size="18" />监控总览</router-link
        >
        <router-link to="/new" active-class="active"
          ><Plus :size="18" />新建监控</router-link
        >
        <router-link to="/validation" active-class="active"
          ><FlaskConical :size="18" />运行验证</router-link
        >
      </nav>
      <div class="sidebar-bottom">
        <div
          v-for="group in connectionGroups"
          :key="group.name"
          class="connection-group"
        >
          <div class="source-heading">{{ group.name }}</div>
          <div
            v-for="source in group.sources"
            :key="source.key"
            class="connection-entry"
            :data-connection="source.key"
            :title="connectionHint(source)"
          >
            <div class="source-status">
              <span>{{ source.name }}</span
              ><span :class="'text-' + connectionStatus(source).color"
                ><i
                  class="dot"
                  :class="'dot-' + connectionStatus(source).color"
                ></i
                >{{ connectionStatus(source).label }}</span
              >
            </div>
            <div v-if="source.model && source.enabled" class="connection-model">
              {{ source.model }}
            </div>
          </div>
        </div>
        <button class="settings-button" @click="showSettings = true">
          <Settings :size="17" />数据源与设置<ArrowUpRight :size="14" />
        </button>
        <div class="sidebar-note">客观监控 · 不构成投资建议</div>
      </div>
    </aside>
    <div class="app-main">
      <header class="topbar">
        <div class="workspace-name">
          个人工作空间 <span>/</span>
          <b>{{
            $route.name === "create"
              ? "新建监控"
              : $route.name === "validation"
                ? "运行验证"
                : $route.name === "task-detail"
                  ? "任务详情"
                  : "监控总览"
          }}</b>
        </div>
        <div class="market-status">
          <span
            class="dot"
            :class="
              health?.trading_calendar?.is_trading_day
                ? 'dot-green'
                : 'dot-gray'
            "
          ></span
          >{{ phases[health?.trading_calendar?.market_phase] || "连接中"
          }}<span class="timezone">北京时间</span
          ><button
            class="icon-button mobile-settings"
            title="数据源与设置"
            aria-label="数据源与设置"
            @click="showSettings = true"
          >
            <Settings :size="16" />
          </button>
        </div>
      </header>
      <div
        v-if="health?.chaos?.mode && health.chaos.mode !== 'NORMAL'"
        class="simulation-notice"
      >
        <FlaskConical :size="16" />异常模拟正在影响全部任务<router-link
          to="/validation"
          >查看并恢复数据流 →</router-link
        >
      </div>
      <router-view />
      <footer class="footer-note">
        <span>AlphaRadar</span
        ><span>规则确定性判定 · 证据可追溯 · 异常显式降级</span>
      </footer>
    </div>
  </div>
  <SettingsModal
    :open="showSettings"
    @close="
      showSettings = false;
      refreshHealth();
    "
  />
</template>
