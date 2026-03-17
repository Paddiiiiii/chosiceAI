<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>文档管理</span>
          <div>
            <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".txt">
              <el-button type="primary" size="small"><el-icon><Upload /></el-icon> 上传文本</el-button>
            </el-upload>
          </div>
        </div>
      </template>

      <el-table :data="documents" stripe>
        <el-table-column prop="doc_id" label="文档 ID" width="140" />
        <el-table-column prop="filename" label="文件名" min-width="200" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">
              <el-icon v-if="isProcessing(row.status)" class="is-loading"><Loading /></el-icon>
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="Chunk 数" width="80" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button-group size="small">
              <el-button type="primary" @click="process(row)" :disabled="isProcessing(row.status)">
                {{ row.status === 'completed' ? '重新处理' : '处理' }}
              </el-button>
              <el-button type="success" @click="buildIdx" :disabled="row.status !== 'completed'">建索引</el-button>
              <el-popconfirm title="确定删除？" @confirm="doDelete(row.doc_id)">
                <template #reference>
                  <el-button type="danger">删除</el-button>
                </template>
              </el-popconfirm>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="documents.some(d => isProcessing(d.status))" style="margin-top: 12px;">
        <el-text type="info" size="small">
          <el-icon class="is-loading"><Loading /></el-icon>
          有文档正在处理中，页面每 5 秒自动刷新...
        </el-text>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listDocuments, uploadDocument, processDocument,
  reprocessDocument, deleteDocument, buildIndexes,
} from '../api'

const documents = ref([])
let timer = null

onMounted(() => { fetchDocs(); startPolling() })
onUnmounted(() => { if (timer) clearInterval(timer) })

async function fetchDocs() {
  const { data } = await listDocuments()
  documents.value = data
}

function startPolling() {
  timer = setInterval(() => {
    if (documents.value.some(d => isProcessing(d.status))) fetchDocs()
  }, 5000)
}

async function handleUpload(file) {
  try {
    await uploadDocument(file)
    await fetchDocs()
    ElMessage.success('上传成功')
  } catch (e) {
    ElMessage.error('上传失败: ' + e.message)
  }
  return false
}

async function process(row) {
  if (row.status === 'completed') {
    await reprocessDocument(row.doc_id)
  } else {
    await processDocument(row.doc_id)
  }
  ElMessage.info('处理已启动')
  setTimeout(fetchDocs, 1000)
}

async function buildIdx() {
  await buildIndexes()
  ElMessage.info('索引构建已启动')
}

async function doDelete(docId) {
  await deleteDocument(docId)
  await fetchDocs()
  ElMessage.success('已删除')
}

const isProcessing = (s) => ['correcting', 'parsing', 'chunking', 'indexing'].includes(s)
const statusType = (s) => ({
  uploaded: 'info', correcting: 'warning', parsing: 'warning',
  chunking: 'warning', indexing: 'warning', completed: 'success', error: 'danger',
}[s] || 'info')
const statusLabel = (s) => ({
  uploaded: '已上传', correcting: 'OCR纠错中', parsing: '解析中',
  chunking: '分块中', indexing: '建索引中', completed: '已完成', error: '错误',
}[s] || s)
</script>
