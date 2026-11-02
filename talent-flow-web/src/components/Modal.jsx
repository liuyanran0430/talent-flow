import Icon from './Icon'

/**
 * 通用弹窗外壳，对齐原型中 fixed inset-0 遮罩 + 居中卡片的样式。
 */
export default function Modal({ open, onClose, children, maxWidth = 'max-w-lg', z = 'z-30' }) {
  if (!open) return null
  return (
    <div className={`fixed inset-0 ${z} bg-slate-950/45 flex items-stretch md:items-center justify-center p-0 md:p-5`}>
      {/* 移动端全屏弹框，桌面端保持居中卡片 */}
      <div className={`w-full ${maxWidth} rounded-none md:rounded-2xl bg-white shadow-2xl h-full md:h-auto max-h-full md:max-h-[90vh] overflow-y-auto`}>{children}</div>
    </div>
  )
}

export function ModalHeader({ title, subtitle, onClose }) {
  return (
    <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5">
      <div>
        <h2 className="text-lg font-bold">{title}</h2>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      <button className="text-slate-400 hover:text-slate-700" onClick={onClose}>
        <Icon icon="solar:close-circle-outline" width={22} />
      </button>
    </div>
  )
}
