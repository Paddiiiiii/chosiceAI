<template>
  <div class="routing-page">
    <el-row :gutter="20" style="height: 100%">
      <!-- 左侧：对话区 -->
      <el-col :span="16" style="height: 100%">
        <el-card class="chat-card" shadow="never">
          <!-- 对话历史 -->
          <div class="chat-messages" ref="chatRef">
            <div v-if="messages.length === 0" class="empty-hint">
              <el-icon :size="48" color="#c0c4cc"><ChatDotRound /></el-icon>
              <p>输入任务描述，系统将路由到正确的负责角色</p>
              <p class="hint-example">例如：「侦察计划该谁去做？」「谁负责组织战斗协同？」</p>
            </div>
            <div v-for="(msg, idx) in messages" :key="idx" :class="['chat-msg', msg.role]">
              <div v-if="msg.role === 'user'" class="msg-user">
                <el-icon><UserFilled /></el-icon>
                <span>{{ msg.content }}</span>
              </div>
              <div v-else class="msg-system">
                <el-icon><Cpu /></el-icon>
                <div class="routing-result" v-if="msg.result">
                  <el-descriptions :column="1" border size="small">
                    <el-descriptions-item label="牵头负责">
                      <el-tag type="primary" size="large">{{ msg.result.lead }}</el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item label="参与协助" v-if="msg.result.participants?.length">
                      <el-tag v-for="p in msg.result.participants" :key="p" class="mr-1">{{ p }}</el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item label="审批角色" v-if="msg.result.approver">
                      <el-tag type="warning">{{ msg.result.approver }}</el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item label="判断依据">
                      {{ msg.result.reasoning }}
                    </el-descriptions-item>
                    <el-descriptions-item label="置信度">
                      <el-progress :percentage="Math.round(msg.result.confidence * 100)" :stroke-width="14" :text-inside="true" />
                    </el-descriptions-item>
                    <el-descriptions-item label="出处" v-if="msg.result.basis">
                      <el-text size="small" type="info">{{ msg.result.basis.title_chain }}</el-text>
                      <br />
                      <el-text size="small">{{ msg.result.basis.text_snippet }}</el-text>
                    </el-descriptions-item>
                  </el-descriptions>
                </div>
              </div>
            </div>
            <div v-if="loading" class="msg-loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在分析中...</span>
            </div>
          </div>

          <!-- 输入区 -->
          <div class="chat-input">
            <el-input
              v-model="inputText"
              placeholder="输入旅长的指示或任务描述..."
              @keyup.enter="sendQuery"
              :disabled="loading"
              size="large"
            >
              <template #append>
                <el-button @click="sendQuery" :loading="loading" type="primary">
                  <el-icon><Promotion /></el-icon>
                </el-button>
              </template>
            </el-input>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：过滤条件 -->
      <el-col :span="8">
        <el-card shadow="never">
          <template #header>过滤条件（可选）</template>
          <el-form label-position="top" size="small">
            <el-form-item label="战斗阶段">
              <el-select v-model="filters.phase" clearable placeholder="全部">
                <el-option label="战斗准备" value="战斗准备" />
                <el-option label="战斗实施" value="战斗实施" />
                <el-option label="主要样式" value="主要样式" />
              </el-select>
            </el-form-item>
            <el-form-item label="战斗类型">
              <el-select v-model="filters.battle_type" clearable placeholder="全部">
                <el-option label="进攻战斗" value="进攻战斗" />
                <el-option label="防御战斗" value="防御战斗" />
              </el-select>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 检索结果 -->
        <el-card shadow="never" style="margin-top: 16px" v-if="lastSearchResults.length">
          <template #header>检索到的相关段落</template>
          <div v-for="(r, i) in lastSearchResults" :key="i" class="search-item">
            <div class="search-title">{{ i + 1 }}. {{ r.title }}</div>
            <el-text size="small" type="info">{{ r.title_chain }}</el-text>
            <el-text size="small" class="search-text">{{ r.text?.substring(0, 120) }}...</el-text>
            <el-divider />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, watch } from 'vue'
import { chatQuery } from '../api'

const STORAGE_KEY = 'routing_chat_history'

const inputText = ref('')
const loading = ref(false)
const messages = ref([])
const lastSearchResults = ref([])
const chatRef = ref(null)
const filters = ref({ phase: '', battle_type: '' })

// 从 sessionStorage 恢复对话
onMounted(() => {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY)
    if (saved) {
      const data = JSON.parse(saved)
      messages.value = data.messages || []
      lastSearchResults.value = data.searchResults || []
      scrollToBottom()
    }
  } catch {}
})

// 对话变化时保存到 sessionStorage
watch([messages, lastSearchResults], () => {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      messages: messages.value,
      searchResults: lastSearchResults.value,
    }))
  } catch {}
}, { deep: true })

const sendQuery = async () => {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  loading.value = true
  scrollToBottom()

  try {
    const ctx = {}
    if (filters.value.phase) ctx.phase = filters.value.phase
    if (filters.value.battle_type) ctx.battle_type = filters.value.battle_type
    const context = Object.keys(ctx).length > 0 ? ctx : null

    const { data } = await chatQuery(text, context)
    messages.value.push({ role: 'system', result: data.result })
    lastSearchResults.value = data.search_results || []
  } catch (e) {
    messages.value.push({ role: 'system', result: { lead: '错误', reasoning: e.message, confidence: 0 } })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

const scrollToBottom = () => {
  nextTick(() => {
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  })
}
</script>

<style scoped>
.routing-page { height: calc(100vh - 96px); }
.chat-card { height: 100%; display: flex; flex-direction: column; }
.chat-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 0; }
.chat-messages { flex: 1; overflow-y: auto; padding: 20px; }
.chat-input { padding: 12px 20px; border-top: 1px solid #e4e7ed; }
.empty-hint { text-align: center; padding: 80px 0; color: #909399; }
.hint-example { font-size: 13px; margin-top: 8px; color: #c0c4cc; }
.chat-msg { margin-bottom: 16px; }
.msg-user { display: flex; align-items: flex-start; gap: 8px; justify-content: flex-end; }
.msg-user span { background: #409eff; color: #fff; padding: 8px 14px; border-radius: 12px 12px 2px 12px; max-width: 70%; }
.msg-system { display: flex; align-items: flex-start; gap: 8px; }
.routing-result { max-width: 100%; }
.msg-loading { display: flex; align-items: center; gap: 8px; color: #909399; padding: 8px; }
.mr-1 { margin-right: 4px; }
.search-item { margin-bottom: 4px; }
.search-title { font-weight: 500; font-size: 13px; margin-bottom: 2px; }
.search-text { display: block; margin-top: 4px; line-height: 1.5; }
</style>
