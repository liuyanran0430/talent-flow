import Icon from './Icon'
import { SECTIONS, useApp } from '../context/AppContext'

export default function Header() {
  const { section } = useApp()
  const current = SECTIONS.find((s) => s.key === section)

  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8">
      <div className="flex items-center gap-2 text-sm text-slate-500">
        <span>招聘配置</span>
        <Icon icon="solar:alt-arrow-right-outline" width={14} />
        <span className="text-slate-800 font-medium">{current?.label}</span>
      </div>
      <div className="flex items-center gap-5">
        <button className="relative text-slate-500 hover:text-slate-800">
          <Icon icon="solar:bell-outline" width={21} />
          <span className="absolute -top-1 -right-1 w-2 h-2 bg-rose-500 rounded-full border border-white"></span>
        </button>
        <div className="h-7 w-px bg-slate-200"></div>
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 text-white flex items-center justify-center text-xs font-bold">
            林
          </div>
          <span className="text-sm font-medium">林婧</span>
          <Icon icon="solar:alt-arrow-down-outline" width={14} className="text-slate-400" />
        </div>
      </div>
    </header>
  )
}
