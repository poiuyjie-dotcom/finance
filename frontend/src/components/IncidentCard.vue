<script setup>
import { computed, ref } from "vue";
import { api } from "../api";
import { TriangleAlert } from "lucide-vue-next";

const props = defineProps({ detail: Object });
const emit = defineEmits(["changed", "refreshDetail"]);

const manualValues = ref({});
const resolving = ref(false);
const error = ref("");

const latest = computed(() => props.detail?.recent_logs?.[0] || null);
const conflictConds = computed(() =>
  (latest.value?.condition_details || []).filter(
    (d) => d.citation.conflict_with && !d.citation.conflict_with.resolved_by,
  ),
);
const taskHalted = computed(() => props.detail?.task?.status === "ERROR_HALT");
const show = computed(
  () =>
    conflictConds.value.length > 0 ||
    taskHalted.value ||
    props.detail?.task?.conflict_resolution,
);
const resolution = computed(
  () => props.detail?.task?.conflict_resolution || null,
);

async function resolve(mode, conditionId = null, value = null) {
  if (!props.detail) return;
  resolving.value = true;
  error.value = "";
  try {
    await api.resolveConflict(props.detail.task.id, {
      mode,
      condition_id: conditionId,
      value,
    });
    emit("changed");
    emit("refreshDetail", props.detail.task.id);
  } catch (e) {
    error.value = e.message;
  } finally {
    resolving.value = false;
  }
}
</script>

<template>
  <div class="panel incident-panel" v-if="show">
    <div class="incident-title"><TriangleAlert :size="18" />数据异常处理</div>

    <div v-if="resolution" class="incident-cur">
      当前裁决：<b>{{
        {
          TRUST_PRIMARY: "以主源（扶摇）为准",
          TRUST_BACKUP: "以备源（iFinD）为准",
          MANUAL: `手工确认值 ${resolution.value}`,
        }[resolution.mode] || resolution.mode
      }}</b>
      （{{ (resolution.set_at || "").replace("T", " ").slice(5, 16) }} 设置）
      <button
        class="mini danger"
        :disabled="resolving"
        @click="resolve('CLEAR')"
      >
        撤销裁决
      </button>
    </div>

    <div
      v-for="d in conflictConds"
      :key="'ic' + d.condition_id"
      class="incident-body"
    >
      <div style="margin-bottom: 6px">
        <b>{{ d.condition_id }} · {{ d.label }}</b
        >： 扶摇 <b>{{ d.citation.raw_value }}</b> vs
        {{ d.citation.conflict_with.source }}
        <b>{{ d.citation.conflict_with.value }}</b
        >（偏差 {{ d.citation.conflict_with.diff_pct }}%）
      </div>
      <div
        style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center"
      >
        <button
          class="mini primary"
          :disabled="resolving"
          @click="resolve('TRUST_PRIMARY')"
        >
          以扶摇为准
        </button>
        <button
          class="mini primary"
          :disabled="resolving"
          @click="resolve('TRUST_BACKUP')"
        >
          以 iFinD 为准
        </button>
        <input
          v-model="manualValues[d.condition_id]"
          type="number"
          step="0.01"
          :placeholder="`手工确认值（${d.citation.unit}）`"
          style="width: 150px; padding: 3px 7px; font-size: 12px"
        />
        <button
          class="mini"
          :disabled="
            resolving ||
            manualValues[d.condition_id] === '' ||
            manualValues[d.condition_id] == null
          "
          @click="
            resolve(
              'MANUAL',
              d.condition_id,
              Number(manualValues[d.condition_id]),
            )
          "
        >
          用此值判定
        </button>
      </div>
    </div>

    <div v-if="taskHalted" class="incident-body">
      任务因连续数据失败熔断（ERROR_HALT）。确认数据源恢复后可解除：
      <button
        class="mini primary"
        :disabled="resolving"
        @click="resolve('CLEAR')"
      >
        解除熔断并恢复
      </button>
    </div>
    <div v-if="error" class="banner banner-bad" role="alert">{{ error }}</div>
  </div>
</template>
