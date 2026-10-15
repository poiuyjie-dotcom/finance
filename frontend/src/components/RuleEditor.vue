<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps({ selectedTask: Object, editRuleId: String })
const emit = defineEmits(['changed', 'created', 'refreshDetail', 'editClosed'])

const nl = ref('')
const parsing = ref(false)
const parseResult = ref(null)     // { compliance_passed, compliance_notice, draft_rule, ... }
const draft = ref(null)           // 编辑中的规则副本
const mode = ref('empty')         // empty | draft(新任务草稿) | edit(编辑已存在任务)
const editingTaskId = ref(null)
const editingVersion = ref(1)
const saving = ref(false)
const createdMsg = ref('')
const lastDiff = ref(null)
const versions = ref([])
const showVersions = ref(false)
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
  parsing.value = true; parseResult.value = null; errMsg.value = ''; createdMsg.value = ''
  try {
    parseResult.value = await api.parseNl(nl.value)
    if (parseResult.value.draft_rule && parseResult.value.compliance_passed) {
      draft.value = JSON.parse(JSON.stringify(parseResult.value.draft_rule))
      editingTaskId.value = null
      mode.value = 'draft'
    }
  } catch (e) { errMsg.value = e.message } finally { parsing.value = false }
}

// 显式进入编辑模式（左栏「编辑规则」按钮）；收起后回到空态
watch(() => props.editRuleId, async (id) => {
  if (id) {
    try {
      const detail = await api.getTask(id)
      draft.value = JSON.parse(JSON.stringify(detail.current_rule))
      editingTaskId.value = id
      editingVersion.value = detail.task.current_version
      mode.value = 'edit'
      if (!nl.value) nl.value = detail.current_rule.original_nl_query || ''
      lastDiff.value = null
      versions.value = []
    } catch (e) { errMsg.value = e.message }
  } else {
    mode.value = 'empty'; draft.value = null; editingTaskId.value = null; lastDiff.value = null
  }
}, { immediate: true })

function closeEditor() {
  mode.value = 'empty'; draft.value = null; editingTaskId.value = null
  lastDiff.value = null; parseResult.value = null
  emit('editClosed')
}

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

async function save() {
  saving.value = true; errMsg.value = ''; lastDiff.value = null
  try {
    if (mode.value === 'edit') {
      const r = await api.updateRule(editingTaskId.value, draft.value, '前端可视化编辑器修改')
      lastDiff.value = r.latest_diff
      editingVersion.value = r.current_version
      emit('changed'); emit('refreshDetail', editingTaskId.value)
    } else {
      const r = await api.createTask(draft.value)
      createdMsg.value = `任务已创建（v1），已出现在左侧列表，点击它的「立即巡检」查看首次归因。`
      closeEditor()
      emit('changed')
    }
  } catch (e) { errMsg.value = e.message } finally { saving.value = false }
}

async function loadVersions() {
  if (!editingTaskId.value) return
  versions.value = await api.versions(editingTaskId.value)
  showVersions.value = true
}

async function doRollback(v) {
  await api.rollback(editingTaskId.value, v)
  emit('changed'); emit('refreshDetail', editingTaskId.value)
  loadVersions()
}
</script>

<template>
  <!-- ① 主入口：自然语言 -->
  <div class="panel">
    <div class="panel-title">① 自然语言 → 可检查规则 <span class="sub">主入口：输入关注点，AI 编译为可修改的结构化规则</span></div>
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

    <div v-if="parseResult && !parseResult.compliance_passed" class="banner banner-bad" style="margin-top:9px">
      ⛔ <b>合规边界拦截</b>：{{ parseResult.compliance_notice }}
    </div>
    <div v-if="parseResult?.compliance_notice && parseResult.compliance_passed" class="banner banner-warn" style="margin-top:9px">
      ⚠️ {{ parseResult.compliance_notice }}
    </div>
    <div v-if="parseResult?.jev" class="banner banner-info" style="margin-top:8px; font-size:11px">
      🧠 <b>Jev 语义护栏</b>（{{ parseResult.jev.model }}）：
      预测/荐股意图概率 <b>{{ (parseResult.jev.wants_prediction ?? 0).toFixed(2) }}</b> ·
      意图分类 <b>{{ {objective_monitor: '客观监控', mixed: '混合意图', pure_advice_request: '纯违规诉求'}[parseResult.jev.intent] || parseResult.jev.intent }}</b>
      <template v-if="parseResult.jev.intent_confidence != null">（置信度 {{ parseResult.jev.intent_confidence.toFixed(2) }}）</template>
      <span style="color:var(--dim)">—— 概率由 Jev 输出，拦截/放行决策由确定性代码执行</span>
    </div>
    <div v-if="createdMsg" class="banner banner-good" style="margin-top:9px">✅ {{ createdMsg }}</div>
    <div v-if="errMsg" class="banner banner-bad" style="margin-top:9px">操作失败：{{ errMsg }}</div>
  </div>

  <!-- ② 编辑器：空态指引 -->
  <div class="panel" v-if="mode === 'empty'">
    <div class="panel-title">② 规则树编辑器</div>
    <div class="empty-guide">
      <div class="empty-step">📌 在上方 <b>①</b> 输入关注点并解析，这里会生成<b>可编辑的规则树草稿</b>（算子 / 阈值 / 口径均可修改）</div>
      <div class="empty-step">✏️ 想修改已有任务：在左侧任务卡点 <b>「编辑规则」</b>，保存后自动生成新版本与 Diff</div>
      <div class="empty-step">🔍 只想查看：直接点左侧任务卡，右栏展示「为什么触发 / 未触发」逐条件归因</div>
    </div>
  </div>

  <!-- ② 编辑器：草稿 / 编辑模式 -->
  <div class="panel" v-if="draft && mode !== 'empty'">
    <div class="panel-title">
      ② 规则树编辑器
      <span class="badge" :class="mode === 'edit' ? 'badge-blue' : 'badge-violet'">
        {{ mode === 'edit' ? `编辑：${selectedTask?.task?.title || ''} v${editingVersion}` : '新任务草稿' }}
      </span>
      <button class="mini" style="margin-left:auto" @click="closeEditor">收起 ✕</button>
    </div>

    <div v-if="mode === 'edit' && lastDiff == null" class="banner banner-info" style="margin-bottom:10px; font-size:11px">
      正在编辑已有任务：修改任意阈值 / 算子后保存，将生成新版本并自动重置该任务的冷却与去重状态。
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
        {{ mode === 'edit' ? `保存并生成 v${editingVersion + 1}` : '创建监控任务 (v1)' }}
      </button>
      <button v-if="mode === 'edit'" @click="loadVersions">版本历史与回滚</button>
      <button @click="closeEditor">收起</button>
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
        <h3>规则版本演进</h3>
        <div v-for="v in versions" :key="v.version_num" style="margin-bottom:10px">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="badge badge-blue">v{{ v.version_num }}</span>
            <span style="font-size:11px;color:var(--dim)">{{ v.change_type }} {{ v.change_reason || '' }}</span>
            <button class="mini" v-if="v.version_num !== editingVersion" @click="doRollback(v.version_num)">
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
