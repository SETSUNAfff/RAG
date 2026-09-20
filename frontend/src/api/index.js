import client from './client'

export async function getConfig() {
  const { data } = await client.get('/config')
  return data
}

export function getUserId() {
  const key = 'rag_ui_user_id'
  let value = localStorage.getItem(key)
  if (!value) {
    value = `anonymous-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
    localStorage.setItem(key, value)
  }
  return value
}

export async function listConversations(userId) {
  const { data } = await client.get('/conversations', {
    params: { user_id: userId, page: 1, page_size: 100 }
  })
  return data
}

export async function createConversation(userId, title) {
  const { data } = await client.post('/conversations', {
    user_id: userId,
    title: title || 'Untitled'
  })
  return data
}

export async function updateConversation(id, payload) {
  const { data } = await client.patch(`/conversations/${id}`, payload)
  return data
}

export async function deleteConversation(id) {
  const { data } = await client.delete(`/conversations/${id}`)
  return data
}

export async function listMessages(conversationId) {
  const { data } = await client.get('/messages', {
    params: { conversation_id: conversationId, page: 1, page_size: 100 }
  })
  return data
}

export async function listDocuments(params = {}) {
  const { data } = await client.get('/documents', { params })
  return data
}

export async function getDocument(id) {
  const { data } = await client.get(`/documents/${id}`, { timeout: 10000 })
  return data
}

export async function uploadDocument(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await client.post('/documents/upload', formData, {
    onUploadProgress: event => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
  })
  return data
}

export async function reindexDocument(id, file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await client.post(`/documents/${id}/reindex`, formData, {
    onUploadProgress: event => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
  })
  return data
}

export async function deleteDocument(id) {
  const { data } = await client.delete(`/documents/${id}`)
  return data
}

export async function batchDeleteDocuments(ids) {
  const { data } = await client.post('/documents/batch-delete', { ids })
  return data
}

export async function getDocumentContent(id) {
  const { data } = await client.get(`/documents/${id}/content`)
  return data
}

export async function listDocumentChunks(id, params = {}) {
  const { data } = await client.get(`/documents/${id}/chunks`, { params })
  return data
}

export async function listEvaluationCases(params = {}) {
  const { data } = await client.get('/evaluations/cases', { params })
  return data
}

export async function createEvaluationCase(payload) {
  const { data } = await client.post('/evaluations/cases', payload)
  return data
}

export async function updateEvaluationCase(id, payload) {
  const { data } = await client.patch(`/evaluations/cases/${id}`, payload)
  return data
}

export async function deleteEvaluationCase(id) {
  const { data } = await client.delete(`/evaluations/cases/${id}`)
  return data
}

export async function importEvaluationCases(payload) {
  const { data } = await client.post('/evaluations/cases/import', payload)
  return data
}

export async function createEvaluationRun(payload = {}) {
  const { data } = await client.post('/evaluations/runs', payload)
  return data
}

export async function listEvaluationRuns(params = {}) {
  const { data } = await client.get('/evaluations/runs', { params })
  return data
}

export async function getEvaluationRun(id) {
  const { data } = await client.get(`/evaluations/runs/${id}`)
  return data
}

export async function listEvaluationResults(runId, params = {}) {
  const { data } = await client.get(`/evaluations/runs/${runId}/results`, { params })
  return data
}

export async function startReconcile() {
  const { data } = await client.post('/admin/reconcile')
  return data
}

export async function getReconcileStatus(taskId) {
  const { data } = await client.get(`/admin/reconcile/${taskId}`, { timeout: 10000 })
  return data
}
