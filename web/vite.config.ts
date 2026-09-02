import path from 'node:path'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Connect, type Plugin } from 'vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** SPA fallback would otherwise swallow /espectrogramas/ — serve the PNG gallery. */
function espectrogramasGallery(): Plugin {
  const rewrite = (req: Connect.IncomingMessage) => {
    const raw = req.url ?? ''
    const pathname = raw.split('?')[0]
    if (pathname === '/espectrogramas' || pathname === '/espectrogramas/') {
      const query = raw.includes('?') ? raw.slice(raw.indexOf('?')) : ''
      req.url = `/espectrogramas/index.html${query}`
    }
  }
  const attach = (server: { middlewares: Connect.Server }) => {
    server.middlewares.use((req, _res, next) => {
      rewrite(req)
      next()
    })
  }
  return {
    name: 'espectrogramas-gallery',
    configureServer: attach,
    configurePreviewServer: attach,
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), espectrogramasGallery()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
