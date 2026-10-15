import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import TaskDetail from './views/TaskDetail.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: Dashboard },
    { path: '/task/:id', name: 'task-detail', component: TaskDetail, props: true },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
