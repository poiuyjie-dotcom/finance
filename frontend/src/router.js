import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "./views/Dashboard.vue";
import TaskDetail from "./views/TaskDetail.vue";
import CreateMonitor from "./views/CreateMonitor.vue";
import Validation from "./views/Validation.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: Dashboard },
    { path: "/new", name: "create", component: CreateMonitor },
    { path: "/validation", name: "validation", component: Validation },
    {
      path: "/task/:id",
      name: "task-detail",
      component: TaskDetail,
      props: true,
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
