import { useEffect, useMemo, useState } from 'react'
import Icon from '../components/Icon'
import Modal, { ModalHeader } from '../components/Modal'
import { useApp } from '../context/AppContext'

const STATUS_MAP = {
  open: { label: '招聘中', badge: 'bg-emerald-50 text-emerald-700', iconBg: 'bg-cyan-50 text-cyan-700' },
  paused: { label: '已暂停', badge: 'bg-slate-100 text-slate-600', iconBg: 'bg-slate-50 text-slate-600' },
  closed: { label: '已关闭', badge: 'bg-slate-100 text-slate-600', iconBg: 'bg-slate-50 text-slate-600' },
}

const STATUS_ORDER = { open: 0, paused: 1, closed: 2 }

const PAGE_SIZE = 10 // 职位列表每页条数

export default function Jobs() {
  const { navigate, showToast } = useApp()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [department, setDepartment] = useState('all')
  const [formOpen, setFormOpen] = useState(false)
  const [formJobId, setFormJobId] = useState(null)
  const [formName, setFormName] = useState('')
  const [formDeptId, setFormDeptId] = useState('')
  const [formHeadcount, setFormHeadcount] = useState(1)
  const [formStatus, setFormStatus] = useState('open')
  const [formDescription, setFormDescription] = useState('')
  const [deptOpen, setDeptOpen] = useState(false)
  const [deptName, setDeptName] = useState('')
  const [deptResponsibility, setDeptResponsibility] = useState('')
  const [departments, setDepartments] = useState([])
  const [editingDeptId, setEditingDeptId] = useState(null)
  const [jobs, setJobs] = useState([])
  const [page, setPage] = useState(1) // 当前页码

  const fetchJobs = async () => {
    try {
      const res = await fetch('http://localhost:8000/jobs')
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '加载失败')
      setJobs(json.data || [])
    } catch (e) {
      showToast(`职位列表加载失败：${e.message}`, 'error')
    }
  }

  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return jobs.filter((j) => {
      const haystack = `${j.name} ${j.dept_label || ''}`.toLowerCase()
      return (
        (!kw || haystack.includes(kw)) &&
        (status === 'all' || j.status === status) &&
        (department === 'all' || j.dept_label === department)
      )
    }).sort((a, b) => (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9))
  }, [jobs, search, status, department])

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
  }, [search, status, department])

  const stats = useMemo(() => {
  const open = jobs.filter((j) => j.status === 'open').length
  const paused = jobs.filter((j) => j.status === 'paused').length
  const closed = jobs.filter((j) => j.status === 'closed').length
  return [
    { label: '招聘中', value: open, note: '进行中的职位', noteClass: 'text-emerald-600', icon: 'solar:case-round-outline', iconClass: 'text-cyan-600' },
    { label: '已暂停', value: paused, note: '暂停中的职位', noteClass: 'text-slate-500', icon: 'solar:clipboard-list-outline', iconClass: 'text-violet-600' },
    { label: '已关闭', value: closed, note: '已结束招聘', noteClass: 'text-slate-400', icon: 'solar:check-circle-outline', iconClass: 'text-slate-400' },
  ]
}, [jobs])

  const resetFilters = () => {
    setSearch('')
    setStatus('all')
    setDepartment('all')
  }

  const openJobForm = (job) => {
    if (job) {
      setFormJobId(job.id)
      setFormName(job.name || '')
      setFormDeptId(job.department_id ? String(job.department_id) : '')
      setFormHeadcount(job.headcount || 1)
      setFormStatus(job.status || 'open')
      setFormDescription(job.description || '')
    } else {
      setFormJobId(null)
      setFormName('')
      setFormDeptId('')
      setFormHeadcount(1)
      setFormStatus('open')
      setFormDescription('')
    }
    setFormOpen(true)
  }

  const saveJobForm = async () => {
    const name = formName.trim()
    if (!name) {
      showToast('请先填写职位名称')
      return
    }
    const isEdit = !!formJobId
    try {
      const res = await fetch(isEdit ? `http://localhost:8000/jobs/${formJobId}` : 'http://localhost:8000/jobs', {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          department_id: formDeptId ? Number(formDeptId) : null,
          headcount: Number(formHeadcount) || 1,
          status: formStatus,
          description: formDescription.trim() || null,
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || (isEdit ? '修改失败' : '保存失败'))
      setFormOpen(false)
      showToast(`职位「${name}」已${isEdit ? '更新' : '保存'}`)
      fetchJobs()
    } catch (e) {
      showToast(`${isEdit ? '修改' : '保存'}职位失败：${e.message}`, 'error')
    }
  }

  const fetchDepartments = async () => {
    try {
      const res = await fetch('http://localhost:8000/departments')
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '加载失败')
      setDepartments(json.data || [])
    } catch (e) {
      showToast(`部门列表加载失败：${e.message}`, 'error')
    }
  }

  useEffect(() => {
    fetchDepartments()
    fetchJobs()
  }, [])

  const resetDeptForm = () => {
    setDeptName(''); setDeptResponsibility(''); setEditingDeptId(null)
  }

  const openDeptForm = () => {
    resetDeptForm()
    setDeptOpen(true)
    fetchDepartments()
  }

  const editDepartment = (dept) => {
    setDeptName(dept.name)
    setDeptResponsibility(dept.responsibility || '')
    setEditingDeptId(dept.id)
  }

  const deleteDepartment = async (id, name) => {
    try {
      const res = await fetch(`http://localhost:8000/departments/${id}`, { method: 'DELETE' })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '删除失败')
      showToast(`部门「${name}」已删除`)
      if (editingDeptId === id) resetDeptForm()
      fetchDepartments()
    } catch (e) {
      showToast(`删除部门失败：${e.message}`, 'error')
    }
  }

  const saveDepartment = async () => {
    const name = deptName.trim()
    if (!name) { showToast('请先填写部门名称'); return }
    const isEdit = editingDeptId != null
    try {
      const url = isEdit
        ? `http://localhost:8000/departments/${editingDeptId}`
        : 'http://localhost:8000/departments'
      const res = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, responsibility: deptResponsibility.trim() || null }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || (isEdit ? '修改失败' : '新增失败'))
      showToast(`部门「${name}」已${isEdit ? '更新' : '创建'}`)
      resetDeptForm()
      fetchDepartments()
    } catch (e) {
      showToast(`${isEdit ? '修改' : '新增'}部门失败：${e.message}`, 'error')
    }
  }

  return (
    <section className="p-8 max-w-[1440px] mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-7">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">职位管理</h1>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              {jobs.filter((j) => j.status === 'open').length} 个进行中
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-500">统一管理职位状态与招聘目标。</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={openDeptForm}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Icon icon="solar:buildings-outline" width={18} />部门信息
          </button>
          <button
            onClick={() => openJobForm(null)}
            className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800"
          >
            <Icon icon="solar:add-circle-outline" width={18} />新建职位
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-5 mb-6">
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
            <label className="relative min-w-[280px] flex-1">
              <Icon icon="solar:magnifer-outline" width={18} className="absolute left-3 top-3 text-slate-400" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索职位名称或部门"
                className="w-full rounded-lg border border-slate-300 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm"
            >
              <option value="all">全部状态</option>
              <option value="open">招聘中</option>
              <option value="paused">已暂停</option>
              <option value="closed">已关闭</option>
            </select>
            <select
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm"
            >
              <option value="all">全部部门</option>
              {departments.map((d) => (
                <option key={d.id} value={d.name}>{d.name}</option>
              ))}
            </select>
            <button
              onClick={resetFilters}
              className="inline-flex items-center gap-1 rounded-lg px-3 py-2.5 text-sm text-slate-500 hover:bg-slate-100"
            >
              <Icon icon="solar:restart-outline" width={17} />重置
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="px-6 py-3 text-left font-semibold">职位</th>
                <th className="px-3 py-3 text-left font-semibold">招聘部门</th>
                <th className="px-3 py-3 text-left font-semibold">状态</th>
                <th className="px-3 py-3 text-left font-semibold">候选人</th>
                <th className="px-6 py-3 text-right font-semibold">操作</th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((j) => {
                const st = STATUS_MAP[j.status] || STATUS_MAP.open
                return (
                <tr key={j.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${st.iconBg}`}>
                        <Icon icon="solar:case-round-outline" width={20} />
                      </div>
                      <div>
                        <div className="font-semibold text-slate-800">{j.name}</div>
                        <div className="mt-1 text-xs text-slate-500">招聘 {j.headcount} 人</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-4">
                    <span className="text-sm text-slate-600">{j.dept_label || '未分配部门'}</span>
                  </td>
                  <td className="px-3 py-4">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${st.badge}`}>{st.label}</span>
                  </td>
                  <td className="px-3 py-4">
                    <div className="font-medium text-slate-700">{j.candidates ?? 0} 人</div>
                    <div className="mt-1 text-xs text-slate-400">{(j.candidates ?? 0) > 0 ? '已投递' : '暂无候选人'}</div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex justify-end gap-3">
                      <button onClick={() => openJobForm(j)} className="text-slate-500 hover:text-cyan-700">编辑</button>
                      <button
                        onClick={() => navigate('requirements', { jobId: j.id })}
                        disabled={j.status !== 'open'}
                        className="text-slate-500 hover:text-cyan-700 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-slate-500"
                        title={j.status !== 'open' ? '仅招聘中的职位可配置要求' : '配置该职位的要求'}
                      >
                        要求配置
                      </button>
                    </div>
                  </td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {filtered.length === 0 && (
          <div className="px-6 py-12 text-center">
            <Icon icon="solar:magnifer-outline" width={34} className="text-slate-300" />
            <p className="mt-3 font-medium text-slate-600">未找到匹配的职位</p>
            <p className="mt-1 text-sm text-slate-400">请调整搜索条件或筛选项后重试。</p>
          </div>
        )}

        {/* 分页栏 */}
        {filtered.length > 0 && (
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

      {/* 新建/编辑职位弹窗 */}
      <Modal open={formOpen} onClose={() => setFormOpen(false)} maxWidth="max-w-2xl">
        <ModalHeader title={formJobId ? '编辑职位' : '新建职位'} subtitle="填写基础信息后即可关联部门与职位要求。" onClose={() => setFormOpen(false)} />
        <div className="grid grid-cols-2 gap-5 p-6">
          <label className="text-sm font-medium text-slate-700">
            职位名称
            <input
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="例如：产品经理"
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500"
            />
          </label>
          <label className="text-sm font-medium text-slate-700">
            所属部门
            <select value={formDeptId} onChange={(e) => setFormDeptId(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm">
              <option value="">请选择部门</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">
            招聘人数
            <input type="number" min="1" value={formHeadcount} onChange={(e) => setFormHeadcount(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm" />
          </label>
          <label className="text-sm font-medium text-slate-700">
            招聘状态
            <select value={formStatus} onChange={(e) => setFormStatus(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm">
              {Object.entries(STATUS_MAP).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </label>
          <label className="col-span-2 text-sm font-medium text-slate-700">
            职位要求
            <textarea
              value={formDescription}
              onChange={(e) => setFormDescription(e.target.value)}
              placeholder="概述岗位职责、核心能力与招聘目标"
              className="mt-2 h-24 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500"
            />
          </label>
        </div>
        <div className="flex items-center justify-end rounded-b-2xl bg-slate-50 px-6 py-4">
          <div className="flex gap-3">
            <button onClick={() => setFormOpen(false)} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium">取消</button>
            <button onClick={saveJobForm} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white">保存职位</button>
          </div>
        </div>
      </Modal>

      {/* 部门管理弹窗：左侧已有部门列表（可编辑/删除），右侧新增/编辑表单 */}
      <Modal open={deptOpen} onClose={() => setDeptOpen(false)} maxWidth="max-w-3xl">
        <ModalHeader
          title="部门管理"
          subtitle="维护部门列表，用于职位关联与组织管理。"
          onClose={() => setDeptOpen(false)}
        />
        <div className="grid grid-cols-2 gap-6 p-6">
          {/* 已有部门列表 */}
          <div className="flex flex-col">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-medium text-slate-700">已有部门</span>
              <span className="text-xs text-slate-400">{departments.length} 个</span>
            </div>
            <div className="flex-1 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100 max-h-80">
              {departments.length === 0 ? (
                <div className="p-4 text-sm text-slate-400">暂无部门</div>
              ) : departments.map((d) => (
                <div
                  key={d.id}
                  className={`flex items-start justify-between gap-2 p-3 ${editingDeptId === d.id ? 'bg-cyan-50' : 'hover:bg-slate-50'}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-slate-800">{d.name}</div>
                    {d.responsibility && (
                      <div className="mt-0.5 line-clamp-2 text-xs leading-5 text-slate-500">{d.responsibility}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => editDepartment(d)}
                      className="rounded p-1 text-slate-400 hover:text-cyan-600"
                      title="编辑"
                    >
                      <Icon icon="solar:pen-outline" width={16} />
                    </button>
                    <button
                      onClick={() => deleteDepartment(d.id, d.name)}
                      className="rounded p-1 text-slate-400 hover:text-rose-600"
                      title="删除"
                    >
                      <Icon icon="solar:trash-bin-trash-outline" width={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 新增/编辑表单 */}
          <div className="flex flex-col gap-5">
            <div className="text-sm font-medium text-slate-700">
              {editingDeptId ? '编辑部门' : '新增部门'}
            </div>
            <label className="text-sm font-medium text-slate-700">
              部门名称
              <input
                value={deptName}
                onChange={(e) => setDeptName(e.target.value)}
                placeholder="例如：技术中心"
                className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500"
              />
            </label>
            <label className="text-sm font-medium text-slate-700">
              部门职责
              <textarea
                value={deptResponsibility}
                onChange={(e) => setDeptResponsibility(e.target.value)}
                placeholder="概述部门的核心职责与业务范围"
                className="mt-2 h-24 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500"
              />
            </label>
            {editingDeptId && (
              <button
                onClick={resetDeptForm}
                className="self-start text-xs text-slate-500 hover:text-cyan-600"
              >
                ← 返回新增模式
              </button>
            )}
          </div>
        </div>
        <div className="flex items-center justify-end rounded-b-2xl bg-slate-50 px-6 py-4">
          <div className="flex gap-3">
            <button onClick={() => setDeptOpen(false)} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium">取消</button>
            <button onClick={saveDepartment} className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white">
              {editingDeptId ? '保存修改' : '保存部门'}
            </button>
          </div>
        </div>
      </Modal>
    </section>
  )
}
