import { fileURLToPath, URL } from 'node:url'
import type { ProxyOptions, ConfigEnv, ViteDevServer } from 'vite'
import { defineConfig, loadEnv } from 'vite'
import type { IncomingMessage, ServerResponse } from 'node:http'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import DefineOptions from 'unplugin-vue-define-options/vite'
import { existsSync, unlinkSync, renameSync } from 'node:fs'
import path from 'node:path'
import { createHtmlPlugin } from 'vite-plugin-html'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const envDir = './env'

// Custom plugin: rename entry HTML to index.html after build
const renameHtmlPlugin = (outDir: string, entry: string) => {
  return {
    name: 'rename-html',
    closeBundle: () => {
      const buildDir = path.resolve(__dirname, outDir)
      const oldFile = path.join(buildDir, entry)
      const newFile = path.join(buildDir, 'index.html')

      if (existsSync(oldFile)) {
        if (existsSync(newFile)) {
          unlinkSync(newFile)
        }
        renameSync(oldFile, newFile)
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig((conf: ConfigEnv) => {
  const mode = conf.mode
  const ENV = loadEnv(mode, envDir)
  const proxyConf: Record<string, string | ProxyOptions> = {}

  proxyConf['/admin/api'] = {
    target: 'http://127.0.0.1:8080',
    changeOrigin: true,
    ws: true,
  }
  proxyConf['/chat/api'] = {
    target: 'http://127.0.0.1:8080',
    changeOrigin: true,
    ws: true,
  }
  proxyConf['/ws'] = {
    target: 'http://127.0.0.1:8080',
    changeOrigin: true,
    ws: true,
  }
  proxyConf['/doc'] = {
    target: 'http://127.0.0.1:8080',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(ENV.VITE_BASE_PATH, '/'),
  }
  proxyConf['/schema'] = {
    target: 'http://127.0.0.1:8080',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(ENV.VITE_BASE_PATH, '/'),
  }
  proxyConf['/static'] = {
    target: 'http://127.0.0.1:8080',
    changeOrigin: true,
    rewrite: (path: string) => path.replace(ENV.VITE_BASE_PATH, '/'),
  }

  // OSS file proxy rules
  proxyConf[`^${ENV.VITE_BASE_PATH}.+\\/oss\\/file\\/.*$`] = {
    target: `http://127.0.0.1:8080`,
    changeOrigin: true,
  }
  proxyConf[`^${ENV.VITE_BASE_PATH}oss\\/file\\/.*$`] = {
    target: `http://127.0.0.1:8080`,
    changeOrigin: true,
  }
  proxyConf[`^${ENV.VITE_BASE_PATH}oss\\/get_url\\/.*$`] = {
    target: `http://127.0.0.1:8080`,
    changeOrigin: true,
  }

  return {
    preflight: false,
    lintOnSave: false,
    base: './',
    envDir: envDir,
    plugins: [
      vue(),
      vueJsx(),
      DefineOptions(),
      createHtmlPlugin({ template: ENV.VITE_ENTRY }),
      renameHtmlPlugin(`dist${ENV.VITE_BASE_PATH}`, ENV.VITE_ENTRY),
    ],
    server: {
      cors: true,
      host: '0.0.0.0',
      port: Number(ENV.VITE_APP_PORT),
      strictPort: true,
      proxy: proxyConf,
      fs: { allow: ['.'] },
      configureServer(server: ViteDevServer) {
        server.middlewares.use((req: IncomingMessage, _res: ServerResponse, next: () => void) => {
          const url = req.url || ''
          // SPA fallback: /admin/* → admin.html, /chat/* → chat.html
          if (url === '/admin' || url.startsWith('/admin/')) {
            req.url = '/admin.html'
          } else if (url === '/chat' || url.startsWith('/chat/')) {
            req.url = '/chat.html'
          } else if (url === '/') {
            req.url = '/admin.html'
          }
          next()
        })
      },
    },
    build: {
      outDir: `dist${ENV.VITE_BASE_PATH}`,
      target: 'es2022',
      rollupOptions: {
        input: ENV.VITE_ENTRY,
      },
    },
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
  }
})
