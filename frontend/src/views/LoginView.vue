<script setup lang="ts">
import {Lock,User} from '@element-plus/icons-vue';import {ref} from 'vue';import {useRouter} from 'vue-router';import {ElMessage} from 'element-plus';import {api} from '@/api/client'
const username=ref('admin'),password=ref(''),loading=ref(false),router=useRouter()
async function submit(){loading.value=true;try{const r=await api.login(username.value,password.value);localStorage.setItem('token',r.data.data.access_token);await router.push('/dashboard')}catch{ElMessage.error('用户名或密码错误')}finally{loading.value=false}}
</script>
<template><div class="login-page"><ElCard class="login-card" shadow="always"><h1>活动采集系统</h1><p>登录管理后台</p><ElForm @submit.prevent="submit"><ElFormItem><ElInput v-model="username" placeholder="用户名" :prefix-icon="User" /></ElFormItem><ElFormItem><ElInput v-model="password" type="password" show-password placeholder="密码" :prefix-icon="Lock" @keyup.enter="submit" /></ElFormItem><ElButton type="primary" native-type="submit" :loading="loading" class="full">登录</ElButton></ElForm></ElCard></div></template>
