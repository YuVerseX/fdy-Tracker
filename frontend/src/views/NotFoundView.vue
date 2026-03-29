<template>
  <main class="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center px-6 text-center">
    <p class="text-sm font-medium uppercase tracking-[0.2em] text-sky-700">404</p>
    <h1 class="mt-4 text-3xl font-semibold text-slate-900">这个页面不存在</h1>
    <p class="mt-3 text-sm text-slate-600">
      你可以回到招聘列表继续浏览，或者进入管理台检查路由配置。
    </p>
    <div class="mt-6 flex flex-wrap justify-center gap-3">
      <router-link
        :to="{ name: 'PostList' }"
        class="rounded-lg bg-sky-700 px-4 py-2 text-white transition hover:bg-sky-800"
      >
        返回列表
      </router-link>
      <router-link
        :to="{ name: 'AdminDashboard' }"
        class="rounded-lg border border-slate-300 px-4 py-2 text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
      >
        进入管理台
      </router-link>
    </div>
  </main>
</template>
