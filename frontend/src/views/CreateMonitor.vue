<script setup>
import { useRouter } from "vue-router";
import { ArrowLeft } from "lucide-vue-next";
import RuleEditor from "../components/RuleEditor.vue";
const router = useRouter();
</script>
<template>
  <main class="page create-page">
    <router-link to="/" class="back-link"
      ><ArrowLeft :size="15" />监控总览</router-link
    >
    <div class="page-heading">
      <div>
        <div class="eyebrow">NEW MONITOR</div>
        <h1>新建监控</h1>
        <p class="page-subtitle">设定你关注的变化，让监控持续运行。</p>
      </div>
    </div>
    <RuleEditor @created="(id) => router.push(`/task/${id}`)" />
  </main>
</template>
