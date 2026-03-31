<template>
  <main class="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 text-center">
    <p class="text-sm font-medium uppercase tracking-[0.2em] text-sky-700">404</p>
    <h1 class="mt-4 text-3xl font-semibold text-slate-900">这个页面不存在</h1>
    <p class="mt-3 text-sm text-slate-600">
      你可以回到招聘列表继续浏览，看看其它正在关注的公告。
    </p>
    <div class="mt-6 flex flex-wrap justify-center gap-3">
      <router-link
        :to="{ name: 'PostList' }"
        class="rounded-lg bg-sky-700 px-4 py-2 text-white transition hover:bg-sky-800"
      >
        返回列表
      </router-link>
    </div>
  </main>
</template>
