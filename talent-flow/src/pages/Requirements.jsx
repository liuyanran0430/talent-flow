import { useState, useEffect, useMemo } from 'react'
import Icon from '../components/Icon'
import Modal, { ModalHeader } from '../components/Modal'
import { useApp } from '../context/AppContext'
import { ALGO_SETTINGS } from '../utils/matchScore'

const IMPORTANCE_STARS = { 高: '★★★', 中: '★★☆', 低: '★☆☆' }

const EMPTY_FORM = { name: '', type: '必须', importance: '高', standard: '' }

const PAGE_SIZE = 10 // 要求列表每页条数

const TPL_ICON_BY_IDX = [
  { icon: 'solar:cpu-bolt-outline', iconBg: 'bg-blue-50 text-blue-600' },
  { icon: 'solar:code-square-outline', iconBg: 'bg-violet-50 text-violet-600' },
  { icon: 'solar:chart-outline', iconBg: 'bg-amber-50 text-amber-600' },
]
const TPL_ICON_FALLBACK = { icon: 'solar:document-add-outline', iconBg: 'bg-slate-50 text-slate-600' }

export default function Requirements() {
  const { showToast, selectedJob: ctxSelectedJob } = useApp()
  const [requirements, setRequirements] = useState([])
  const [page, setPage] = useState(1) // 当前页码
  const [departments, setDepartments] = useState([])
  const [jobOptions, setJobOptions] = useState([])
  const [selectedDeptId, setSelectedDeptId] = useState('')
  const [selectedJobId, setSelectedJobId] = useState(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [deptRes, jobRes] = await Promise.all([
          fetch('http://localhost:8000/departments'),
          fetch('http://localhost:8000/jobs'),
        ])
        const [deptJson, jobJson] = await Promise.all([deptRes.json(), jobRes.json()])
        setDepartments(deptJson.data || [])
        // 仅招聘中职位可关联
        const opts = (jobJson.data || []).filter((j) => j.status === 'open')
        setJobOptions(opts)
        const target = ctxSelectedJob?.jobId ? opts.find((o) => o.id === ctxSelectedJob.jobId) : null
        if (target) {
          setSelectedDeptId(target.department_id ? String(target.department_id) : '')
          setSelectedJobId(target.id)
        } else if (opts.length) {
          setSelectedDeptId(opts[0].department_id ? String(opts[0].department_id) : '')
          setSelectedJobId(opts[0].id)
        }
      } catch {
        // ignore
      }
    }
    load()
  }, [])

  // 部门筛选后的职位选项
  const deptJobOptions = selectedDeptId
    ? jobOptions.filter((j) => String(j.department_id) === selectedDeptId)
    : jobOptions

  // 切换部门时，若当前职位不属于该部门则清空
  const onDeptChange = (v) => {
    setSelectedDeptId(v)
    if (selectedJobId) {
      const sel = jobOptions.find((j) => j.id === selectedJobId)
      if (!sel || (v && String(sel.department_id) !== v)) setSelectedJobId(null)
    }
  }

  const onJobChange = (id) => {
    setSelectedJobId(id ? Number(id) : null)
    const job = jobOptions.find((j) => j.id === Number(id))
    if (job) showToast('已关联职位：' + job.name)
  }

  // 当前选中职位展示名（部门-职位名）
  const selectedJobLabel = useMemo(() => {
    const job = jobOptions.find((j) => j.id === selectedJobId)
    if (!job) return ''
    const dept = departments.find((d) => d.id === job.department_id)
    return dept ? `${dept.name}-${job.name}` : job.name
  }, [jobOptions, departments, selectedJobId])

  useEffect(() => {
    if (selectedJobId) fetchRequirements(selectedJobId)
    setPage(1) // 切换职位后回到第一页
  }, [selectedJobId])

  // 分页
  const totalPages = Math.max(1, Math.ceil(requirements.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const paginated = useMemo(
    () => requirements.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [requirements, safePage]
  )

  const fetchRequirements = async (jobId) => {
    try {
      const res = await fetch(`http://localhost:8000/requirements/${jobId}/items`)
      const json = await res.json()
      if (json.code === 0) {
        const IMPORTANCE_ORDER = { 高: 0, 中: 1, 低: 2 }
        const list = (json.data || []).slice().sort((a, b) => {
          const ai = IMPORTANCE_ORDER[a.importance] ?? 99
          const bi = IMPORTANCE_ORDER[b.importance] ?? 99
          if (ai !== bi) return ai - bi
          return (a.id ?? 0) - (b.id ?? 0)
        })
        setRequirements(list)
      }
    } catch {
      // ignore
    }
  }

  // 要求配置变化后的重算入口：查询该职位已解析候选人，确认后触发后台重算匹配建议与AI得分
  const recalcAfterChange = async (jobId) => {
    if (!jobId) return
    let parsedCount = 0
    try {
      const res = await fetch(`http://localhost:8000/candidates?job_id=${jobId}&page_size=200`)
      const json = await res.json()
      const list = (json.data?.items || json.data || []).filter((c) => c.status === 'review' || c.status === 'finish')
      parsedCount = list.length
    } catch { /* 查询失败不阻塞，交由后端判定 */ }
    if (!parsedCount) return
    if (!window.confirm(`该职位已有 ${parsedCount} 位已解析候选人，是否重新计算其匹配建议与AI得分？\n将重新解析简历并覆盖现有匹配建议（含人工修改），该操作不可恢复。`)) return
    try {
      const res = await fetch(`http://localhost:8000/requirements/${jobId}/recalculate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          weights: ALGO_SETTINGS.weights,
          must_gate: ALGO_SETTINGS.mustGate,
          recommend_threshold: ALGO_SETTINGS.recommendThreshold,
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '重算失败')
      const count = json.data?.count ?? 0
      showToast(count
        ? `已开始重新计算 ${count} 位候选人的匹配建议与AI得分，解析完成后刷新页面查看`
        : '该职位暂无需要重算的候选人')
    } catch (e) {
      showToast(`触发重算失败：${e.message}`, 'error')
    }
  }

  // 要求项弹窗
  const [reqModalOpen, setReqModalOpen] = useState(false)
  const [editingItemId, setEditingItemId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [generating, setGenerating] = useState(false)
  const [applying, setApplying] = useState(false)
  const [jdGenOpen, setJdGenOpen] = useState(false)
  const [jdContent, setJdContent] = useState('')
  const [jdLoading, setJdLoading] = useState(false)
  const [genResult, setGenResult] = useState(null)

  const openJDGen = async () => {
    if (!selectedJobId) { showToast('请先选择职位'); return }
    setGenResult(null)
    setJdContent('')
    setJdGenOpen(true)
    setJdLoading(true)
    try {
      const res = await fetch(`http://localhost:8000/jobs/${selectedJobId}`)
      const json = await res.json()
      if (json.code === 0) setJdContent(json.data.description || '')
    } catch {
      setJdContent('')
    } finally {
      setJdLoading(false)
    }
  }

  const doGenerate = async () => {
    if (!jdContent.trim()) { showToast('该职位未填写职位要求（JD），无法生成'); return }
    setGenerating(true)
    try {
      const res = await fetch(`http://localhost:8000/requirements/${selectedJobId}/generate`, { method: 'POST' })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || json.detail?.[0]?.msg || '生成失败')
      setGenResult(json.data || [])
    } catch (e) {
      showToast(`生成失败：${e.message}`, 'error')
    } finally {
      setGenerating(false)
    }
  }

  // 编辑生成结果中的单项字段（要求项/类型/重要程度/判定标准）
  const updateGenItem = (idx, key, value) => {
    setGenResult((items) => items.map((it, i) => (i === idx ? { ...it, [key]: value } : it)))
  }

  const applyGenResult = async () => {
    if (!selectedJobId) { showToast('请先选择职位'); return }
    if (!genResult?.length) { showToast('生成结果为空，无法应用'); return }
    if (genResult.some((it) => !it.name.trim())) { showToast('要求项名称不能为空'); return }
    setApplying(true)
    try {
      const res = await fetch(`http://localhost:8000/requirements/${selectedJobId}/items/batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          items: genResult.map((it) => ({
            name: it.name.trim(),
            type: it.type,
            importance: it.importance,
            standard: it.standard || null,
          })),
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || json.detail?.[0]?.msg || '应用失败')
      setJdGenOpen(false)
      showToast(`已应用 ${json.data?.length || 0} 项要求`)
      fetchRequirements(selectedJobId)
      recalcAfterChange(selectedJobId)
    } catch (e) {
      showToast(`应用失败：${e.message}`, 'error')
    } finally {
      setApplying(false)
    }
  }

  // 模板弹窗
  const [tplSaveOpen, setTplSaveOpen] = useState(false)
  const [tplName, setTplName] = useState('AI算法工程师通用版')
  const [tplDesc, setTplDesc] = useState('')
  const [tplMgrOpen, setTplMgrOpen] = useState(false)
  const [templates, setTemplates] = useState([])
  const [selectedTplId, setSelectedTplId] = useState(null)
  const [applyingTplId, setApplyingTplId] = useState(null)
  const [deletingTplId, setDeletingTplId] = useState(null)
  const [viewingTpl, setViewingTpl] = useState(null)

  const fetchTemplates = async () => {
    try {
      const res = await fetch('http://localhost:8000/templates')
      const json = await res.json()
      if (json.code === 0) setTemplates(json.data || [])
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    fetchTemplates()
  }, [])

  const setField = (k, v) => setForm((f) => ({ ...f, [k]: v }))

  const openAdd = () => {
    setEditingItemId(null)
    setForm(EMPTY_FORM)
    setReqModalOpen(true)
  }

  const openEdit = (item) => {
    setEditingItemId(item.id)
    setForm({ name: item.name, type: item.type, importance: item.importance, standard: item.standard || '' })
    setReqModalOpen(true)
  }

  const saveRequirement = async () => {
    if (!form.name.trim()) {
      showToast('请先填写要求项名称')
      return
    }
    if (!selectedJobId) {
      showToast('请先选择职位')
      return
    }
    const isEdit = !!editingItemId
    try {
      const url = isEdit
        ? `http://localhost:8000/requirements/items/${editingItemId}`
        : `http://localhost:8000/requirements/${selectedJobId}/items`
      const res = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_id: selectedJobId,
          name: form.name.trim(),
          type: form.type,
          importance: form.importance,
          standard: form.standard || null,
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '保存失败')
      setReqModalOpen(false)
      showToast(isEdit ? '要求项已更新' : '已新增要求项')
      fetchRequirements(selectedJobId)
      recalcAfterChange(selectedJobId)
    } catch (e) {
      showToast(`保存失败：${e.message}`, 'error')
    }
  }

  const deleteRequirement = async (item) => {
    if (!window.confirm(`确定删除要求项「${item.name}」吗？此操作不可恢复。`)) return
    try {
      const res = await fetch(`http://localhost:8000/requirements/items/${item.id}`, { method: 'DELETE' })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '删除失败')
      showToast('要求项已删除')
      fetchRequirements(selectedJobId)
      recalcAfterChange(selectedJobId)
    } catch (e) {
      showToast(`删除失败：${e.message}`, 'error')
    }
  }

  const clearRequirements = async () => {
    if (!selectedJobId) { showToast('请先选择职位'); return }
    if (!requirements.length) { showToast('当前无要求项'); return }
    if (!window.confirm(`确定清空「${selectedJobLabel}」的所有要求项吗？此操作不可恢复。`)) return
    try {
      for (const r of requirements) {
        await fetch(`http://localhost:8000/requirements/items/${r.id}`, { method: 'DELETE' })
      }
      await fetchRequirements()
      showToast('已清空所有要求项')
      recalcAfterChange(selectedJobId)
    } catch (e) {
      showToast(`清空失败：${e.message}`, 'error')
    }
  }

  const applyTemplate = async (tpl) => {
    if (!selectedJobId) {
      showToast('请先选择职位')
      return
    }
    if (!tpl.items?.length) {
      showToast(`模板「${tpl.name}」下没有要求项`)
      return
    }
    setApplyingTplId(tpl.id)
    try {
      const res = await fetch(`http://localhost:8000/templates/${tpl.id}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: selectedJobId }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '应用失败')
      const data = json.data || {}
      setTplMgrOpen(false)
      setSelectedTplId(null)
      showToast(`已将模板「${tpl.name}」的 ${data.applied ?? tpl.items.length} 项要求应用到当前职位`)
      fetchRequirements(selectedJobId)
      fetchTemplates()
      recalcAfterChange(selectedJobId)
    } catch (e) {
      showToast(`应用模板失败：${e.message}`, 'error')
    } finally {
      setApplyingTplId(null)
    }
  }

  const deleteTemplate = async () => {
    const tpl = templates.find((t) => t.id === selectedTplId)
    if (!tpl) return
    if (!window.confirm(`确定删除模板「${tpl.name}」吗？此操作不可恢复。`)) return
    setDeletingTplId(tpl.id)
    try {
      const res = await fetch(`http://localhost:8000/templates/${tpl.id}`, { method: 'DELETE' })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '删除失败')
      setSelectedTplId(null)
      showToast(`模板「${tpl.name}」已删除`)
      fetchTemplates()
    } catch (e) {
      showToast(`删除模板失败：${e.message}`, 'error')
    } finally {
      setDeletingTplId(null)
    }
  }

  const saveTemplate = async () => {
    const name = tplName.trim()
    if (!name) { showToast('请先填写模板名称'); return }
    if (!requirements.length) { showToast('当前无要求项，无法保存模板'); return }
    try {
      const res = await fetch('http://localhost:8000/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          description: tplDesc.trim() || null,
          items: requirements.map((r) => ({
            name: r.name,
            type: r.type,
            importance: r.importance,
            standard: r.standard || null,
          })),
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || json.detail?.[0]?.msg || '保存失败')
      setTplSaveOpen(false)
      showToast(`模板「${name}」已保存`)
    } catch (e) {
      showToast(`保存模板失败：${e.message}`, 'error')
    }
  }

  return (
    <section className="p-8 max-w-[1440px] mx-auto">
      <div className="flex items-start justify-between mb-7">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">职位要求配置</h1>
            <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></span>已自动保存
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-2">定义候选人筛选标准，AI 将根据要求计算匹配度与推荐排序。</p>
        </div>
      </div>

      {/* 关联职位 */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 mb-6 shadow-sm">
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-60">
            <label className="block text-xs font-semibold text-slate-600 mb-2">部门</label>
            <select
              value={selectedDeptId}
              onChange={(e) => onDeptChange(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm bg-white outline-none focus:border-cyan-500"
            >
              <option value="">全部部门</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>
          <div className="w-72">
            <label className="block text-xs font-semibold text-slate-600 mb-2">关联职位</label>
            <select
              value={selectedJobId ?? ''}
              onChange={(e) => onJobChange(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm bg-white outline-none focus:border-cyan-500"
            >
              <option value="">请选择职位</option>
              {deptJobOptions.map((j) => (
                <option key={j.id} value={j.id}>{j.name}</option>
              ))}
            </select>
          </div>
          <button
            onClick={openJDGen}
            disabled={generating || !selectedJobId}
            className="ml-auto inline-flex items-center gap-2 rounded-lg border border-cyan-300 bg-cyan-50 px-4 py-2.5 text-sm font-medium text-cyan-700 hover:bg-cyan-100 disabled:opacity-50 disabled:cursor-not-allowed"
            title={!selectedJobId ? '请先选择职位' : '基于职位要求(JD)调用AI生成要求项'}
          >
            <Icon icon={generating ? 'solar:refresh-circle-outline' : 'solar:magic-stick-outline'} width={18} className={generating ? 'animate-spin' : ''} />
            {generating ? '正在生成…' : '基于JD生成要求'}
          </button>
        </div>
      </div>

      {/* 要求列表 */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 flex justify-between items-center border-b border-slate-200">
          <div>
            <h2 className="font-bold text-slate-900">要求列表 <span className="text-sm font-normal text-slate-400">（共 {requirements.length} 项）</span></h2>
            <p className="text-xs text-slate-500 mt-1">高优先级的必备项将获得更高匹配权重。</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => { fetchTemplates(); setSelectedTplId(null); setTplMgrOpen(true) }}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium hover:bg-slate-50"
            >
              <Icon icon="solar:widget-outline" width={18} />选择模板
            </button>
            <button
              onClick={openAdd}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium hover:bg-slate-50"
            >
              <Icon icon="solar:add-circle-outline" width={18} />新增要求项
            </button>
            <button
              onClick={() => { const job = jobOptions.find((j) => j.id === selectedJobId); setTplName(job ? job.name + '通用版' : ''); setTplDesc(''); setTplSaveOpen(true) }}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium hover:bg-slate-50"
            >
              <Icon icon="solar:bookmark-outline" width={18} />存为模板
            </button>
            <button
              onClick={clearRequirements}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium hover:bg-slate-50"
            >
              <Icon icon="solar:trash-bin-trash-outline" width={18} />清空
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="text-left font-semibold px-6 py-3 w-14">#</th>
                <th className="text-left font-semibold px-3 py-3 min-w-[165px]">要求项</th>
                <th className="text-left font-semibold px-3 py-3 w-28">类型</th>
                <th className="text-left font-semibold px-3 py-3 w-28">重要程度</th>
                <th className="text-left font-semibold px-3 py-3 min-w-[200px]">判定标准</th>
                <th className="text-right font-semibold px-6 py-3 w-24">操作</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((r, i) => (
                <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50/70">
                  <td className="align-top px-6 py-4 text-slate-400 font-medium">{(safePage - 1) * PAGE_SIZE + i + 1}</td>
                  <td className="px-3 py-4">
                    <div className="font-semibold text-slate-800">{r.name}</div>
                  </td>
                  <td className="align-top px-3 py-4">
                    <span className={`inline-flex items-center gap-1.5 ${r.type === '必须' ? 'text-rose-700' : 'text-sky-700'}`}>
                      <span className={`w-2 h-2 rounded-full ${r.type === '必须' ? 'bg-rose-500' : 'border border-sky-500'}`}></span>
                      {r.type}
                    </span>
                  </td>
                  <td className="align-top px-3 py-4">
                    <span className={`font-medium ${r.importance === '高' ? 'text-amber-600' : r.importance === '中' ? 'text-slate-600' : 'text-slate-400'}`}>
                      {IMPORTANCE_STARS[r.importance]} {r.importance}
                    </span>
                  </td>
                  <td className="align-top px-3 py-4">
                    <div className="text-xs text-slate-500 leading-5">{r.standard || '—'}</div>
                  </td>
                  <td className="align-top px-6 py-4">
                    <div className="flex justify-end gap-3">
                      <button onClick={() => openEdit(r)} className="text-slate-400 hover:text-cyan-700" title="编辑">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                        </svg>
                      </button>
                      <button onClick={() => deleteRequirement(r)} className="text-slate-400 hover:text-rose-600" title="删除">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
          <p className="text-xs text-slate-500">
            最后更新：{requirements.length
              ? new Date(Math.max(...requirements.map((r) => new Date(r.updated_at || r.created_at).getTime()))).toLocaleString()
              : '暂无要求项'}
          </p>
          {requirements.length > 0 && (
            <div className="flex items-center gap-1">
              <span className="mr-2 text-xs text-slate-500">
                共 {requirements.length} 条 · 第 {safePage} / {totalPages} 页
              </span>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                className="inline-flex items-center rounded-lg px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-200/70 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Icon icon="solar:alt-arrow-left-outline" width={15} />
              </button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`h-7 w-7 rounded-lg text-xs font-medium ${
                    p === safePage ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200/70'
                  }`}
                >
                  {p}
                </button>
              ))}
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
                className="inline-flex items-center rounded-lg px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-200/70 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Icon icon="solar:alt-arrow-right-outline" width={15} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* 基于JD生成要求弹窗 */}
      <Modal open={jdGenOpen} onClose={() => setJdGenOpen(false)} maxWidth="max-w-4xl">
        <ModalHeader title="基于职位JD生成要求" subtitle="预览岗位JD，AI 提取结果的类型与重要程度可调整，确认后将覆盖当前职位要求" onClose={() => setJdGenOpen(false)} />
        <div className="p-6 space-y-5">
          {/* 岗位JD */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Icon icon="solar:document-text-outline" width={18} className="text-slate-500" />
              <h3 className="text-sm font-semibold text-slate-700">岗位JD</h3>
              <span className="text-xs text-slate-400">{selectedJobLabel}</span>
            </div>
            {jdLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-400 py-8 justify-center">
                <Icon icon="solar:refresh-circle-outline" width={20} className="animate-spin" />
                正在加载职位信息…
              </div>
            ) : jdContent.trim() ? (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 max-h-48 overflow-y-auto">
                <p className="text-sm leading-6 text-slate-600 whitespace-pre-wrap">{jdContent}</p>
              </div>
            ) : (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                <div className="flex items-center gap-2 text-sm text-amber-700">
                  <Icon icon="solar:info-circle-outline" width={18} />
                  该职位未填写职位要求（JD），请先在职位管理中编辑职位的「职位要求」字段。
                </div>
              </div>
            )}
          </div>

          {/* 生成结果（可编辑） */}
          {genResult && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Icon icon="solar:check-circle-outline" width={18} className="text-emerald-600" />
                <h3 className="text-sm font-semibold text-slate-700">生成结果</h3>
                <span className="text-xs text-slate-400">共 {genResult.length} 项 · 类型与重要程度可调整</span>
              </div>
              <div className="rounded-xl border border-slate-200 overflow-y-auto max-h-64">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-xs text-slate-500">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium w-10">#</th>
                      <th className="px-3 py-2 text-left font-medium min-w-[140px]">要求项</th>
                      <th className="px-3 py-2 text-left font-medium w-24">类型</th>
                      <th className="px-3 py-2 text-left font-medium w-24">重要程度</th>
                      <th className="px-3 py-2 text-left font-medium min-w-[200px]">判定标准</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {genResult.map((it, i) => (
                      <tr key={i} className="hover:bg-slate-50">
                        <td className="px-3 py-2 text-slate-400 align-top">{i + 1}</td>
                        <td className="px-3 py-2 align-top">
                          <div className="text-sm font-medium text-slate-800 py-1">{it.name}</div>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <select
                            value={it.type}
                            onChange={(e) => updateGenItem(i, 'type', e.target.value)}
                            className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm outline-none focus:border-cyan-500"
                          >
                            <option>必须</option>
                            <option>加分</option>
                          </select>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <select
                            value={it.importance}
                            onChange={(e) => updateGenItem(i, 'importance', e.target.value)}
                            className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm outline-none focus:border-cyan-500"
                          >
                            <option>高</option>
                            <option>中</option>
                            <option>低</option>
                          </select>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <div className="text-xs text-slate-600 leading-5 py-1">{it.standard || '—'}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
        <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end gap-3">
          <button onClick={() => setJdGenOpen(false)} className="px-4 py-2.5 rounded-lg border border-slate-300 text-sm font-medium hover:bg-slate-100">关闭</button>
          {genResult ? (
            <button
              onClick={applyGenResult}
              disabled={applying}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-cyan-600 text-white text-sm font-medium hover:bg-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Icon icon={applying ? 'solar:refresh-circle-outline' : 'solar:check-circle-outline'} width={17} className={applying ? 'animate-spin' : ''} />
              {applying ? '应用中…' : '确认应用'}
            </button>
          ) : (
            <button onClick={doGenerate} disabled={generating || !jdContent.trim()} className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-cyan-600 text-white text-sm font-medium hover:bg-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed">
              <Icon icon={generating ? 'solar:refresh-circle-outline' : 'solar:magic-stick-3-outline'} width={17} className={generating ? 'animate-spin' : ''} />
              {generating ? '正在生成…' : '生成要求'}
            </button>
          )}
        </div>
      </Modal>

      {/* 新增/编辑要求项弹窗 */}
      <Modal open={reqModalOpen} onClose={() => setReqModalOpen(false)} maxWidth="max-w-xl">
        <ModalHeader title={editingItemId === null ? '新增要求项' : '编辑要求项'} onClose={() => setReqModalOpen(false)} />
        <div className="p-6 space-y-4">
          <label className="block text-sm font-medium">
            要求项名称
            <input
              value={form.name}
              onChange={(e) => setField('name', e.target.value)}
              placeholder="例如：Python 基础"
              className="mt-2 w-full border border-slate-300 rounded-lg px-3 py-2.5 outline-none focus:border-cyan-500"
            />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="text-sm font-medium">
              类型
              <select value={form.type} onChange={(e) => setField('type', e.target.value)} className="mt-2 w-full border border-slate-300 rounded-lg px-3 py-2.5">
                <option>必须</option>
                <option>加分</option>
              </select>
            </label>
            <label className="text-sm font-medium">
              重要程度
              <select value={form.importance} onChange={(e) => setField('importance', e.target.value)} className="mt-2 w-full border border-slate-300 rounded-lg px-3 py-2.5">
                <option>高</option>
                <option>中</option>
                <option>低</option>
              </select>
            </label>
          </div>
          <label className="block text-sm font-medium">
            判定标准
            <textarea
              value={form.standard}
              onChange={(e) => setField('standard', e.target.value)}
              placeholder="说明 AI 如何判断候选人是否满足此项"
              className="mt-2 w-full h-20 border border-slate-300 rounded-lg px-3 py-2.5 outline-none focus:border-cyan-500"
            />
          </label>
        </div>
        <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end gap-3">
          <button onClick={() => setReqModalOpen(false)} className="px-4 py-2.5 rounded-lg border border-slate-300 text-sm">取消</button>
          <button onClick={saveRequirement} className="px-4 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-medium">保存要求项</button>
        </div>
      </Modal>

      {/* 存为模板弹窗 */}
      <Modal open={tplSaveOpen} onClose={() => setTplSaveOpen(false)} maxWidth="max-w-md">
        <ModalHeader title="存为要求模板" onClose={() => setTplSaveOpen(false)} />
        <div className="p-6 space-y-4">
          <label className="block text-sm font-medium">
            模板名称
            <input
              value={tplName}
              onChange={(e) => setTplName(e.target.value)}
              placeholder="例如：后端工程师基础版"
              className="mt-2 w-full border border-slate-300 rounded-lg px-3 py-2.5 outline-none focus:border-cyan-500"
            />
          </label>
          <label className="block text-sm font-medium">
            模板说明
            <textarea
              value={tplDesc}
              onChange={(e) => setTplDesc(e.target.value)}
              placeholder="简要描述模板的适用场景、覆盖能力或筛选重点，便于后续选择"
              className="mt-2 w-full h-20 border border-slate-300 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-cyan-500 resize-none"
            />
          </label>
          <p className="text-xs text-slate-500">将保存当前全部要求项，后续可快速关联至其它职位。</p>
        </div>
        <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end gap-3">
          <button onClick={() => setTplSaveOpen(false)} className="px-4 py-2.5 rounded-lg border border-slate-300 text-sm">取消</button>
          <button
            onClick={saveTemplate}
            className="px-4 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-medium"
          >
            保存模板
          </button>
        </div>
      </Modal>

      {/* 选择模板弹窗 */}
      <Modal open={tplMgrOpen} onClose={() => setTplMgrOpen(false)} maxWidth="max-w-4xl">
        <ModalHeader title="选择模板" subtitle="选择一个模板，点击右下角「应用」将其要求项追加到当前职位。" onClose={() => setTplMgrOpen(false)} />
        <div className="p-6">
          {!selectedJobId && (
            <div className="mb-4 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
              请先在上方选择职位后再应用模板。
            </div>
          )}
          {templates.length === 0 ? (
            <div className="text-center py-12 text-sm text-slate-500">
              暂无模板，可先点击「存为模板」创建。
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-5">
              {templates.map((t, i) => {
                const meta = TPL_ICON_BY_IDX[i] || TPL_ICON_FALLBACK
                const itemCount = t.items?.length ?? 0
                const usage = t.usage_count ?? 0
                const checked = selectedTplId === t.id
                return (
                  <article
                    key={t.id}
                    onClick={() => setSelectedTplId(t.id)}
                    className={`rounded-xl border p-5 shadow-sm flex flex-col cursor-pointer transition ${
                      checked ? 'border-cyan-500 ring-2 ring-cyan-100' : 'border-slate-200 hover:border-slate-300'
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name="tpl-select"
                          checked={checked}
                          onChange={() => setSelectedTplId(t.id)}
                          onClick={(e) => e.stopPropagation()}
                          className="h-4 w-4 accent-cyan-600"
                        />
                        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${meta.iconBg}`}>
                          <Icon icon={meta.icon} width={18} />
                        </div>
                      </label>
                      <span className="text-[11px] text-slate-400">{new Date(t.created_at).toLocaleDateString()}</span>
                    </div>
                    <h3 className="mt-3 font-bold text-slate-900">{t.name}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-500 flex-1">{t.description || '—'}</p>
                    <div className="mt-4 flex items-center justify-between">
                      <span className="text-xs text-slate-500">{itemCount} 项要求 · 使用 {usage} 次</span>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-3 rounded-b-2xl bg-slate-50 px-6 py-4">
          <button
            onClick={() => {
              const tpl = templates.find((t) => t.id === selectedTplId)
              if (tpl) setViewingTpl(tpl)
            }}
            disabled={!selectedTplId}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
            title={!selectedTplId ? '请先选择一个模板' : '查看模板详情'}
          >
            <Icon icon="solar:file-text-outline" width={18} />查看
          </button>
          <button
            onClick={deleteTemplate}
            disabled={!selectedTplId || deletingTplId !== null}
            className="inline-flex items-center gap-2 rounded-lg border border-rose-300 px-4 py-2.5 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-50 disabled:cursor-not-allowed"
            title={!selectedTplId ? '请先选择一个模板' : '删除选中模板'}
          >
            <Icon icon="solar:trash-bin-trash-outline" width={18} />
            {deletingTplId !== null ? '删除中…' : '删除'}
          </button>
          <button
            onClick={() => {
              const tpl = templates.find((t) => t.id === selectedTplId)
              if (tpl) applyTemplate(tpl)
            }}
            disabled={!selectedTplId || applyingTplId !== null || !selectedJobId}
            className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed"
            title={!selectedJobId ? '请先选择职位' : !selectedTplId ? '请先选择一个模板' : '应用模板到当前职位'}
          >
            <Icon icon="solar:download-minimalistic-outline" width={18} />
            {applyingTplId !== null ? '应用中…' : '应用'}
          </button>
        </div>
      </Modal>

      {/* 模板详情查看子弹窗 */}
      <Modal open={!!viewingTpl} onClose={() => setViewingTpl(null)} maxWidth="max-w-3xl">
        <ModalHeader
          title={viewingTpl?.name || '模板详情'}
          subtitle="模板基础信息与包含的要求项"
          onClose={() => setViewingTpl(null)}
        />
        <div className="p-6 space-y-5">
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-4">
            <div className="text-sm text-slate-700 leading-6">{viewingTpl?.description || '（无说明）'}</div>
            <div className="mt-3 flex items-center gap-4 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1">
                <Icon icon="solar:calendar-outline" width={14} />
                {viewingTpl?.created_at ? new Date(viewingTpl.created_at).toLocaleString() : '—'}
              </span>
              <span className="inline-flex items-center gap-1">
                <Icon icon="solar:graph-up-outline" width={14} />
                使用 {viewingTpl?.usage_count ?? 0} 次
              </span>
              <span className="inline-flex items-center gap-1">
                <Icon icon="solar:list-check-outline" width={14} />
                {viewingTpl?.items?.length ?? 0} 项要求
              </span>
            </div>
          </div>

          <div>
            <h4 className="text-sm font-semibold text-slate-800 mb-3">要求项列表</h4>
            <div className="rounded-lg border border-slate-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs text-slate-500">
                  <tr>
                    <th className="text-left font-semibold px-4 py-2.5 w-10">#</th>
                    <th className="text-left font-semibold px-3 py-2.5">要求项</th>
                    <th className="text-left font-semibold px-3 py-2.5 w-20">类型</th>
                    <th className="text-left font-semibold px-3 py-2.5 w-20">重要程度</th>
                    <th className="text-left font-semibold px-3 py-2.5 min-w-[180px]">判定标准</th>
                  </tr>
                </thead>
                <tbody>
                  {(viewingTpl?.items || []).length === 0 ? (
                    <tr>
                      <td colSpan={5} className="text-center text-slate-400 py-6">该模板暂无要求项</td>
                    </tr>
                  ) : (
                    viewingTpl.items.map((it, i) => (
                      <tr key={it.id} className="border-t border-slate-100 align-top">
                        <td className="px-4 py-3 text-slate-400">{i + 1}</td>
                        <td className="px-3 py-3 font-medium text-slate-800">{it.name}</td>
                        <td className="px-3 py-3 text-slate-700">{it.type}</td>
                        <td className="px-3 py-3 text-slate-700">{IMPORTANCE_STARS[it.importance]} {it.importance}</td>
                        <td className="px-3 py-3 text-xs text-slate-500 leading-5">{it.standard || '—'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="flex justify-end rounded-b-2xl bg-slate-50 px-6 py-4">
          <button onClick={() => setViewingTpl(null)} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium hover:bg-slate-50">关闭</button>
        </div>
      </Modal>
    </section>
  )
}
