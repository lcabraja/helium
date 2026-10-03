import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: {'process.env.NODE_ENV': JSON.stringify('production')},
  resolve: {dedupe: ['react', 'react-dom', '@astryxdesign/core', '@stylexjs/stylex']},
  build: {
    lib: {entry: 'manager.tsx', formats: ['es'], fileName: 'manager', cssFileName: 'manager'},
    cssCodeSplit: false,
    sourcemap: false,
    target: 'chrome154',
  },
});
