import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(() => {
  const apiTarget = process.env.VITE_DEV_API_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true
        },
        '/docs': {
          target: apiTarget,
          changeOrigin: true
        },
        '/openapi.json': {
          target: apiTarget,
          changeOrigin: true
        },
        '/redoc': {
          target: apiTarget,
          changeOrigin: true
        }
      }
    }
  }
})
