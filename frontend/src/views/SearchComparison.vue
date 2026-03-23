<template>
  <div>
    <!-- 检索通道选择（发送前可选） -->
    <el-card shadow="never" style="margin-bottom: 12px">
      <el-form inline size="small">
        <el-form-item label="检索通道">
          <el-checkbox v-model="opts.use_vector">向量</el-checkbox>
          <el-checkbox v-model="opts.use_bm25">BM25</el-checkbox>
          <el-checkbox v-model="opts.use_graph">图谱</el-checkbox>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 查询输入 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <el-input v-model="query" placeholder="输入检索查询..." @keyup.enter="doSearch" size="large">
        <template #append>
          <el-button @click="doSearch" :loading="loading" type="primary">检索对比</el-button>
        </template>
      </el-input>
    </el-card>

    <!-- 四路结果对比 -->
    <el-row :gutter="16" v-if="result">
      <el-col :span="6">
        <el-card shadow="never">
          <template #header>
            <span>🔷 向量检索 ({{ result.vector_results.length }})</span>
          </template>
          <ResultList :items="result.vector_results" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <template #header>
            <span>🔶 BM25 检索 ({{ result.bm25_results.length }})</span>
          </template>
          <ResultList :items="result.bm25_results" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <template #header>
            <span>🟣 图谱检索 ({{ result.graph_results.length }})</span>
          </template>
          <ResultList :items="result.graph_results" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <template #header>
            <span>🟢 RRF 融合 ({{ result.rrf_results.length }})</span>
          </template>
          <ResultList :items="result.rrf_results" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, defineComponent, h } from 'vue'
import { ElMessage } from 'element-plus'
import { searchComparison } from '../api'

const query = ref('')
const loading = ref(false)
const result = ref(null)
const opts = ref({
  use_vector: true,
  use_bm25: true,
  use_graph: true,
})

const doSearch = async () => {
  if (!query.value.trim() || loading.value) return
  loading.value = true
  try {
    const retrieval = { ...opts.value }
    const { data } = await searchComparison(query.value, null, retrieval)
    result.value = data
  } catch (e) {
    ElMessage.error('检索失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

// 内联结果列表组件
const ResultList = defineComponent({
  props: { items: Array },
  setup(props) {
    return () => h('div', { class: 'result-list' },
      props.items.map((item, idx) =>
        h('div', { class: 'result-item', key: idx }, [
          h('div', { class: 'ri-rank' }, `#${idx + 1}`),
          h('div', { class: 'ri-title' }, item.title || item.chunk_id),
          h('div', { class: 'ri-chain' }, item.title_chain || ''),
          h('div', { class: 'ri-score' }, `得分: ${item.score?.toFixed(4) || '-'}`),
          h('div', { class: 'ri-text' }, (item.text || '').substring(0, 150) + '...'),
          h('hr'),
        ])
      )
    )
  }
})
</script>

<style scoped>
.result-list { max-height: 600px; overflow-y: auto; }
.result-item { margin-bottom: 12px; font-size: 13px; }
.ri-rank { font-weight: bold; color: #409eff; }
.ri-title { font-weight: 500; margin: 4px 0; }
.ri-chain { color: #909399; font-size: 12px; }
.ri-score { color: #e6a23c; font-size: 12px; margin: 2px 0; }
.ri-text { color: #606266; line-height: 1.6; margin-top: 4px; }
</style>
