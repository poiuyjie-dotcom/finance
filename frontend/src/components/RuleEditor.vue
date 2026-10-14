<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({ selectedTask: Object })
const emit = defineEmits(['changed', 'created', 'refreshDetail'])

const nl = ref('')
const parsing = ref(false)
const parseResult = ref(null)     // { compliance_passed, compliance_notice, draft_rule, ... }
const draft = ref(null)           // 编辑中的规则副本
const editingExisting = ref(false) // 是否在编辑已存在任务的规则
const saving = ref(false)
const lastDiff = ref(null)
const versions = ref([])
const showVersions = ref(false)
const rollbackTo = ref(null)
const errMsg = ref('')

const EXAMPLES = [
  '当宁德时代跌破 290 元且换手率大于 3%，或者出现减持公告时提醒我',
  '比亚迪进入热榜前 10 名，且碳酸锂主力期货跌幅超过 4%',
  '沪深300 PE 低于 13.5 倍，或单日跌幅超过 2% 时提醒我',
  '当比亚迪跌破 240 元时提醒我满仓抄底',
  '推荐几只明天必涨的牛股',
]

const METRICS = [
  { v: 'last_price', n: '最新价', unit: '元' },
  { v: 'pct_chg', n: '当日涨跌幅', unit: '%' },
  { v: 'turnover_rate_pct', n: '换手率', unit: '%' },
  { v: 'pe_ttm', n: '市盈率PE(TTM)', unit: '倍' },
  { v: 'hot_rank', n: '热榜排名', unit: '名' },
  { v: 'announcement_keywords', n: '公告关键词', unit: '篇' },
  { v: 'days_to_earnings', n: '距财报披露', unit: '个交易日' },
  { v: 'futures_pct_chg', n: '期货涨跌幅', unit: '%' },
]
const OPS = ['>', '>=', '<', '<=', '==', 'CONTAINS_ANY', 'NOT_CONTAINS', 'IN_WINDOW', 'OUTSIDE_WINDOW']

async function parse() {
  parsing.value = true; parseResult.value = null; errMsg.value = ''
  try {
    parseResult.value = await api.parseNl(nl.value)
    if (parseResult.value.draft_rule && parseResult.value.compliance_passed) {
      draft.value = JSON.parse(JSON.stringify(parseResult.value.draft_rule))
      editingExisting.value = false
    }
  } catch (e) { errMsg.value = e.message } finally { parsing.value = false }
}

// 选中任务时载入其规则供修改
watch(() => props.selectedTask, (st) => {
  if (st?.current_rule) {
    draft.value = JSON.parse(JSON.stringify(st.current_rule))
    editingExisting.value = true
    lastDiff.value = null
    if (!nl.value) nl.value = st.current_rule.original_nl_query || ''
  }
}, { immediate: true })

const allConditions = computed(() => draft.value ? draft.value.rule_tree.conditions : [])
const subGroups = computed(() => draft.value ? (draft.value.rule_tree.sub_groups || []) : [])
const hasSub = computed(() => subGroups.value.length > 0)

function updateUnit(cond) {
  const m = METRICS.find(x => x.v === cond.metric_field)
  if (m) cond.unit = m.unit
}

function removeCond(list, idx) { list.splice(idx, 1); if (!list.length) list.push(newCond()) }
function newCond() {
  return { condition_id: `cond_${Date.now() % 100000}`, label: '新条件', category: 'PRICE_VALUATION',
    target_code: '300750.SZ', target_name: '宁德时代', metric_field: 'last_price', operator: '<',
    threshold_value: 200, unit: '元', statistical_caliber: '扶摇行情快照（不复权实时价）',
    primary_source: 'FUYAO_QUOTE', backup_source: null, staleness_tolerance_seconds: 900 }
}

function dirtyVsSelected() {
  if (!editingExisting.value || !props.selectedTask?.current_rule) return true
  return JSON.stringify(draft.value) !== JSON.stringify(props.selectedTask.current_rule)
}

async function save() {
  saving.value = true; errMsg.value = ''; lastDiff.value = null
  try {
    if (editingExisting.value) {
      const r = await api.updateRule(props.selectedTask.task.id, draft.value, '前端可视化编辑器修改')
      lastDiff.value = r.latest_diff
      emit('changed'); emit('refreshDetail', props.selectedTask.task.id)
      loadVersions()
    } else {
      const r = await api.createTask(draft.value)
      emit('changed'); emit('created', r.id)
    }
  } catch (e) { errMsg.value = e.message } finally { saving.value = false }
}

async function loadVersions() {
  if (!props.selectedTask) return
  versions.value = await api.versions(props.selectedTask.task.id)
  showVersions.value = true
}

