<template>
  <el-dialog
    :model-value="visible"
    :title="config ? 'Edit Evaluation Config' : 'Create Evaluation Config'"
    width="520px"
    @update:model-value="$emit('update:visible', $event)"
    @close="resetForm"
  >
    <el-form :model="form" label-width="120px">
      <el-form-item label="Name" required>
        <el-input v-model="form.name" placeholder="e.g. Weekly Quality Check" />
      </el-form-item>
      <el-form-item label="Metrics">
        <el-checkbox-group v-model="form.metrics">
          <el-checkbox value="faithfulness">Faithfulness</el-checkbox>
          <el-checkbox value="answer_relevancy">AnswerRelevancy</el-checkbox>
        </el-checkbox-group>
      </el-form-item>
      <el-form-item label="Schedule (cron)">
        <el-input v-model="form.schedule_crontab" placeholder="e.g. 0 * * * * (hourly) or empty for manual" />
      </el-form-item>
      <el-form-item label="Active">
        <el-switch v-model="form.is_active" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('update:visible', false)">Cancel</el-button>
      <el-button type="primary" @click="submitForm" :disabled="!form.name || form.metrics.length === 0">
        {{ config ? 'Update' : 'Create' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, watch } from 'vue'
import type { EvaluationConfig } from '@/api/application/evaluation'
import { createEvaluationConfig, updateEvaluationConfig } from '@/api/application/evaluation'

const props = defineProps<{
  visible: boolean
  config: EvaluationConfig | null
  applicationId?: string
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  saved: []
}>()

const form = ref({ name: '', metrics: ['faithfulness', 'answer_relevancy'], schedule_crontab: '', is_active: true })

watch(
  () => props.visible,
  (val) => {
    if (val && props.config) {
      form.value = {
        name: props.config.name,
        metrics: [...props.config.metrics],
        schedule_crontab: props.config.schedule_crontab || '',
        is_active: props.config.is_active,
      }
    } else if (val) {
      resetForm()
    }
  }
)

function resetForm() {
  form.value = { name: '', metrics: ['faithfulness', 'answer_relevancy'], schedule_crontab: '', is_active: true }
}

async function submitForm() {
  if (props.config?.id) {
    await updateEvaluationConfig(props.applicationId!, props.config.id, form.value)
  } else {
    await createEvaluationConfig(props.applicationId!, form.value)
  }
  emit('saved')
}
</script>
