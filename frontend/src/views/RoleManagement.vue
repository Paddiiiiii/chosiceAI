<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>角色列表</span>
          <el-button type="primary" @click="showAdd" size="small">
            <el-icon><Plus /></el-icon> 新增角色
          </el-button>
        </div>
      </template>

      <el-table :data="roles" stripe>
        <el-table-column prop="role_id" label="角色 ID" width="100" />
        <el-table-column prop="name" label="角色名称" min-width="200" />
        <el-table-column prop="mention_count" label="提及次数" width="100" sortable />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="showEdit(row)">编辑</el-button>
            <el-popconfirm title="确定删除?" @confirm="doDelete(row.role_id)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
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
import { getRoles, addRole, updateRole, deleteRole } from '../api'

const roles = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref('')
const formName = ref('')
const saving = ref(false)

onMounted(fetchRoles)

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
</script>
