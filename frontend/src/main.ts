import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ElButton } from 'element-plus/es/components/button/index'
import { ElIcon } from 'element-plus/es/components/icon/index'
import { ElInput } from 'element-plus/es/components/input/index'
import { ElOption, ElSelect } from 'element-plus/es/components/select/index'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/icon/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/select/style/css'
import './styles.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)

;[
  ElButton,
  ElIcon,
  ElInput,
  ElOption,
  ElSelect
].forEach(component => {
  app.component(component.name!, component)
})

app.use(createPinia()).use(router).mount('#app')
