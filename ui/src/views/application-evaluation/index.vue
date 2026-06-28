<template>
  <div class="evaluation-page">
    <div class="evaluation-header">
      <h2>{{ $t('views.evaluation.title') }}</h2>
      <el-button type="primary" @click="openCreateDialog">
        {{ $t('views.evaluation.createConfig') }}
      </el-button>
    </div>

    <!-- Stats Cards -->
    <el-row :gutter="20" class="stats-row" v-if="stats">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-label">{{ $t('views.evaluation.avgFaithfulness') }}</div>
          <div class="stat-value">{{ stats.avg_faithfulness?.toFixed(3) || '-' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-label">{{ $t('views.evaluation.avgAnswerRelevancy') }}</div>
          <div class="stat-value">{{ stats.avg_answer_relevancy?.toFixed(3) || '-' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-label">{{ $t('views.evaluation.totalEvaluations') }}</div>
          <div class="stat-value">{{ stats.total_count || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-label">{{ $t('views.evaluation.activeConfigs') }}</div>
          <div class="stat-value">{{ configs.filter((c: any) => c.is_active).length }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Trend Chart -->
    <el-card class="chart-card" v-if="stats && stats.trend_data?.length > 0">
      <div class="chart-container" ref="chartRef"></div>
    </el-card>

    <!-- Config List + Results Table -->
    <el-tabs v-model="activeTab">
      <el-tab-pane :label="$t('views.evaluation.configs')" name="configs">
        <el-table :data="configs" stripe>
          <el-table-column prop="name" :label="$t('views.evaluation.name')" />
          <el-table-column prop="metrics_display" :label="$t('views.evaluation.metrics')" />
          <el-table-column prop="schedule_crontab" :label="$t('views.evaluation.schedule')" />
          <el-table-column prop="is_active" :label="$t('views.evaluation.status')">
            <template #default="{ row }">
              <el-switch :model-value="row.is_active" disabled />
            </template>
          </el-table-column>
          <el-table-column :label="$t('views.evaluation.actions')" width="280">
            <template #default="{ row }">
              <el-button size="small" @click="triggerRun(row)">Run</el-button>
              <el-button size="small" @click="openEditDialog(row)">Edit</el-button>
              <el-button size="small" type="danger" @click="deleteConfig(row)">Delete</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane :label="$t('views.evaluation.results')" name="results">
        <el-select v-model="filterConfigId" :placeholder="$t('views.evaluation.filterConfig')" clearable @change="loadResults" class="filter-select">
          <el-option v-for="c in configs" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <el-table :data="results" stripe v-loading="resultsLoading">
          <el-table-column prop="question" :label="$t('views.evaluation.question')" width="200" show-overflow-tooltip />
          <el-table-column prop="answer" :label="$t('views.evaluation.answer')" width="250" show-overflow-tooltip />
          <el-table-column prop="faithfulness_score" :label="$t('views.evaluation.faithfulness')" width="100">
            <template #default="{ row }">
              <span :class="scoreClass(row.faithfulness_score)">{{ row.faithfulness_score?.toFixed(3) || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="answer_relevancy_score" :label="$t('views.evaluation.answerRelevancy')" width="120">
            <template #default="{ row }">
              <span :class="scoreClass(row.answer_relevancy_score)">{{ row.answer_relevancy_score?.toFixed(3) || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="run_at" :label="$t('views.evaluation.runAt')" width="160" />
        </el-table>
        <el-pagination
          v-if="resultTotal > 20"
          v-model:current-page="resultPage"
          :page-size="20"
          :total="resultTotal"
          layout="prev, pager, next"
          @change="loadResults"
        />
      </el-tab-pane>
    </el-tabs>

    <EvaluationFormDialog
      v-model:visible="dialogVisible"
      :config="editingConfig"
      @saved="onConfigSaved"
    />
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import {
  getEvaluationConfigs,
  getEvaluationResults,
  getEvaluationStats,
  triggerEvaluation,
  deleteEvaluationConfig,
} from '@/api/application/evaluation'
import type { EvaluationConfig } from '@/api/application/evaluation'
import EvaluationFormDialog from './component/EvaluationFormDialog.vue'

const props = defineProps<{ applicationId?: string }>()

const chartRef = ref<HTMLElement>()
const activeTab = ref('configs')
const dialogVisible = ref(false)
const editingConfig = ref<EvaluationConfig | null>(null)
const configs = ref<EvaluationConfig[]>([])
const results = ref<any[]>([])
const stats = ref<any>(null)
const filterConfigId = ref<string | null>(null)
const resultPage = ref(1)
const resultTotal = ref(0)
const resultsLoading = ref(false)

async function loadConfigs() {
  const res = await getEvaluationConfigs(props.applicationId!)
  configs.value = res.data || []
}
async function loadStats() {
  const res = await getEvaluationStats(props.applicationId!, 30)
  stats.value = res.data
  await nextTick()
  renderChart()
}
async function loadResults() {
  resultsLoading.value = true
  const res = await getEvaluationResults(props.applicationId!, filterConfigId.value || undefined, resultPage.value)
  results.value = res.data?.results || []
  resultTotal.value = res.data?.total || 0
  resultsLoading.value = false
}

function renderChart() {
  if (!chartRef.value || !stats.value?.trend_data?.length) return
  const chart = echarts.init(chartRef.value)
  const data = stats.value.trend_data
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['Faithfulness', 'AnswerRelevancy'] },
    xAxis: { type: 'category', data: data.map((d: any) => d.date) },
    yAxis: { type: 'value', min: 0, max: 1 },
    series: [
      { name: 'Faithfulness', type: 'line', data: data.map((d: any) => d.avg_faithfulness), smooth: true },
      { name: 'AnswerRelevancy', type: 'line', data: data.map((d: any) => d.avg_answer_relevancy), smooth: true },
    ],
  })
}

function scoreClass(score: number | null) {
  if (score === null) return ''
  if (score >= 0.8) return 'score-good'
  if (score >= 0.5) return 'score-ok'
  return 'score-bad'
}

function openCreateDialog() {
  editingConfig.value = null
  dialogVisible.value = true
}
function openEditDialog(config: EvaluationConfig) {
  editingConfig.value = { ...config }
  dialogVisible.value = true
}
async function deleteConfig(config: EvaluationConfig) {
  await deleteEvaluationConfig(props.applicationId!, config.id!)
  await loadConfigs()
}
async function triggerRun(config: EvaluationConfig) {
  await triggerEvaluation(props.applicationId!, config.id!)
}
function onConfigSaved() {
  dialogVisible.value = false
  loadConfigs()
}

onMounted(() => {
  loadConfigs()
  loadStats()
  loadResults()
})
</script>

<style scoped lang="scss">
.evaluation-page { padding: 20px; }
.evaluation-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.stats-row { margin-bottom: 20px; }
.stat-label { font-size: 14px; color: #909399; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 600; color: #303133; }
.chart-card { margin-bottom: 20px; }
.chart-container { height: 300px; }
.filter-select { width: 250px; margin-bottom: 12px; }
.score-good { color: #67c23a; font-weight: 600; }
.score-ok { color: #e6a23c; font-weight: 600; }
.score-bad { color: #f56c6c; font-weight: 600; }
</style>
