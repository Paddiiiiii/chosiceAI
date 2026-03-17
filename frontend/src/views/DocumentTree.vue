<template>
  <div>
    <el-row :gutter="16">
      <!-- 文档选择 + 树 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>文档结构树</template>
          <el-select v-model="selectedDoc" placeholder="选择文档" style="width: 100%; margin-bottom: 12px" @change="loadTree">
            <el-option v-for="d in docs" :key="d.doc_id" :label="d.filename" :value="d.doc_id" />
          </el-select>
          <el-tree
            v-if="treeData.length"
            :data="treeData"
            :props="{ label: 'title', children: 'children' }"
            highlight-current
            @node-click="onNodeClick"
            default-expand-all
          />
          <el-empty v-else description="请选择文档" />
        </el-card>
      </el-col>

      <!-- 节点详情 -->
      <el-col :span="14">
        <el-card ref="detailCard" shadow="never" v-if="selectedNode">
          <template #header>{{ selectedNode.title }}</template>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="ID">{{ selectedNode.id }}</el-descriptions-item>
            <el-descriptions-item label="层级">{{ selectedNode.level }}</el-descriptions-item>
            <el-descriptions-item label="行范围">{{ selectedNode.line_start }} - {{ selectedNode.line_end }}</el-descriptions-item>
            <el-descriptions-item label="子节点数">{{ selectedNode.children?.length || 0 }}</el-descriptions-item>
          </el-descriptions>
          <div v-if="selectedNode.text" style="margin-top: 12px;">
            <h4>节点文本</h4>
            <div class="node-text">{{ selectedNode.text }}</div>
          </div>

          <!-- 该节点的 Chunks -->
          <div v-if="nodeChunks.length" style="margin-top: 16px;">
            <h4>关联 Chunks ({{ nodeChunks.length }})</h4>
            <el-table :data="nodeChunks" size="small" stripe>
              <el-table-column prop="chunk_id" label="Chunk ID" width="180" />
              <el-table-column prop="chunk_type" label="类型" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.chunk_type === 'overview' ? 'warning' : 'success'" size="small">
                    {{ row.chunk_type }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="title" label="标题" />
              <el-table-column prop="metadata.char_count" label="字数" width="60" />
            </el-table>
          </div>
        </el-card>
        <el-card shadow="never" v-else>
          <el-empty description="点击左侧树节点查看详情" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { listDocuments, getStructure, listChunks } from '../api'

const docs = ref([])
const selectedDoc = ref('')
const treeData = ref([])
const selectedNode = ref(null)
const nodeChunks = ref([])
const allChunks = ref([])
const detailCard = ref(null)

onMounted(async () => {
  const { data } = await listDocuments()
  docs.value = data
})

const loadTree = async (docId) => {
  try {
    const [treeRes, chunksRes] = await Promise.all([
      getStructure(docId),
      listChunks({ doc_id: docId }),
    ])
    treeData.value = treeRes.data.children || []
    allChunks.value = chunksRes.data
  } catch (e) {
    treeData.value = []
  }
}

const onNodeClick = (node) => {
  selectedNode.value = node
  // 查找匹配的 chunks
  nodeChunks.value = allChunks.value.filter(c =>
    c.chunk_id === node.id || c.chunk_id.startsWith(node.id + '_')
  )
  // 点击后将右侧详情卡片滚动到可视区域
  nextTick(() => {
    detailCard.value?.$el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}
</script>

<style scoped>
.node-text {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  line-height: 1.8;
  font-size: 14px;
  max-height: 300px;
  overflow-y: auto;
  white-space: pre-wrap;
}
</style>
