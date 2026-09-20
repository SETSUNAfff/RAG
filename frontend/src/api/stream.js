import { API_BASE } from './client'

const DEFAULT_IDLE_TIMEOUT = 35000

function dispatchEvent(event, handlers) {
  const type = event.type
  if (type === 'connected' && handlers.onConnected) handlers.onConnected(event)
  if (type === 'status' && handlers.onStatus) handlers.onStatus(event)
  if (type === 'token' && handlers.onToken) handlers.onToken(event.content || '')
  if (type === 'citations' && handlers.onCitations) handlers.onCitations(event)
  if (type === 'answer_done' && handlers.onAnswerDone) handlers.onAnswerDone(event)
  if (type === 'suggestions' && handlers.onSuggestions) handlers.onSuggestions(event)
  if (type === 'cancelled' && handlers.onCancelled) handlers.onCancelled(event)
  if (type === 'error' && handlers.onError) handlers.onError(event)
  if (type === 'done' && handlers.onDone) handlers.onDone(event)
}

function parseBlock(block, handlers) {
  const lines = block.split(/\r?\n/)
  let eventName = ''
  let eventId = ''
  const dataLines = []

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    if (line.startsWith('id:')) eventId = line.slice(3).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }

  if (!dataLines.length) {
    if (handlers.onHeartbeat) handlers.onHeartbeat()
    return null
  }

  let event
  try {
    event = JSON.parse(dataLines.join('\n'))
  } catch (error) {
    throw new Error('服务器返回了无法解析的流式数据')
  }
  event.type = eventName || event.type || 'message'
  if (eventId) event.event_id = eventId
  dispatchEvent(event, handlers)
  return event.type
}

function readWithTimeout(reader, timeoutMs) {
  let timer
  return Promise.race([
    reader.read(),
    new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(new Error('流式连接长时间没有数据')), timeoutMs)
    })
  ]).finally(() => clearTimeout(timer))
}

export async function cancelChatGeneration(generationId) {
  if (!generationId) return false
  const response = await fetch(
    `${API_BASE}/chat/${encodeURIComponent(generationId)}/cancel`,
    { method: 'POST' }
  )
  if (!response.ok) {
    throw new Error(`停止生成失败 (${response.status})`)
  }
  return true
}

export async function streamChat(payload, handlers = {}, options = {}) {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: options.signal
  })

  if (!response.ok) {
    let detail = `请求失败 (${response.status})`
    try {
      const body = await response.json()
      if (body && body.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch (error) {
      // Keep the status-based fallback when the body is not JSON.
    }
    throw new Error(detail)
  }

  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('text/event-stream')) {
    throw new Error(`服务器未返回 SSE 流 (${contentType || '未知内容类型'})`)
  }
  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  const idleTimeout = options.idleTimeout || DEFAULT_IDLE_TIMEOUT
  let buffer = ''
  let terminalReceived = false

  const consumeBuffer = () => {
    let boundary = buffer.search(/\r?\n\r?\n/)
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary)
      const delimiterLength = buffer.slice(boundary, boundary + 4) === '\r\n\r\n' ? 4 : 2
      buffer = buffer.slice(boundary + delimiterLength)
      const eventType = parseBlock(block, handlers)
      if (eventType === 'done') terminalReceived = true
      boundary = buffer.search(/\r?\n\r?\n/)
    }
  }

  try {
    while (!terminalReceived) {
      let result
      try {
        result = await readWithTimeout(reader, idleTimeout)
      } catch (error) {
        await reader.cancel().catch(() => {})
        throw error
      }
      if (result.done) break
      buffer += decoder.decode(result.value, { stream: true })
      consumeBuffer()
    }

    buffer += decoder.decode()
    consumeBuffer()
    if (buffer.trim() && !terminalReceived) {
      const eventType = parseBlock(buffer, handlers)
      if (eventType === 'done') terminalReceived = true
    }

    if (!terminalReceived) {
      throw new Error('流式连接意外结束，未收到完成事件')
    }
    return { completed: true }
  } finally {
    if (terminalReceived) {
      await reader.cancel().catch(() => {})
    }
    reader.releaseLock()
  }
}
