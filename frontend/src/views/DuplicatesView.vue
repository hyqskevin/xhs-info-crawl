<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/api/client'

const rows = ref<any[]>([])

async function load() {
  const items = (await api.duplicates()).data.data.items
  rows.value = await Promise.all(items.map(async (row: any) => {
    const [left, right] = await Promise.all([api.activity(row.activity_a_id), api.activity(row.activity_b_id)])
    return { ...row, activity_a: left.data.data, activity_b: right.data.data }
  }))
}

async function merge(id: number, keep = 'a') {
  await api.merge(id, keep)
  ElMessage.success('合并完成')
  await load()
}

async function ignore(id: number) {
  await api.ignore(id)
  ElMessage.success('已忽略')
  await load()
}

onMounted(load)
</script>

<template>
  <ElCard shadow="never">
    <ElTable :data="rows">
      <ElTableColumn label="活动 A" min-width="220">
        <template #default="scope"><strong>{{ scope.row.activity_a?.name }}</strong><div>{{ scope.row.activity_a?.start_time }}</div><div>{{ scope.row.activity_a?.location }}</div></template>
      </ElTableColumn>
      <ElTableColumn label="活动 B" min-width="220">
        <template #default="scope"><strong>{{ scope.row.activity_b?.name }}</strong><div>{{ scope.row.activity_b?.start_time }}</div><div>{{ scope.row.activity_b?.location }}</div></template>
      </ElTableColumn>
      <ElTableColumn prop="similarity" label="相似度"><template #default="scope"><ElProgress :percentage="Math.round(scope.row.similarity * 100)" /></template></ElTableColumn>
      <ElTableColumn prop="matched_fields" label="匹配字段" />
      <ElTableColumn label="操作" width="260">
        <template #default="scope"><ElButton size="small" type="primary" @click="merge(scope.row.id, 'a')">保留 A</ElButton><ElButton size="small" @click="merge(scope.row.id, 'b')">保留 B</ElButton><ElButton size="small" type="warning" @click="ignore(scope.row.id)">不是重复</ElButton></template>
      </ElTableColumn>
    </ElTable>
    <ElEmpty v-if="!rows.length" description="暂无去重候选" />
  </ElCard>
</template>
