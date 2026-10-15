<script setup>
import { ref, watch } from "vue";
import { ArrowRight, Check, Sparkles, Save, X } from "lucide-vue-next";
import { api } from "../api";
import RuleGroupEditor from "./RuleGroupEditor.vue";
const props = defineProps({
  selectedTask: Object,
  editRuleId: String,
  showNl: { type: Boolean, default: true },
});
const emit = defineEmits(["changed", "created", "editClosed"]);
const nl = ref("");
const step = ref(1);
const draft = ref(null);
const parseResult = ref(null);
const busy = ref(false);
const error = ref("");
const examples = [
  {
    name: "价格与事件",
    text: "当宁德时代跌破 290 元且换手率大于 3%，或者出现减持公告时提醒我",
  },
  {
    name: "热度与商品联动",
    text: "比亚迪进入热榜前 10 名，且碳酸锂主力期货跌幅超过 4%",
  },
  {
    name: "指数估值",
    text: "沪深300 PE 低于 13.5 倍，或单日跌幅超过 2% 时提醒我",
  },
];
watch(
  () => props.editRuleId,
  async (id) => {
    if (!id) return;
    busy.value = true;
    try {
      const d = await api.getTask(id);
      draft.value = structuredClone(d.current_rule);
      step.value = 2;
    } catch (e) {
      error.value = e.message;
    } finally {
      busy.value = false;
    }
  },
  { immediate: true },
);
async function parse() {
  busy.value = true;
  error.value = "";
  draft.value = null;
  parseResult.value = null;
  try {
    parseResult.value = await api.parseNl(nl.value);
    if (parseResult.value.compliance_passed && parseResult.value.draft_rule) {
      draft.value = JSON.parse(JSON.stringify(parseResult.value.draft_rule));
      step.value = 2;
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
async function save() {
  busy.value = true;
  error.value = "";
  try {
    if (props.editRuleId) {
      await api.updateRule(props.editRuleId, draft.value, "可视化规则编辑");
      emit("changed");
      emit("editClosed");
    } else {
      const r = await api.createTask(draft.value);
      emit("created", r.id);
    }
  } catch (e) {
    error.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <div class="monitor-builder">
    <div v-if="showNl" class="builder-steps">
      <div
        v-for="(name, i) in ['描述关注点', '检查监控规则', '确认并启动']"
        :key="name"
        :class="{ current: step === i + 1, done: step > i + 1 }"
      >
        <span
          ><Check v-if="step > i + 1" :size="13" /><template v-else>{{
            i + 1
          }}</template></span
        >{{ name }}
      </div>
    </div>
    <div v-if="error" class="banner banner-bad" role="alert">{{ error }}</div>
    <section v-if="showNl && step === 1" class="builder-section">
      <div class="section-heading">
        <h2>你想关注什么变化？</h2>
        <Sparkles :size="20" class="text-green" />
      </div>
      <textarea
        v-model="nl"
        rows="5"
        placeholder="例如：当宁德时代跌破 290 元且换手率大于 3%，或者出现减持公告时提醒我"
        aria-label="监控关注点"
      ></textarea>
      <div class="builder-examples">
        <button
          v-for="example in examples"
          :key="example.name"
          class="example-option"
          @click="nl = example.text"
        >
          <span>{{ example.name }}</span>
          <p>{{ example.text }}</p>
          <ArrowRight :size="16" />
        </button>
      </div>
      <div
        v-if="parseResult && !parseResult.compliance_passed"
        class="banner banner-bad"
        role="alert"
      >
        <b>无法创建此监控</b>
        <p>{{ parseResult.compliance_notice }}</p>
      </div>
      <div class="builder-actions">
        <span class="muted">仅监控客观条件，不生成买卖建议</span
        ><button class="primary" :disabled="busy || !nl.trim()" @click="parse">
          <span v-if="busy" class="spin"></span
          >{{ busy ? "正在解析…" : "生成监控规则" }}<ArrowRight :size="16" />
        </button>
      </div>
    </section>
    <template v-if="draft">
      <section v-if="step === 2" class="builder-section">
        <div class="section-heading">
          <h2>{{ editRuleId ? "编辑监控规则" : "检查监控规则" }}</h2>
          <button
            v-if="editRuleId"
            class="icon-button"
            title="取消编辑"
            aria-label="取消编辑"
            @click="emit('editClosed')"
          >
            <X :size="18" />
          </button>
        </div>
        <label class="field-label"
          >任务名称<input v-model="draft.rule_name"
        /></label>
        <div v-if="parseResult?.compliance_notice" class="banner banner-warn">
          {{ parseResult.compliance_notice }}
        </div>
        <div v-if="draft.ai_interpretation_summary" class="interpretation">
          <Sparkles :size="17" />
          <p>{{ draft.ai_interpretation_summary }}</p>
        </div>
        <RuleGroupEditor :group="draft.rule_tree" />
        <div class="schedule-editor">
          <h3>运行策略</h3>
          <div class="schedule-fields">
            <label
              >巡检间隔（秒）<input
                v-model.number="draft.schedule_config.interval_seconds"
                type="number"
                min="10" /></label
            ><label
              >冷却静默（分钟）<input
                v-model.number="draft.schedule_config.cooldown_minutes"
                type="number"
                min="0" /></label
            ><label
              >去重窗口（分钟）<input
                v-model.number="draft.schedule_config.dedup_window_minutes"
                type="number"
                min="0"
            /></label>
          </div>
          <label class="checkbox-label"
            ><input
              v-model="draft.schedule_config.trading_calendar_only"
              type="checkbox"
            />仅在交易日巡检</label
          >
        </div>
        <div class="builder-actions">
          <button v-if="showNl" @click="step = 1">返回修改描述</button
          ><button v-else @click="emit('editClosed')">取消</button
          ><button
            v-if="editRuleId"
            class="primary"
            :disabled="busy || !draft.rule_name.trim()"
            @click="save"
          >
            <Save :size="16" />{{
              busy
                ? "保存中…"
                : `保存为 v${(selectedTask?.task?.current_version || 1) + 1}`
            }}</button
          ><button
            v-else
            class="primary"
            :disabled="!draft.rule_name.trim()"
            @click="step = 3"
          >
            确认规则<ArrowRight :size="16" />
          </button>
        </div>
      </section>
      <section v-if="step === 3" class="builder-section">
        <div class="section-heading">
          <h2>确认并启动</h2>
          <Check :size="21" class="text-green" />
        </div>
        <h3 class="confirm-title">{{ draft.rule_name }}</h3>
        <blockquote class="original-query">
          {{ draft.original_nl_query }}
        </blockquote>
        <dl class="kv confirmation-kv">
          <dt>巡检频率</dt>
          <dd>每 {{ draft.schedule_config.interval_seconds }} 秒</dd>
          <dt>触发后冷却</dt>
          <dd>{{ draft.schedule_config.cooldown_minutes }} 分钟</dd>
          <dt>同一事件去重</dt>
          <dd>{{ draft.schedule_config.dedup_window_minutes }} 分钟</dd>
          <dt>运行时间</dt>
          <dd>
            {{
              draft.schedule_config.trading_calendar_only ? "仅交易日" : "每日"
            }}
          </dd>
          <dt>数据异常</dt>
          <dd>显式降级，保留原始证据</dd>
        </dl>
        <details v-if="parseResult?.jev" class="raw-details">
          <summary>合规检查记录</summary>
          <p>
            {{ parseResult.jev.model }} · 预测 / 荐股意图概率
            {{ parseResult.jev.wants_prediction }} ·
            {{ parseResult.jev.intent }}
          </p>
        </details>
        <div class="builder-actions">
          <button @click="step = 2">返回规则</button
          ><button class="primary" :disabled="busy" @click="save">
            <Check :size="16" />{{ busy ? "创建中…" : "启动监控" }}
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
