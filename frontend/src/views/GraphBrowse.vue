<template>
  <div class="graph-browse">
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>流程图谱可视化</span>
          <div>
            <el-button size="small" @click="loadGraph" :loading="loading">
              <el-icon><Refresh /></el-icon> 刷新
            </el-button>
            <el-tag v-if="stats" type="info" size="small" style="margin-left: 8px">
              节点 {{ Object.values(stats.nodes || {}).reduce((a, b) => a + b, 0) }} / 边 {{ Object.values(stats.relationships || {}).reduce((a, b) => a + b, 0) }}
            </el-tag>
          </div>
        </div>
      </template>
      <div ref="networkContainer" class="network-container"></div>
      <div v-if="!loading && (!graphData?.nodes?.length)" class="empty-tip">
        暂无图谱数据，请先在「文档管理」中构建流程图谱
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getGraphViz, getGraphStats } from '../api'
import { DataSet } from 'vis-data'
import { Network } from 'vis-network'

const networkContainer = ref(null)
const loading = ref(false)
const graphData = ref(null)
const stats = ref(null)
let network = null

async function loadGraph() {
  loading.value = true
  try {
    const [vizRes, statsRes] = await Promise.all([
      getGraphViz(500),
      getGraphStats(),
    ])
    graphData.value = vizRes.data
    stats.value = statsRes.data

    if (!networkContainer.value || !graphData.value?.nodes?.length) {
      loading.value = false
      return
    }

    const colors = graphData.value.labelColors || {}
    const defaultColor = graphData.value.defaultColor || '#757575'

    const nodes = new DataSet(
      graphData.value.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        title: n.title,
        color: colors[n.group] || defaultColor,
        font: { size: 12 },
      }))
    )
    const edges = new DataSet(
      graphData.value.edges.map((e) => ({
        from: e.from,
        to: e.to,
        label: e.label,
        title: e.title,
        arrows: 'to',
        font: { size: 10, align: 'middle' },
      }))
    )

    const options = {
      nodes: { shape: 'dot', size: 16 },
      edges: { width: 1.5 },
      physics: {
        enabled: true,
        barnesHut: {
          gravitationalConstant: -3000,
          centralGravity: 0.1,
          springLength: 120,
          springConstant: 0.04,
          damping: 0.09,
        },
        stabilization: { iterations: 150 },
      },
      interaction: { hover: true, tooltipDelay: 200 },
    }

    network = new Network(networkContainer.value, { nodes, edges }, options)
  } catch (e) {
    console.error('Load graph failed:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadGraph)
</script>

<style scoped>
.graph-browse {
  height: calc(100vh - 140px);
}
.network-container {
  width: 100%;
  height: 600px;
  min-height: 400px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fff;
}
.empty-tip {
  padding: 40px;
  text-align: center;
  color: #909399;
}
</style>
