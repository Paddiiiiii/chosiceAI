<template>
  <div>
    <!-- 全部审核通过提示 -->
    <el-result v-if="allPassed" icon="success" title="所有文档 OCR 纠错已全部审核完毕" sub-title="没有待审核的 OCR 纠错条目">
      <template #extra>
        <el-button type="primary" @click="forceRefresh">刷新检查</el-button>
      </template>
    </el-result>

    <template v-else>
      <!-- 文档选择 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <el-row :gutter="12" align="middle">
          <el-col :span="6">
            <el-select v-model="selectedDoc" placeholder="选择文档" @change="loadCorrections">
              <el-option v-for="d in docs" :key="d.doc_id" :label="d.filename" :value="d.doc_id">
                <span>{{ d.filename }}</span>
                <el-badge v-if="d._pendingCount > 0" :value="d._pendingCount" type="danger" style="margin-left: 8px" />
              </el-option>
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-select v-model="statusFilter" clearable placeholder="筛选状态" @change="applyFilter">
              <el-option label="待审核" value="pending" />
              <el-option label="已通过" value="approved" />
              <el-option label="已拒绝" value="rejected" />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-statistic :value="stats.pending" title="待审核" />
          </el-col>
          <el-col :span="4">
            <el-statistic :value="stats.total" title="总计" />
          </el-col>
        </el-row>
      </el-card>

      <!-- 纠错列表 -->
      <el-table :data="displayItems" stripe max-height="600">
        <el-table-column prop="line" label="行号" width="70" />
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.type === 'garbled' ? 'danger' : 'warning'" size="small">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="original" label="原文" min-width="250" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="color: #f56c6c; text-decoration: line-through">{{ row.original }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="corrected" label="纠正后" min-width="250" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="color: #67c23a">{{ row.corrected }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row, $index }">
            <el-button-group size="small">
              <el-button type="success" @click="approve($index)" :disabled="row.status !== 'pending'">通过</el-button>
              <el-button type="danger" @click="reject($index)" :disabled="row.status !== 'pending'">拒绝</el-button>
              <el-button @click="openContextEdit($index)">原文编辑</el-button>
            </el-button-group>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 原文编辑弹窗 -->
    <el-dialog v-model="editVisible" title="原文上下文编辑" width="800px" top="5vh">
      <div v-if="contextLoading" style="text-align:center; padding: 40px;">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span style="margin-left: 8px">加载上下文...</span>
      </div>
      <template v-else>
        <!-- 所属位置 -->
        <div v-if="contextTitleChain" class="chunk-title-chain">
          <el-icon><Document /></el-icon>
          <span>{{ contextTitleChain }}</span>
        </div>

        <!-- 原文上下文，问题文字标红 -->
        <div class="context-label">原文上下文 <span style="color:#999; font-size:12px">（红色标注为需纠正内容，来自原始文本第 {{ editItem?.line }} 行附近）</span></div>
        <div class="context-box" v-html="highlightedContextText"></div>

        <!-- 纠正信息 -->
        <el-row :gutter="16" style="margin-top: 16px">
          <el-col :span="12">
            <div class="edit-label">识别的问题文本</div>
            <div class="original-text">{{ editItem?.original }}</div>
          </el-col>
          <el-col :span="12">
            <div class="edit-label">纠正为</div>
            <el-input v-model="editText" type="textarea" :rows="3" placeholder="输入纠正后的文字" />
          </el-col>
        </el-row>
      </template>

      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Document } from '@element-plus/icons-vue'
import { listDocuments, listCorrections, updateCorrection, getCorrectionContext } from '../api'

const docs = ref([])
const selectedDoc = ref('')
const corrections = ref([])
const statusFilter = ref('')
const editVisible = ref(false)
const editText = ref('')
const editIndex = ref(-1)
const editItem = ref(null)
const contextText = ref('')
const contextTitleChain = ref('')
const contextHighlight = ref('')
const contextLoading = ref(false)
const allPassed = ref(false)

const stats = computed(() => ({
  total: corrections.value.length,
  pending: corrections.value.filter(c => c.status === 'pending').length,
}))

