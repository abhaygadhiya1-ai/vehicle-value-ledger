import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// Builds one self-contained page, dist/index.html (code, styles and fonts inlined); `npm run build` copies it to
// dashboard/index.html, beside the export's data.js, which it reads, so export.py stays the contract. (The third pass
// built it as next.html beside the old page until it passed every look check, part 8.)
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  publicDir: false,
  // keep `/*! */` legal comments: the icon set's licence must appear in every copy of the page (icons.tsx)
  build: { rollupOptions: { input: 'index.html', output: { comments: { legal: true } } } },
})
