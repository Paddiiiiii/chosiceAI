<template>
  <div>
    <!-- 过滤 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-row :gutter="12">
        <el-col :span="6">
          <el-select v-model="filters.doc_id" clearable placeholder="文档" @change="fetchChunks">
            <el-option v-for="d in docs" :key="d.doc_id" :label="d.filename" :value="d.doc_id" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.chunk_type" clearable placeholder="类型" @change="fetchChunks">
            <el-option label="overview" value="overview" />
            <el-option label="detail" value="detail" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.phase" clearable placeholder="阶段" @change="fetchChunks">
            <el-option label="战斗准备" value="战斗准备" />
            <el-option label="战斗实施" value="战斗实施" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-input v-model="searchText" placeholder="搜索标题..." clearable @input="onFilter" />
        </el-col>
        <el-col :span="4">
          <el-statistic :value="displayChunks.length" title="结果数" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 列表 -->
    <el-table :data="displayChunks" stripe @row-click="showDetail" style="cursor: pointer" max-height="600">
      <el-table-column prop="chunk_id" label="ID" width="180" />
      <el-table-column prop="chunk_type" label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.chunk_type === 'overview' ? 'warning' : 'success'" size="small">{{ row.chunk_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="context_tags.phase" label="阶段" width="100" />
      <el-table-column prop="context_tags.battle_type" label="战斗类型" width="100" />
      <el-table-column label="角色" width="200">
        <template #default="{ row }">
          <el-tag v-for="r in row.roles_mentioned" :key="r" size="small" class="mr-1">{{ r }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="metadata.char_count" label="字数" width="60" />
    </el-table>

    <!-- 详情弹窗 -->
    <el-dialog v-model="dialogVisible" :title="detailChunk?.title" width="70%">
      <el-descriptions :column="2" border size="small" v-if="detailChunk">
        <el-descriptions-item label="Chunk ID">{{ detailChunk.chunk_id }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ detailChunk.chunk_type }}</el-descriptions-item>
        <el-descriptions-item label="层级">{{ detailChunk.level }}</el-descriptions-item>
        <el-descriptions-item label="字数">{{ detailChunk.metadata?.char_count }}</el-descriptions-item>
        <el-descriptions-item label="标题链" :span="2">{{ detailChunk.title_chain }}</el-descriptions-item>
        <el-descriptions-item label="阶段">{{ detailChunk.context_tags?.phase }}</el-descriptions-item>
        <el-descriptions-item label="战斗类型">{{ detailChunk.context_tags?.battle_type }}</el-descriptions-item>
        <el-descriptions-item label="父 ID">{{ detailChunk.parent_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="子 ID">{{ detailChunk.children_ids?.join(', ') || '-' }}</el-descriptions-item>
        <el-descriptions-item label="文档 ID">{{ detailChunk.document_id }}</el-descriptions-item>
        <el-descriptions-item label="来源文件">{{ detailChunk.metadata?.source_file }}</el-descriptions-item>
        <el-descriptions-item label="角色提及" :span="2">
          <el-tag v-for="r in detailChunk.roles_mentioned" :key="r" class="mr-1">{{ r }}</el-tag>
          <span v-if="!detailChunk.roles_mentioned?.length" style="color: #c0c4cc">无</span>
        </el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 16px;">
        <h4>正文内容</h4>
        <div class="chunk-text">{{ detailChunk?.text }}</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { listChunks, listDocuments } from '../api'

const docs = ref([])
const chunks = ref([])
const filters = ref({ doc_id: '', chunk_type: '', phase: '' })
const searchText = ref('')
const dialogVisible = ref(false)
const detailChunk = ref(null)

const displayChunks = computed(() => {
  if (!searchText.value) return chunks.value
  const kw = searchText.value.toLowerCase()
  return chunks.value.filter(c => c.title.toLowerCase().includes(kw) || c.chunk_id.includes(kw))
})

onMounted(async () => {
  const { data } = await listDocuments()
  docs.value = data
  await fetchChunks()
})

const fetchChunks = async () => {
  const params = {}
  if (filters.value.doc_id) params.doc_id = filters.value.doc_id
  if (filters.value.chunk_type) params.chunk_type = filters.value.chunk_type
  if (filters.value.phase) params.phase = filters.value.phase
  const { data } = await listChunks(params)
  chunks.value = data
}

const showDetail = (row) => {
  detailChunk.value = row
  dialogVisible.value = true
}

const onFilter = () => {} // reactive via computed
</script>

<style scoped>
.chunk-text {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
  line-height: 1.8;
  white-space: pre-wrap;
  max-height: 400px;
  overflow-y: auto;
}
.mr-1 { margin-right: 4px; }
</style>
