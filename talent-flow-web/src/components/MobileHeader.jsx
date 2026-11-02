import Icon from './Icon'
import { SECTIONS, useApp } from '../context/AppContext'

/** 移动端顶部栏：汉堡按钮打开侧栏抽屉；桌面端隐藏（md:hidden） */
export default function MobileHeader() {
  const { section, openDrawer } = useApp()
  const current = SECTIONS.find((s) => s.key === section)

  return (
    <header className="md:hidden sticky top-0 z-20 h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4">
      <div className="flex items-center gap-3">
        <button
          onClick={openDrawer}
          className="text-slate-600 hover:text-slate-900 -ml-1 p-1"
          aria-label="打开导航菜单"
        >
          <Icon icon="solar:hamburger-menu-outline" width={22} />
        </button>
        <span className="text-sm font-semibold text-slate-800">{current?.label || 'TalentFlow'}</span>
      </div>
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 text-white flex items-center justify-center text-xs font-bold">
        林
      </div>
    </header>
  )
}
