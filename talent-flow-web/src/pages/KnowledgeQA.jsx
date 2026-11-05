import { useEffect, useRef, useState } from 'react'
import Icon from '../components/Icon'
import { useApp } from '../context/AppContext'

/**
 * 招聘知识问答页（静态骨架）
 *
 * 当前为纯前端演示版本：问答内容来自本地模拟数据，尚未接入后端知识检索接口。
 * 页面为单栏对话式结构，不做知识领域分类；问题分类与检索由后端负责。
 */

const QUICK_QUESTIONS = [
  { text: '大模型应用工程师岗位的必须项有哪些？', answerKey: 'standard' },
  { text: '面试评价等级怎么划分？', answerKey: 'interview' },
  { text: '候选人四种状态分别是什么意思？', answerKey: 'stage' },
  { text: '简历解析失败了怎么办？', answerKey: 'faq' },
]

// 自由输入时按关键字粗分，仅用于静态演示；真实实现由后端分类器判定
const KEYWORD_RULES = [
  { key: 'interview', words: ['面试', '评价', '打分', '评语', '等级'] },
  { key: 'stage', words: ['状态', '阶段', '流程', '流转', '重算', 'pending', 'finish'] },
  { key: 'standard', words: ['岗位', '必须项', '能力', '判定', '标准', '要求项'] },
  { key: 'faq', words: ['上传', '删除', '重复', '简历', '查重', '系统'] },
]

// 模拟答案：真实实现时应由后端检索知识库生成，并按引用编号返回来源
const ANSWERS = {
  standard: {
    conclusion:
      '以「大模型应用工程师」为例，必须项通常包含 3 条：Python 开发经验、RAG 原理、Agent 项目经验。判定以已发布的组织标准为准，未关联标准的要求项按 JD 原文判定。',
    citations: [
      { code: 'S1', title: 'RAG 原理', status: '已发布' },
      { code: 'S2', title: 'Python 开发经验', status: '已发布' },
      { code: 'S3', title: 'Agent 项目经验', status: '未关联标准' },
    ],
    caveat: '判定口径以已发布标准为准；如需调整口径请联系岗位负责人更新标准条目。',
  },
  stage: {
    conclusion:
      '候选人状态共 4 种：pending（待解析）、processing（解析中）、review（待 HR 复核确认）、finish（已确认终态）。解析失败不单独设状态，失败原因记录在简历信息中并停留在 review。',
    citations: [
      { code: 'S1', title: '候选人状态机', status: '现行制度 1.0' },
      { code: 'S2', title: '解析失败处理', status: '现行制度 1.0' },
    ],
    caveat: 'processing 超过 3 分钟未完成会判定为僵死并允许重新触发；该规则可能随版本调整。',
  },
  interview: {
    conclusion:
      '面试评价按维度打分并给出等级结论，评语需引用简历或面试记录中的具体事实。无法给出事实依据的结论应标记为「证据不足」，不允许凭印象给结论。',
    citations: [
      { code: 'S1', title: '等级定义', status: '现行制度 1.0' },
      { code: 'S2', title: '证据记录要求', status: '现行制度 1.0' },
    ],
    caveat: '本回答来源为人工维护的制度手册，如与实际执行版本不一致以最新制度文件为准。',
  },
  faq: {
    conclusion:
      '同一份简历重复上传时会命中内容查重，系统返回已存在的候选人，不会重复入库；删除候选人会级联清理其简历、匹配建议与打分记录，简历文件也会一并删除。',
    citations: [
      { code: 'S1', title: '重复上传查重', status: '现行制度 1.0' },
      { code: 'S2', title: '删除候选人的影响范围', status: '现行制度 1.0' },
    ],
    caveat: '删除操作不可恢复，执行前请确认候选人不再需要留档。',
  },
  fallback: {
    conclusion:
      '当前为静态演示版本，尚未接入知识库检索。真实版本会自动识别问题所属制度并检索对应片段，信息不足时会先追问澄清，检索不到依据时不会臆测。',
    citations: [{ code: 'S1', title: '待接入知识库', status: '演示' }],
    caveat: '接入后端后，本回答将由检索到的制度片段生成，并标注来源。',
  },
}

function resolveAnswer(question, answerKey) {
  if (answerKey && ANSWERS[answerKey]) return ANSWERS[answerKey]
  const text = question.toLowerCase()
  const hit = KEYWORD_RULES.find((rule) => rule.words.some((w) => text.includes(w.toLowerCase())))
  return ANSWERS[hit?.key || 'fallback']
}

