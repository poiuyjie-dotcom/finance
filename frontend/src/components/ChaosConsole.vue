<script setup>
import { onMounted, ref } from "vue";
import {
  FlaskConical,
  RotateCcw,
  Clock,
  Unplug,
  GitCompareArrows,
  Check,
} from "lucide-vue-next";
import { api } from "../api";
const mode = ref("NORMAL");
const selected = ref("STALE_DATA");
const busy = ref(false);
const hint = ref("");
const error = ref("");
const scenarios = [
  {
    id: "STALE_DATA",
    name: "数据过期",
    text: "行情业务时点延迟 45 分钟",
    icon: Clock,
  },
  {
    id: "SOURCE_CONFLICT",
    name: "双源价格冲突",
    text: "股票行情双源偏差超过阈值",
    icon: GitCompareArrows,
  },
  {
    id: "API_TIMEOUT",
    name: "上游接口超时",
    text: "扶摇与 iFinD 请求失败",
    icon: Unplug,
  },
];
onMounted(async () => {
  try {
    mode.value = (await api.health()).chaos.mode;
  } catch (e) {
    error.value = e.message;
  }
});
async function inject(value) {
  busy.value = true;
  error.value = "";
  try {
    const r = await api.faultInject(value);
    mode.value = value;
    hint.value = r.hint;
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="validation-section">
    <div class="section-heading">
      <h2><FlaskConical :size="19" />数据异常模拟</h2>
      <span
        class="badge"
        :class="mode === 'NORMAL' ? 'badge-green' : 'badge-amber'"
        >{{ mode === "NORMAL" ? "正常数据流" : "模拟已开启" }}</span
      >
    </div>
    <div class="banner banner-warn">
      模拟会影响全部任务的后续巡检。验证完成后，请恢复正常数据流。
    </div>
    <fieldset class="scenario-list">
      <legend>选择异常场景</legend>
      <label
        v-for="s in scenarios"
        :key="s.id"
        class="scenario-option"
        :class="{ selected: selected === s.id }"
        ><input
          v-model="selected"
          type="radio"
          :value="s.id"
          name="scenario" /><component :is="s.icon" :size="21" /><span
          ><strong>{{ s.name }}</strong
          ><small>{{ s.text }}</small></span
        ><Check v-if="selected === s.id" :size="17"
      /></label>
    </fieldset>
    <div class="builder-actions">
      <button :disabled="busy || mode === 'NORMAL'" @click="inject('NORMAL')">
        <RotateCcw :size="16" />恢复正常数据流</button
      ><button class="primary" :disabled="busy" @click="inject(selected)">
        <FlaskConical :size="16" />{{ busy ? "处理中…" : "启用所选模拟" }}
      </button>
    </div>
    <div v-if="hint" class="banner banner-info">{{ hint }}</div>
    <div v-if="error" class="banner banner-bad" role="alert">{{ error }}</div>
    <router-link to="/" class="back-link"
      >返回监控总览，查看巡检结果 →</router-link
    >
  </section>
</template>
