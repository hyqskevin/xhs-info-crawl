import { createApp } from 'vue'
import ElementPlus from 'element-plus'
// Element Plus 默认 CSS 必须在我们的 tokens 之前导入,
// 否则 tokens.css 里的 --el-* 变量无法覆盖。
import 'element-plus/dist/index.css'
import './design/tokens.css'
import App from './App.vue'
import { initBaseUrlFromLocation } from './api/client'

// 必须先调:解析 URL 里 ?statusPort=9000,所有 API 请求指向 launcher status_server
// 否则默认 baseUrl=http://127.0.0.1:8001(业务后端) 会拿到 404 / 没 /system-config 端点
initBaseUrlFromLocation()

createApp(App).use(ElementPlus).mount('#app')
