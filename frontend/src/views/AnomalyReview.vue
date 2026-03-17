<template>
  <div>
    <!-- 全部审核通过提示 -->
    <el-result v-if="allPassed" icon="success" title="所有文档异常条目已全部审核完毕" sub-title="没有待处理的异常条目">
      <template #extra>
        <el-button type="primary" @click="forceRefresh">刷新检查</el-button>
      </template>
    </el-result>

    <template v-else>
      <el-card shadow="never" style="margin-bottom: 16px">
        <el-row :gutter="12" align="middle">
          <el-col :span="6">
            <el-select v-model="selectedDoc" clearable placeholder="选择文档" @change="fetchReviews">
              <el-option v-for="d in docs" :key="d.doc_id" :label="d.filename" :value="d.doc_id">
                <span>{{ d.filename }}</span>
                <el-badge v-if="d._pendingCount > 0" :value="d._pendingCount" type="danger" style="margin-left: 8px" />
              </el-option>
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select v-model="typeFilter" clearable placeholder="类型" @change="fetchReviews">
              <el-option label="OCR 错误" value="ocr_error" />
              <el-option label="角色标注" value="role_annotation" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select v-model="statusFilter" clearable placeholder="状态">
              <el-option label="待处理" value="pending" />
              <el-option label="已解决" value="resolved" />
              <el-option label="已忽略" value="ignored" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-statistic :value="pendingCount" title="待处理" />
          </el-col>
        </el-row>
      </el-card>

      <el-table :data="displayItems" stripe max-height="600">
        <el-table-column prop="item_id" label="ID" width="140" />
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.type === 'ocr_error' ? 'danger' : 'warning'" size="small">
              {{ row.type === 'ocr_error' ? 'OCR 错误' : '角色标注' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="300" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'pending' ? 'info' : 'success'" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">查看</el-button>
            <el-button size="small" type="success" @click="resolve(row)" :disabled="row.status !== 'pending'">已解决</el-button>
            <el-button size="small" @click="ignore(row)" :disabled="row.status !== 'pending'">忽略</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="审核详情" width="600px">
      <el-descriptions :column="1" border size="small" v-if="detailItem">
        <el-descriptions-item label="类型">{{ detailItem.type }}</el-descriptions-item>
        <el-descriptions-item label="描述">{{ detailItem.description }}</el-descriptions-item>
        <el-descriptions-item label="Chunk ID">{{ detailItem.chunk_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="原始文本">
          <div style="white-space: pre-wrap; max-height: 200px; overflow-y: auto;">{{ detailItem.original_text }}</div>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listDocuments, listReviews, updateReview } from '../api'

const docs = ref([])
const selectedDoc = ref('')
const reviews = ref([])
const typeFilter = ref('')
const statusFilter = ref('')
const detailVisible = ref(false)
const detailItem = ref(null)
const allPassed = ref(false)

const pendingCount = computed(() => reviews.value.filter(r => r.status === 'pending').length)
const displayItems = computed(() => {
  let items = reviews.value
  if (statusFilter.value) items = items.filter(r => r.status === statusFilter.value)
  return items
})

onMounted(async () => {
  await initPage()
})

const initPage = async () => {
  const { data } = await listDocuments()
  docs.value = data

  if (!docs.value.length) {
    allPassed.value = true
    return
  }

  // 逐个文档检查，找到第一个有待处理异常条目的文档并自动选中
  let foundPending = false
  for (const doc of docs.value) {
    try {
      const { data: revs } = await listReviews({ doc_id: doc.doc_id })
      const pending = revs.filter(r => r.status === 'pending').length
      doc._pendingCount = pending
      if (!foundPending && pending > 0) {
        selectedDoc.value = doc.doc_id
        reviews.value = revs
        foundPending = true
      }
    } catch {
      doc._pendingCount = 0
    }
  }

  if (!foundPending) {
    if (docs.value.some(d => d._pendingCount !== undefined)) {
      allPassed.value = true
    } else {
      selectedDoc.value = docs.value[0].doc_id
      await fetchReviews()
    }
  }
}

const forceRefresh = async () => {
  allPassed.value = false
  await initPage()
}

const fetchReviews = async () => {
  const params = {}
  if (selectedDoc.value) params.doc_id = selectedDoc.value
  if (typeFilter.value) params.type = typeFilter.value
  const { data } = await listReviews(params)
  reviews.value = data
}

const viewDetail = (item) => { detailItem.value = item; detailVisible.value = true }
const resolve = async (item) => {
  await updateReview(item.item_id, item.document_id, 'resolved')
  item.status = 'resolved'
  ElMessage.success('已标记为解决')
}
const ignore = async (item) => {
  await updateReview(item.item_id, item.document_id, 'ignored')
  item.status = 'ignored'
  ElMessage.success('已忽略')
}
const statusLabel = (s) => ({ pending: '待处理', resolved: '已解决', ignored: '已忽略' }[s] || s)
</script>
