import { useState, useRef, useEffect, useMemo } from 'react'
import Icon from '../components/Icon'
import Modal, { ModalHeader } from '../components/Modal'
import { useApp } from '../context/AppContext'
import { upsertCandidateMatch } from '../utils/matchScore'

const API_BASE = 'http://localhost:8000'

const PAGE_SIZE = 5 // 导入队列每页条数
const ALLOWED = ['pdf', 'doc', 'docx']
const MAX_SIZE = 20 * 1024 * 1024

// 上传单个简历到后端 /resumes/upload，返回 { candidate_id, message }（message=duplicate 表示重复）
async function uploadResume(file, jobId) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('name', file.name.replace(/\.[^.]+$/, ''))
  if (jobId) fd.append('job_id', jobId)
  const res = await fetch(`${API_BASE}/resumes/upload`, { method: 'POST', body: fd })
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || `上传失败 (${res.status})`)
  return { candidate_id: json.data.candidate_id, message: json.message }
}

// 调用 GET /candidates/{id} 从数据库获取候选人详情（识别结果预览数据来源）
async function fetchCandidate(id) {
  const res = await fetch(`${API_BASE}/candidates/${id}`)
  const json = await res.json()
  if (!res.ok || json.code !== 0) throw new Error(json.message || '查询失败')
  return json.data
}

// 轮询单个候选人状态，解析完成后 resolve 候选人对象；容忍瞬时网络失败（连续 5 次失败才放弃）
// resolveOnPending=false 时把 pending 也视为解析中（用于点击"开始分析"后，后端尚未提交 processing 的窗口期）
function pollCandidate(id, { onUpdate, interval = 1500, maxFailures = 5, resolveOnPending = true } = {}) {
  return new Promise((resolve, reject) => {
    let failures = 0
    const tick = async () => {
      try {
        const res = await fetch(`${API_BASE}/candidates/${id}`)
        const json = await res.json()
        if (!res.ok || json.code !== 0) throw new Error(json.message || '查询失败')
        failures = 0
        const c = json.data
        if (onUpdate) onUpdate(c)
        if (c.status === 'processing' || (c.status === 'pending' && !resolveOnPending)) {
          setTimeout(tick, interval)
        } else {
          resolve(c)
        }
      } catch (e) {
        failures += 1
        if (failures >= maxFailures) {
          reject(e)
        } else {
          setTimeout(tick, interval) // 瞬时失败，继续轮询
        }
      }
    }
    tick()
  })
}

