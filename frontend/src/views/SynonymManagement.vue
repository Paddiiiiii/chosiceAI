<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>ES 同义词管理</span>
          <div>
            <el-button type="primary" @click="showAdd" size="small"><el-icon><Plus /></el-icon> 新增</el-button>
            <el-text size="small" type="warning" style="margin-left: 12px">修改后需重建索引才能生效</el-text>
          </div>
        </div>
      </template>

      <el-table :data="synonyms" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="同义词组" min-width="400">
          <template #default="{ row }">
            <el-tag v-for="t in row.terms" :key="t" class="mr-1" size="large">{{ t }}</el-tag>
            <el-text size="small" type="info" style="margin-left: 8px">共 {{ row.terms.length }} 个词</el-text>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="showEdit(row)">编辑</el-button>
            <el-popconfirm title="确定删除?" @confirm="doDelete(row.id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑同义词组' : '新增同义词组'" width="550px">
      <el-form label-width="80px">
        <el-form-item label="同义词">
          <div style="width: 100%">
            <!-- 已添加的词 -->
            <div style="margin-bottom: 8px; min-height: 32px;">
              <el-tag
                v-for="(t, idx) in termsList"
                :key="idx"
                closable
                @close="removeTerm(idx)"
                class="mr-1"
                size="large"
              >{{ t }}</el-tag>
            </div>
            <!-- 输入新词 -->
            <el-input
              v-model="newTerm"
              placeholder="输入同义词后按 Enter 或点击添加，支持逗号分隔批量输入"
              @keyup.enter="addTerms"
              size="default"
            >
              <template #append>
                <el-button @click="addTerms">添加</el-button>
              </template>
            </el-input>
            <el-text size="small" type="info" style="margin-top: 4px; display: block;">
              一组中的所有词互为同义词，不限数量。例如：侦察、侦查、侦搜 都是同义的。
            </el-text>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="doSave" :disabled="termsList.length < 2">
          保存（{{ termsList.length }} 个词）
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listSynonyms, addSynonym, updateSynonym, deleteSynonym } from '../api'

const synonyms = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(0)
const termsList = ref([])
const newTerm = ref('')

onMounted(fetchSynonyms)

async function fetchSynonyms() {
  const { data } = await listSynonyms()
  synonyms.value = data
}

function showAdd() {
  isEdit.value = false
  termsList.value = []
  newTerm.value = ''
  dialogVisible.value = true
}

function showEdit(row) {
  isEdit.value = true
  editId.value = row.id
  termsList.value = [...row.terms]
  newTerm.value = ''
  dialogVisible.value = true
}

function addTerms() {
  // 支持中英文逗号、顿号、空格分隔批量输入
  const input = newTerm.value
  if (!input.trim()) return
  const parts = input.split(/[,，、\s]+/).map(t => t.trim()).filter(Boolean)
  for (const p of parts) {
    if (!termsList.value.includes(p)) {
      termsList.value.push(p)
    }
  }
  newTerm.value = ''
}

function removeTerm(idx) {
  termsList.value.splice(idx, 1)
}

async function doSave() {
  if (termsList.value.length < 2) return ElMessage.warning('至少需要2个同义词')
  if (isEdit.value) { await updateSynonym(editId.value, termsList.value) }
  else { await addSynonym(termsList.value) }
  dialogVisible.value = false
  await fetchSynonyms()
  ElMessage.success('保存成功')
}

async function doDelete(id) {
  await deleteSynonym(id)
  await fetchSynonyms()
  ElMessage.success('已删除')
}
</script>

<style scoped>
.mr-1 { margin-right: 6px; margin-bottom: 4px; }
</style>
