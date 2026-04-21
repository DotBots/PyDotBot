/// <reference types="vitest" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import eslint from 'vite-plugin-eslint';
import { nodePolyfills } from 'vite-plugin-node-polyfills';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    base: '/PyDotBot/',
    plugins: [
      react(),
      nodePolyfills(),
      eslint(),
    ],
    // Inject process.* shims needed by pino and the qrkey library
    define: {
      ...(mode !== 'test' ? { 'process.version': JSON.stringify('v18.0.0') } : {}),
      'process.env.REACT_APP_MQTT_BROKER_HOST': JSON.stringify(env.VITE_MQTT_BROKER_HOST ?? ''),
      'process.env.REACT_APP_MQTT_BROKER_PORT': JSON.stringify(env.VITE_MQTT_BROKER_PORT ?? ''),
      'process.env.REACT_APP_MQTT_VERSION': JSON.stringify(env.VITE_MQTT_VERSION ?? ''),
      'process.env.REACT_APP_MQTT_USE_SSL': JSON.stringify(env.VITE_MQTT_USE_SSL ?? ''),
      'process.env.REACT_APP_MQTT_BROKER_USERNAME': JSON.stringify(env.VITE_MQTT_BROKER_USERNAME ?? ''),
      'process.env.REACT_APP_MQTT_BROKER_PASSWORD': JSON.stringify(env.VITE_MQTT_BROKER_PASSWORD ?? ''),
      'process.env.REACT_APP_MQTT_PATH': JSON.stringify(env.VITE_MQTT_PATH ?? ''),
    },
    server: {
      watch: {
        ignored: ['**/coverage/**'],
      },
    },
    build: {
      outDir: 'build',
      chunkSizeWarningLimit: 800,
      rollupOptions: {
        onwarn(warning, warn) {
          if (warning.code === 'EVAL' && warning.id?.includes('vm-browserify')) return;
          warn(warning);
        },
        output: {
          manualChunks: {
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
            'maps-vendor': ['leaflet', 'react-leaflet'],
            'mqtt-vendor': ['mqtt'],
            'crypto-vendor': ['jose', 'futoin-hkdf'],
          },
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/setupTests.ts'],
      server: {
        deps: {
          inline: ['react-leaflet'],
        },
      },
      coverage: {
        provider: 'v8',
        reporter: ['text', 'lcov'],
        reportsDirectory: './coverage',
        exclude: [
          'build/**',
          'vite.config.ts',
          'eslint.config.mjs',
          'src/vite-env.d.ts',
          'src/types.ts',
          'src/declarations.d.ts'
        ],
      },
    },
  };
});
