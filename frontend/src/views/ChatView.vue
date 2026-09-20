 <template>
   <div class="chat-view">
     <aside class="sources-panel" :style="{ width: sourcePanelWidth + 'px' }">
       <div class="sources-panel-header">
         <span class="sources-panel-title">来源</span>
         <el-button type="text" icon="el-icon-chat-line-round" @click="historyDrawerVisible = true">会话</el-button>
       </div>
       <div class="sources-toolbar">
         <el-input
           v-model="keyword"
           placeholder="搜索文档"
           clearable
           prefix-icon="el-icon-search"
           @keyup.enter.native="loadDocuments(1)"
           @clear="loadDocuments(1)"
         ></el-input>
       </div>
       <div class="sources-actions">
         <el-checkbox v-model="selectAllChecked" :indeterminate="isIndeterminate" @change="toggleSelectAll">全选</el-checkbox>
         <el-button
           v-if="selectedDocIds.length"
           type="text"
           class="danger-text"
           icon="el-icon-delete"
           @click="batchDelete"
         >删除选中 ({{ selectedDocIds.length }})</el-button>
       </div>
       <div class="source-list">
         <div
           v-for="doc in documents"
           :key="doc.id"
           class="source-item"
           :class="{ selected: isSelected(doc.id) }"
           @click.stop="toggleDocSelection(doc.id)"
         >
           <el-checkbox :value="isSelected(doc.id)" @click.stop.native></el-checkbox>
           <div class="source-icon"><i class="el-icon-document"></i></div>
           <div class="source-info" @click.stop="openDetail(doc)">
             <div class="source-title">{{ doc.title }}</div>
             <div class="source-meta">{{ formatSource(doc.source_type) }} · {{ statusLabel(doc.status) }}</div>
           </div>
           <div class="source-actions" @click.stop>
             <el-button type="text" icon="el-icon-view" title="详情" @click="openDetail(doc)"></el-button>
             <el-button type="text" class="danger-text" icon="el-icon-delete" title="删除" @click="deleteDocument(doc)"></el-button>
           </div>
         </div>
         <div v-if="!documents.length" class="source-empty">暂无来源文档</div>
       </div>
     </aside>
 
     <div class="panel-resize-handle" @mousedown="startResize"></div>
 
     <section class="chat-main">
       <header class="chat-header">
         <div>
           <div class="chat-title">{{ activeConversation ? activeConversation.title : '新建对话' }}</div>
           <div v-if="statusText" class="chat-status">{{ statusText }}</div>
         </div>
         <div class="chat-user">用户：{{ userId }}</div>
       </header>
 
       <div ref="messageList" class="chat-messages">
         <div v-if="!messages.length" class="empty-chat">
           <div class="welcome-card">
             <div class="welcome-brand"><i class="el-icon-coin"></i></div>
             <h2 class="welcome-title">{{ config.welcome_title || '向知识库提问' }}</h2>
             <p class="welcome-subtitle">{{ config.welcome_subtitle || '选择来源文档，开始问答' }}</p>
             <div v-if="welcomeQuestions.length" class="welcome-questions">
               <div
                 v-for="(q, idx) in welcomeQuestions"
                 :key="idx"
                 class="welcome-question"
                 @click="askQuestion(q)"
               >{{ q }}</div>
             </div>
           </div>
         </div>
 
         <div
           v-for="(message, index) in messages"
           :key="message.id || message.localId || index"
           class="message-row"
           :class="message.role"
         >
          <div class="message-bubble" :class="{ streaming: message.streaming }">
                        <div v-if="message.role === 'assistant'" class="markdown-body">
              <template v-if="message.content || !message.streaming">
                <div v-html="renderMarkdown(message.content)"></div>
              </template>
              <template v-else>
                <div class="thinking-bubble-text">
                  <span class="thinking-pulse-inline"></span>
                  <span>智能助手思考中</span>
                  <span class="thinking-dots-inline">.......</span>
                </div>
              </template>
            </div>
             <div v-else class="message-plain">{{ message.content }}</div>
             <div v-if="message.role === 'assistant' && message.error" class="message-error">
               <i class="el-icon-warning-outline"></i> {{ message.error }}
             </div>
             <div
               v-if="message.role === 'assistant' && message.status && message.status !== 'completed'"
               class="message-stream-status"
             >
               {{ message.status === 'cancelled' ? '已停止，当前为部分回答' : '生成失败，当前为部分回答' }}
             </div>
             <div
               v-if="message.role === 'assistant' && message.citations && message.citations.length"
               class="citation-row"
             >
               <div class="citation-row-label">引用来源</div>
               <div class="citation-tags">
                 <el-tag
                   v-for="(citation, cidx) in message.citations"
                   :key="citation.chunk_id"
                   size="small"
                   type="info"
                   class="citation-tag"
                 >
                   {{ cidx + 1 }}. {{ citation.title || '来源文档' }}{{ citation.page_no ? ` · P${citation.page_no}` : '' }}
                 </el-tag>
               </div>
             </div>
             <div
               v-if="message.role === 'assistant' && message.suggestedQuestions && message.suggestedQuestions.length"
               class="suggested-questions"
             >
               <div
                 v-for="(q, idx) in message.suggestedQuestions"
                 :key="idx"
                 class="suggested-question"
                 @click="askQuestion(q)"
               >{{ q }}</div>
             </div>
             <div v-if="message.role === 'assistant' && !message.error" class="message-actions">
               <el-button type="text" icon="el-icon-document-copy" title="复制" @click="copyAnswer(message)">复制</el-button>
               <el-button type="text" icon="el-icon-notebook-1" title="保存到笔记" @click="saveToNotes(message)">保存到笔记</el-button>
               <el-button type="text" icon="el-icon-thumb" title="点赞" @click="thumbUp(message)"></el-button>
               <el-button type="text" icon="el-icon-thumb" style="transform: rotate(180deg);" title="点踩" @click="thumbDown(message)"></el-button>
             </div>
             <el-button
               v-if="message.role === 'assistant' && ['cancelled', 'failed'].includes(message.status)"
               type="text"
               icon="el-icon-refresh"
               class="retry-answer-button"
               :disabled="sending"
               @click="retryAnswer(message)"
             >重新生成</el-button>
           </div>
         </div>
       </div>
 
       <footer class="chat-input">
         <div class="chat-input-box">
            <el-input
             v-model="input"
             type="textarea"
             :rows="3"
             resize="none"
             placeholder="输入问题，Enter 发送，Shift+Enter 换行"
              @keydown.native.enter.exact.prevent="sendMessage"
            ></el-input>
           <div class="chat-send">
             <el-button
               v-if="sending"
               type="danger"
               icon="el-icon-video-pause"
               @click="stopGeneration"
             >停止生成</el-button>
             <el-button
               v-else
               type="primary"
               icon="el-icon-s-promotion"
               @click="sendMessage"
             >发送</el-button>
           </div>
        </div>

      </footer>
     </section>
 
     <el-dialog
       title="上传来源"
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
 
     <el-drawer
       :visible.sync="detailDrawerVisible"
       size="560px"
       :title="detailDoc ? detailDoc.title : '文档详情'"
       direction="ltr"
     >
       <div v-if="detailDoc" class="drawer-body">
         <div class="detail-grid">
           <div class="detail-block">
             <div class="detail-label">文档名称</div>
             <div class="detail-value">{{ detailDoc.title }}</div>
           </div>
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
             <div class="detail-value">{{ detailDoc.version || '-' }}</div>
           </div>
           <div class="detail-block">
             <div class="detail-label">创建时间</div>
             <div class="detail-value">{{ formatTime(detailDoc.created_at) }}</div>
           </div>
         </div>
         <el-divider></el-divider>
         <div v-loading="detailLoading" class="source-detail-content">{{ detailContent || '暂无内容' }}</div>
       </div>
     </el-drawer>
 
     <el-drawer
       :visible.sync="historyDrawerVisible"
       size="320px"
       title="会话历史"
       direction="ltr"
     >
       <div class="drawer-body">
         <div class="conversation-list">
           <div
             v-for="conv in conversations"
             :key="conv.id"
             class="conversation-item"
             :class="{ active: conv.id === activeConversationId }"
             @click="selectConversation(conv)"
           >
             <div class="conversation-title">{{ conv.title || '未命名对话' }}</div>
             <div class="conversation-actions" @click.stop>
               <el-button type="text" title="重命名" icon="el-icon-edit" @click="renameConversation(conv)"></el-button>
               <el-button type="text" class="danger-text" title="删除" icon="el-icon-delete" @click="deleteConversation(conv)"></el-button>
             </div>
           </div>
           <div v-if="!conversations.length" class="conversation-empty">暂无会话</div>
         </div>
       </div>
     </el-drawer>
   </div>
 </template>
 
 <script>
 import MarkdownIt from 'markdown-it'
 import eventBus from '@/utils/eventBus'
 import {
   batchDeleteDocuments,
   createConversation,
   deleteConversation,
   getConfig,
   getDocument,
   getDocumentContent,
   getUserId,
   listConversations,
   listDocuments,
   listMessages,
   updateConversation,
   uploadDocument
 } from '@/api'
 import { getErrorMessage } from '@/api/client'
 import { cancelChatGeneration, streamChat } from '@/api/stream'
 
 const md = new MarkdownIt({
   html: false,
   linkify: true,
   breaks: true
 })
 
 const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'md', 'markdown', 'html', 'htm', 'txt']
 
 export default {
   name: 'ChatView',
   data() {
     return {
       userId: '',
       config: {},
       documents: [],
       totalDocs: 0,
       docPage: 1,
       docPageSize: 100,
       keyword: '',
       selectedDocIds: [],
       sourcePanelWidth: 360,
       minSourcePanelWidth: 260,
       maxSourcePanelWidth: 520,
       isResizing: false,
       conversations: [],
       activeConversationId: null,
       messages: [],
       input: '',
       sending: false,
       statusText: '',
       uploadVisible: false,
       uploading: false,
       uploadPollToken: 0,
       detailDrawerVisible: false,
       detailDoc: null,
       detailContent: '',
       detailLoading: false,
       historyDrawerVisible: false,
       streamController: null,
       activeGenerationId: null,
       activeStreamId: 0,
       stopRequested: false,
       scrollFrame: null
     }
   },
   computed: {
     activeConversation() {
       return this.conversations.find(conv => conv.id === this.activeConversationId) || null
     },
     welcomeQuestions() {
       return Array.isArray(this.config.welcome_questions) ? this.config.welcome_questions : []
     },
     selectAllChecked: {
       get() {
         return this.documents.length > 0 && this.selectedDocIds.length === this.documents.length
       },
       set(value) {
         this.selectedDocIds = value ? this.documents.map(doc => doc.id) : []
       }
     },
    isIndeterminate() {
      return this.selectedDocIds.length > 0 && this.selectedDocIds.length < this.documents.length
    },
  },
   created() {
     this.userId = getUserId()
     this.sourcePanelWidth = Math.max(this.minSourcePanelWidth, Math.round(window.innerWidth / 3))
     this.loadConfig()
     this.loadDocuments()
     this.loadConversations()
     eventBus.$on('new-conversation', this.newChat)
     eventBus.$on('open-upload', this.openUpload)
   },
   activated() {
     this.scrollToBottom()
   },
   beforeDestroy() {
     this.uploadPollToken += 1
     this.cancelCurrentStream(true)
     if (this.scrollFrame) cancelAnimationFrame(this.scrollFrame)
     eventBus.$off('new-conversation', this.newChat)
     eventBus.$off('open-upload', this.openUpload)
     document.removeEventListener('mousemove', this.onResize)
     document.removeEventListener('mouseup', this.stopResize)
   },
   methods: {
     async loadConfig() {
       try {
         this.config = await getConfig()
       } catch (error) {
         this.config = {}
       }
     },
     async loadDocuments(page) {
       try {
         const data = await listDocuments({
           page: page || this.docPage,
           page_size: this.docPageSize,
           keyword: this.keyword.trim() || undefined
         })
         this.documents = data.items || []
         this.totalDocs = data.total || 0
         this.docPage = data.page || 1
         if (this.selectedDocIds.length === 0 && this.documents.length > 0) {
           this.selectedDocIds = this.documents.map(doc => doc.id)
         }
       } catch (error) {
         this.$message.error(getErrorMessage(error))
       }
     },
     isSelected(id) {
       return this.selectedDocIds.includes(id)
     },
     toggleDocSelection(id) {
       const index = this.selectedDocIds.indexOf(id)
       if (index >= 0) {
         this.selectedDocIds.splice(index, 1)
       } else {
         this.selectedDocIds.push(id)
       }
     },
     toggleSelectAll(value) {
       this.selectedDocIds = value ? this.documents.map(doc => doc.id) : []
     },
     async batchDelete() {
       if (!this.selectedDocIds.length) return
       try {
         await this.$confirm(`确认删除选中的 ${this.selectedDocIds.length} 个文档？`, '批量删除', { type: 'warning' })
         await batchDeleteDocuments(this.selectedDocIds)
         this.$message.success('已删除')
         this.selectedDocIds = []
         this.loadDocuments(1)
       } catch (error) {
         if (error !== 'cancel') this.$message.error(getErrorMessage(error))
       }
     },
     async deleteDocument(doc) {
       try {
         await this.$confirm(`确认删除文档「${doc.title}」？`, '删除文档', { type: 'warning' })
         await batchDeleteDocuments([doc.id])
         this.selectedDocIds = this.selectedDocIds.filter(id => id !== doc.id)
         this.$message.success('文档已删除')
         this.loadDocuments(this.docPage)
       } catch (error) {
         if (error !== 'cancel') this.$message.error(getErrorMessage(error))
       }
     },
     async openDetail(doc) {
       this.detailDoc = doc
       this.detailDrawerVisible = true
       this.detailContent = ''
       this.detailLoading = true
       try {
         const data = await getDocumentContent(doc.id)
         this.detailContent = data.content || '暂无内容'
       } catch (error) {
         this.$message.error(getErrorMessage(error))
         this.detailContent = '加载失败'
       } finally {
         this.detailLoading = false
       }
     },
     openUpload() {
       this.uploadVisible = true
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
           this.pollUploadedDocument(doc.id, doc.title)
         })
         .catch(error => {
           this.$message.error(getErrorMessage(error))
           if (options.onError) options.onError(error)
         })
         .finally(() => {
           this.uploading = false
         })
     },
     async pollUploadedDocument(documentId, title) {
       const token = ++this.uploadPollToken
       const deadline = Date.now() + 10 * 60 * 1000
       let consecutiveErrors = 0
       while (Date.now() < deadline && token === this.uploadPollToken) {
         await new Promise(resolve => setTimeout(resolve, 2000))
         try {
           const doc = await getDocument(documentId)
           consecutiveErrors = 0
           await this.loadDocuments(1)
           if (doc.status === 'ready') {
             this.$message.success(`文档「${title}」入库完成`)
             return
           }
           if (doc.status === 'failed') {
             this.$message.error(doc.error_message || `文档「${title}」入库失败`)
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
       if (token === this.uploadPollToken) {
         this.$message.warning(`文档「${title}」仍在处理，可稍后在文档管理中查看`)
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
     clearUploadFiles() {
       if (this.$refs.uploadRef) this.$refs.uploadRef.clearFiles()
     },
     async loadConversations() {
       try {
         const data = await listConversations(this.userId)
         this.conversations = data.items || []
       } catch (error) {
         this.$message.error(getErrorMessage(error))
       }
     },
      async selectConversation(conv) {
        await this.cancelCurrentStream(true)
        this.activeConversationId = conv.id
        this.statusText = ''
        await this.loadMessages(conv.id)
       this.historyDrawerVisible = false
     },
     async loadMessages(id) {
       try {
         const data = await listMessages(id)
         this.messages = (data.items || [])
           .filter(item => item.role !== 'tool')
           .map(item => ({
             id: item.id,
             localId: `msg-${item.id}`,
              role: item.role,
              content: item.content || '',
              citations: Array.isArray(item.citations) ? item.citations : [],
              suggestedQuestions: item.suggested_questions || [],
              status: item.status || 'completed',
              replyToMessageId: item.reply_to_message_id,
              traceId: item.trace_id || '',
              streaming: false,
              error: ''
            }))
         this.scrollToBottom()
       } catch (error) {
         this.$message.error(getErrorMessage(error))
       }
     },
      async newChat() {
        await this.cancelCurrentStream(true)
        this.activeConversationId = null
       this.messages = []
       this.input = ''
       this.statusText = ''
       this.$nextTick(() => this.scrollToBottom())
     },
     askQuestion(question) {
       this.input = question
       this.sendMessage()
     },
     async ensureConversation() {
       if (this.activeConversationId) return this.activeConversationId
       const question = this.input.trim()
       const created = await createConversation(this.userId, question.slice(0, 50))
       this.activeConversationId = created.id
       this.conversations.unshift(created)
       await this.loadMessages(created.id)
       return created.id
     },
      async sendMessage() {
        const question = this.input.trim()
        if (!question || this.sending) return

        let conversationId
        try {
          conversationId = await this.ensureConversation()
       } catch (error) {
         this.$message.error(getErrorMessage(error))
          return
        }

        this.input = ''
        const userMessage = {
          localId: `local-user-${Date.now()}`,
          role: 'user',
          content: question,
          status: 'completed'
        }
        const assistantMessage = {
          localId: `local-assistant-${Date.now()}`,
         role: 'assistant',
          content: '',
          citations: [],
          suggestedQuestions: [],
          streaming: true,
          status: null,
          replyToMessageId: null,
          traceId: '',
          error: ''
        }
        this.messages.push(userMessage, assistantMessage)
        await this.startChatStream({
          conversationId,
          question,
          userMessage,
          assistantMessage
        })
      },
      async retryAnswer(assistantMessage) {
        if (this.sending) return
        const userMessage = this.messages.find(
          item => item.id === assistantMessage.replyToMessageId
        )
        if (!userMessage) {
          this.$message.error('找不到这条回答对应的原始问题')
          return
        }
        assistantMessage.content = ''
        assistantMessage.citations = []
        assistantMessage.suggestedQuestions = []
        assistantMessage.streaming = true
        assistantMessage.status = null
        assistantMessage.traceId = ''
        assistantMessage.error = ''
        await this.startChatStream({
          conversationId: this.activeConversationId,
          question: userMessage.content,
          userMessage,
          assistantMessage,
          retryUserMessageId: userMessage.id
        })
      },
      async startChatStream({
        conversationId,
        question,
        userMessage,
        assistantMessage,
        retryUserMessageId = null
      }) {
        if (this.streamController) {
          this.streamController.abort()
        }
        const controller = new AbortController()
        const streamId = this.activeStreamId + 1
        this.activeStreamId = streamId
        this.streamController = controller
        this.activeGenerationId = null
        this.stopRequested = false
        this.sending = true
        this.statusText = '正在检索知识库...'
        this.scrollToBottom()

        const payload = {
          conversation_id: conversationId,
          user_id: this.userId,
          question
        }
        if (retryUserMessageId) {
          payload.retry_user_message_id = retryUserMessageId
        }
        if (this.selectedDocIds.length) {
          payload.source_ids = this.selectedDocIds
        }

        const self = this
        try {
          await streamChat(
           payload,
            {
              onConnected: event => {
                if (self.activeStreamId !== streamId) return
                self.activeGenerationId = event.generation_id
                userMessage.id = event.user_message_id
                assistantMessage.replyToMessageId = event.user_message_id
                assistantMessage.traceId = event.trace_id || ''
                if (self.stopRequested) self.requestBackendCancellation(streamId)
              },
              onToken: content => {
                if (self.activeStreamId !== streamId) return
                assistantMessage.content += content
                self.statusText = '正在生成回答...'
                self.scrollToBottom()
              },
              onStatus: event => {
                if (self.activeStreamId !== streamId) return
                self.statusText = event.message || ''
              },
              onCitations: event => {
                if (self.activeStreamId !== streamId) return
                assistantMessage.citations = event.citations || []
              },
              onAnswerDone: event => {
                if (self.activeStreamId !== streamId) return
                assistantMessage.content = event.answer || assistantMessage.content
                assistantMessage.citations = event.citations || assistantMessage.citations
                assistantMessage.id = event.assistant_message_id
                assistantMessage.status = 'completed'
                assistantMessage.streaming = false
                assistantMessage.error = ''
                self.sending = false
                self.statusText = ''
                self.loadConversations()
                self.scrollToBottom()
              },
              onSuggestions: event => {
                if (self.activeStreamId !== streamId) return
                assistantMessage.suggestedQuestions = event.suggested_questions || []
                self.scrollToBottom()
              },
              onCancelled: event => {
                if (self.activeStreamId !== streamId) return
                assistantMessage.content = event.answer || assistantMessage.content
                assistantMessage.id = event.assistant_message_id || assistantMessage.id
                assistantMessage.status = 'cancelled'
                assistantMessage.streaming = false
                assistantMessage.error = ''
                self.sending = false
                self.statusText = ''
              },
              onError: event => {
                if (self.activeStreamId !== streamId) return
                assistantMessage.error = (event && event.message) || '回答生成失败'
                assistantMessage.id = event.assistant_message_id || assistantMessage.id
                assistantMessage.status = 'failed'
                assistantMessage.traceId = event.trace_id || assistantMessage.traceId
                assistantMessage.streaming = false
                self.sending = false
                self.statusText = ''
              },
              onDone: event => {
                if (self.activeStreamId !== streamId) return
                assistantMessage.id = event.assistant_message_id || assistantMessage.id
                assistantMessage.status = event.status || assistantMessage.status || 'completed'
                assistantMessage.streaming = false
                self.sending = false
                self.statusText = ''
                self.loadConversations()
              }
            },
            { signal: controller.signal }
          )
        } catch (error) {
          if (self.activeStreamId === streamId && error.name !== 'AbortError') {
            assistantMessage.error = getErrorMessage(error)
            assistantMessage.status = 'failed'
            assistantMessage.streaming = false
            self.statusText = ''
          }
        } finally {
          if (self.activeStreamId === streamId) {
            self.sending = false
            self.statusText = ''
            self.streamController = null
            self.activeGenerationId = null
            self.stopRequested = false
            self.scrollToBottom()
          }
        }
      },
      async requestBackendCancellation(streamId) {
        const generationId = this.activeGenerationId
        if (!generationId || this.activeStreamId !== streamId) return
        try {
          await cancelChatGeneration(generationId)
        } catch (error) {
          if (this.activeStreamId === streamId && this.streamController) {
            this.streamController.abort()
          }
          this.$message.error(getErrorMessage(error))
        }
      },
      async stopGeneration() {
        if (!this.streamController) return
        this.stopRequested = true
        this.statusText = '正在停止生成...'
        if (this.activeGenerationId) {
          await this.requestBackendCancellation(this.activeStreamId)
        }
      },
      async cancelCurrentStream(userRequested) {
        if (!this.streamController) return
        const controller = this.streamController
        const generationId = this.activeGenerationId
        this.activeStreamId += 1
        this.streamController = null
        this.activeGenerationId = null
        this.sending = false
        this.statusText = ''
        if (userRequested && generationId) {
          try {
            await cancelChatGeneration(generationId)
          } catch (error) {
            // The stream may already have completed; aborting locally is sufficient.
          }
        }
        controller.abort()
      },
     renderMarkdown(content) {
       return md.render(content || '')
     },
     copyAnswer(message) {
       const text = message.content
       if (!text) return
       if (navigator.clipboard && navigator.clipboard.writeText) {
         navigator.clipboard.writeText(text).then(() => this.$message.success('已复制'))
       } else {
         const textarea = document.createElement('textarea')
         textarea.value = text
         document.body.appendChild(textarea)
         textarea.select()
         document.execCommand('copy')
         document.body.removeChild(textarea)
         this.$message.success('已复制')
       }
     },
     saveToNotes(message) {
       this.$message.info('保存到笔记功能即将上线')
     },
     thumbUp(message) {
       this.$message.success('已点赞')
     },
     thumbDown(message) {
       this.$message.success('已点踩')
     },
     async renameConversation(conv) {
       try {
         const { value } = await this.$prompt('请输入新的会话标题', '重命名会话', {
           inputValue: conv.title || '',
           inputPattern: /.+/,
           inputErrorMessage: '标题不能为空'
         })
         const updated = await updateConversation(conv.id, { title: value })
         const index = this.conversations.findIndex(item => item.id === conv.id)
         if (index >= 0) this.$set(this.conversations, index, updated)
       } catch (error) {
         if (error !== 'cancel') this.$message.error(getErrorMessage(error))
       }
     },
     async deleteConversation(conv) {
       try {
         await this.$confirm(`确认删除会话「${conv.title || '未命名对话'}」？`, '删除会话', {
           type: 'warning'
         })
         await deleteConversation(conv.id)
         this.conversations = this.conversations.filter(item => item.id !== conv.id)
         if (this.activeConversationId === conv.id) this.newChat()
         this.$message.success('会话已删除')
       } catch (error) {
         if (error !== 'cancel') this.$message.error(getErrorMessage(error))
       }
     },
     startResize(event) {
       this.isResizing = true
       this.resizeStartX = event.clientX
       this.resizeStartWidth = this.sourcePanelWidth
       document.addEventListener('mousemove', this.onResize)
       document.addEventListener('mouseup', this.stopResize)
     },
     onResize(event) {
       if (!this.isResizing) return
       const delta = event.clientX - this.resizeStartX
       let newWidth = this.resizeStartWidth + delta
       newWidth = Math.max(this.minSourcePanelWidth, Math.min(this.maxSourcePanelWidth, newWidth))
       this.sourcePanelWidth = newWidth
     },
     stopResize() {
       this.isResizing = false
       document.removeEventListener('mousemove', this.onResize)
       document.removeEventListener('mouseup', this.stopResize)
     },
     scrollToBottom() {
       if (this.scrollFrame) return
       this.scrollFrame = requestAnimationFrame(() => {
         this.scrollFrame = null
         this.$nextTick(() => {
           const el = this.$refs.messageList
           if (el) el.scrollTop = el.scrollHeight
         })
       })
     },
     formatSource(value) {
       const map = {
         pdf: 'PDF',
         docx: 'Word',
         md: 'Markdown',
         markdown: 'Markdown',
         html: 'HTML',
         txt: 'TXT',
         other: '其他'
       }
       return map[value] || value || '-'
     },
     statusLabel(value) {
       const map = {
         pending: '待处理',
         processing: '处理中',
         ready: '已完成',
         failed: '失败'
       }
       return map[value] || value || '-'
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

