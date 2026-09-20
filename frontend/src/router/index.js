import Vue from 'vue'
import VueRouter from 'vue-router'
import ChatView from '@/views/ChatView.vue'
import DocumentsView from '@/views/DocumentsView.vue'
import EvaluationView from '@/views/EvaluationView.vue'

Vue.use(VueRouter)

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', name: 'chat', component: ChatView },
  { path: '/documents', name: 'documents', component: DocumentsView },
  { path: '/evaluation', name: 'evaluation', component: EvaluationView }
]

export default new VueRouter({
  mode: 'hash',
  routes
})