export default function ImportResume() {
  const {
    showToast,
    importQueue: queue,
    setImportQueue: setQueue,
    importSelected: selected,
    setImportSelected: setSelected,
    importPreviewVisible: previewVisible,
    setImportPreviewVisible: setPreviewVisible,
    importDeptId: selectedDeptId,
    setImportDeptId: setSelectedDeptId,
    importJobId: selectedJobId,
    setImportJobId: setSelectedJobId,
  } = useApp()
  const [parsing, setParsing] = useState(false)
  const [queuePage, setQueuePage] = useState(1) // 导入队列当前页码
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [experience, setExperience] = useState('')
  const [dirty, setDirty] = useState(false)
  const [dragging, setDragging] = useState(false)
  // 职位匹配建议（jobfits）与编辑弹窗
  const [matchRows, setMatchRows] = useState([])
  const [fitModalOpen, setFitModalOpen] = useState(false)
  const [editingFit, setEditingFit] = useState(null)
  const [fitForm, setFitForm] = useState({ suggestion: '证据不足', evidence: '' })
  const fileInputRef = useRef(null)
  const pollIdRef = useRef(null) // 当前轮询的候选人 id，用于切换时取消旧轮询
  const [departments, setDepartments] = useState([])
  const [jobs, setJobs] = useState([])

  const valid = [name, phone, email, experience].every((v) => v.trim().length > 0)

  const hasProcessing = queue.some((it) => it.candidate?.status === 'processing')
  const [, setTick] = useState(0)
  // 存在解析中的项时每 10 秒重渲染一次，使"僵死超时后重新显示开始分析"的判断生效
  useEffect(() => {
    if (!hasProcessing) return
    const t = setInterval(() => setTick((n) => n + 1), 10000)
    return () => clearInterval(t)
  }, [hasProcessing])

  useEffect(() => {
    fetch(`${API_BASE}/departments`)
      .then((r) => r.json())
      .then((json) => { if (json.code === 0) setDepartments(json.data || []) })
      .catch(() => {})
  }, [])

  // 部门变化时清空职位并拉取该部门职位列表；仅在部门值真正变化时清空（兼容 StrictMode 双执行与页面恢复）
  const prevDeptRef = useRef(selectedDeptId)
  useEffect(() => {
    if (prevDeptRef.current !== selectedDeptId) {
      prevDeptRef.current = selectedDeptId
      setSelectedJobId('')
    }
    if (!selectedDeptId) { setJobs([]); return }
    fetch(`${API_BASE}/jobs`)
      .then((r) => r.json())
      .then((json) => {
        if (json.code === 0) setJobs((json.data || []).filter((j) => j.department_id === Number(selectedDeptId)))
      })
      .catch(() => {})
  }, [selectedDeptId])

  const fillFromCandidate = (c) => {
    setDirty(false) // 解析自动填充不算手动修改
    setName(c.name || '')
    setPhone(c.phone || '')
    setEmail(c.email || '')
    setExperience(c.experience || '')
  }

  // 加载候选人的职位匹配建议（jobfits），按所属职位要求项补齐名称
  const loadJobfits = async (candidate) => {
    if (!candidate?.id) { setMatchRows([]); return }
    try {
      const [fitRes, reqRes] = await Promise.all([
        fetch(`${API_BASE}/jobfits/candidates/${candidate.id}`),
        candidate.job_id
          ? fetch(`${API_BASE}/requirements/${candidate.job_id}/items`)
          : Promise.resolve(null),
      ])
      const fitJson = await fitRes.json()
      const reqJson = reqRes ? await reqRes.json() : null
      const reqMap = new Map((reqJson?.data || []).map((r) => [r.id, r.name]))
      const rows = (fitJson.data || []).map((f) => ({
        ...f,
        name: reqMap.get(f.requirement_item_id) || '未知要求项',
      }))
      setMatchRows(rows)
    } catch {
      setMatchRows([])
    }
  }

  const openFitEdit = (row) => {
    setEditingFit(row)
    setFitForm({ suggestion: row.suggestion, evidence: row.evidence || '' })
    setFitModalOpen(true)
  }

  const saveFit = async () => {
    if (!editingFit) return
    try {
      const res = await fetch(`${API_BASE}/jobfits/${editingFit.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ suggestion: fitForm.suggestion, evidence: fitForm.evidence }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '保存失败')
      setFitModalOpen(false)
      showToast('匹配建议已更新')
      loadJobfits(selected)
    } catch (e) {
      showToast(`保存失败：${e.message}`, 'error')
    }
  }

  // 用候选人 id 调 GET /candidates/{id} 取候选人，若仍在解析则轮询至完成，填充预览
  // forceParsing：明确知道已开始解析（如点击"开始分析"），无论首次查到的状态如何都走解析中流程
  const selectAndPollById = async (id, forceParsing = false) => {
    const candidate = await fetchCandidate(id)
    setSelected(candidate)
    setPreviewVisible(true)
    setQueue((q) => q.map((it) => (it.candidate_id === id ? { ...it, candidate } : it)))
    pollIdRef.current = id // 切换目标：旧轮询结果将被丢弃，避免覆盖当前预览
    if (candidate.status === 'processing' || forceParsing) {
      setMatchRows([])
      setParsing(true) // 解析中：预览显示 loading
      try {
        const done = await pollCandidate(id, {
          onUpdate: (c) =>
            setQueue((q) => q.map((it) => (it.candidate_id === id ? { ...it, candidate: c } : it))),
          resolveOnPending: !forceParsing, // 强制解析模式下 pending 继续等，防止后端提交前提前结束
        })
        if (pollIdRef.current !== done.id) return // 已切到其他项，丢弃本次结果
        fillFromCandidate(done)
        setParsing(false)
        setQueue((q) =>
          q.map((it) => (it.candidate_id === done.id ? { ...it, candidate: done, parsed: true } : it))
        )
        loadJobfits(done)
        showToast('解析完成，请确认预览信息')
      } catch (e) {
        if (pollIdRef.current !== id) return
        setParsing(false)
        showToast(`解析轮询失败：${e.message}`, 'error')
        // 兜底：再拉一次最新状态，避免队列停留在"解析中"
        try {
          const latest = await fetchCandidate(id)
          setQueue((q) => q.map((it) => (it.candidate_id === id ? { ...it, candidate: latest } : it)))
          if (latest.status !== 'processing') {
            fillFromCandidate(latest)
            loadJobfits(latest)
          }
        } catch { /* 忽略兜底失败 */ }
      }
    } else {
      setParsing(false) // 切到非解析中的候选人时关闭 loading
      fillFromCandidate(candidate)
      loadJobfits(candidate)
    }
  }

  const handleFiles = async (fileList) => {
    if (!selectedJobId) {
      showToast('请先选择部门与职位')
      return
    }
    const list = Array.from(fileList).slice(0, 20)
    const validFiles = list.filter(
      (f) => ALLOWED.includes(f.name.split('.').pop().toLowerCase()) && f.size > 0 && f.size <= MAX_SIZE
    )
    if (!validFiles.length) {
      showToast('请选择非空的 PDF、DOC 或 DOCX 格式简历文件')
      return
    }
    // 追加到已有队列（不清空），batchId 保证跨批次 id 唯一
    const batchId = Date.now()
    const newLen = queue.length + validFiles.length // 上传后跳到最后一页
    setQueue((q) => [
      ...q,
      ...validFiles.map((f, idx) => ({ id: `${batchId}-${idx}`, name: f.name, status: 'uploading' })),
    ])
    showToast(`已添加 ${validFiles.length} 份简历，上传后可点击「开始分析」进行解析`)

    let lastId = null
    let badCount = 0
    await Promise.all(
      validFiles.map(async (file, i) => {
        try {
          const { candidate_id, message } = await uploadResume(file, selectedJobId)
          const dup = message === 'duplicate'
          if (dup || !candidate_id) badCount += 1
          setQueue((q) =>
            q.map((it) => (it.id === `${batchId}-${i}` ? { ...it, status: dup ? 'duplicate' : 'done', candidate_id } : it))
          )
          lastId = candidate_id // 记录最后一个上传成功的
          if (dup) {
            showToast(`「${file.name}」已存在，重复上传`)
          }
        } catch (e) {
          badCount += 1
          setQueue((q) => q.map((it) => (it.id === `${batchId}-${i}` ? { ...it, status: 'failed', error: e.message } : it)))
        }
      })
    )

    if (lastId) {
      // 上传后选中最后一个上传项；未解析（pending）时不展示识别结果预览（保持初始状态）
      setQueuePage(Math.ceil(newLen / PAGE_SIZE))
      const last = await fetchCandidate(lastId)
      setSelected(last)
      setQueue((q) => q.map((it) => (it.candidate_id === lastId ? { ...it, candidate: last } : it)))
      pollIdRef.current = null // 丢弃旧的轮询
      if (last.status === 'processing') {
        selectAndPollById(lastId, true)
      } else if (last.status !== 'pending') {
        selectAndPollById(lastId)
      } else {
        setPreviewVisible(false)
        setParsing(false)
        setMatchRows([])
      }
    } else if (badCount === validFiles.length) {
      showToast('', 'error')
    }
  }

  // 点击队列项：切换预览到该候选人（done 或 duplicate 都可点）
  const selectQueueItem = (item) => {
    if ((item.status !== 'done' && item.status !== 'duplicate') || !item.candidate_id) return
    // 未解析：识别结果预览恢复初始占位状态
    if ((item.candidate?.status ?? 'pending') === 'pending') {
      pollIdRef.current = null // 丢弃进行中的轮询结果
      setSelected(null)
      setPreviewVisible(false)
      setParsing(false)
      setMatchRows([])
      return
    }
    if (selected && selected.id === item.candidate_id) return
    selectAndPollById(item.candidate_id)
  }

  // 开始分析：触发后端解析并轮询至完成
  const startAnalyze = async (item) => {
    if (!item.candidate_id) return
    try {
      const res = await fetch(`${API_BASE}/resumes/${item.candidate_id}/analyze`, { method: 'POST' })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '启动解析失败')
      setQueue((q) =>
        q.map((it) =>
          it.candidate_id === item.candidate_id
            ? { ...it, candidate: { ...it.candidate, status: 'processing' } }
            : it
        )
      )
      showToast(`开始解析「${item.name}」`)
      // forceParsing：analyze 已成功，无论首次查询状态如何都显示 loading 并轮询
      selectAndPollById(item.candidate_id, true)
    } catch (e) {
      showToast(`解析启动失败：${e.message}`, 'error')
    }
  }

  // 挂载时恢复：队列持久化在全局 context，切回本页后恢复预览（解析中则继续轮询）
  const restoredRef = useRef(false)
  useEffect(() => {
    if (restoredRef.current) return // 防 StrictMode 双执行导致重复轮询
    restoredRef.current = true
    if (!selected) return
    if (selected.status === 'processing') {
      selectAndPollById(selected.id, true)
    } else {
      fillFromCandidate(selected)
      loadJobfits(selected)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 确认：候选人状态 review→finish，计算匹配打分存 matches 表，该项从导入队列移除
  const confirmCandidate = async (f) => {
    if (!f.candidate_id) return
    try {
      const res = await fetch(`${API_BASE}/candidates/${f.candidate_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'finish' }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '确认失败')
      // 计算匹配打分与各项建议个数并落库
      const jobId = f.candidate?.job_id || selected?.job_id
      if (jobId) {
        try {
          await upsertCandidateMatch(f.candidate_id, jobId)
        } catch { /* 打分失败不影响确认流程 */ }
      }
      setQueue((q) => q.filter((it) => it.candidate_id !== f.candidate_id))
      // 若移除的是当前选中项，关闭预览
      if (selected && selected.id === f.candidate_id) {
        setSelected(null)
        setPreviewVisible(false)
        setMatchRows([])
      }
      showToast(`已确认「${f.candidate?.name || f.name}」`)
    } catch (e) {
      showToast(`确认失败：${e.message}`, 'error')
    }
  }

  // 清空导入队列：二次确认；未解析（pending）的简历连同数据库记录与文件一并删除
  const clearQueue = async () => {
    if (queue.length === 0) return
    const pendingItems = queue.filter(
      (it) => it.candidate_id && (it.candidate?.status ?? 'pending') === 'pending'
    )
    const msg = pendingItems.length > 0
      ? `确定要清空导入队列吗？将移除队列中的 ${queue.length} 项，其中 ${pendingItems.length} 份未解析简历及其文件将被删除，该操作不可恢复。`
      : `确定要清空导入队列吗？将移除队列中的 ${queue.length} 项，该操作不可恢复。`
    if (!window.confirm(msg)) return
    // 删除未解析候选人（后端同时删除数据库记录与简历文件）
    await Promise.all(
      pendingItems.map(async (it) => {
        try {
          await fetch(`${API_BASE}/candidates/${it.candidate_id}`, { method: 'DELETE' })
        } catch { /* 删除失败不阻塞清空 */ }
      })
    )
    pollIdRef.current = null // 丢弃进行中的轮询
    setQueue([])
    setQueuePage(1)
    setSelected(null)
    setPreviewVisible(false)
    setParsing(false)
    setMatchRows([])
    showToast('导入队列已清空')
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const submitImport = async () => {
    if (!valid || !selected) {
      showToast('请先补全并校验候选人信息')
      return
    }
    try {
      const res = await fetch(`${API_BASE}/candidates/${selected.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          phone: phone.trim(),
          email: email.trim(),
          experience: experience.trim(),
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '更新失败')
      setDirty(false)
      setQueue((q) =>
        q.map((it) => (it.candidate_id === selected.id ? { ...it, candidate: json.data } : it))
      )
      showToast(`候选人「${name.trim()}」信息更改成功`)
    } catch (e) {
      showToast(`提交失败：${e.message}`, 'error')
    }
  }

  // 队列分页
  const queueTotalPages = Math.max(1, Math.ceil(queue.length / PAGE_SIZE))
  const queueSafePage = Math.min(queuePage, queueTotalPages)
  const queuePaginated = useMemo(
    () => queue.slice((queueSafePage - 1) * PAGE_SIZE, queueSafePage * PAGE_SIZE),
    [queue, queueSafePage]
  )

  const queueStyle = (s) =>
    s === 'done' ? 'bg-emerald-50 text-emerald-600'
    : s === 'failed' ? 'bg-rose-50 text-rose-600'
    : s === 'duplicate' ? 'bg-amber-50 text-amber-600'
    : 'bg-cyan-50 text-cyan-600'
  const queueIcon = (s) =>
    s === 'done' ? 'solar:file-check-outline'
    : s === 'failed' ? 'solar:file-remove-outline'
    : s === 'duplicate' ? 'solar:file-minus-outline'
    : 'solar:file-text-outline'
  const queueStatusText = (f) => {
    if (f.status === 'uploading') return '上传中…'
    if (f.status === 'duplicate') return '已存在，重复上传'
    if (f.status === 'failed') return `失败：${f.error}`
    // done：按候选人解析状态细分；candidate 未加载时默认待解析（刚上传成功）
    const cs = f.candidate?.status ?? 'pending'
    if (cs === 'pending') return '待解析'
    if (cs === 'processing') return '解析中…'
    return '待确认'
  }
  // 队列项右侧操作按钮：pending→开始分析，review→确认，解析中→无（僵死超3分钟可重新开始分析）
  const queueAction = (f) => {
    if (f.status !== 'done' && f.status !== 'duplicate') return null
    const cs = f.candidate?.status ?? 'pending' // 未加载时默认待解析
    if (cs === 'processing') {
      // 僵死自愈：解析超 3 分钟未完成（后端重载导致任务丢失），重新显示"开始分析"
      const startedAt = f.candidate?.updated_at ? new Date(f.candidate.updated_at).getTime() : 0
      const stale = startedAt && Date.now() - startedAt > 180000
      if (!stale) return null
    }
    if (cs === 'pending' || cs === 'processing') {
      return (
        <button
          key={`act-${f.id}`}
          onClick={(e) => { e.stopPropagation(); startAnalyze(f) }}
          className="flex-none w-[68px] rounded-md bg-cyan-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-cyan-700"
        >
          开始分析
        </button>
      )
    }
    if (cs !== 'processing') {
      return (
        <button
          key={`act-${f.id}`}
          onClick={(e) => { e.stopPropagation(); confirmCandidate(f) }}
          className="flex-none w-[68px] rounded-md bg-cyan-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-cyan-700"
        >
          确认
        </button>
      )
    }
    return null
  }

  return (
    <section className="h-screen p-8 max-w-[1440px] mx-auto flex flex-col overflow-hidden">
      {/* 部门和职位选择 */}
      <div className="flex items-center gap-4 mb-4 flex-none">
        <select
          value={selectedDeptId}
          onChange={(e) => setSelectedDeptId(e.target.value)}
          disabled={queue.length > 0}
          title={queue.length > 0 ? '导入队列不为空，不能切换部门' : undefined}
          className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500 disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
        >
          <option value="">选择部门</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
        <select
          value={selectedJobId}
          onChange={(e) => setSelectedJobId(e.target.value)}
          disabled={!selectedDeptId || queue.length > 0}
          title={queue.length > 0 ? '导入队列不为空，不能切换职位' : undefined}
          className="rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500 disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
        >
          <option value="">选择职位</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>{j.name}</option>
          ))}
        </select>
        {queue.length > 0 && (
          <p className="flex items-center gap-1.5 text-xs text-amber-600">
            <Icon icon="solar:info-circle-outline" width={14} />
            导入队列不为空，处理完队列中的简历后方可切换部门与职位
          </p>
        )}
      </div>
      <div className="flex-1 grid grid-cols-10 grid-rows-1 gap-6 min-h-0">
        {/* 导入模块 4 */}
        <div className="col-span-4 flex flex-col gap-6 min-h-0">
          <div className="flex-1 min-h-0 flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            {!selectedJobId ? (
              <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-amber-300 bg-amber-50 px-4 py-14 text-center">
                <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-amber-100 text-amber-600">
                  <Icon icon="solar:info-circle-outline" width={23} />
                </div>
                <h2 className="mt-3 font-semibold text-amber-700">请先选择部门与职位</h2>
                <p className="mt-2 text-xs text-amber-600">在上方选择部门和职位后，即可上传简历</p>
              </div>
            ) : (
            <label
              className={`cursor-pointer rounded-xl border-2 border-dashed bg-slate-50 px-4 py-14 text-center transition hover:border-cyan-500 hover:bg-cyan-50 block ${
                dragging ? 'border-cyan-500 bg-cyan-50' : 'border-slate-300'
              }`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.doc,.docx"
                multiple
                className="hidden"
                onChange={(e) => handleFiles(e.target.files)}
              />
              <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-100 text-cyan-700">
                <Icon icon="solar:upload-minimalistic-outline" width={23} />
              </div>
              <h2 className="mt-3 font-semibold text-slate-800">拖拽简历至此，或点击选择文件</h2>
              <p className="mt-2 text-xs text-slate-500">支持 PDF、DOC、DOCX，单文件 ≤ 20MB，最多 20 份。</p>
              <button type="button" onClick={() => fileInputRef.current?.click()} className="mt-4 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white">选择简历文件</button>
            </label>
            )}

            <div className="mt-4 flex-1 min-h-0 flex flex-col rounded-lg border border-slate-200 overflow-hidden">
              <div className="flex-none flex items-center justify-between border-b border-slate-200 px-3 py-2.5">
                <h2 className="text-sm font-semibold text-slate-800">导入队列</h2>
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">{queue.length} 份</span>
                  {queue.length > 0 && (
                    <button
                      onClick={clearQueue}
                      className="inline-flex items-center gap-1 rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-600 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-600"
                    >
                      <Icon icon="solar:trash-bin-trash-outline" width={13} />
                      清空
                    </button>
                  )}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto px-3 py-3 text-center text-xs text-slate-400">
                {queue.length === 0 ? (
                  '暂未选择简历文件'
                ) : (
                  queuePaginated.map((f, i) => {
                    const clickable = (f.status === 'done' || f.status === 'duplicate') && f.candidate_id
                    const active = clickable && selected && selected.id === f.candidate_id
                    return (
                      <div
                        key={f.id}
                        onClick={() => clickable && selectQueueItem(f)}
                        className={`flex items-center justify-between text-left px-2 py-2 rounded-lg ${i ? 'mt-1' : ''} ${
                          clickable ? 'cursor-pointer hover:bg-slate-50' : ''
                        } ${active ? 'bg-cyan-50 ring-1 ring-cyan-200' : ''}`}
                      >
                        <div className="flex min-w-0 items-center gap-2">
                          <div className={`flex h-8 w-8 flex-none items-center justify-center rounded-lg ${queueStyle(f.status)}`}>
                            <Icon icon={queueIcon(f.status)} width={16} />
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-xs font-medium text-slate-700">{f.name}</div>
                            <div className="mt-0.5 text-[11px] text-slate-500">{queueStatusText(f)}</div>
                          </div>
                        </div>
                        {queueAction(f)}
                      </div>
                    )
                  })
                )}
              </div>
              {queue.length > 0 && (
                <div className="flex-none flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3 py-1.5">
                  <span className="text-[11px] text-slate-500">共 {queue.length} 份 · 第 {queueSafePage} / {queueTotalPages} 页</span>
                  <div className="flex items-center gap-0.5">
                    <button
                      onClick={() => setQueuePage((p) => Math.max(1, p - 1))}
                      disabled={queueSafePage <= 1}
                      className="inline-flex items-center rounded-md px-1.5 py-1 text-slate-600 hover:bg-slate-200/70 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Icon icon="solar:alt-arrow-left-outline" width={14} />
                    </button>
                    {Array.from({ length: queueTotalPages }, (_, i) => i + 1).map((p) => (
                      <button
                        key={p}
                        onClick={() => setQueuePage(p)}
                        className={`h-5 w-5 rounded-md text-[11px] font-medium ${
                          p === queueSafePage ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-200/70'
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                    <button
                      onClick={() => setQueuePage((p) => Math.min(queueTotalPages, p + 1))}
                      disabled={queueSafePage >= queueTotalPages}
                      className="inline-flex items-center rounded-md px-1.5 py-1 text-slate-600 hover:bg-slate-200/70 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Icon icon="solar:alt-arrow-right-outline" width={14} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 识别结果预览 6 */}
        <div className="col-span-6 flex flex-col gap-6 min-h-0">
          {previewVisible ? (
            parsing ? (
              <div className="flex flex-1 min-h-0 flex-col items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="h-12 w-12 animate-spin rounded-full border-4 border-cyan-100 border-t-cyan-600" />
                <h3 className="mt-4 font-semibold text-slate-700">正在解析简历</h3>
                <p className="mt-2 text-sm text-slate-400">AI 正在提取候选人信息与经历，请稍候…</p>
              </div>
            ) : (
              <div className="flex flex-1 min-h-0 flex-col rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 flex-none">
                  <div>
                    <h2 className="font-bold text-slate-900">识别结果预览</h2>
                    <p className="mt-1 text-xs text-slate-500">已自动提取结构化信息，请补充或修正标记字段。</p>
                  </div>
                  <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                    valid ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
                  }`}>
                    <Icon icon={valid ? 'solar:check-circle-outline' : 'solar:danger-triangle-outline'} width={15} />
                    {valid ? '校验通过' : '请补全必填字段'}
                  </span>
                </div>
                <div className="flex-1 min-h-0 overflow-y-auto">
                  <div className="grid grid-cols-2 gap-5 p-6 content-start">
                  <label className="text-sm font-medium text-slate-700">
                    候选人姓名
                    <input value={name} onChange={(e) => { setName(e.target.value); setDirty(true) }} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                  </label>
                  <label className="text-sm font-medium text-slate-700">
                    联系电话
                    <input value={phone} onChange={(e) => { setPhone(e.target.value); setDirty(true) }} placeholder="请输入联系电话" className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                  </label>
                  <label className="text-sm font-medium text-slate-700">
                    邮箱地址
                    <input value={email} onChange={(e) => { setEmail(e.target.value); setDirty(true) }} placeholder="请输入邮箱地址" className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                  </label>
                  <label className="text-sm font-medium text-slate-700">
                    工作年限
                    <input value={experience} onChange={(e) => { setExperience(e.target.value); setDirty(true) }} placeholder="如 5 年" className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-cyan-500" />
                  </label>
                </div>
                {/* 职位匹配建议列表 */}
                <div className="px-6 pb-6">
                  <div className="rounded-lg border border-slate-200 overflow-hidden">
                    <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5">
                      <h3 className="text-sm font-semibold text-slate-800">职位匹配建议</h3>
                      <span className="text-xs text-slate-400">共 {matchRows.length} 项</span>
                    </div>
                    <div>
                      <table className="w-full text-sm">
                        <thead className="bg-white text-xs text-slate-500 sticky top-0">
                          <tr>
                            <th className="px-4 py-2.5 text-left font-semibold w-36">要求项</th>
                            <th className="px-4 py-2.5 text-left font-semibold w-28">匹配建议</th>
                            <th className="px-4 py-2.5 text-left font-semibold min-w-[200px]">依据</th>
                            <th className="px-4 py-2.5 text-right font-semibold w-20">操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {matchRows.length === 0 ? (
                            <tr>
                              <td colSpan={4} className="px-4 py-8 text-center text-xs text-slate-400">
                                暂无匹配建议，完成要求项配置并解析后将在此展示
                              </td>
                            </tr>
                          ) : (
                            matchRows.map((f) => (
                              <tr key={f.id} className="border-t border-slate-100 align-top hover:bg-slate-50/70">
                                <td className="px-4 py-3 font-medium text-slate-800">{f.name}</td>
                                <td className="px-4 py-3">
                                  <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                                    f.suggestion === '满足' ? 'text-emerald-700'
                                    : f.suggestion === '不满足' ? 'text-rose-700'
                                    : 'text-amber-700'
                                  }`}>
                                    <span className={`w-2 h-2 rounded-full ${
                                      f.suggestion === '满足' ? 'bg-emerald-500'
                                      : f.suggestion === '不满足' ? 'bg-rose-500'
                                      : 'bg-amber-500'
                                    }`}></span>
                                    {f.suggestion}
                                  </span>
                                </td>
                                <td className="px-4 py-3 text-xs text-slate-500 leading-5">{f.evidence || '—'}</td>
                                <td className="px-4 py-3">
                                  <div className="flex justify-end">
                                    <button onClick={() => openFitEdit(f)} className="text-slate-400 hover:text-cyan-700" title="编辑">
                                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                                      </svg>
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
                </div>
                <div className="flex-none flex items-center justify-end border-t border-slate-200 bg-slate-50 px-6 py-4">
                  <button
                    onClick={submitImport}
                    disabled={!dirty}
                    className={`inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white bg-slate-900 hover:bg-slate-800 ${!dirty ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <Icon icon="solar:check-circle-outline" width={18} />
                    修改
                  </button>
                </div>
              </div>
            )
          ) : (
            <div className="flex flex-1 min-h-0 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white text-slate-400 shadow-sm">
                <Icon icon="solar:document-text-outline" width={28} />
              </div>
              <h3 className="mt-4 font-semibold text-slate-700">识别结果预览</h3>
              <p className="mt-2 max-w-sm text-sm text-slate-400">上传简历并完成解析后，结构化的候选人信息将在此显示，便于你核对与修正。</p>
            </div>
          )}
        </div>
      </div>

      {/* 编辑匹配建议弹窗 */}
      <Modal open={fitModalOpen} onClose={() => setFitModalOpen(false)} maxWidth="max-w-xl">
        <ModalHeader title="编辑匹配建议" subtitle={editingFit?.name} onClose={() => setFitModalOpen(false)} />
        <div className="p-6 space-y-4">
          <label className="block text-sm font-medium">
            匹配建议
            <select
              value={fitForm.suggestion}
              onChange={(e) => setFitForm((f) => ({ ...f, suggestion: e.target.value }))}
              className="mt-2 w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-cyan-500"
            >
              <option>满足</option>
              <option>不满足</option>
              <option>证据不足</option>
            </select>
          </label>
          <label className="block text-sm font-medium">
            匹配依据
            <textarea
              value={fitForm.evidence}
              onChange={(e) => setFitForm((f) => ({ ...f, evidence: e.target.value }))}
              placeholder="引用简历原文关键内容作为佐证"
              className="mt-2 w-full h-24 border border-slate-300 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-cyan-500 resize-none"
            />
          </label>
        </div>
        <div className="px-6 py-4 bg-slate-50 rounded-b-2xl flex justify-end gap-3">
          <button onClick={() => setFitModalOpen(false)} className="px-4 py-2.5 rounded-lg border border-slate-300 text-sm font-medium hover:bg-slate-100">取消</button>
          <button onClick={saveFit} className="px-4 py-2.5 rounded-lg bg-slate-900 text-white text-sm font-medium">保存</button>
        </div>
      </Modal>
    </section>
  )
}
