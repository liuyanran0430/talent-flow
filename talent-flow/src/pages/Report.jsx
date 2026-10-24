import { useEffect, useMemo, useState } from 'react'
import Icon from '../components/Icon'
import Modal, { ModalHeader } from '../components/Modal'
import { useApp } from '../context/AppContext'
import { upsertCandidateMatch, updateAlgoSettings, ALGO_SETTINGS } from '../utils/matchScore'

const API_BASE = 'http://localhost:8000'

const PAGE_SIZE = 10 // 候选人匹配概览每页条数

const AVATAR_BGS = [
  'from-cyan-500 to-blue-600',
  'from-violet-500 to-fuchsia-600',
  'from-rose-500 to-orange-500',
  'from-emerald-500 to-teal-600',
  'from-amber-500 to-yellow-600',
]

// 依据岗位匹配结果生成关键结论（真实数据：jobfits 的建议 + 匹配依据）
const ICON_HIT = { icon: 'solar:check-circle-bold', cls: 'text-emerald-500', label: '关键命中：' }
const ICON_BONUS = { icon: 'solar:star-bold', cls: 'text-cyan-500', label: '加分亮点：' }
const ICON_VERIFY = { icon: 'solar:info-circle-outline', cls: 'text-amber-500', label: '建议核实：' }
const ICON_GAP = { icon: 'solar:danger-triangle-outline', cls: 'text-rose-500', label: '待补强：' }

function buildConclusions(chips) {
  const withEv = (c) => (c.evidence ? `「${c.label}」${c.suggestion}，依据：${c.evidence}` : `「${c.label}」${c.suggestion}`)
  const list = []
  // 1. 满足的基本项（带匹配依据），最多展示 3 条
  chips.filter((c) => c.type !== '加分' && c.suggestion === '满足').slice(0, 3).forEach((c) => {
    list.push({ ...ICON_HIT, text: withEv(c) })
  })
  // 2. 满足的加分项
  chips.filter((c) => c.type === '加分' && c.suggestion === '满足').forEach((c) => {
    list.push({ ...ICON_BONUS, text: withEv(c) })
  })
  // 3. 证据不足的基本项（汇总一条）
  const insufficient = chips.filter((c) => c.type !== '加分' && c.suggestion === '证据不足')
  if (insufficient.length) {
    list.push({ ...ICON_VERIFY, text: `${insufficient.map((c) => `「${c.label}」`).join('')}证据不足，建议面试进一步核实` })
  }
  // 4. 不满足的基本项（汇总一条）
  const unsat = chips.filter((c) => c.type !== '加分' && c.suggestion === '不满足')
  if (unsat.length) {
    list.push({ ...ICON_GAP, text: `${unsat.map((c) => `「${c.label}」`).join('')}未满足岗位要求` })
  }
  return list
}

// 拉取全部部门
async function fetchDepartments() {
  const res = await fetch(`${API_BASE}/departments`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '部门查询失败')
  return json.data || []
}

// 拉取招聘中的职位
async function fetchJobs() {
  const res = await fetch(`${API_BASE}/jobs`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '职位查询失败')
  return (json.data || []).filter((j) => j.status === 'open')
}

// 拉取 review / finish 状态候选人（已解析未确认 + 已确认）
async function fetchCandidates() {
  const res = await fetch(`${API_BASE}/candidates?status=all&page_size=100`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '候选人查询失败')
  return (json.data?.items || []).filter((c) => c.status === 'review' || c.status === 'finish')
}

// 拉取某候选人的岗位匹配打分（matches）
async function fetchMatches(candidateId) {
  const res = await fetch(`${API_BASE}/matches/candidates/${candidateId}`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '打分查询失败')
  return json.data || []
}

// 拉取某候选人的职位匹配建议（含要求项名称、类型与建议，用于技能标签与维度分析）
async function fetchFitChips(candidateId, jobId) {
  const [fitRes, reqRes] = await Promise.all([
    fetch(`${API_BASE}/jobfits/candidates/${candidateId}`),
    jobId ? fetch(`${API_BASE}/requirements/${jobId}/items`) : Promise.resolve(null),
  ])
  const fitJson = await fitRes.json()
  const reqJson = reqRes ? await reqRes.json() : null
  const reqMap = new Map((reqJson?.data || []).map((r) => [r.id, r]))
  return (fitJson.data || []).map((f) => {
    const req = reqMap.get(f.requirement_item_id)
    return {
      label: req?.name || '未知要求项',
      type: req?.type || '必须',
      suggestion: f.suggestion,
      evidence: f.evidence || '',
    }
  })
}

