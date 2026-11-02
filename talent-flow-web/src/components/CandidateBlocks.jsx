import Icon from './Icon'

const SUGGESTION_CLS = {
  满足: 'border-emerald-200 text-emerald-700',
  不满足: 'border-rose-200 text-rose-700',
  证据不足: 'border-amber-200 text-amber-700',
}

/**
 * 职位匹配建议表（公共展示）
 * fits: [{ id, name, suggestion, evidence }]
 * onChangeSuggestion(fitId, value)：改下拉回调（可选，不传则只读）
 * loading / 空态由外部或内部处理
 */
export function JobfitTable({ fits, onChangeSuggestion, loading = false, dense = false }) {
  if (loading) return <p className="mt-2 text-sm text-slate-400">加载匹配建议中…</p>
  const cellPad = dense ? 'px-3 py-2' : 'px-4 py-3'
  const headPad = dense ? 'px-3 py-2' : 'px-4 py-2.5'
  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5">
        <h3 className="text-sm font-semibold text-slate-800">职位匹配建议</h3>
        <span className="text-xs text-slate-400">共 {fits.length} 项</span>
      </div>
      {fits.length === 0 ? (
        <p className="px-4 py-8 text-center text-xs text-slate-400">暂无匹配建议数据</p>
      ) : (
        <>
          {/* 桌面端：表格 */}
          <table className="hidden md:table w-full text-sm">
            <thead className="bg-white text-xs text-slate-500">
              <tr>
                <th className={`${headPad} text-left font-semibold w-36`}>要求项</th>
                <th className={`${headPad} text-left font-semibold w-36`}>匹配建议</th>
                <th className={`${headPad} text-left font-semibold min-w-[200px]`}>依据</th>
              </tr>
            </thead>
            <tbody>
              {fits.map((f) => (
                <tr key={f.id} className="border-t border-slate-100 align-top hover:bg-slate-50/70">
                  <td className={`${cellPad} font-medium text-slate-800`}>{f.name}</td>
                  <td className={cellPad}>
                    {onChangeSuggestion ? (
                      <select
                        value={f.suggestion}
                        onChange={(e) => onChangeSuggestion(f.id, e.target.value)}
                        className={`rounded-md border px-2 py-1.5 text-xs font-medium outline-none focus:border-cyan-500 ${SUGGESTION_CLS[f.suggestion] || 'border-slate-200 text-slate-600'}`}
                      >
                        <option>满足</option>
                        <option>不满足</option>
                        <option>证据不足</option>
                      </select>
                    ) : (
                      <span className={`inline-flex rounded-md border px-2 py-1.5 text-xs font-medium ${SUGGESTION_CLS[f.suggestion] || 'border-slate-200 text-slate-600'}`}>
                        {f.suggestion}
                      </span>
                    )}
                  </td>
                  <td className={`${cellPad} text-xs text-slate-500 leading-5`}>
                    {f.evidence || <span className="text-slate-300">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* 移动端：卡片列表 */}
          <ul className="md:hidden divide-y divide-slate-100">
            {fits.map((f) => (
              <li key={f.id} className="px-4 py-3 space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <span className="text-sm font-medium text-slate-800 min-w-0">{f.name}</span>
                  {onChangeSuggestion ? (
                    <select
                      value={f.suggestion}
                      onChange={(e) => onChangeSuggestion(f.id, e.target.value)}
                      className={`flex-none rounded-md border px-2 py-1.5 text-xs font-medium outline-none focus:border-cyan-500 ${SUGGESTION_CLS[f.suggestion] || 'border-slate-200 text-slate-600'}`}
                    >
                      <option>满足</option>
                      <option>不满足</option>
                      <option>证据不足</option>
                    </select>
                  ) : (
                    <span className={`flex-none inline-flex rounded-md border px-2 py-1.5 text-xs font-medium ${SUGGESTION_CLS[f.suggestion] || 'border-slate-200 text-slate-600'}`}>
                      {f.suggestion}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 leading-5">
                  {f.evidence || <span className="text-slate-300">—</span>}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

/**
 * AI 整体分析（公共展示）：候选人优势 + 需关注风险
 * candidate: { advantages: [{point,evidence}], risks: [{point,evidence}] }
 * 无数据时显示占位
 */
export function AiAnalysisBlock({ candidate, compact = false }) {
  const advs = candidate?.advantages || []
  const rks = candidate?.risks || []
  const textCls = compact ? 'text-[11px] leading-4' : 'text-xs'
  const cardPad = compact ? 'p-3' : 'p-4'
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Icon icon="solar:stars-outline" width={15} className="text-cyan-600" />
        <h3 className="text-sm font-semibold text-slate-800">AI 整体分析</h3>
      </div>
      {advs.length === 0 && rks.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-xs text-slate-400">
          暂无 AI 整体分析，解析完成且提取到候选人优势或风险后将在此显示
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          {/* 优势 */}
          <div className={`rounded-lg border border-emerald-200 bg-emerald-50/50 ${cardPad}`}>
            <div className="flex items-center gap-2 mb-1.5">
              <Icon icon="solar:medal-star-outline" width={14} className="text-emerald-600" />
              <span className="text-xs font-semibold text-emerald-800">候选人优势</span>
              <span className="text-[11px] text-emerald-600">（{advs.length}）</span>
            </div>
            {advs.length === 0 ? (
              <p className="text-[11px] text-slate-400">暂无优势项（无充分证据时优势不输出）</p>
            ) : (
              <ul className="space-y-1.5">
                {advs.map((a, i) => (
                  <li key={i} className={textCls}>
                    <div className="flex items-start gap-1.5">
                      <span className="text-emerald-600 mt-0.5">✓</span>
                      <span className="font-medium text-emerald-900">{a.point}</span>
                    </div>
                    <div className="ml-4 mt-0.5 text-slate-500">证据：{a.evidence}</div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {/* 风险 */}
          <div className={`rounded-lg border border-rose-200 bg-rose-50/50 ${cardPad}`}>
            <div className="flex items-center gap-2 mb-1.5">
              <Icon icon="solar:danger-triangle-outline" width={14} className="text-rose-600" />
              <span className="text-xs font-semibold text-rose-800">需关注风险</span>
              <span className="text-[11px] text-rose-600">（{rks.length}）</span>
            </div>
            {rks.length === 0 ? (
              <p className="text-[11px] text-slate-400">暂无需关注的风险</p>
            ) : (
              <ul className="space-y-1.5">
                {rks.map((r, i) => (
                  <li key={i} className={textCls}>
                    <div className="flex items-start gap-1.5">
                      <span className="text-rose-500 mt-0.5">⚠</span>
                      <span className="font-medium text-rose-900">{r.point}</span>
                    </div>
                    {r.evidence && <div className="ml-4 mt-0.5 text-slate-500">证据：{r.evidence}</div>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
