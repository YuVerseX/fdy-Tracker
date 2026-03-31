<template>
  <div class="min-h-screen">
    <main class="app-shell max-w-3xl justify-center">
      <AppPageHeader
        eyebrow="404"
        title="这个页面不存在"
        description="你可以回到招聘列表继续浏览，看看其它正在关注的公告。"
        action-label="返回列表"
        :action-to="{ name: 'PostList' }"
      />
    </main>
  </div>
</template>

<script setup>
import AppPageHeader from '../components/ui/AppPageHeader.vue'
</script>
