import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api/v1',
  timeout: 120000,
})

// ─────────── Chat / 路由查询 ───────────
export const chatQuery = (input, context = null, retrieval = null) =>
  api.post('/chat', { input, context, retrieval })

// ─────────── 文档管理 ───────────
export const listDocuments = () => api.get('/documents')
export const getDocument = (docId) => api.get(`/documents/${docId}`)
export const uploadDocument = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/documents/upload', fd)
}
export const processDocument = (docId) => api.post(`/documents/${docId}/process`)
export const reprocessDocument = (docId) => api.post(`/documents/${docId}/reprocess`)
export const deleteDocument = (docId) => api.delete(`/documents/${docId}`)
export const buildIndexes = () => api.post('/documents/build-indexes')
export const getOriginalText = (docId) => api.get(`/documents/${docId}/original-text`)
export const getCorrectedText = (docId) => api.get(`/documents/${docId}/corrected-text`)

// ─────────── Chunks ───────────
export const listChunks = (params) => api.get('/chunks', { params })
export const getChunk = (chunkId) => api.get(`/chunks/${chunkId}`)
export const getChunkStats = () => api.get('/chunks/stats/summary')

// ─────────── 角色管理 ───────────
export const getRoles = () => api.get('/roles')
export const addRole = (name) => api.post('/roles', { name })
export const updateRole = (roleId, name) => api.put(`/roles/${roleId}`, { name })
export const deleteRole = (roleId) => api.delete(`/roles/${roleId}`)
export const extractRoles = () => api.post('/roles/extract', null, { timeout: 60000 })
export const approveRole = (roleId) => api.post(`/roles/${roleId}/approve`)
export const rejectRole = (roleId) => api.post(`/roles/${roleId}/reject`)

// ─────────── 审核 ───────────
export const listReviews = (params) => api.get('/review/items', { params })
export const updateReview = (itemId, docId, status) =>
  api.put(`/review/items/${itemId}`, { status }, { params: { doc_id: docId } })
export const listCorrections = (docId) => api.get('/review/corrections', { params: { doc_id: docId } })
export const updateCorrection = (index, docId, data) =>
  api.put(`/review/corrections/${index}`, data, { params: { doc_id: docId } })
export const getReviewStats = () => api.get('/review/stats')
export const getCorrectionContext = (docId, { line = 0, original = '', corrected = '' } = {}) =>
  api.get('/review/corrections/context', { params: { doc_id: docId, line, original, corrected } })

// ─────────── 检索对比 ───────────
export const searchComparison = (query, filters = null, retrieval = null) =>
  api.post('/search/comparison', { query, filters, retrieval })
export const refreshCache = () => api.post('/search/refresh-cache')

// ─────────── 图谱 ───────────
export const rebuildGraphApi = (useLlm = false) =>
  api.post(`/graph/rebuild?use_llm=${useLlm}`, null, { timeout: 600000 })
export const getGraphStats = () => api.get('/graph/stats')
export const getGraphViz = (maxNodes = 500) =>
  api.get('/graph/viz', { params: { max_nodes: maxNodes } })
export const getRoleTasks = (role, phase = null) =>
  api.get('/graph/role_tasks', { params: { role, phase } })
export const getTaskRoles = (chunkId = null, taskName = null) =>
  api.get('/graph/task_roles', { params: { chunk_id: chunkId, task_name: taskName } })
export const getTaskDecompose = (chunkId) =>
  api.get('/graph/task_decompose', { params: { chunk_id: chunkId } })
export const getTaskPrerequisites = (chunkId) =>
  api.get('/graph/task_prerequisites', { params: { chunk_id: chunkId } })
export const getTaskProducts = (chunkId = null, role = null, phase = null) =>
  api.get('/graph/task_products', { params: { chunk_id: chunkId, role, phase } })
export const getTaskDetail = (chunkId) =>
  api.get('/graph/task_detail', { params: { chunk_id: chunkId } })

// ─────────── 任务解析 ───────────
export const resolveQuery = (query, topK = 3) =>
  api.post('/resolve', { query, top_k: topK })

// ─────────── 同义词 ───────────
export const listSynonyms = () => api.get('/synonyms')
export const addSynonym = (terms) => api.post('/synonyms', { terms })
export const updateSynonym = (id, terms) => api.put(`/synonyms/${id}`, { terms })
export const deleteSynonym = (id) => api.delete(`/synonyms/${id}`)

// ─────────── 结构树 ───────────
export const getStructure = (docId) => api.get(`/structure/${docId}`)
export const listStructures = () => api.get('/structure')

// ─────────── 层级模式 ───────────
export const getLevelPatterns = () => api.get('/level-patterns')
export const updateLevelPatterns = (patterns) => api.put('/level-patterns', patterns)
export const testPattern = (pattern, testText) => api.post('/level-patterns/test', { pattern, test_text: testText })
export const resetPatterns = () => api.post('/level-patterns/reset')

export default api
