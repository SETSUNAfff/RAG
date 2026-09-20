<template>
  <div class="evaluation-view">
    <div class="eval-panel">
      <header class="docs-header">
        <div>
          <div class="page-title">效果评测</div>
          <div class="page-subtitle">批量评测问答效果、检索命中率与引用质量</div>
        </div>
        <div class="eval-actions">
          <el-button icon="el-icon-upload2" @click="openImport">导入评测集</el-button>
          <el-button type="primary" icon="el-icon-video-play" :loading="running" @click="startEvaluation">
            运行评测
          </el-button>
        </div>
      </header>

      <div v-if="latestRun && latestRun.metrics_summary" class="eval-summary">
        <div class="metric-grid">
          <div class="metric-card" v-for="metric in summaryMetrics" :key="metric.key">
            <div class="metric-label">{{ metric.label }}</div>
            <div class="metric-value">{{ formatNumber(latestRun.metrics_summary[metric.key]) }}</div>
          </div>
        </div>
        <div class="run-status-line">
          <span :class="['run-status', latestRun.status]">{{ statusLabel(latestRun.status) }}</span>
          <span>{{ latestRun.message || '' }}</span>
        </div>
      </div>

      <div class="eval-tabs">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="用例管理" name="cases">
            <div class="docs-toolbar">
              <el-input
                v-model="caseFilters.keyword"
                placeholder="搜索问题"
                clearable
                prefix-icon="el-icon-search"
                style="width: 220px"
                @keyup.enter.native="searchCases"
                @clear="searchCases"
              ></el-input>
              <el-select v-model="caseFilters.difficulty" placeholder="难度" clearable style="width: 120px" @change="searchCases">
                <el-option label="easy" value="easy"></el-option>
                <el-option label="medium" value="medium"></el-option>
                <el-option label="hard" value="hard"></el-option>
              </el-select>
              <el-button type="primary" icon="el-icon-plus" @click="openCreateCase">新建用例</el-button>
            </div>

            <div class="docs-table">
              <el-table :data="cases" v-loading="caseLoading" @selection-change="onCaseSelectionChange">
                <el-table-column type="selection" width="44"></el-table-column>
                <el-table-column prop="external_id" label="编号" width="110"></el-table-column>
                <el-table-column prop="question" label="问题" min-width="260" show-overflow-tooltip></el-table-column>
                <el-table-column prop="chapter" label="章节" min-width="150" show-overflow-tooltip></el-table-column>
                <el-table-column prop="difficulty" label="难度" width="90">
                  <template slot-scope="scope">
                    <el-tag :type="difficultyTagType(scope.row.difficulty)" size="small">{{ scope.row.difficulty }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="status" label="状态" width="110">
                  <template slot-scope="scope">
                    <el-tag :type="statusTagType(scope.row.status)" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="期望 chunk" width="110">
                  <template slot-scope="scope">
                    <span>{{ Array.isArray(scope.row.expected_chunk_ids) ? scope.row.expected_chunk_ids.length : 0 }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="150">
                  <template slot-scope="scope">
                    <el-button type="text" icon="el-icon-edit" @click="openEditCase(scope.row)">编辑</el-button>
                    <el-button type="text" class="danger-text" icon="el-icon-delete" @click="removeCase(scope.row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="docs-footer">
              <el-pagination
                background
                layout="total, prev, pager, next"
                :total="caseTotal"
                :current-page="casePage"
                :page-size="casePageSize"
                @current-change="handleCasePageChange"
              ></el-pagination>
            </div>
          </el-tab-pane>

          <el-tab-pane label="评测历史" name="runs">
            <div class="docs-table">
              <el-table :data="runs" v-loading="runLoading" @row-click="openRunDetail">
                <el-table-column prop="id" label="ID" width="80"></el-table-column>
                <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip></el-table-column>
                <el-table-column prop="status" label="状态" width="100">
                  <template slot-scope="scope">
                    <el-tag :type="statusTagType(scope.row.status)" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="completed_cases" label="进度" width="120">
                  <template slot-scope="scope">{{ scope.row.completed_cases }} / {{ scope.row.total_cases }}</template>
                </el-table-column>
                <el-table-column prop="message" label="说明" min-width="260" show-overflow-tooltip></el-table-column>
                <el-table-column prop="completed_at" label="完成时间" width="170">
                  <template slot-scope="scope">{{ formatTime(scope.row.completed_at) }}</template>
                </el-table-column>
              </el-table>
            </div>
            <div class="docs-footer">
              <el-pagination
                background
                layout="total, prev, pager, next"
                :total="runTotal"
                :current-page="runPage"
                :page-size="runPageSize"
                @current-change="handleRunPageChange"
              ></el-pagination>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>

    <el-dialog :title="editingCase ? '编辑用例' : '新建用例'" :visible.sync="caseDialogVisible" width="640px" top="6vh">
      <el-form label-width="110px" :model="caseForm">
        <el-form-item label="编号" required>
          <el-input v-model="caseForm.external_id" placeholder="case-001"></el-input>
        </el-form-item>
        <el-form-item label="问题" required>
          <el-input v-model="caseForm.question" type="textarea" :rows="2"></el-input>
        </el-form-item>
        <el-form-item label="期望答案" required>
          <el-input v-model="caseForm.expected_answer" type="textarea" :rows="4"></el-input>
        </el-form-item>
        <el-form-item label="文档标题">
          <el-input v-model="caseForm.expected_document_titles" placeholder="每行一个标题"></el-input>
        </el-form-item>
        <el-form-item label="期望原文">
          <el-input v-model="caseForm.expected_source_text" type="textarea" :rows="4"></el-input>
        </el-form-item>
        <el-form-item label="章节">
          <el-input v-model="caseForm.chapter"></el-input>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="caseForm.difficulty" style="width: 100%">
            <el-option label="easy" value="easy"></el-option>
            <el-option label="medium" value="medium"></el-option>
            <el-option label="hard" value="hard"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="caseForm.status" style="width: 100%">
            <el-option label="active" value="active"></el-option>
            <el-option label="archived" value="archived"></el-option>
            <el-option label="待人工复核" value="pending_review"></el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <div slot="footer">
        <el-button @click="caseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingCase" @click="saveCase">保存</el-button>
      </div>
    </el-dialog>

    <el-dialog title="导入评测集" :visible.sync="importDialogVisible" width="680px" top="6vh">
      <el-alert
        title="粘贴 evaluation_cases.json 的内容，或仅粘贴其中的 cases 数组。"
        type="info"
        :closable="false"
        show-icon
      ></el-alert>
      <el-input
        v-model="importText"
        type="textarea"
        :rows="12"
        class="import-json-input"
        placeholder='{"cases": [...]}'
      ></el-input>
      <el-checkbox v-model="importReplace">清空后重新导入</el-checkbox>
      <div slot="footer">
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" @click="submitImport">导入</el-button>
      </div>
    </el-dialog>

    <el-drawer :visible.sync="runDetailVisible" size="720px" title="评测详情" direction="rtl">
      <div v-if="detailRun" class="eval-drawer-body">
        <div v-if="detailRun.metrics_summary" class="metric-grid">
          <div class="metric-card" v-for="metric in summaryMetrics" :key="metric.key">
            <div class="metric-label">{{ metric.label }}</div>
            <div class="metric-value">{{ formatNumber(detailRun.metrics_summary[metric.key]) }}</div>
          </div>
        </div>

        <div v-if="detailRun.metrics_summary && detailRun.metrics_summary.difficulty" class="group-block">
          <div class="group-title">按难度</div>
          <div class="group-item" v-for="(group, name) in detailRun.metrics_summary.difficulty" :key="name">
            <span class="group-name">{{ name }}</span>
            <span class="group-value">recall {{ formatNumber(group.metrics.retrieval_recall) }}</span>
            <span class="group-value">rouge {{ formatNumber(group.metrics.rouge_l) }}</span>
          </div>
        </div>

        <div class="group-block">
          <div class="group-title">结果明细</div>
          <el-table :data="results" v-loading="resultLoading" size="small">
            <el-table-column type="expand">
              <template slot-scope="scope">
                <div class="result-detail">
                  <div class="detail-label">期望答案</div>
                  <div class="detail-text">{{ (scope.row.raw_json && scope.row.raw_json.expected_answer) || '--' }}</div>
                  <div class="detail-label">实际回答</div>
                  <div class="detail-text">{{ scope.row.answer || '--' }}</div>
                  <div class="detail-label">检索 chunk</div>
                  <div class="detail-text">{{ formatIds(scope.row.retrieved_chunk_ids) }}</div>
                  <div class="detail-label">引用 chunk</div>
                  <div class="detail-text">{{ formatIds(scope.row.citation_chunk_ids) }}</div>
                  <div class="detail-label">检索次数 / 最终证据数</div>
                  <div class="detail-text">
                    {{ (scope.row.raw_json && scope.row.raw_json.tool_call_count) || 0 }}
                    /
                    {{ (scope.row.raw_json && scope.row.raw_json.evidence_chunk_count) || 0 }}
                  </div>
                  <div v-if="scope.row.error" class="detail-label">错误</div>
                  <div v-if="scope.row.error" class="detail-text danger-text">{{ scope.row.error }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="question" label="问题" min-width="220" show-overflow-tooltip></el-table-column>
            <el-table-column prop="difficulty" label="难度" width="90"></el-table-column>
            <el-table-column prop="retrieval_recall" label="召回" width="80">
              <template slot-scope="scope">{{ formatNumber(scope.row.retrieval_recall) }}</template>
            </el-table-column>
            <el-table-column prop="retrieval_precision" label="精确率@1" width="90">
              <template slot-scope="scope">{{ formatNumber(scope.row.retrieval_precision) }}</template>
            </el-table-column>
            <el-table-column prop="recall_at_20" label="召回@20" width="90">
              <template slot-scope="scope">{{ formatNumber(scope.row.recall_at_20) }}</template>
            </el-table-column>
            <el-table-column prop="hit" label="命中" width="70">
              <template slot-scope="scope">{{ scope.row.hit ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column prop="rouge_l" label="ROUGE" width="90">
              <template slot-scope="scope">{{ formatNumber(scope.row.rouge_l) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template slot-scope="scope">
                <el-tag v-if="scope.row.error" type="danger" size="small">失败</el-tag>
                <el-tag v-else-if="scope.row.stale" type="warning" size="small">过期</el-tag>
                <el-tag v-else type="success" size="small">成功</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div class="chunk-pagination">
            <el-pagination
              background
              layout="total, prev, pager, next"
              :total="resultTotal"
              :current-page="resultPage"
              :page-size="resultPageSize"
              @current-change="loadRunResults"
            ></el-pagination>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script>
import {
  createEvaluationCase,
  createEvaluationRun,
  deleteEvaluationCase,
  getEvaluationRun,
  importEvaluationCases,
  listEvaluationCases,
  listEvaluationResults,
  listEvaluationRuns,
  updateEvaluationCase
} from '@/api'
import { getErrorMessage } from '@/api/client'

export default {
  name: 'EvaluationView',
  data() {
    return {
      activeTab: 'cases',
      cases: [],
      caseTotal: 0,
      casePage: 1,
      casePageSize: 20,
      caseLoading: false,
      caseFilters: { keyword: '', difficulty: '' },
      selectedCaseIds: [],
      caseDialogVisible: false,
      editingCase: null,
      savingCase: false,
      caseForm: this.emptyCaseForm(),
      importDialogVisible: false,
      importText: '',
      importReplace: false,
      importing: false,
      runs: [],
      runTotal: 0,
      runPage: 1,
      runPageSize: 20,
      runLoading: false,
      latestRun: null,
      running: false,
      pollTimer: null,
      runDetailVisible: false,
      detailRun: null,
      results: [],
      resultTotal: 0,
      resultPage: 1,
      resultPageSize: 30,
      resultLoading: false,
      summaryMetrics: [
        { key: 'retrieval_precision', label: '检索精确率@1' },
        { key: 'retrieval_recall', label: '检索召回率' },
        { key: 'recall_at_20', label: '召回@20' },
        { key: 'mrr', label: 'MRR' },
        { key: 'hit', label: '命中率' },
        { key: 'rouge_l', label: 'ROUGE-L' },
        { key: 'embedding_sim', label: '语义相似度' },
      ]
    }
  },
  created() {
    this.loadCases()
    this.loadRuns()
  },
  beforeDestroy() {
    this.clearPolling()
  },
  methods: {
    emptyCaseForm() {
      return {
        external_id: '',
        question: '',
        expected_answer: '',
        expected_document_titles: '',
        expected_source_text: '',
        chapter: '',
        difficulty: 'medium',
        status: 'active'
      }
    },
    async loadCases() {
      this.caseLoading = true
      try {
        const data = await listEvaluationCases({
          page: this.casePage,
          page_size: this.casePageSize,
          keyword: this.caseFilters.keyword || undefined,
          difficulty: this.caseFilters.difficulty || undefined
        })
        this.cases = data.items || []
        this.caseTotal = data.total || 0
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.caseLoading = false
      }
    },
    searchCases() {
      this.casePage = 1
      this.loadCases()
    },
    handleCasePageChange(page) {
      this.casePage = page
      this.loadCases()
    },
    onCaseSelectionChange(rows) {
      this.selectedCaseIds = rows.map(item => item.id)
    },
    openCreateCase() {
      this.editingCase = null
      this.caseForm = this.emptyCaseForm()
      this.caseDialogVisible = true
    },
    openEditCase(row) {
      this.editingCase = row
      this.caseForm = {
        external_id: row.external_id,
        question: row.question,
        expected_answer: row.expected_answer,
        expected_document_titles: Array.isArray(row.expected_document_titles)
          ? row.expected_document_titles.join('\n')
          : '',
        expected_source_text: row.expected_source_text || '',
        chapter: row.chapter || '',
        difficulty: row.difficulty || 'medium',
        status: row.status || 'active'
      }
      this.caseDialogVisible = true
    },
    async saveCase() {
      if (!this.caseForm.external_id || !this.caseForm.question || !this.caseForm.expected_answer) {
        this.$message.warning('编号、问题、期望答案不能为空')
        return
      }
      this.savingCase = true
      try {
        const payload = {
          ...this.caseForm,
          expected_document_titles: this.splitTitles(this.caseForm.expected_document_titles)
        }
        if (this.editingCase) {
          await updateEvaluationCase(this.editingCase.id, payload)
        } else {
          await createEvaluationCase(payload)
        }
        this.$message.success('已保存')
        this.caseDialogVisible = false
        this.loadCases()
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.savingCase = false
      }
    },
    async removeCase(row) {
      try {
        await this.$confirm(`确认删除用例「${row.external_id}」？`, '删除用例', { type: 'warning' })
        await deleteEvaluationCase(row.id)
        this.$message.success('已删除')
        this.loadCases()
      } catch (error) {
        if (error !== 'cancel') this.$message.error(getErrorMessage(error))
      }
    },
    splitTitles(value) {
      if (!value) return []
      return value.split('\n').map(item => item.trim()).filter(Boolean)
    },
    openImport() {
      this.importText = ''
      this.importReplace = false
      this.importDialogVisible = true
    },
    async submitImport() {
      try {
        const parsed = JSON.parse(this.importText)
        const cases = Array.isArray(parsed) ? parsed : parsed.cases
        if (!Array.isArray(cases) || !cases.length) {
          throw new Error('未找到 cases 数组')
        }
        this.importing = true
        const result = await importEvaluationCases({ replace: this.importReplace, cases })
        this.$message.success(`新增 ${result.created}，更新 ${result.updated}，跳过 ${result.skipped}`)
        this.importDialogVisible = false
        this.loadCases()
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.importing = false
      }
    },
    async startEvaluation() {
      if (this.running) return
      this.running = true
      try {
        const run = await createEvaluationRun({
          case_ids: this.selectedCaseIds.length ? this.selectedCaseIds : null
        })
        this.$message.success(`评测已启动 #${run.id}`)
        this.activeTab = 'runs'
        this.loadRuns()
        this.pollRunStatus(run.id)
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.running = false
      }
    },
    pollRunStatus(runId) {
      this.clearPolling()
      this.pollTimer = setInterval(async () => {
        try {
          const run = await getEvaluationRun(runId)
          this.latestRun = run
          if (run.status === 'success' || run.status === 'failed') {
            this.clearPolling()
            this.loadRuns()
          }
        } catch (error) {
          this.clearPolling()
        }
      }, 3000)
    },
    clearPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },
    async loadRuns() {
      this.runLoading = true
      try {
        const data = await listEvaluationRuns({ page: this.runPage, page_size: this.runPageSize })
        this.runs = data.items || []
        this.runTotal = data.total || 0
        if (this.runs.length && !this.latestRun) {
          this.latestRun = this.runs[0]
        }
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.runLoading = false
      }
    },
    handleRunPageChange(page) {
      this.runPage = page
      this.loadRuns()
    },
    openRunDetail(row) {
      this.detailRun = row
      this.results = []
      this.resultTotal = 0
      this.resultPage = 1
      this.runDetailVisible = true
      this.loadRunResults(1)
    },
    async loadRunResults(page) {
      if (!this.detailRun) return
      this.resultPage = page
      this.resultLoading = true
      try {
        const data = await listEvaluationResults(this.detailRun.id, {
          page,
          page_size: this.resultPageSize
        })
        this.results = data.items || []
        this.resultTotal = data.total || 0
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.resultLoading = false
      }
    },
    formatNumber(value) {
      if (value === null || value === undefined || value === '') return '--'
      return (value * 100).toFixed(1) + '%'
    },
    formatIds(ids) {
      if (!ids || !ids.length) return '--'
      return ids.join(', ')
    },
    formatTime(value) {
      if (!value) return '--'
      return String(value).replace('T', ' ').slice(0, 19)
    },
    statusLabel(status) {
      const map = {
        pending: '等待',
        running: '运行中',
        success: '成功',
        failed: '失败',
        active: '启用',
        archived: '停用',
        pending_review: '待复核'
      }
      return map[status] || status
    },
    statusTagType(status) {
      const map = {
        pending: 'info',
        running: 'warning',
        success: 'success',
        failed: 'danger',
        active: 'success',
        archived: 'info',
        pending_review: 'warning'
      }
      return map[status] || 'info'
    },
    difficultyTagType(difficulty) {
      const map = { easy: 'success', medium: 'warning', hard: 'danger' }
      return map[difficulty] || 'info'
    }
  }
}
</script>
