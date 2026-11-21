import { mergeConfig } from 'vite'
import base from './vite.config'

export default mergeConfig(base, {
  server: { proxy: { '/api': { target: 'http://localhost:8001', rewrite: (path: string) => path.replace(/^\/api/, '') } } },
})
