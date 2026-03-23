import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/routing' },
  { path: '/routing', name: 'RoutingQuery', component: () => import('../views/RoutingQuery.vue'), meta: { title: '路由查询' } },
  { path: '/search', name: 'SearchComparison', component: () => import('../views/SearchComparison.vue'), meta: { title: '检索对比' } },
  { path: '/tree', name: 'DocumentTree', component: () => import('../views/DocumentTree.vue'), meta: { title: '结构浏览' } },
  { path: '/graph-browse', name: 'GraphBrowse', component: () => import('../views/GraphBrowse.vue'), meta: { title: '图谱浏览' } },
  { path: '/chunks', name: 'ChunkDetail', component: () => import('../views/ChunkDetail.vue'), meta: { title: 'Chunk 详情' } },
  { path: '/ocr-review', name: 'OcrReview', component: () => import('../views/OcrReview.vue'), meta: { title: 'OCR 审核' } },
  { path: '/roles', name: 'RoleManagement', component: () => import('../views/RoleManagement.vue'), meta: { title: '角色管理' } },
  { path: '/anomaly-review', name: 'AnomalyReview', component: () => import('../views/AnomalyReview.vue'), meta: { title: '异常审核' } },
  { path: '/synonyms', name: 'SynonymManagement', component: () => import('../views/SynonymManagement.vue'), meta: { title: '同义词管理' } },
  { path: '/level-patterns', name: 'LevelPatternConfig', component: () => import('../views/LevelPatternConfig.vue'), meta: { title: '层级配置' } },
  { path: '/documents', name: 'DocumentManagement', component: () => import('../views/DocumentManagement.vue'), meta: { title: '文档管理' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
