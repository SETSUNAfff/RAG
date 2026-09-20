const { defineConfig } = require('@vue/cli-service')

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    port: process.env.VUE_APP_PORT || 8080,
    proxy: {
      '/api': {
        target: process.env.VUE_APP_BACKEND_URL || 'http://127.0.0.1:8200',
        changeOrigin: true
      }
    }
  }
})