function AnswerCard({ answer }) {
  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1.5 text-xs font-semibold text-cyan-700">结论</div>
        <p className="text-sm leading-6 text-slate-700">{answer.conclusion}</p>
      </div>
      <div>
        <div className="mb-1.5 text-xs font-semibold text-cyan-700">依据</div>
        <div className="flex flex-wrap gap-2">
          {answer.citations.map((c) => (
            <span
              key={c.code}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600"
            >
              <Icon icon="solar:book-2-outline" width={14} className="text-slate-400" />
              <span className="font-medium text-slate-800">{c.code}</span>
              <span className="text-slate-400">·</span>
              <span>{c.title}</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                {c.status}
              </span>
            </span>
          ))}
        </div>
      </div>
      <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">
        <Icon icon="solar:lightbulb-outline" width={14} className="inline mr-1" />
        {answer.caveat}
      </div>
    </div>
  )
}

export default function KnowledgeQA() {
  const { showToast } = useApp()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const listRef = useRef(null)
  const timerRef = useRef(null)

  // 卸载时清理模拟请求定时器，避免更新已卸载组件
  useEffect(() => () => clearTimeout(timerRef.current), [])

  // 新消息或思考态变化时滚动到底部
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, thinking])

  const ask = (text, answerKey) => {
    const question = (text ?? input).trim()
    if (!question || thinking) return
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: 'user', text: question }])
    setInput('')
    setThinking(true)
    // 静态骨架：用固定延时模拟检索与生成过程
    timerRef.current = setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: 'assistant', answer: resolveAnswer(question, answerKey) },
      ])
      setThinking(false)
    }, 700)
  }

  const resetSession = () => {
    clearTimeout(timerRef.current)
    setThinking(false)
    setMessages([])
    setInput('')
    showToast('已开启新的对话')
  }

  return (
    <section className="p-4 md:p-8 max-w-[1440px] mx-auto">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900">招聘知识问答</h1>
          <p className="mt-2 text-sm text-slate-500">
            面向 HR 与业务招聘人员，答案附带知识来源依据。
          </p>
        </div>
        <button
          onClick={resetSession}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <Icon icon="solar:add-circle-outline" width={18} />新建对话
        </button>
      </div>

      {/* 对话区 */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-[calc(100vh-16rem)] min-h-[440px]">
        <div className="flex items-center gap-2 border-b border-slate-200 px-4 py-3">
          <Icon icon="solar:book-2-outline" width={18} className="text-cyan-600" />
          <span className="text-sm font-medium text-slate-800">招聘制度问答</span>
          <span className="ml-auto text-xs text-slate-400">答案附带来源</span>
        </div>

        <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && !thinking ? (
            <div>
              <div className="rounded-2xl rounded-tl-sm bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                您好，我可以回答招聘制度相关问题：岗位要求、面试评价、流程规则与系统操作等。
                答案会附带知识来源，检索不到依据时不会臆测。
              </div>
              <div className="mt-5 text-xs font-medium text-slate-500">可以这样问</div>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {QUICK_QUESTIONS.map((q) => (
                  <button
                    key={q.text}
                    onClick={() => ask(q.text, q.answerKey)}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-left text-sm text-slate-700 hover:border-cyan-200 hover:bg-cyan-50"
                  >
                    <Icon
                      icon="solar:magic-stick-3-outline"
                      width={15}
                      className="mr-1.5 text-cyan-600"
                    />
                    {q.text}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m) =>
              m.role === 'user' ? (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-slate-900 px-4 py-2.5 text-sm leading-6 text-white">
                    {m.text}
                  </div>
                </div>
              ) : (
                <div key={m.id} className="flex justify-start">
                  <div className="max-w-[92%] rounded-2xl rounded-tl-sm border border-slate-200 bg-slate-50 px-4 py-3">
                    <AnswerCard answer={m.answer} />
                  </div>
                </div>
              )
            )
          )}

          {thinking && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-tl-sm bg-slate-50 px-4 py-3 text-sm text-slate-500">
                <Icon
                  icon="solar:refresh-circle-outline"
                  width={16}
                  className="mr-1.5 inline animate-spin"
                />
                正在检索知识并生成回答…
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 p-3 md:p-4">
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  ask()
                }
              }}
              placeholder="输入招聘制度相关问题，Enter 发送 / Shift+Enter 换行"
              className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2.5 text-sm leading-6 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            />
            <button
              onClick={() => ask()}
              disabled={thinking || !input.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Icon icon="solar:send-rounded" width={17} />发送
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            回答由知识库生成，涉及能力判定与流程裁决请以已发布标准或最新制度文件为准。
          </p>
        </div>
      </div>
    </section>
  )
}
