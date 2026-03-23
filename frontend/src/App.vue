<template>
  <el-container class="app-container">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="app-aside">
      <div class="logo">
        <el-icon :size="24"><Aim /></el-icon>
        <span>任务路由系统</span>
      </div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#1d1e1f"
        text-color="#bbb"
        active-text-color="#409eff"
      >
        <el-menu-item-group title="核心功能">
          <el-menu-item index="/routing">
            <el-icon><ChatDotRound /></el-icon>
            <span>路由查询</span>
          </el-menu-item>
          <el-menu-item index="/search">
            <el-icon><Search /></el-icon>
            <span>检索对比</span>
          </el-menu-item>
        </el-menu-item-group>

        <el-menu-item-group title="数据浏览">
          <el-menu-item index="/tree">
            <el-icon><Collection /></el-icon>
            <span>结构浏览</span>
          </el-menu-item>
          <el-menu-item index="/graph-browse">
            <el-icon><Share /></el-icon>
            <span>图谱浏览</span>
          </el-menu-item>
          <el-menu-item index="/chunks">
            <el-icon><Document /></el-icon>
            <span>Chunk 详情</span>
          </el-menu-item>
        </el-menu-item-group>

        <el-menu-item-group title="审核管理">
          <el-menu-item index="/ocr-review">
            <el-icon><EditPen /></el-icon>
            <span>OCR 审核</span>
          </el-menu-item>
          <el-menu-item index="/anomaly-review">
            <el-icon><Warning /></el-icon>
            <span>异常审核</span>
          </el-menu-item>
        </el-menu-item-group>

        <el-menu-item-group title="系统配置">
          <el-menu-item index="/roles">
            <el-icon><User /></el-icon>
            <span>角色管理</span>
          </el-menu-item>
          <el-menu-item index="/synonyms">
            <el-icon><Connection /></el-icon>
            <span>同义词管理</span>
          </el-menu-item>
          <el-menu-item index="/level-patterns">
            <el-icon><Setting /></el-icon>
            <span>层级配置</span>
          </el-menu-item>
          <el-menu-item index="/documents">
            <el-icon><FolderOpened /></el-icon>
            <span>文档管理</span>
          </el-menu-item>
        </el-menu-item-group>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <el-header class="app-header">
        <h2>{{ $route.meta.title || '任务路由智能系统' }}</h2>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }

.app-container { height: 100vh; }

.app-aside {
  background: #1d1e1f;
  border-right: 1px solid #333;
  overflow-y: auto;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  color: #409eff;
  font-size: 16px;
  font-weight: bold;
  border-bottom: 1px solid #333;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: 56px;
}
.app-header h2 {
  font-size: 18px;
  color: #303133;
}

.app-main {
  background: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
}

.el-menu {
  border-right: none !important;
}
.el-menu-item-group__title {
  color: #666 !important;
  font-size: 12px !important;
  padding-left: 16px !important;
}
</style>
