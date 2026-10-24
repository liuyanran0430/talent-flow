import { createContext, useCallback, useContext, useRef, useState } from 'react'
import Icon from '../components/Icon'
import { logger } from '../utils/logger'

const AppContext = createContext(null)

export const SECTIONS = [
  { key: 'jobs', label: '职位管理', icon: 'solar:case-round-outline' },
  { key: 'requirements', label: '职位要求配置', icon: 'solar:clipboard-list-outline' },
  { key: 'import', label: '导入简历', icon: 'solar:upload-outline' },
  { key: 'candidates', label: '候选人管理', icon: 'solar:document-text-outline' },
  { key: 'report', label: '职位匹配看板', icon: 'solar:chart-square-outline' },
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

  const navigate = useCallback((key, payload) => {
    setSection(key)
    setSelectedJob(payload ?? null)
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
