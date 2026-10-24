import { useEffect, useMemo, useState } from 'react'
import Icon from '../components/Icon'
import Modal, { ModalHeader } from '../components/Modal'
import { useApp } from '../context/AppContext'
import { upsertCandidateMatch, ALGO_SETTINGS } from '../utils/matchScore'

const API_BASE = 'http://localhost:8000'

const PAGE_SIZE = 10 // 候选人列表每页条数

// 拉取全部职位（id → name 映射，用于意向职位展示与筛选）
async function fetchJobs() {
  const res = await fetch(`${API_BASE}/jobs`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '职位查询失败')
  return json.data || []
}

// 拉取 review / finish 状态候选人（已解析未确认 + 已确认）
async function fetchCandidates() {
  const res = await fetch(`${API_BASE}/candidates?status=all&page_size=500`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '候选人查询失败')
  return (json.data?.items || []).filter((c) => c.status === 'review' || c.status === 'finish')
}

// 拉取某候选人的职位匹配建议（jobfits），按所属职位要求项补齐名称
async function fetchJobfits(candidate, jobIdMap) {
  const [fitRes, reqRes] = await Promise.all([
    fetch(`${API_BASE}/jobfits/candidates/${candidate.id}`),
    candidate.job_id
      ? fetch(`${API_BASE}/requirements/${candidate.job_id}/items`)
      : Promise.resolve(null),
  ])
  const fitJson = await fitRes.json()
  const reqJson = reqRes ? await reqRes.json() : null
  const reqMap = new Map((reqJson?.data || []).map((r) => [r.id, r.name]))
  return (fitJson.data || []).map((f) => ({ ...f, name: reqMap.get(f.requirement_item_id) || '未知要求项' }))
}

// 拉取某候选人的岗位匹配打分（matches）
async function fetchMatches(candidateId) {
  const res = await fetch(`${API_BASE}/matches/candidates/${candidateId}`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '打分查询失败')
  return json.data || []
}

