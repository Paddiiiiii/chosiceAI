<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>角色列表</span>
          <div>
            <el-button size="small" @click="doExtract" :loading="extracting">
              <el-icon><MagicStick /></el-icon> 自动提取
            </el-button>
            <el-button type="primary" @click="showAdd" size="small">
              <el-icon><Plus /></el-icon> 新增角色
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="roles" stripe>
        <el-table-column prop="role_id" label="角色 ID" width="100" />
        <el-table-column prop="name" label="角色名称" min-width="200">
          <template #default="{ row }">
            <span :style="{ color: isPending(row) ? '#f56c6c' : '' }">{{ row.name }}</span>
            <el-tag v-if="isPending(row)" type="danger" size="small" style="margin-left: 6px">待审批</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="mention_count" label="提及次数" width="100" sortable />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <template v-if="isPending(row)">
              <el-button size="small" type="success" @click="doApprove(row.role_id)">同意</el-button>
              <el-button size="small" type="danger" @click="doReject(row.role_id)">不同意</el-button>
            </template>
            <template v-else>
              <el-button size="small" @click="showEdit(row)">编辑</el-button>
              <el-popconfirm title="确定删除?" @confirm="doDelete(row.role_id)">
                <template #reference>
                  <el-button size="small" type="danger">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑角色' : '新增角色'" width="400px">
      <el-form label-width="80px">
        <el-form-item label="角色名称">
          <el-input v-model="formName" placeholder="如：参谋长" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="doSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getRoles, addRole, updateRole, deleteRole, extractRoles, approveRole, rejectRole } from '../api'

const roles = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref('')
const formName = ref('')
const saving = ref(false)
const extracting = ref(false)

onMounted(fetchRoles)

function isPending(row) {
  return row.status === 'pending'
}

async function fetchRoles() {
  const { data } = await getRoles()
  roles.value = data.roles || []
}

function showAdd() {
  isEdit.value = false
  formName.value = ''
  dialogVisible.value = true
}

function showEdit(role) {
  isEdit.value = true
  editId.value = role.role_id
  formName.value = role.name
  dialogVisible.value = true
}

async function doSave() {
  if (!formName.value.trim()) return ElMessage.warning('请输入角色名称')
  saving.value = true
  try {
    if (isEdit.value) {
      await updateRole(editId.value, formName.value)
    } else {
      await addRole(formName.value)
    }
    dialogVisible.value = false
    await fetchRoles()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

async function doDelete(roleId) {
  await deleteRole(roleId)
  await fetchRoles()
  ElMessage.success('已删除')
}

async function doExtract() {
  extracting.value = true
  try {
    const { data } = await extractRoles()
    await fetchRoles()
    ElMessage.success(data?.message || `提取完成，新增 ${data?.added || 0} 个待审批角色`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || '提取失败')
  } finally {
    extracting.value = false
  }
}

async function doApprove(roleId) {
  await approveRole(roleId)
  await fetchRoles()
  ElMessage.success('已通过')
}

async function doReject(roleId) {
  try {
    await rejectRole(roleId)
    await fetchRoles()
    ElMessage.success('已拒绝并删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}
</script>
