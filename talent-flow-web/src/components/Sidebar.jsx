import Icon from './Icon'
import { SECTIONS, useApp } from '../context/AppContext'

export default function Sidebar() {
  const { section, navigate, drawerOpen, closeDrawer } = useApp()

  return (
    <>
      {/* 移动端抽屉遮罩：点击关闭 */}
      {drawerOpen && (
        <div className="fixed inset-0 z-30 bg-slate-950/45 md:hidden" onClick={closeDrawer} />
      )}
      {/* 移动端 fixed 抽屉（-translate-x-full 滑出/滑入），桌面端静态常显 */}
      <aside
        className={`w-72 md:w-64 flex-none bg-slate-950 text-slate-300 px-4 py-5 flex flex-col fixed inset-y-0 left-0 z-40 transition-transform duration-300 md:static md:translate-x-0 ${
          drawerOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
      <div className="flex items-center gap-3 px-2 pb-7 border-b border-slate-800">
        <div className="w-10 h-10 rounded-xl bg-cyan-500 text-slate-950 flex items-center justify-center shadow-lg shadow-cyan-500/20">
          <Icon icon="solar:users-group-rounded-bold" width={23} />
        </div>
        <div>
          <div className="font-bold text-white">TalentFlow</div>
          <div className="text-xs text-slate-500 mt-0.5">智能招聘中台</div>
        </div>
        <button onClick={closeDrawer} className="ml-auto text-slate-500 hover:text-slate-300 md:hidden" aria-label="关闭导航菜单">
          <Icon icon="solar:close-circle-outline" width={22} />
        </button>
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
    </>
  )
}