const displayItems = computed(() => {
  if (!statusFilter.value) return corrections.value
  return corrections.value.filter(c => c.status === statusFilter.value)
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

  // 逐个文档检查，找到第一个有待审核条目的文档并自动选中
  let foundPending = false
  for (const doc of docs.value) {
    try {
      const { data: corrs } = await listCorrections(doc.doc_id)
      const pendingCount = corrs.filter(c => c.status === 'pending').length
      doc._pendingCount = pendingCount
      if (!foundPending && pendingCount > 0) {
        selectedDoc.value = doc.doc_id
        corrections.value = corrs
        foundPending = true
      }
    } catch {
      doc._pendingCount = 0
    }
  }

  if (!foundPending) {
    // 没有待审核的，检查是否有任何纠错记录
    if (docs.value.some(d => d._pendingCount !== undefined)) {
      allPassed.value = true
    } else {
      // 默认选第一个文档
      selectedDoc.value = docs.value[0].doc_id
      await loadCorrections(docs.value[0].doc_id)
    }
  }
}

const forceRefresh = async () => {
  allPassed.value = false
  await initPage()
}

const loadCorrections = async (docId) => {
  const { data } = await listCorrections(docId)
  corrections.value = data
}

const approve = async (idx) => {
  await updateCorrection(idx, selectedDoc.value, { status: 'approved' })
  corrections.value[idx].status = 'approved'
  ElMessage.success('已通过')
}

const reject = async (idx) => {
  await updateCorrection(idx, selectedDoc.value, { status: 'rejected' })
  corrections.value[idx].status = 'rejected'
  ElMessage.success('已拒绝')
}

const openContextEdit = async (idx) => {
  const item = corrections.value[idx]
  editIndex.value = idx
  editItem.value = item
  editText.value = item.corrected
  editVisible.value = true
  contextLoading.value = true
  contextText.value = ''
  contextTitleChain.value = ''

  try {
    const { data } = await getCorrectionContext(selectedDoc.value, {
      line: item.line,
      original: item.original,
      corrected: item.corrected,
    })
    contextText.value = data.text || ''
    contextTitleChain.value = data.title_chain || ''
    contextHighlight.value = data.highlight || ''
  } catch (e) {
    ElMessage.warning('加载上下文失败')
  } finally {
    contextLoading.value = false
  }
}

const highlightedContextText = computed(() => {
  if (!contextText.value) return ''
  const text = contextText.value
  // 用后端返回的 highlight 字段（它是实际能在 chunk 中找到的文本）
  const hl = contextHighlight.value
  if (!hl) {
    // 后端没有找到可高亮的文本，尝试用 original 和 corrected 手动查找
    for (const kw of [editItem.value?.corrected, editItem.value?.original]) {
      if (!kw) continue
      const kwFlat = kw.replace(/\n/g, '')
      const textFlat = text.replace(/\n/g, '')
      const idx = textFlat.indexOf(kwFlat)
      if (idx !== -1) {
        // 在原始文本（含换行）中定位对应位置
        return doHighlight(text, kw)
      }
    }
    return escapeHtml(text).replace(/\n/g, '<br>')
  }
  return doHighlight(text, hl)
})

function doHighlight(text, keyword) {
  if (!keyword) return escapeHtml(text).replace(/\n/g, '<br>')
  // 去掉换行做平铺匹配，然后映射回原文
  const kwFlat = keyword.replace(/\n/g, '')
  const textFlat = text.replace(/\n/g, '')
  const idx = textFlat.indexOf(kwFlat)
  if (idx === -1) {
    // 再试子串
    const sub = kwFlat.substring(0, Math.min(20, kwFlat.length))
    const subIdx = textFlat.indexOf(sub)
    if (subIdx === -1) return escapeHtml(text).replace(/\n/g, '<br>')
    // 高亮子串
    const before = textFlat.substring(0, subIdx)
    const match = textFlat.substring(subIdx, subIdx + sub.length)
    const after = textFlat.substring(subIdx + sub.length)
    return escapeHtml(before).replace(/\n/g, '<br>') +
      '<span class="highlight-error">' + escapeHtml(match) + '</span>' +
      escapeHtml(after).replace(/\n/g, '<br>')
  }
  const before = textFlat.substring(0, idx)
  const match = textFlat.substring(idx, idx + kwFlat.length)
  const after = textFlat.substring(idx + kwFlat.length)
  return escapeHtml(before).replace(/\n/g, '<br>') +
    '<span class="highlight-error">' + escapeHtml(match).replace(/\n/g, '<br>') + '</span>' +
    escapeHtml(after).replace(/\n/g, '<br>')
}

const escapeHtml = (str) => {
  if (!str) return ''
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const saveEdit = async () => {
  await updateCorrection(editIndex.value, selectedDoc.value, { status: 'modified', corrected: editText.value })
  corrections.value[editIndex.value].corrected = editText.value
  corrections.value[editIndex.value].status = 'modified'
  editVisible.value = false
  ElMessage.success('已修改')
}

const applyFilter = () => {}
const statusType = (s) => ({ pending: 'info', approved: 'success', rejected: 'danger', modified: 'warning' }[s] || 'info')
const statusLabel = (s) => ({ pending: '待审核', approved: '已通过', rejected: '已拒绝', modified: '已修改' }[s] || s)
</script>

<style scoped>
.chunk-title-chain {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f0f9eb;
  border-radius: 4px;
  font-size: 13px;
  color: #67c23a;
  font-weight: 500;
}
.context-label {
  font-weight: bold;
  margin-bottom: 8px;
  font-size: 14px;
}
.context-box {
  background: #fafafa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  max-height: 350px;
  overflow-y: auto;
  padding: 12px 16px;
  font-size: 13.5px;
  line-height: 2;
  color: #303133;
}
.edit-label {
  font-weight: bold;
  margin-bottom: 6px;
  font-size: 13px;
  color: #606266;
}
.original-text {
  background: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 4px;
  padding: 8px 12px;
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.8;
  min-height: 76px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

<style>
/* 非 scoped，v-html 内容需要全局样式 */
.highlight-error {
  color: #f56c6c;
  font-weight: bold;
  text-decoration: underline wavy #f56c6c;
}
</style>