export default function Report() {
  const { showToast } = useApp()
  const [departments, setDepartments] = useState([])
  const [jobs, setJobs] = useState([])
  const [candidates, setCandidates] = useState([])
  const [scores, setScores] = useState({}) // candidate_id → score
  const [fitChips, setFitChips] = useState({}) // candidate_id → [{ label, type, suggestion }]
  const [loading, setLoading] = useState(true)
  const [deptId, setDeptId] = useState('all')
  const [jobId, setJobId] = useState('all')
  const [filter, setFilter] = useState('all')
  const [selectedCandidateId, setSelectedCandidateId] = useState(null) // 维度分析选中的候选人，默认列表第一个
  const [page, setPage] = useState(1) // 概览列表当前页码
  const [algoOpen, setAlgoOpen] = useState(false)
  const [threshold, setThreshold] = useState(() => ALGO_SETTINGS.recommendThreshold)
  const [weights, setWeights] = useState(() => ({ ...ALGO_SETTINGS.weights }))
  const [gate, setGate] = useState(() => ALGO_SETTINGS.mustGate)
  const [savingAlgo, setSavingAlgo] = useState(false)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [deptList, jobList, list] = await Promise.all([fetchDepartments(), fetchJobs(), fetchCandidates()])
        setDepartments(deptList)
        setJobs(jobList)
        setCandidates(list)
        const scoreMap = {}
        const chipMap = {}
        await Promise.all(
          list.map(async (c) => {
            try {
              const matches = await fetchMatches(c.id)
              const hit = matches.find((m) => m.job_id === c.job_id)
              if (hit) scoreMap[c.id] = hit.score
            } catch { /* 单个失败忽略 */ }
            try {
              chipMap[c.id] = await fetchFitChips(c.id, c.job_id)
            } catch { chipMap[c.id] = [] }
          })
        )
        setScores(scoreMap)
        setFitChips(chipMap)
      } catch (e) {
        showToast(`加载失败：${e.message}`, 'error')
      } finally {
        setLoading(false)
      }
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 职位选项：按部门联动
  const jobOptions = useMemo(
    () => (deptId === 'all' ? jobs : jobs.filter((j) => String(j.department_id) === String(deptId))),
    [jobs, deptId]
  )

  // 统计卡片（真实数据）
  const stats = useMemo(() => {
    const total = candidates.length
    const recommended = candidates.filter((c) => c.status === 'finish' && (scores[c.id] ?? 0) >= threshold).length
    const scored = candidates.filter((c) => scores[c.id] != null)
    const avg = scored.length ? (scored.reduce((s, c) => s + scores[c.id], 0) / scored.length).toFixed(1) : '—'
    const pending = candidates.filter((c) => c.status === 'review').length
    return [
      { label: '已分析候选人', value: total, note: '含待确认与已确认', icon: 'solar:users-group-rounded-outline', iconClass: 'text-cyan-600' },
      { label: '推荐', value: recommended, note: `匹配分 ≥ ${threshold} 分`, icon: 'solar:stars-outline', iconClass: 'text-amber-500' },
      { label: '平均匹配分', value: avg, unit: avg === '—' ? '' : '分', note: `基于 ${scored.length} 位已打分候选人`, icon: 'solar:chart-2-outline', iconClass: 'text-violet-600' },
      { label: '待确认', value: pending, note: '已解析待人工确认', icon: 'solar:hourglass-line-outline', iconClass: 'text-amber-500' },
    ]
  }, [candidates, scores, threshold])

  // 筛选标签（真实计数）
  const filterTabs = useMemo(() => {
    const recommended = candidates.filter((c) => c.status === 'finish' && (scores[c.id] ?? 0) >= threshold).length
    const pending = candidates.filter((c) => c.status === 'review').length
    return [
      { key: 'all', label: `全部 ${candidates.length}` },
      { key: 'recommended', label: `推荐 ${recommended}` },
      { key: 'pending', label: `待确认 ${pending}` },
    ]
  }, [candidates, scores, threshold])

  const filtered = useMemo(() => {
    let list = candidates
    if (jobId !== 'all') list = list.filter((c) => c.job_id === Number(jobId))
    if (filter === 'recommended') list = list.filter((c) => c.status === 'finish' && (scores[c.id] ?? 0) >= threshold)
    if (filter === 'pending') list = list.filter((c) => c.status === 'review')
    return list
  }, [candidates, jobId, filter, scores, threshold])

  // 分页
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const paginated = useMemo(
    () => filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [filtered, safePage]
  )

  // 筛选条件变化时回到第一页
  useEffect(() => {
    setPage(1)
  }, [jobId, filter])

  // 维度分析候选人：选中项，默认当前页列表第一个
  const dimensionCandidate = useMemo(
    () => paginated.find((c) => c.id === selectedCandidateId) || paginated[0] || null,
    [paginated, selectedCandidateId]
  )

  // 维度分析：按候选人统计，基本项以基本项总数为分母，加分项以加分项总数为分母
  const dimensionStats = useMemo(() => {
    const chips = dimensionCandidate ? fitChips[dimensionCandidate.id] || [] : []
    const mustItems = chips.filter((it) => it.type !== '加分')
    const bonusItems = chips.filter((it) => it.type === '加分')
    const countBy = (list, suggestion) => list.filter((it) => it.suggestion === suggestion).length
    const mustTotal = mustItems.length
    const bonusTotal = bonusItems.length
    const pct = (n, total) => (total ? Math.round((n / total) * 100) : 0)
    return [
      { label: '基本项满足', value: countBy(mustItems, '满足'), total: mustTotal, bar: 'bg-emerald-500', color: 'text-emerald-600' },
      { label: '基本项证据不足', value: countBy(mustItems, '证据不足'), total: mustTotal, bar: 'bg-amber-500', color: 'text-amber-600' },
      { label: '基本项不满足', value: countBy(mustItems, '不满足'), total: mustTotal, bar: 'bg-rose-500', color: 'text-rose-600' },
      { label: '加分项满足', value: countBy(bonusItems, '满足'), total: bonusTotal, bar: 'bg-violet-500', color: 'text-violet-600' },
    ].map((it) => ({ ...it, pct: pct(it.value, it.total) }))
  }, [dimensionCandidate, fitChips])

  // 保存算法设置：权重修改则重算所有候选人得分；门槛/阈值修改影响推荐标记
  const saveAlgoSettings = async () => {
    const weightHigh = Number(weights.高)
    const weightMid = Number(weights.中)
    const weightLow = Number(weights.低)
    if (![weightHigh, weightMid, weightLow].every((n) => Number.isFinite(n) && n >= 0 && n <= 100) || weightHigh + weightMid + weightLow === 0) {
      showToast('权重必须为 0-100 的数字，且不能全部为 0')
      return
    }
    setSavingAlgo(true)
    try {
      // 持久化设置（localStorage），计算函数读取的 ALGO_SETTINGS 立即生效
      updateAlgoSettings({
        weights: { 高: weightHigh, 中: weightMid, 低: weightLow },
        mustGate: gate,
        recommendThreshold: threshold,
      })
      setAlgoOpen(false)
      // 重新计算所有已关联职位的候选人的匹配分并落库
      const targets = candidates.filter((c) => c.job_id)
      if (targets.length) showToast(`正在按新算法重算 ${targets.length} 位候选人的匹配分…`)
      const updated = {}
      await Promise.all(
        targets.map(async (c) => {
          try {
            const saved = await upsertCandidateMatch(c.id, c.job_id)
            updated[c.id] = saved.score
          } catch { /* 单个重算失败忽略 */ }
        })
      )
      setScores((s) => ({ ...s, ...updated }))
      showToast(`匹配算法设置已保存${targets.length ? `，已重算 ${Object.keys(updated).length} 位候选人的匹配分` : ''}`)
    } finally {
      setSavingAlgo(false)
    }
  }

  return (
    <section className="p-8 max-w-[1440px] mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-7">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">职位匹配看板</h1>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>分析已完成
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-500">基于选定职位要求，对候选人简历进行多维匹配分析。</p>
        </div>
        <div className="flex gap-3">
          <select
            value={deptId}
            onChange={(e) => { setDeptId(e.target.value); setJobId('all') }}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-700"
          >
            <option value="all">全部部门</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
          <select
            value={jobId}
            onChange={(e) => {
              const id = e.target.value
              setJobId(id)
              if (id !== 'all') {
                const hit = jobs.find((j) => String(j.id) === id)
                showToast(`已切换至「${hit?.dept_label ? `${hit.dept_label}-` : ''}${hit?.name || ''}」的匹配分析`)
              }
            }}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-700 min-w-[200px]"
          >
            <option value="all">全部职位</option>
            {jobOptions.map((j) => (
              <option key={j.id} value={j.id}>{j.name}</option>
            ))}
          </select>
          <button
            onClick={() => setAlgoOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium hover:bg-slate-50"
          >
            <Icon icon="solar:settings-outline" width={18} />匹配算法设置
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-5 mb-6">
        {stats.map((s) => (
          <div key={s.label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between text-sm text-slate-500">
              <span>{s.label}</span>
              <Icon icon={s.icon} width={20} className={s.iconClass} />
            </div>
            <div className="mt-3 text-3xl font-bold text-slate-900">
              {s.value}
              {s.unit && <span className="ml-1 text-base font-medium text-slate-400">{s.unit}</span>}
            </div>
            <p className="mt-2 text-xs text-slate-500">{s.note}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-8 rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
            <div>
              <h2 className="font-bold text-slate-900">候选人匹配概览</h2>
              <p className="mt-1 text-xs text-slate-500">点击候选人可查看详细匹配报告。</p>
            </div>
            <div className="flex gap-2">
              {filterTabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setFilter(t.key)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                    filter === t.key ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div className="divide-y divide-slate-100">
            {loading && (
              <div className="px-6 py-12 text-center text-sm text-slate-400">加载中…</div>
            )}
            {!loading && paginated.map((c, i) => {
              const score = scores[c.id]
              const pending = c.status === 'review'
              const recommended = !pending && score != null && score >= threshold
              const chips = (fitChips[c.id] || []).slice(0, 3)
              return (
                <button
                  key={c.id}
                  onClick={() => setSelectedCandidateId(c.id)}
                  className={`w-full flex items-center gap-4 px-6 py-4 text-left border-l-2 ${
                    dimensionCandidate?.id === c.id ? 'bg-slate-50 border-cyan-500' : 'border-transparent hover:bg-slate-50'
                  }`}
                >
                  <div className={`flex h-10 w-10 flex-none items-center justify-center rounded-full bg-gradient-to-br ${AVATAR_BGS[i % AVATAR_BGS.length]} text-sm font-bold text-white`}>
                    {(c.name || '?')[0]}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold flex items-center gap-2">
                      {c.name || '未命名'}
                      {pending ? (
                        <span className="rounded bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">待确认</span>
                      ) : (
                        <>
                          <span className="rounded bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">已确认</span>
                          {recommended && (
                            <span className="inline-flex items-center gap-1 rounded bg-cyan-50 px-2 py-0.5 text-xs font-medium text-cyan-700">
                              <Icon icon="solar:stars-outline" width={12} />推荐
                            </span>
                          )}
                        </>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {c.experience ? `${c.experience} · ` : ''}导入于 {new Date(c.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="hidden lg:flex gap-1">
                    {chips.map((s, j) => (
                      <span
                        key={j}
                        className={`rounded px-2 py-1 text-xs ${
                          s.suggestion === '满足' ? 'bg-emerald-50 text-emerald-700' : s.suggestion === '不满足' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700'
                        }`}
                      >{s.label}</span>
                    ))}
                  </div>
                  <div className="ml-3 text-right">
                    <div className={`text-xl font-bold ${pending ? 'text-slate-300' : score == null ? 'text-slate-300' : score >= threshold ? 'text-emerald-600' : score >= 50 ? 'text-amber-600' : 'text-rose-600'}`}>
                      {score != null ? score : '—'}<span className="text-xs font-medium">分</span>
                    </div>
                    <div className="mt-1 h-1.5 w-20 rounded-full bg-slate-100">
                      <div
                        className={`h-full rounded-full ${score == null ? 'bg-slate-200' : score >= threshold ? 'bg-emerald-500' : score >= 50 ? 'bg-amber-500' : 'bg-rose-500'}`}
                        style={{ width: `${score ?? 0}%` }}
                      ></div>
                    </div>
                  </div>
                  <Icon icon="solar:alt-arrow-right-outline" width={18} className="ml-2 text-slate-400" />
                </button>
              )
            })}
            {!loading && filtered.length === 0 && (
              <div className="px-6 py-12 text-center">
                <Icon icon="solar:magnifer-outline" width={34} className="mx-auto text-slate-300" />
                <p className="mt-3 font-medium text-slate-600">暂无匹配的候选人</p>
                <p className="mt-1 text-sm text-slate-400">在导入简历页完成解析并确认后，候选人将在此显示。</p>
              </div>
            )}
            {!loading && filtered.length > 0 && (
              <div className="flex items-center justify-between border-t border-slate-200 px-6 py-3.5">
                <span className="text-xs text-slate-500">
                  共 {filtered.length} 条 · 第 {safePage} / {totalPages} 页
                </span>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={safePage <= 1}
                    className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Icon icon="solar:alt-arrow-left-outline" width={16} />上一页
                  </button>
                  {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`h-8 w-8 rounded-lg text-sm font-medium ${
                        p === safePage ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      {p}
                    </button>
                  ))}
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={safePage >= totalPages}
                    className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    下一页<Icon icon="solar:alt-arrow-right-outline" width={16} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="col-span-4 space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <div>
              <h2 className="font-bold text-slate-900">{dimensionCandidate ? `${dimensionCandidate.name || '未命名'} · 维度分析` : '维度分析'}</h2>
              <p className="mt-1 text-xs text-slate-500">点击左侧列表中的候选人可切换分析对象。</p>
            </div>
            <div className="mt-5 space-y-4">
              {dimensionStats.map((d) => (
                <div key={d.label}>
                  <div className="mb-1.5 flex justify-between text-xs">
                    <span>{d.label}</span>
                    <span className={`font-semibold ${d.color}`}>{d.value} 项 / {d.total} 项（{d.pct}%）</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100">
                    <div className={`h-full rounded-full ${d.bar}`} style={{ width: `${d.pct}%` }}></div>
                  </div>
                </div>
              ))}
              {dimensionStats.every((d) => d.value === 0) && (
                <p className="pt-2 text-center text-xs text-slate-400">该候选人暂无打分数据，确认后自动统计。</p>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="font-bold text-slate-900">{dimensionCandidate ? `${dimensionCandidate.name || '未命名'} · 关键结论` : '关键结论'}</h2>
            <div className="mt-4 space-y-3 text-sm max-h-[240px] overflow-y-auto">
              {dimensionCandidate ? (
                buildConclusions(fitChips[dimensionCandidate.id] || []).map((c, i) => (
                  <div key={i} className="flex gap-3">
                    <Icon icon={c.icon} width={18} className={`mt-0.5 flex-none ${c.cls}`} />
                    <p><span className="font-medium">{c.label}</span>{c.text}</p>
                  </div>
                ))
              ) : (
                <p className="pt-2 text-center text-xs text-slate-400">暂无匹配结论，解析并确认候选人后自动生成。</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 匹配算法设置弹窗 */}
      <Modal open={algoOpen} onClose={() => setAlgoOpen(false)} maxWidth="max-w-3xl">
        <ModalHeader title="匹配算法设置" subtitle="配置 AI 对候选人简历的解析维度与推荐阈值。" onClose={() => setAlgoOpen(false)} />
        <div className="bg-white rounded-xl shadow-sm divide-y divide-slate-200 max-h-[70vh] overflow-y-auto">
          <div className="p-6">
            <div className="flex justify-between items-start">
              <div>
                <h2 className="font-bold">要求项权重策略</h2>
                <p className="text-sm text-slate-500 mt-1">必备项优先保障准入，加分项用于同类候选人的排序。</p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700">已启用</span>
            </div>
            <div className="grid grid-cols-3 gap-4 mt-5">
              {[
                { key: '高', label: '高重要程度' },
                { key: '中', label: '中重要程度' },
                { key: '低', label: '低重要程度' },
              ].map((w) => (
                <label key={w.key} className="rounded-lg border border-slate-200 p-4">
                  <span className="text-xs text-slate-500">{w.label}</span>
                  <div className="mt-2 flex items-end gap-1">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={weights[w.key]}
                      onChange={(e) => setWeights((f) => ({ ...f, [w.key]: e.target.value }))}
                      className="w-16 text-xl font-bold outline-none"
                    />
                    <span className="text-sm text-slate-500 mb-1">%</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className="p-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="font-bold">必备项准入门槛</h2>
                <p className="text-sm text-slate-500 mt-1">未满足必备要求时，候选人分数将封顶在推荐线以下。</p>
              </div>
              <select
                value={String(gate)}
                onChange={(e) => setGate(Number(e.target.value))}
                className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="100">满足 100%</option>
                <option value="80">满足 80% 及以上</option>
                <option value="60">满足 60% 及以上</option>
              </select>
            </div>
          </div>

          <div className="p-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="font-bold">推荐分数阈值</h2>
                <p className="text-sm text-slate-500 mt-1">达到阈值的候选人将进入推荐队列。</p>
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="60"
                  max="95"
                  value={threshold}
                  onChange={(e) => setThreshold(Number(e.target.value))}
                  className="accent-cyan-600"
                />
                <span className="w-12 text-sm font-bold text-cyan-700">{threshold} 分</span>
              </div>
            </div>
          </div>

          <div className="p-5 text-right">
            <button
              onClick={saveAlgoSettings}
              disabled={savingAlgo}
              className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-60"
            >
              {savingAlgo ? '保存并重算中…' : '保存算法设置'}
            </button>
          </div>
        </div>
      </Modal>
    </section>
  )
}
