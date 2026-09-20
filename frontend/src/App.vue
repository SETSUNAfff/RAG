<template>
  <div class="app-shell">
    <header class="app-topbar">
      <div class="topbar-left">
        <div class="brand">
          <span class="brand-icon"><i class="el-icon-coin"></i></span>
          <span class="brand-name">{{ config.brand_name || 'RAG 知识库' }}</span>
        </div>
        <nav class="topbar-nav">
          <router-link to="/documents" class="nav-link" :class="{ active: $route.path === '/documents' }">文档管理</router-link>
          <router-link to="/evaluation" class="nav-link" :class="{ active: $route.path === '/evaluation' }">效果评测</router-link>
        </nav>
      </div>
      <div class="topbar-right">
        <template v-if="isChatRoute">
          <el-button
            type="primary"
            icon="el-icon-plus"
            class="topbar-btn-primary"
            @click="newConversation"
          >新建对话</el-button>
          <el-button
            icon="el-icon-upload2"
            class="topbar-btn-secondary"
            @click="openUpload"
          >上传来源</el-button>
        </template>
        <el-button icon="el-icon-setting" class="topbar-btn-secondary" title="设置">设置</el-button>
        <el-avatar :size="32" icon="el-icon-user-solid" class="topbar-avatar"></el-avatar>
      </div>
    </header>
    <main class="app-main">
      <transition name="page" mode="out-in">
        <keep-alive include="ChatView">
          <router-view />
        </keep-alive>
      </transition>
    </main>
  </div>
</template>

<script>
import { getUserId } from '@/api'
import { getConfig } from '@/api'
import eventBus from '@/utils/eventBus'

export default {
  name: 'App',
  data() {
    return {
      userId: getUserId(),
      config: {}
    }
  },
  computed: {
    isChatRoute() {
      return this.$route.path === '/chat' || this.$route.path === '/'
    }
  },
  created() {
    this.loadConfig()
  },
  methods: {
    async loadConfig() {
      try {
        const data = await getConfig()
        this.config = data || {}
      } catch (error) {
        this.config = {}
      }
    },
    newConversation() {
      eventBus.$emit('new-conversation')
    },
    openUpload() {
      eventBus.$emit('open-upload')
    }
  }
}
</script>
