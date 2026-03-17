<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>标题层级正则模式</span>
          <div>
            <el-button @click="addRow" size="small"><el-icon><Plus /></el-icon> 新增层级</el-button>
            <el-button type="warning" @click="resetDefaults" size="small">恢复默认</el-button>
            <el-button type="primary" @click="saveAll" size="small" :loading="saving">保存</el-button>
          </div>
        </div>
      </template>

      <el-table :data="patterns" stripe>
        <el-table-column prop="level" label="层级" width="70">
          <template #default="{ row }">
            <el-input-number v-model="row.level" :min="1" :max="10" size="small" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="正则表达式" min-width="300">
          <template #default="{ row }">
            <el-input v-model="row.pattern" size="small" placeholder="如 ^第[一二三]+章\s*(.*)" />
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" width="120">
          <template #default="{ row }">
            <el-input v-model="row.description" size="small" />
          </template>
        </el-table-column>
        <el-table-column prop="example" label="示例" width="180">
          <template #default="{ row }">
            <el-input v-model="row.example" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="测试" width="80">
          <template #default="{ row }">
            <el-button size="small" @click="testRow(row)" circle>
              <el-icon><CaretRight /></el-icon>
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="" width="60">
          <template #default="{ $index }">
            <el-button size="small" type="danger" @click="removeRow($index)" circle>
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 测试结果 -->
    <el-card shadow="never" style="margin-top: 16px">
      <template #header>正则测试</template>
      <el-row :gutter="12">
        <el-col :span="16">
          <el-input v-model="testText" placeholder="输入测试文本，如：第二章 合同战术基本理论" />
        </el-col>
        <el-col :span="4">
          <el-button @click="testAll">全部测试</el-button>
        </el-col>
      </el-row>
      <div v-if="testResult" style="margin-top: 12px;">
        <el-alert :type="testResult.matched ? 'success' : 'warning'" :closable="false"
          :title="testResult.matched ? `✅ 匹配层级 ${testResult.level}：${testResult.match_text}` : '❌ 未匹配任何层级'" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getLevelPatterns, updateLevelPatterns, testPattern, resetPatterns } from '../api'

const patterns = ref([])
const saving = ref(false)
const testText = ref('')
const testResult = ref(null)

onMounted(async () => {
  const { data } = await getLevelPatterns()
  patterns.value = data
})

const addRow = () => {
  const maxLevel = Math.max(...patterns.value.map(p => p.level), 0)
  patterns.value.push({ level: maxLevel + 1, pattern: '', description: '', example: '' })
}

const removeRow = (idx) => patterns.value.splice(idx, 1)

const saveAll = async () => {
  saving.value = true
  try {
    await updateLevelPatterns(patterns.value)
    ElMessage.success('保存成功')
  } finally { saving.value = false }
}

const resetDefaults = async () => {
  await resetPatterns()
  const { data } = await getLevelPatterns()
  patterns.value = data
  ElMessage.success('已恢复默认')
}

const testRow = async (row) => {
  const text = row.example || testText.value
  if (!text) return ElMessage.warning('请输入测试文本')
  const { data } = await testPattern(row.pattern, text)
  testResult.value = { ...data, level: row.level }
}

const testAll = async () => {
  if (!testText.value) return ElMessage.warning('请输入测试文本')
  for (const p of patterns.value) {
    const { data } = await testPattern(p.pattern, testText.value)
    if (data.matched) {
      testResult.value = { ...data, level: p.level }
      return
    }
  }
  testResult.value = { matched: false }
}
</script>
