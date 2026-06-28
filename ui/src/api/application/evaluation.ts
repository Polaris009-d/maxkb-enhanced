/**
 * API client for evaluation configuration and results.
 */
import { get, post, put, del } from '@/request/index'
import useStore from '@/stores'

const prefix = { _value: '/workspace/' }
Object.defineProperty(prefix, 'value', {
  get: function () {
    const { user } = useStore()
    return this._value + user.getWorkspaceId() + '/application'
  },
})

export interface EvaluationConfig {
  id?: string
  application_id?: string
  name: string
  metrics: string[]
  schedule_crontab: string | null
  is_active: boolean
  last_run_at?: string
  created_at?: string
  updated_at?: string
}

export interface EvaluationResult {
  id: string
  evaluation_config_id: string
  chat_record_id: string
  question: string
  answer: string
  contexts: string[]
  faithfulness_score: number | null
  answer_relevancy_score: number | null
  run_at: string
}

export interface EvaluationStats {
  avg_faithfulness: number
  avg_answer_relevancy: number
  total_count: number
  trend_data: Array<{
    date: string
    avg_faithfulness: number
    avg_answer_relevancy: number
    count: number
  }>
}

export const getEvaluationConfigs = (applicationId: string) =>
  get(`${prefix.value}/${applicationId}/evaluation/config`)

export const createEvaluationConfig = (applicationId: string, data: Partial<EvaluationConfig>) =>
  post(`${prefix.value}/${applicationId}/evaluation/config`, data)

export const updateEvaluationConfig = (applicationId: string, configId: string, data: Partial<EvaluationConfig>) =>
  put(`${prefix.value}/${applicationId}/evaluation/config/${configId}`, data)

export const deleteEvaluationConfig = (applicationId: string, configId: string) =>
  del(`${prefix.value}/${applicationId}/evaluation/config/${configId}`)

export const triggerEvaluation = (applicationId: string, configId: string) =>
  post(`${prefix.value}/${applicationId}/evaluation/config/${configId}/trigger`, {})

export const getEvaluationResults = (applicationId: string, configId?: string, page = 1, pageSize = 20) => {
  let url = `${prefix.value}/${applicationId}/evaluation/result?page=${page}&page_size=${pageSize}`
  if (configId) url += `&config_id=${configId}`
  return get(url)
}

export const getEvaluationStats = (applicationId: string, days = 30) =>
  get(`${prefix.value}/${applicationId}/evaluation/stats?days=${days}`)
