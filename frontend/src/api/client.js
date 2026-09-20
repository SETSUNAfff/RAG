import axios from 'axios'

export const API_BASE = process.env.VUE_APP_API_BASE || '/api/v1'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 120000
})

export function getErrorMessage(error) {
  const data = error && error.response && error.response.data
  if (data && typeof data.detail === 'string') {
    return data.detail
  }
  if (data && Array.isArray(data.detail)) {
    return data.detail.map(item => item.msg || JSON.stringify(item)).join('; ')
  }
  return (error && error.message) || '请求失败'
}

export default client
