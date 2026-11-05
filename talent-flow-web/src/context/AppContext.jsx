import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import Icon from '../components/Icon'
import { logger } from '../utils/logger'

const AppContext = createContext(null)

export const SECTIONS = [
  { key: 'jobs', label: '职位管理', icon: 'solar:case-round-outline' },
  { key: 'requirements', label: '职位要求配置', icon: 'solar:clipboard-list-outline' },
  { key: 'import', label: '导入简历', icon: 'solar:upload-outline' },
  { key: 'candidates', label: '候选人管理', icon: 'solar:document-text-outline' },
  { key: 'report', label: '职位匹配看板', icon: 'solar:chart-square-outline' },
  { key: 'qa', label: '招聘知识问答', icon: 'solar:question-circle-outline' },
]

function Toast({ text, visible }) {
  return (
    <div
      className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-50 rounded-xl bg-slate-900 text-white px-4 py-3 text-sm shadow-xl items-center gap-2 ${
        visible ? 'flex' : 'hidden'
      }`}
    >
      <Icon icon="solar:check-circle-bold" width={18} className="text-emerald-400" />
      <span>{text}</span>
    </div>
  )
}

export function AppProvider({ children }) {
  const [section, setSection] = useState('jobs')
  const [selectedJob, setSelectedJob] = useState(null)
  const [toast, setToast] = useState({ visible: false, text: '' })
  const toastTimer = useRef(null)
  // 导入简历页的导入队列与选中候选人：提升到全局，切换页面不丢失
  const [importQueue, setImportQueue] = useState([])
  const [importSelected, setImportSelected] = useState(null)
  const [importPreviewVisible, setImportPreviewVisible] = useState(false)
  // 导入简历页上方选择的部门与职位：同样持久化
  const [importDeptId, setImportDeptId] = useState('')
  const [importJobId, setImportJobId] = useState('')
  // 移动端侧栏抽屉开合状态
  const [drawerOpen, setDrawerOpen] = useState(false)
  const openDrawer = useCallback(() => setDrawerOpen(true), [])
  const closeDrawer = useCallback(() => setDrawerOpen(false), [])

  // 抽屉开启时锁定 body 滚动，防止穿透滚动
  useEffect(() => {
    if (!drawerOpen) return
    document.body.classList.add('overflow-hidden')
    return () => document.body.classList.remove('overflow-hidden')
  }, [drawerOpen])

  // 同步当前区块到全局，供 logger 上报 page 字段
  useEffect(() => {
    window.__TALENT_SECTION__ = section
  }, [section])

  const navigate = useCallback((key, payload) => {
    // 页面切换记录到前端日志（仅 info，不上报），配合后端 rid 还原用户操作路径
    logger.info('nav', '进入页面', key)
    setSection(key)
    setSelectedJob(payload ?? null)
    setDrawerOpen(false) // 跳转后自动收起移动端抽屉
  }, [])

  const showToast = useCallback((text, level = 'info') => {
    // 失败类提示联动日志：error/warn 级别自动记录并上报后端
    if (level === 'error') logger.error('toast', text)
    else if (level === 'warn') logger.warn('toast', text)
    setToast({ visible: true, text })
    clearTimeout(toastTimer.current)
    toastTimer.current = setTimeout(() => {
      setToast((t) => ({ ...t, visible: false }))
    }, 2600)
  }, [])

  return (
    <AppContext.Provider
      value={{
        section,
        navigate,
        selectedJob,
        showToast,
        importQueue,
        setImportQueue,
        importSelected,
        setImportSelected,
        importPreviewVisible,
        setImportPreviewVisible,
        importDeptId,
        setImportDeptId,
        importJobId,
        setImportJobId,
        drawerOpen,
        openDrawer,
        closeDrawer,
      }}
    >
      {children}
      <Toast text={toast.text} visible={toast.visible} />
    </AppContext.Provider>
  )
}

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
