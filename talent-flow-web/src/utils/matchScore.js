// 匹配得分计算
// 公式：
//   1. 单项得分：满足=1，证据不足=0.5，不满足=0
//   2. 基础分 Base = 100 × Σ(权重 × 单项得分) / Σ权重（仅"必须"类要求项，权重按重要程度）
//   3. 必备项准入门槛：必须项满足率 < 门槛时，分数封顶在推荐线以下
//   4. 加分项：每满足一项 +2 分，上限 +6 分，总分封顶 100
const API_BASE = 'http://localhost:8000'

// 匹配算法设置（localStorage 持久化，修改请调用 updateAlgoSettings）
const DEFAULT_ALGO_SETTINGS = {
  weights: { 高: 45, 中: 35, 低: 20 },
  mustGate: 80, // 必备项准入门槛：满足 80% 及以上
  recommendThreshold: 75, // 推荐分数阈值
}
const SETTINGS_STORAGE_KEY = 'talent-flow-algo-settings'

function loadAlgoSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY)
    if (!raw) return { ...DEFAULT_ALGO_SETTINGS }
    const saved = JSON.parse(raw)
    return {
      ...DEFAULT_ALGO_SETTINGS,
      ...saved,
      weights: { ...DEFAULT_ALGO_SETTINGS.weights, ...(saved.weights || {}) },
    }
  } catch {
    return { ...DEFAULT_ALGO_SETTINGS }
  }
}

export const ALGO_SETTINGS = loadAlgoSettings()

// 更新算法设置并持久化到 localStorage
export function updateAlgoSettings(partial) {
  Object.assign(ALGO_SETTINGS, partial)
  if (partial.weights) Object.assign(ALGO_SETTINGS.weights, partial.weights)
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(ALGO_SETTINGS))
  } catch { /* 存储不可用时忽略 */ }
  return ALGO_SETTINGS
}

const itemScore = (suggestion) => (suggestion === '满足' ? 1 : suggestion === '证据不足' ? 0.5 : 0)

// 计算匹配得分与各建议项个数
// items: 该职位的要求项 [{ name, type: 必须/加分, importance: 高/中/低 }]
// fits:  该候选人的匹配建议 [{ name, suggestion }]
// 返回 { score, counts: { must_satisfied, must_unsatisfied, must_insufficient, bonus_satisfied } }
export function calculateScore(items, fits) {
  if (!items.length || !fits.length) return { score: 0, counts: { must_satisfied: 0, must_unsatisfied: 0, must_insufficient: 0, bonus_satisfied: 0 } }
  const fitMap = new Map(fits.map((f) => [f.name, f.suggestion]))
  const { weights, mustGate, recommendThreshold } = ALGO_SETTINGS

  let mustWeightSum = 0
  let mustEarn = 0
  let mustSatisfied = 0
  let mustUnsatisfied = 0
  let mustInsufficient = 0
  let bonusSatisfied = 0

  for (const it of items) {
    const suggestion = fitMap.get(it.name) ?? '不满足'
    const s = itemScore(suggestion)
    if (it.type === '加分') {
      if (s === 1) bonusSatisfied += 1
    } else {
      const weight = weights[it.importance] ?? 35
      mustWeightSum += weight
      mustEarn += weight * s
      if (suggestion === '满足') mustSatisfied += 1
      else if (suggestion === '证据不足') mustInsufficient += 1
      else mustUnsatisfied += 1
    }
  }
  const counts = { must_satisfied: mustSatisfied, must_unsatisfied: mustUnsatisfied, must_insufficient: mustInsufficient, bonus_satisfied: bonusSatisfied }
  if (mustWeightSum === 0) return { score: 0, counts }

  const mustTotal = mustSatisfied + mustUnsatisfied + mustInsufficient
  const base = (100 * mustEarn) / mustWeightSum
  const gatePass = mustTotal === 0 || (mustSatisfied / mustTotal) * 100 >= mustGate
  let final = gatePass ? base : Math.min(base, recommendThreshold - 1)

  final += Math.min(6, 2 * bonusSatisfied)
  return { score: Math.min(100, Math.max(0, Math.round(final))), counts }
}

// 拉取数据并计算某候选人在某职位的匹配得分与建议项个数
export async function computeCandidateScore(candidateId, jobId) {
  const [fitRes, reqRes] = await Promise.all([
    fetch(`${API_BASE}/jobfits/candidates/${candidateId}`),
    fetch(`${API_BASE}/requirements/${jobId}/items`),
  ])
  const fitJson = await fitRes.json()
  const reqJson = await reqRes.json()
  if (!fitRes.ok || fitJson.code !== 0) throw new Error(fitJson.message || '匹配建议查询失败')
  if (!reqRes.ok || reqJson.code !== 0) throw new Error(reqJson.message || '要求项查询失败')

  const fits = (fitJson.data || []).map((f) => ({
    name: reqJson.data?.find((r) => r.id === f.requirement_item_id)?.name || '未知要求项',
    suggestion: f.suggestion,
  }))
  const items = reqJson.data || []
  return calculateScore(items, fits)
}

// 计算并写入（upsert）候选人在某职位的匹配打分记录（含各项建议个数）
export async function upsertCandidateMatch(candidateId, jobId) {
  const { score, counts } = await computeCandidateScore(candidateId, jobId)
  const payload = { job_id: jobId, candidate_id: candidateId, score, ...counts }

  const listRes = await fetch(`${API_BASE}/matches/candidates/${candidateId}`)
  const listJson = await listRes.json()
  if (!listRes.ok || listJson.code !== 0) throw new Error(listJson.message || '打分查询失败')
  const hit = (listJson.data || []).find((m) => m.job_id === jobId)

  const res = await fetch(`${API_BASE}/matches${hit ? `/${hit.id}` : ''}`, {
    method: hit ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || (hit ? '打分更新失败' : '打分保存失败'))
  return json.data
}
