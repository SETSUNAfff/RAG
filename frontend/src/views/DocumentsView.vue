<template>
  <div class="documents-view">
    <div class="docs-panel">
      <header class="docs-header">
        <div>
          <div class="page-title">文档管理</div>
          <div class="page-subtitle">上传知识库文档并查看入库状态</div>
        </div>
        <el-button type="primary" icon="el-icon-upload2" @click="uploadVisible = true">上传文档</el-button>
      </header>

      <div class="docs-toolbar">
        <el-input
          v-model="keyword"
          class="toolbar-search"
          placeholder="搜索文档标题"
          clearable
          @keyup.enter.native="loadDocuments(1)"
          @clear="loadDocuments(1)"
        >
          <el-button slot="append" icon="el-icon-search" @click="loadDocuments(1)"></el-button>
        </el-input>
        <el-select v-model="statusFilter" class="toolbar-select" placeholder="全部状态" clearable @change="loadDocuments(1)">
          <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value"></el-option>
        </el-select>
        <el-select v-model="sourceFilter" class="toolbar-select" placeholder="全部类型" clearable @change="loadDocuments(1)">
          <el-option v-for="item in sourceOptions" :key="item.value" :label="item.label" :value="item.value"></el-option>
        </el-select>
        <el-button icon="el-icon-refresh" @click="loadDocuments()">刷新</el-button>
        <el-button icon="el-icon-finished" :loading="reconciling" @click="runReconcile">数据对账</el-button>
      </div>

      <div class="docs-table">
        <el-table v-loading="loading" :data="documents" stripe>
          <el-table-column prop="id" label="ID" width="80"></el-table-column>
          <el-table-column prop="title" label="文档名称" min-width="240" show-overflow-tooltip></el-table-column>
          <el-table-column label="类型" width="100">
            <template slot-scope="scope">
              <el-tag size="small">{{ formatSource(scope.row.source_type) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template slot-scope="scope">
              <el-tag :type="statusType(scope.row.status)" size="small">{{ statusLabel(scope.row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="version" label="版本" width="80"></el-table-column>
          <el-table-column label="创建时间" width="170">
            <template slot-scope="scope">{{ formatTime(scope.row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template slot-scope="scope">
              <el-button type="text" icon="el-icon-view" @click="openDetail(scope.row)">详情</el-button>
              <el-button type="text" icon="el-icon-refresh" @click="openReindex(scope.row)">重入库</el-button>
              <el-button type="text" class="danger-text" icon="el-icon-delete" @click="removeDocument(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <footer class="docs-footer">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page.sync="page"
          @current-change="loadDocuments"
        ></el-pagination>
      </footer>
    </div>

    <el-dialog
      title="上传文档"
      :visible.sync="uploadVisible"
      width="520px"
      :close-on-click-modal="false"
      @closed="clearUploadFiles"
    >
      <el-upload
        ref="uploadRef"
        drag
        action="#"
        :auto-upload="false"
        :http-request="handleUpload"
        :limit="1"
        accept=".pdf,.docx,.md,.markdown,.html,.htm,.txt"
        :before-upload="beforeUpload"
        :on-exceed="handleExceed"
      >
        <i class="el-icon-upload"></i>
        <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
        <div slot="tip" class="el-upload__tip">支持 PDF、Word、Markdown、HTML、TXT，单文件上传</div>
      </el-upload>
      <div slot="footer">
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="startUpload">开始上传</el-button>
      </div>
    </el-dialog>

    <el-dialog
      :title="`重新入库：${reindexTarget ? reindexTarget.title : ''}`"
      :visible.sync="reindexVisible"
      width="520px"
      :close-on-click-modal="false"
      @closed="clearReindexFiles"
    >
      <el-upload
        ref="reindexRef"
        drag
        action="#"
        :auto-upload="false"
        :http-request="handleReindex"
        :limit="1"
        accept=".pdf,.docx,.md,.markdown,.html,.htm,.txt"
        :before-upload="beforeUpload"
        :on-exceed="handleReindexExceed"
      >
        <i class="el-icon-upload"></i>
        <div class="el-upload__text">拖拽新版本文件到此处，或 <em>点击选择</em></div>
        <div slot="tip" class="el-upload__tip">重新入库会替换该文档的旧分片和向量</div>
      </el-upload>
      <div slot="footer">
        <el-button @click="reindexVisible = false">取消</el-button>
        <el-button type="primary" :loading="reindexing" @click="startReindex">开始重入库</el-button>
      </div>
    </el-dialog>

    <el-drawer :visible.sync="detailVisible" size="560px" title="文档详情">
      <div v-if="detailDoc" class="detail-panel">
        <div class="detail-block">
          <div class="detail-label">文档名称</div>
          <div class="detail-value">{{ detailDoc.title }}</div>
        </div>
        <div class="detail-grid">
          <div class="detail-block">
            <div class="detail-label">类型</div>
            <div class="detail-value">{{ formatSource(detailDoc.source_type) }}</div>
          </div>
          <div class="detail-block">
            <div class="detail-label">状态</div>
            <div class="detail-value">{{ statusLabel(detailDoc.status) }}</div>
          </div>
          <div class="detail-block">
            <div class="detail-label">版本</div>
            <div class="detail-value">{{ detailDoc.version }}</div>
          </div>
          <div class="detail-block">
            <div class="detail-label">创建时间</div>
            <div class="detail-value">{{ formatTime(detailDoc.created_at) }}</div>
          </div>
        </div>

        <el-divider></el-divider>
        <div class="detail-head">
          <span>Chunk 列表</span>
          <el-button type="text" icon="el-icon-refresh" @click="loadChunks(1)">刷新</el-button>
        </div>
        <div v-loading="chunkLoading" class="chunk-list">
          <div v-for="chunk in chunks" :key="chunk.id" class="chunk-item">
            <div class="chunk-meta">Chunk {{ chunk.id }} · 页码 {{ chunk.page_no || '-' }}</div>
            <div class="chunk-content">{{ chunk.content }}</div>
          </div>
          <div v-if="!chunks.length && !chunkLoading" class="conversation-empty">暂无分片</div>
        </div>
        <div v-if="chunkTotal > chunkPageSize" class="chunk-pagination">
          <el-pagination
            background
            layout="total, prev, pager, next"
            :total="chunkTotal"
            :page-size="chunkPageSize"
            :current-page.sync="chunkPage"
            @current-change="loadChunks"
          ></el-pagination>
        </div>
      </div>
    </el-drawer>

    <el-dialog
      title="数据对账结果"
      :visible.sync="reconcileVisible"
      width="480px"
      :close-on-click-modal="false"
    >
      <div v-if="reconcileResult" class="reconcile-result">
        <div class="reconcile-row">
          <span class="reconcile-label">清理孤儿向量</span>
          <span class="reconcile-value">{{ reconcileResult.orphan_chunks_deleted }} 个</span>
        </div>
        <div class="reconcile-row">
          <span class="reconcile-label">向量缺失文档</span>
          <span class="reconcile-value">{{ reconcileResult.missing_documents_failed }} 个</span>
        </div>
        <div class="reconcile-row">
          <span class="reconcile-label">卡住空文档</span>
          <span class="reconcile-value">{{ reconcileResult.stuck_documents_failed }} 个</span>
        </div>
        <div v-if="reconcileResult.affected_documents && reconcileResult.affected_documents.length" class="reconcile-row">
          <span class="reconcile-label">受影响文档</span>
          <span class="reconcile-value">{{ reconcileResult.affected_documents.join(', ') }}</span>
        </div>
      </div>
      <div v-else class="reconcile-result">
        <el-alert :title="reconcileError || '对账失败'" type="error" :closable="false"></el-alert>
      </div>
      <div slot="footer">
        <el-button type="primary" @click="reconcileVisible = false">关闭</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import {
  deleteDocument,
  getDocument,
  getReconcileStatus,
  listDocumentChunks,
  listDocuments,
  reindexDocument,
  startReconcile,
  uploadDocument
} from '@/api'
import { getErrorMessage } from '@/api/client'

const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'md', 'markdown', 'html', 'htm', 'txt']

export default {
  name: 'DocumentsView',
  data() {
    return {
      documents: [],
      total: 0,
      page: 1,
      pageSize: 20,
      keyword: '',
      statusFilter: '',
      sourceFilter: '',
      loading: false,
      uploadVisible: false,
      uploading: false,
      reindexVisible: false,
      reindexing: false,
      reindexTarget: null,
      detailVisible: false,
      detailDoc: null,
      chunks: [],
      chunkTotal: 0,
      chunkPage: 1,
      chunkPageSize: 20,
      chunkLoading: false,
      reconciling: false,
      reconcileVisible: false,
      reconcileResult: null,
      reconcileError: '',
      documentPollToken: 0,
      statusOptions: [
        { label: '待处理', value: 'pending' },
        { label: '处理中', value: 'processing' },
        { label: '已完成', value: 'ready' },
        { label: '失败', value: 'failed' }
      ],
      sourceOptions: [
        { label: 'PDF', value: 'pdf' },
        { label: 'Word', value: 'docx' },
        { label: 'Markdown', value: 'md' },
        { label: 'HTML', value: 'html' },
        { label: 'TXT', value: 'txt' },
        { label: '其他', value: 'other' }
      ]
    }
  },
  created() {
    this.loadDocuments(1)
  },
  beforeDestroy() {
    this.documentPollToken += 1
  },
  methods: {
    async loadDocuments(page) {
      this.loading = true
      try {
        const data = await listDocuments({
          page: page || this.page,
          page_size: this.pageSize,
          status: this.statusFilter || undefined,
          source_type: this.sourceFilter || undefined,
          keyword: this.keyword.trim() || undefined
        })
        this.documents = data.items || []
        this.total = data.total || 0
        this.page = data.page || 1
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.loading = false
      }
    },
    startUpload() {
      const uploader = this.$refs.uploadRef
      if (!uploader || !uploader.uploadFiles.length) {
        this.$message.warning('请先选择文件')
        return
      }
      uploader.submit()
    },
    handleUpload(options) {
      this.uploading = true
      uploadDocument(options.file, percent => {
        if (options.onProgress) options.onProgress({ percent })
      })
        .then(doc => {
          this.$message.info(`文档「${doc.title}」已上传，正在后台入库`)
          if (options.onSuccess) options.onSuccess(doc)
          this.uploadVisible = false
          this.loadDocuments(1)
          this.pollDocumentUntilFinished(doc.id, doc.title, '入库')
        })
        .catch(error => {
          this.$message.error(getErrorMessage(error))
          if (options.onError) options.onError(error)
        })
        .finally(() => {
          this.uploading = false
        })
    },
    openReindex(doc) {
      this.reindexTarget = doc
      this.reindexVisible = true
      this.$nextTick(() => {
        if (this.$refs.reindexRef) this.$refs.reindexRef.clearFiles()
      })
    },
    startReindex() {
      const uploader = this.$refs.reindexRef
      if (!uploader || !uploader.uploadFiles.length) {
        this.$message.warning('请先选择文件')
        return
      }
      uploader.submit()
    },
    handleReindex(options) {
      this.reindexing = true
      reindexDocument(this.reindexTarget.id, options.file, percent => {
        if (options.onProgress) options.onProgress({ percent })
      })
        .then(doc => {
          this.$message.info(`文档「${doc.title}」已提交重新入库`)
          if (options.onSuccess) options.onSuccess(doc)
          this.reindexVisible = false
          this.loadDocuments(this.page)
          this.pollDocumentUntilFinished(doc.id, doc.title, '重新入库')
        })
        .catch(error => {
          this.$message.error(getErrorMessage(error))
          if (options.onError) options.onError(error)
        })
        .finally(() => {
          this.reindexing = false
        })
    },
    async openDetail(doc) {
      this.detailDoc = doc
      this.detailVisible = true
      this.chunks = []
      this.chunkTotal = 0
      await this.loadChunks(1)
    },
    async loadChunks(page) {
      if (!this.detailDoc) return
      this.chunkLoading = true
      try {
        const data = await listDocumentChunks(this.detailDoc.id, {
          page: page || this.chunkPage,
          page_size: this.chunkPageSize
        })
        this.chunks = data.items || []
        this.chunkTotal = data.total || 0
        this.chunkPage = data.page || 1
      } catch (error) {
        this.$message.error(getErrorMessage(error))
      } finally {
        this.chunkLoading = false
      }
    },
    async runReconcile() {
      if (this.reconciling) return
      this.reconciling = true
      this.reconcileResult = null
      this.reconcileError = ''
      try {
        const started = await startReconcile()
        const taskId = started && started.task_id
        if (!taskId) {
          throw new Error('未返回对账任务 ID')
        }
        if (started.reused) {
          this.$message.info('已有对账任务在进行，等待其完成')
        } else {
          this.$message.info('对账任务已启动，正在处理...')
        }
        await this.pollReconcile(taskId)
      } catch (error) {
        this.reconcileError = getErrorMessage(error)
        this.reconcileVisible = true
      } finally {
        this.reconciling = false
      }
    },
    async pollReconcile(taskId) {
      const deadline = Date.now() + 180000
      let consecutiveErrors = 0
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 2000))
        try {
          const task = await getReconcileStatus(taskId)
          consecutiveErrors = 0
          if (task.status === 'done') {
            this.reconcileResult = task.result || {}
            this.reconcileVisible = true
            this.loadDocuments(1)
            return
          }
          if (task.status === 'failed') {
            this.reconcileError = task.error || '对账失败'
            this.reconcileVisible = true
            return
          }
        } catch (error) {
          consecutiveErrors += 1
          if (consecutiveErrors >= 3) {
            this.reconcileError = `无法读取对账状态：${getErrorMessage(error)}`
            this.reconcileVisible = true
            return
          }
        }
      }
      this.reconcileError = '对账任务超过 3 分钟，已停止轮询，请检查 Milvus 状态后重试'
      this.reconcileVisible = true
    },
    async pollDocumentUntilFinished(documentId, title, actionLabel) {
      const token = ++this.documentPollToken
      const deadline = Date.now() + 10 * 60 * 1000
      let consecutiveErrors = 0
      while (Date.now() < deadline && token === this.documentPollToken) {
        await new Promise(resolve => setTimeout(resolve, 2000))
        try {
          const doc = await getDocument(documentId)
          consecutiveErrors = 0
          await this.loadDocuments(this.page)
          if (doc.status === 'ready') {
            this.$message.success(`文档「${title}」${actionLabel}完成`)
            return
          }
          if (doc.status === 'failed') {
            this.$message.error(doc.error_message || `文档「${title}」${actionLabel}失败`)
            return
          }
        } catch (error) {
          consecutiveErrors += 1
          if (consecutiveErrors >= 3) {
            this.$message.error(`无法读取文档入库状态：${getErrorMessage(error)}`)
            return
          }
        }
      }
      if (token === this.documentPollToken) {
        this.$message.warning(`文档「${title}」仍在处理，可稍后在文档管理中查看`)
      }
    },
    async removeDocument(doc) {
      try {
        await this.$confirm(`确认删除文档「${doc.title}」及其全部分片？`, '删除文档', {
          type: 'warning'
        })
        await deleteDocument(doc.id)
        this.$message.success('文档已删除')
        this.loadDocuments(1)
      } catch (error) {
        if (error !== 'cancel') this.$message.error(getErrorMessage(error))
      }
    },
    beforeUpload(file) {
      const ext = (file.name.split('.').pop() || '').toLowerCase()
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        this.$message.error('不支持该文件类型，请上传 PDF、Word、Markdown、HTML 或 TXT')
        return false
      }
      if (file.size > 100 * 1024 * 1024) {
        this.$message.error('单个文件不能超过 100MB')
        return false
      }
      return true
    },
    handleExceed() {
      this.$message.warning('每次只能上传一个文件')
      if (this.$refs.uploadRef) this.$refs.uploadRef.clearFiles()
    },
    handleReindexExceed() {
      this.$message.warning('每次只能上传一个文件')
      if (this.$refs.reindexRef) this.$refs.reindexRef.clearFiles()
    },
    clearUploadFiles() {
      if (this.$refs.uploadRef) this.$refs.uploadRef.clearFiles()
    },
    clearReindexFiles() {
      if (this.$refs.reindexRef) this.$refs.reindexRef.clearFiles()
    },
    formatSource(value) {
      const found = this.sourceOptions.find(item => item.value === value)
      return found ? found.label : value || '-'
    },
    statusLabel(value) {
      const found = this.statusOptions.find(item => item.value === value)
      return found ? found.label : value || '-'
    },
    statusType(value) {
      const types = {
        pending: 'info',
        processing: 'warning',
        ready: 'success',
        failed: 'danger'
      }
      return types[value] || 'info'
    },
    formatTime(value) {
      if (!value) return '-'
      const date = new Date(value)
      if (Number.isNaN(date.getTime())) return value
      return date.toLocaleString('zh-CN', { hour12: false })
    }
  }
}
</script>

<style scoped>
.reconcile-result {
  padding: 4px 0;
}
.reconcile-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border);
}
.reconcile-row:last-child {
  border-bottom: none;
}
.reconcile-label {
  color: var(--color-text-muted);
}
.reconcile-value {
  font-weight: 600;
  color: var(--color-text);
}
</style>
