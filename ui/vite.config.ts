import { fileURLToPath, URL } from 'node:url'
import type { ProxyOptions, ConfigEnv, ViteDevServer } from 'vite'
import { defineConfig, loadEnv } from 'vite'
import type { IncomingMessage, ServerResponse } from 'node:http'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import DefineOptions from 'unplugin-vue-define-options/vite'
import { createHtmlPlugin } from 'vite-plugin-html'

const envDir = './env'

// SPA history fallback - insert at front of middleware stack to run before Vite internals
const spaFallbackPlugin = () => {
  return {
    name: 'spa-fallback',
    configureServer(server: ViteDevServer) {
      const handler = (req: IncomingMessage, _res: ServerResponse, next: () => void) => {
        const url = req.url || ''
        if (url.startsWith('/admin/api') || url.startsWith('/chat/api') || url.startsWith('/ws/')) return next()
        if (url.includes('.') && !url.endsWith('.html')) return next()
        if (url === '/admin' || url.startsWith('/admin/')) { req.url = '/admin.html'; return next() }
        if (url === '/chat' || url.startsWith('/chat/')) { req.url = '/chat.html'; return next() }
        if (url === '/') { req.url = '/admin.html'; return next() }
        next()
      }
      // Insert at position 0 to run BEFORE Vite's own HTML/static middlewares
      server.middlewares.stack.unshift({ route: '', handle: handler } as any)
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
      spaFallbackPlugin(),
    ],
    server: {
      cors: true,
      host: '0.0.0.0',
      port: Number(ENV.VITE_APP_PORT),
      strictPort: true,
      proxy: proxyConf,
      fs: { allow: ['.'] },
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
