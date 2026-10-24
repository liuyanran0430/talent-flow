import Icon from './Icon'
import { SECTIONS, useApp } from '../context/AppContext'

export default function Sidebar() {
  const { section, navigate } = useApp()

  return (
    <aside className="w-64 flex-none bg-slate-950 text-slate-300 px-4 py-5 flex flex-col">
      <div className="flex items-center gap-3 px-2 pb-7 border-b border-slate-800">
        <div className="w-10 h-10 rounded-xl bg-cyan-500 text-slate-950 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Icon icon="solar:users-group-rounded-bold" width={23} />
        </div>
        <div>
          <div className="font-bold text-white">TalentFlow</div>
          <div className="text-xs text-slate-500 mt-0.5">智能招聘中台</div>
        </div>
      </div>

      <nav className="pt-6 space-y-1 text-sm">
        {SECTIONS.map((s) => {
          const active = section === s.key
          return (
            <button
              key={s.key}
              onClick={() => navigate(s.key)}
              className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-left ${
                active
                  ? 'bg-cyan-500/15 text-cyan-300 font-medium'
                  : 'hover:bg-slate-900'
              }`}
            >
              <Icon icon={s.icon} width={19} />
              {s.label}
            </button>
          )
        })}
      </nav>
    </aside>
  )
}