export default function Candidates() {
  const { navigate, showToast, setImportQueue } = useApp()
  const [candidates, setCandidates] = useState([])
  const [jobs, setJobs] = useState([])
  const [scores, setScores] = useState({}) // candidate_id → score
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [dept, setDept] = useState('all')
  const [job, setJob] = useState('all')
  const [detail, setDetail] = useState(null) // { candidate, fits }
  const [detailLoading, setDetailLoading] = useState(false)
  const [editForm, setEditForm] = useState(null)
  const [page, setPage] = useState(1) // 当前页码

  const load = async () => {
    setLoading(true)
    try {
      const [jobList, list] = await Promise.all([fetchJobs(), fetchCandidates()])
      setJobs(jobList)
      setCandidates(list)
      // 拉取每个候选人的匹配打分，取其关联职位的打分（无则空）
      const scoreMap = {}
      await Promise.all(
        list.map(async (c) => {
          try {
            const matches = await fetchMatches(c.id)
            const hit = matches.find((m) => m.job_id === c.job_id)
            if (hit) scoreMap[c.id] = hit.score
          } catch { /* 单个失败忽略 */ }
        })
      )
      setScores(scoreMap)
    } catch (e) {
      showToast(`加载失败：${e.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const jobIdMap = useMemo(
    () => new Map(jobs.map((j) => [j.id, j.dept_label ? `${j.dept_label}-${j.name}` : j.name])),
    [jobs]
  )

  // 职位 → 部门名映射，用于按部门筛选
  const jobDeptMap = useMemo(() => new Map(jobs.map((j) => [j.id, j.dept_label || ''])), [jobs])
  // 部门选项：从职位列表去重
  const deptOptions = useMemo(
    () => [...new Set(jobs.map((j) => j.dept_label).filter(Boolean))],
    [jobs]
  )
  // 职位选项：部门筛选后联动，仅显示职位名
  const jobOptions = useMemo(
    () => (dept === 'all' ? jobs : jobs.filter((j) => j.dept_label === dept)),
    [jobs, dept]
  )

  // 切换部门时，若当前选中职位不属于该部门则重置
  const onDeptChange = (v) => {
    setDept(v)
    if (job !== 'all') {
      const sel = jobs.find((j) => String(j.id) === job)
      if (!sel || (v !== 'all' && sel.dept_label !== v)) setJob('all')
    }
  }

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return candidates.filter((c) => {
      const jobName = jobIdMap.get(c.job_id) || ''
      const haystack = `${c.name || ''} ${c.phone || ''} ${c.email || ''} ${jobName}`.toLowerCase()
      return (
        (!kw || haystack.includes(kw)) &&
        (dept === 'all' || jobDeptMap.get(c.job_id) === dept) &&
        (job === 'all' || String(c.job_id) === job)
      )
    })
  }, [candidates, jobIdMap, jobDeptMap, search, dept, job])

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
  }, [search, dept, job])

  // 统计卡：基于真实数据计算
  const stats = useMemo(() => {
    const total = candidates.length
    const confirmed = candidates.filter((c) => c.status === 'finish').length
    const weekAgo = Date.now() - 7 * 24 * 3600 * 1000
    const weekNew = candidates.filter((c) => new Date(c.created_at).getTime() >= weekAgo).length
    return [
      { label: '候选人总数', value: total, note: `本周新增 ${weekNew} 人`, noteClass: 'text-emerald-600', icon: 'solar:users-group-rounded-outline', iconClass: 'text-cyan-600' },
      { label: '已确认', value: confirmed, note: '导入流程中已完成确认', noteClass: 'text-emerald-600', icon: 'solar:check-circle-outline', iconClass: 'text-emerald-500' },
      { label: '待确认', value: total - confirmed, note: '已解析待人工确认', icon: 'solar:hourglass-line-outline', iconClass: 'text-amber-500' },
      { label: '本周新增', value: weekNew, note: '近 7 天导入的候选人', icon: 'solar:calendar-mark-outline', iconClass: 'text-violet-600' },
    ]
  }, [candidates])

  const resetFilters = () => {
    setSearch('')
    setDept('all')
    setJob('all')
  }

  // 打开详情弹窗（可查看可编辑），并加载匹配建议
  const openDetail = async (c) => {
    setDetail({ candidate: c, fits: [] })
    setEditForm({
      name: c.name || '',
      job_id: c.job_id ?? '',
      phone: c.phone || '',
      email: c.email || '',
      experience: c.experience || '',
    })
    setDetailLoading(true)
    try {
      const fits = await fetchJobfits(c, jobIdMap)
      setDetail({ candidate: c, fits })
    } catch {
      setDetail({ candidate: c, fits: [] })
    } finally {
      setDetailLoading(false)
    }
  }

  // 修改某条匹配建议，标记为已修改（依据为 AI 解析结果，不允许编辑）
  const setFitField = (fitId, k, v) => {
    setDetail((d) => (d ? { ...d, fits: d.fits.map((f) => (f.id === fitId ? { ...f, [k]: v, _dirty: true } : f)) } : d))
  }

  // 保存所有被修改过的匹配建议
  const saveFits = async () => {
    if (!detail) return
    const changed = detail.fits.filter((f) => f._dirty)
    if (changed.length === 0) return
    await Promise.all(
      changed.map(async (f) => {
        const res = await fetch(`${API_BASE}/jobfits/${f.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ suggestion: f.suggestion, evidence: f.evidence || '' }),
        })
        const json = await res.json()
        if (!res.ok || json.code !== 0) throw new Error(json.message || '匹配建议保存失败')
      })
    )
    setDetail((d) => (d ? { ...d, fits: d.fits.map(({ _dirty, ...rest }) => rest) } : d))
  }

  // 确认候选人：状态 review→finish，打分存 matches 表，并同步移除导入队列中的对应项
  const confirmCandidate = async (c) => {
    try {
      const res = await fetch(`${API_BASE}/candidates/${c.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'finish' }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '确认失败')
      setCandidates((list) => list.map((it) => (it.id === c.id ? { ...it, status: 'finish' } : it)))
      // 计算匹配打分与各项建议个数并落库
      if (c.job_id) {
        try {
          const saved = await upsertCandidateMatch(c.id, c.job_id)
          setScores((s) => ({ ...s, [c.id]: saved.score }))
        } catch { /* 打分失败不影响确认流程 */ }
      }
      // 同步移除导入队列中的该候选人
      setImportQueue((q) => q.filter((it) => it.candidate_id !== c.id))
      showToast(`已确认「${c.name || '未命名'}」`)
    } catch (e) {
      showToast(`确认失败：${e.message}`, 'error')
    }
  }

  const setField = (k, v) => setEditForm((f) => ({ ...f, [k]: v }))

  const saveEdit = async () => {
    if (!editForm.name.trim()) {
      showToast('请填写候选人姓名')
      return
    }
    try {
      const res = await fetch(`${API_BASE}/candidates/${detail.candidate.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editForm.name.trim(),
          job_id: editForm.job_id ? Number(editForm.job_id) : null,
          phone: editForm.phone.trim(),
          email: editForm.email.trim(),
          experience: editForm.experience.trim(),
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '保存失败')
      setCandidates((list) => list.map((c) => (c.id === detail.candidate.id ? json.data : c)))
      setDetail((d) => (d ? { ...d, candidate: json.data } : d))
      // 同步保存被修改的匹配建议，并重算打分与各项建议个数
      try {
        await saveFits()
        if (detail.candidate.job_id) {
          const saved = await upsertCandidateMatch(detail.candidate.id, detail.candidate.job_id)
          setScores((s) => ({ ...s, [detail.candidate.id]: saved.score }))
        }
      } catch { showToast('', 'error') }
      setDetail(null)
      showToast(`候选人「${editForm.name.trim()}」信息已更新`)
    } catch (e) {
      showToast(`保存失败：${e.message}`, 'error')
    }
  }

  const deleteCandidate = async (c) => {
    if (!window.confirm(`确定要删除候选人「${c.name || '未命名'}」吗？此操作不可恢复。`)) return
    try {
      const res = await fetch(`${API_BASE}/candidates/${c.id}`, { method: 'DELETE' })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '删除失败')
      setCandidates((list) => list.filter((x) => x.id !== c.id))
      showToast(`候选人「${c.name || '未命名'}」已删除`)
    } catch (e) {
      showToast(`删除失败：${e.message}`, 'error')
    }
  }

  return (
    <section className="p-8 max-w-[1440px] mx-auto">
      <div className="flex items-start justify-between mb-7">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">候选人管理</h1>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>实时更新
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-500">显示已解析的候选人，含待确认与已确认</p>
        </div>
        <button
          onClick={() => navigate('import')}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
        >
          <Icon icon="solar:upload-outline" width={18} />导入简历
        </button>
      </div>

      <div className="grid grid-cols-4 gap-5 mb-6">
        {stats.map((s) => (
          <div key={s.label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between text-sm text-slate-500">
              <span>{s.label}</span>
              <Icon icon={s.icon} width={20} className={s.iconClass} />
            </div>
            <div className="mt-3 text-3xl font-bold text-slate-900">{s.value}</div>
            <p className={`mt-2 text-xs ${s.noteClass || 'text-slate-500'}`}>{s.note}</p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
        <div className="border-b border-slate-200 p-5">
          <div className="flex flex-wrap gap-3">
            <label className="relative min-w-[300px] flex-1">
              <Icon icon="solar:magnifer-outline" width={18} className="absolute left-3 top-3 text-slate-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索姓名、职位或联系方式"
                className="w-full rounded-lg border border-slate-300 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>
            <select value={dept} onChange={(e) => onDeptChange(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm">
              <option value="all">全部意向部门</option>
              {deptOptions.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <select value={job} onChange={(e) => setJob(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm">
              <option value="all">全部意向职位</option>
              {jobOptions.map((j) => (
                <option key={j.id} value={j.id}>{j.name}</option>
              ))}
            </select>
            <button onClick={resetFilters} className="inline-flex items-center gap-1 rounded-lg px-3 py-2.5 text-sm text-slate-500 hover:bg-slate-100">
              <Icon icon="solar:restart-outline" width={17} />重置
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-6 py-3 text-left font-semibold">候选人</th>
                <th className="px-3 py-3 text-left font-semibold">联系电话</th>
                <th className="px-3 py-3 text-left font-semibold">邮箱地址</th>
                <th className="px-3 py-3 text-left font-semibold">意向职位</th>
                <th className="px-3 py-3 text-left font-semibold">状态</th>
                <th className="px-3 py-3 text-left font-semibold">AI 匹配度</th>
                <th className="px-6 py-3 text-right font-semibold">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-sm text-slate-400">加载中…</td>
                </tr>
              ) : paginated.map((c) => (
                <tr key={c.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 font-bold text-white">
                        {(c.name || '?').slice(0, 1)}
                      </div>
                      <div>
                        <div className="font-semibold text-slate-800">{c.name || '未命名'}</div>
                        <div className="mt-1 text-xs text-slate-500">导入于 {new Date(c.created_at).toLocaleDateString()}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-4 text-slate-600">{c.phone || '—'}</td>
                  <td className="px-3 py-4 text-slate-600">{c.email || '—'}</td>
                  <td className="px-3 py-4 text-slate-600">{c.job_id ? (jobIdMap.get(c.job_id) || '—') : '—'}</td>
                  <td className="px-3 py-4">
                    <div className="flex items-center gap-1.5">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                        c.status === 'finish' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                      }`}>
                        {c.status === 'finish' ? '已确认' : '待确认'}
                      </span>
                      {c.status === 'finish' && scores[c.id] >= ALGO_SETTINGS.recommendThreshold && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-700">
                          <Icon icon="solar:stars-outline" width={13} />推荐
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-4">
                    {scores[c.id] != null ? (
                      <div className="flex items-center gap-2">
                        <span className={`font-bold ${
                          scores[c.id] >= 75 ? 'text-emerald-600' : scores[c.id] >= 50 ? 'text-amber-600' : 'text-rose-600'
                        }`}>{scores[c.id]} 分</span>
                        <div className="h-1.5 w-16 rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${
                              scores[c.id] >= 75 ? 'bg-emerald-500' : scores[c.id] >= 50 ? 'bg-amber-500' : 'bg-rose-500'
                            }`}
                            style={{ width: `${scores[c.id]}%` }}
                          ></div>
                        </div>
                      </div>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => openDetail(c)} className="font-medium text-cyan-700 hover:text-cyan-900">编辑</button>
                      {c.status === 'review' && (
                        <button onClick={() => confirmCandidate(c)} className="font-medium text-emerald-600 hover:text-emerald-900">确认</button>
                      )}
                      <button onClick={() => deleteCandidate(c)} className="text-rose-500 hover:text-rose-700">删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 && (
          <div className="px-6 py-12 text-center">
            <Icon icon="solar:magnifer-outline" width={34} className="text-slate-300" />
            <p className="mt-3 font-medium text-slate-600">暂无已确认的候选人</p>
            <p className="mt-1 text-sm text-slate-400">在导入简历页完成解析并确认后，候选人将在此显示。</p>
          </div>
        )}

        {/* 分页栏 */}
        {!loading && filtered.length > 0 && (
          <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4">
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

      {/* 候选人详情/编辑弹窗（查看与修改合一） */}
      <Modal open={!!detail} onClose={() => setDetail(null)} maxWidth="max-w-2xl">
        {detail && editForm && (
          <>
            <ModalHeader title={`${detail.candidate.name || '未命名'} · 候选人详情`} subtitle="查看解析信息，可直接修改并保存。" onClose={() => setDetail(null)} />
            <div className="p-6 max-h-[70vh] overflow-y-auto">
              <div className="grid grid-cols-2 gap-5">
                <label className="text-sm font-medium text-slate-700">
                  候选人姓名
                  <input value={editForm.name} onChange={(e) => setField('name', e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                </label>
                <label className="text-sm font-medium text-slate-700">
                  意向职位
                  <select value={editForm.job_id} onChange={(e) => setField('job_id', e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500">
                    <option value="">未指定</option>
                    {jobs.map((j) => (
                      <option key={j.id} value={j.id}>{j.dept_label ? `${j.dept_label}-${j.name}` : j.name}</option>
                    ))}
                  </select>
                </label>
                <label className="text-sm font-medium text-slate-700">
                  联系电话
                  <input value={editForm.phone} onChange={(e) => setField('phone', e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                </label>
                <label className="text-sm font-medium text-slate-700">
                  邮箱地址
                  <input value={editForm.email} onChange={(e) => setField('email', e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                </label>
                <label className="text-sm font-medium text-slate-700">
                  工作年限
                  <input value={editForm.experience} onChange={(e) => setField('experience', e.target.value)} placeholder="如 5 年" className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                </label>
              </div>

              <div className="mt-5">
                <h3 className="font-semibold text-slate-800">职位匹配建议</h3>
                {detailLoading ? (
                  <p className="mt-2 text-sm text-slate-400">加载匹配建议中…</p>
                ) : detail.fits.length === 0 ? (
                  <p className="mt-2 text-sm text-slate-400">暂无匹配建议数据。</p>
                ) : (
                  <div className="mt-3 rounded-lg border border-slate-200 overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 text-xs text-slate-500">
                        <tr>
                          <th className="px-3 py-2 text-left font-semibold">要求项</th>
                          <th className="px-3 py-2 text-left font-semibold">匹配建议</th>
                          <th className="px-3 py-2 text-left font-semibold">依据</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.fits.map((f) => (
                          <tr key={f.id} className="border-t border-slate-100">
                            <td className="px-3 py-2 font-medium text-slate-800">{f.name}</td>
                            <td className="px-3 py-2">
                              <select
                                value={f.suggestion}
                                onChange={(e) => setFitField(f.id, 'suggestion', e.target.value)}
                                className={`rounded-md border px-2 py-1.5 text-xs font-medium outline-none focus:border-cyan-500 ${
                                  f.suggestion === '满足' ? 'border-emerald-200 text-emerald-700' : f.suggestion === '不满足' ? 'border-rose-200 text-rose-700' : 'border-amber-200 text-amber-700'
                                }`}
                              >
                                <option>满足</option>
                                <option>不满足</option>
                                <option>证据不足</option>
                              </select>
                            </td>
                            <td className="px-3 py-2 text-xs text-slate-600">
                              {f.evidence || <span className="text-slate-300">—</span>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-3 rounded-b-2xl bg-slate-50 px-6 py-4">
              <button onClick={() => setDetail(null)} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium">关闭</button>
              <button onClick={saveEdit} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800">保存修改</button>
            </div>
          </>
        )}
      </Modal>
    </section>
  )
}