async function doRollback(v) {
  rollbackTo.value = v
  await api.rollback(props.selectedTask.task.id, v)
  emit('changed'); emit('refreshDetail', props.selectedTask.task.id)
  loadVersions()
  rollbackTo.value = null
}
</script>

<template>
  <div class="panel">
    <div class="panel-title">① 自然语言 → 可检查规则 <span class="sub">AI 编译为结构化规则，所有阈值可在下方修改</span></div>
    <textarea v-model="nl" rows="2" placeholder="输入关注点，例如：当宁德时代跌破 290 元且换手率大于 3%，或者出现减持公告时提醒我"></textarea>
    <div class="example-chips">
      <span v-for="(ex, i) in EXAMPLES.slice(0, 3)" :key="i" class="example-chip" @click="nl = ex">示例{{ i + 1 }}</span>
      <span class="example-chip bad" @click="nl = EXAMPLES[3]">混合意图示例（含主观词）</span>
      <span class="example-chip bad" @click="nl = EXAMPLES[4]">合规反例（纯荐股）</span>
    </div>
    <div style="margin-top:9px; display:flex; gap:8px; align-items:center">
      <button class="primary" @click="parse" :disabled="parsing || !nl.trim()">
        <span v-if="parsing" class="spin"></span> AI 解析为可检查规则
      </button>
      <span style="font-size:11px;color:var(--dim)" v-if="parseResult?.used_llm">（LLM 通道）</span>
      <span style="font-size:11px;color:var(--dim)" v-else-if="parseResult">（确定性编译器通道）</span>
    </div>

    <!-- 合规拦截 -->
    <div v-if="parseResult && !parseResult.compliance_passed" class="banner banner-bad" style="margin-top:9px">
      ⛔ <b>合规边界拦截</b>：{{ parseResult.compliance_notice }}
    </div>
    <div v-if="parseResult?.compliance_notice && parseResult.compliance_passed" class="banner banner-warn" style="margin-top:9px">
      ⚠️ {{ parseResult.compliance_notice }}
    </div>
    <div v-if="errMsg" class="banner banner-bad" style="margin-top:9px">解析失败：{{ errMsg }}</div>
  </div>

  <div class="panel" v-if="draft">
    <div class="panel-title">
      ② 规则树编辑器
      <span class="sub">
        {{ editingExisting ? `正在编辑「${selectedTask?.task?.title}」` : '新任务草稿' }}
        <template v-if="editingExisting && dirtyVsSelected()">· 有未保存变更（保存后生成 v{{ (selectedTask?.task?.current_version || 1) + 1 }}）</template>
      </span>
    </div>

    <div v-if="draft.ai_interpretation_summary" class="banner banner-info" style="margin-bottom:10px">
      🤖 {{ draft.ai_interpretation_summary }}
    </div>

    <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px">
      <span style="font-size:12px;color:var(--muted)">顶层逻辑：</span>
      <label style="display:flex;gap:4px;align-items:center;font-size:12px;cursor:pointer">
        <input type="radio" :value="'AND'" v-model="draft.rule_tree.logical_op" style="width:auto" /> 全部满足 (AND)
      </label>
      <label style="display:flex;gap:4px;align-items:center;font-size:12px;cursor:pointer">
        <input type="radio" :value="'OR'" v-model="draft.rule_tree.logical_op" style="width:auto" /> 任一满足 (OR)
      </label>
    </div>

    <!-- 子组（AND 包裹的组合条件） -->
    <div v-for="(g, gi) in subGroups" :key="gi" class="group-box">
      <span class="group-label">{{ g.logical_op === 'AND' ? '以下全部满足' : '以下任一满足' }}</span>
      <div v-for="(c, ci) in g.conditions" :key="c.condition_id" class="cond-card">
        <div class="cond-head">
          <span class="badge badge-violet">{{ c.condition_id }}</span>
          <input v-model="c.label" style="flex:1; padding:3px 7px; font-size:12px" />
          <button class="mini danger" @click="removeCond(g.conditions, ci)">删除</button>
        </div>
        <div class="cond-grid">
          <input v-model="c.target_code" title="标的代码" />
          <input v-model="c.target_name" title="标的名称" />
          <select v-model="c.metric_field" @change="updateUnit(c)">
            <option v-for="m in METRICS" :key="m.v" :value="m.v">{{ m.n }}</option>
          </select>
          <select v-model="c.operator">
            <option v-for="o in OPS" :key="o" :value="o">{{ o }}</option>
          </select>
        </div>
        <div class="cond-grid" style="margin-top:6px; grid-template-columns: 1fr 60px 110px">
          <input v-model="c.threshold_value" title="阈值（关键词条件用逗号分隔）" />
          <span class="unit-label">{{ c.unit }}</span>
          <input v-model.number="c.staleness_tolerance_seconds" title="数据过期容忍（秒）" />
        </div>
        <div class="caliber">口径：{{ c.statistical_caliber }} · 主源 {{ c.primary_source }}</div>
      </div>
    </div>

    <!-- 顶层平铺条件 -->
    <template v-if="!hasSub">
      <div v-for="(c, ci) in allConditions" :key="c.condition_id" class="cond-card">
        <div class="cond-head">
          <span class="badge badge-violet">{{ c.condition_id }}</span>
          <input v-model="c.label" style="flex:1; padding:3px 7px; font-size:12px" />
          <button class="mini danger" @click="removeCond(allConditions, ci)">删除</button>
        </div>
        <div class="cond-grid">
          <input v-model="c.target_code" />
          <input v-model="c.target_name" />
          <select v-model="c.metric_field" @change="updateUnit(c)">
            <option v-for="m in METRICS" :key="m.v" :value="m.v">{{ m.n }}</option>
          </select>
          <select v-model="c.operator">
            <option v-for="o in OPS" :key="o" :value="o">{{ o }}</option>
          </select>
        </div>
        <div class="cond-grid" style="margin-top:6px; grid-template-columns: 1fr 60px 110px">
          <input v-model="c.threshold_value" />
          <span class="unit-label">{{ c.unit }}</span>
          <input v-model.number="c.staleness_tolerance_seconds" title="数据过期容忍（秒）" />
        </div>
        <div class="caliber">口径：{{ c.statistical_caliber }} · 主源 {{ c.primary_source }}</div>
      </div>
    </template>
    <button class="mini" @click="allConditions.push(newCond())" v-if="!hasSub">+ 新增顶层条件</button>

    <!-- 调度与抑制策略 -->
    <div style="margin-top:12px; border-top:1px dashed var(--border); padding-top:10px">
      <div class="panel-title" style="margin-bottom:7px">③ 调度与抑制策略</div>
      <div class="cond-grid" style="grid-template-columns: repeat(4, 1fr)">
        <label style="font-size:11px;color:var(--dim)">巡检间隔(秒)<input v-model.number="draft.schedule_config.interval_seconds" type="number" /></label>
        <label style="font-size:11px;color:var(--dim)">冷却静默(分)<input v-model.number="draft.schedule_config.cooldown_minutes" type="number" /></label>
        <label style="font-size:11px;color:var(--dim)">去重窗口(分)<input v-model.number="draft.schedule_config.dedup_window_minutes" type="number" /></label>
        <label style="font-size:11px;color:var(--dim)">过期容忍(秒)<input :value="900" disabled /></label>
      </div>
    </div>

    <div style="margin-top:12px; display:flex; gap:8px; align-items:center">
      <button class="primary" @click="save" :disabled="saving">
        {{ editingExisting ? '保存并生成新版本' : '创建监控任务 (v1)' }}
      </button>
      <button v-if="editingExisting" @click="loadVersions">版本历史与回滚</button>
    </div>
    <div v-if="lastDiff" class="banner banner-good" style="margin-top:9px">
      ✅ 已升级至 v{{ lastDiff.to_version }}（{{ lastDiff.changed_count }} 处字段变更，冷却与去重状态已重置）
      <div v-for="(c, i) in lastDiff.changes.slice(0, 6)" :key="i" class="diff-item" style="margin-top:5px">
        <span class="diff-path">{{ c.path }}</span>
        <span class="diff-old">{{ c.old_value }}</span> → <span class="diff-new">{{ c.new_value }}</span>
      </div>
    </div>

    <!-- 版本抽屉 -->
    <div v-if="showVersions" class="cite-pop" @click.self="showVersions = false">
      <div class="cite-card">
        <h3>规则版本演进（{{ selectedTask?.task?.title }}）</h3>
        <div v-for="v in versions" :key="v.version_num" style="margin-bottom:10px">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="badge badge-blue">v{{ v.version_num }}</span>
            <span style="font-size:11px;color:var(--dim)">{{ v.change_type }} {{ v.change_reason || '' }}</span>
            <button class="mini" v-if="v.version_num !== selectedTask?.task?.current_version" @click="doRollback(v.version_num)">
              回滚到此版本
            </button>
          </div>
          <template v-if="v.diff_summary?.changes?.length">
            <div v-for="(c, i) in v.diff_summary.changes.slice(0, 8)" :key="i" class="diff-item" style="margin-top:5px">
              <span class="diff-path">{{ c.path }}</span>
              <span class="diff-old">{{ c.old_value }}</span> → <span class="diff-new">{{ c.new_value }}</span>
            </div>
          </template>
        </div>
        <button @click="showVersions = false">关闭</button>
      </div>
    </div>
  </div>
</template>
