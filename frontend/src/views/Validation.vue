<script setup>
import { ref } from "vue";
import { ShieldCheck } from "lucide-vue-next";
import ChaosConsole from "../components/ChaosConsole.vue";
import { api } from "../api";
const query = ref("推荐几只明天必涨的牛股");
const result = ref(null);
const busy = ref(false);
const error = ref("");
async function check() {
  busy.value = true;
  error.value = "";
  try {
    result.value = await api.parseNl(query.value);
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <main class="page validation-page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">SYSTEM VALIDATION</div>
        <h1>运行验证</h1>
        <p class="page-subtitle">数据异常保护与合规边界</p>
      </div>
    </div>
    <ChaosConsole />
    <section class="validation-section">
      <div class="section-heading">
        <h2><ShieldCheck :size="19" />合规检查</h2>
      </div>
      <textarea v-model="query" rows="3" aria-label="合规检查文本"></textarea
      ><button class="primary" :disabled="busy || !query.trim()" @click="check">
        <ShieldCheck :size="16" />{{ busy ? "检查中…" : "检查输入" }}
      </button>
      <div v-if="error" class="banner banner-bad" role="alert">{{ error }}</div>
      <div
        v-if="result"
        class="banner"
        :class="result.compliance_passed ? 'banner-good' : 'banner-bad'"
      >
        <b>{{
          result.compliance_passed ? "符合客观监控要求" : "已拦截投资建议诉求"
        }}</b>
        <p>{{ result.compliance_notice || "可生成客观监控规则。" }}</p>
      </div>
    </section>
  </main>
</template>
