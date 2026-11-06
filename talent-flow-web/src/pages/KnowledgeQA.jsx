import { useEffect, useRef, useState } from 'react'
import Icon from '../components/Icon'
import Modal, { ModalHeader } from '../components/Modal'
import { useApp } from '../context/AppContext'
import { API_BASE, apiFetch, pollTask } from '../utils/api'
import { clearActiveRequestId, setActiveRequestId } from '../utils/requestContext'

/**
 * 招聘知识问答页（单栏对话式）
 *
 * 会话与追问上下文仅保存在前端内存：pending_intent 随下一条请求回传，
 * 刷新页面即开始新会话。问题分类、检索、生成与校验全部由后端完成。
 */

const QUICK_QUESTIONS = [
  '大模型应用工程师岗位的必须项有哪些？',
  '面试评价等级怎么划分？',
  '候选人四种状态分别是什么意思？',
  '简历解析失败了怎么办？',
]

function newSessionId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function candidateLabel(candidate) {
  return [candidate.department_name, candidate.job_name].filter(Boolean).join(' / ')
}

function FixedBubble({ message }) {
  const options = message.pendingIntent?.candidates || []
  return (
    <div className="space-y-3">
      <p className="text-sm leading-6 text-slate-700">{message.answer?.answer}</p>
      {options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((c) => (
            <button
              key={`${c.job_id}-${candidateLabel(c)}`}
              onClick={() => message.onPickOption?.(candidateLabel(c))}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:border-cyan-200 hover:bg-cyan-50"
            >
              {candidateLabel(c)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function AnswerCard({ message, onCitationClick }) {
  const answer = message.answer || {}
  const citations = answer.citations || []
  return (
    <div className="space-y-3">
      {message.job && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
            {message.job.department_name}
          </span>
          <span className="font-medium text-slate-800">{message.job.job_name}</span>
          <span className="text-slate-400">职位要求 {message.job.requirements?.length || 0} 条</span>
        </div>
      )}
      <div>
        <div className="mb-1.5 text-xs font-semibold text-cyan-700">结论</div>
        <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{answer.answer}</p>
      </div>
      {citations.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-semibold text-cyan-700">依据</div>
          <div className="flex flex-wrap gap-2">
            {citations.map((c) => (
              <button
                key={c.source_id}
                onClick={() => onCitationClick(c)}
                title={`${c.document_name} · ${c.segment_id}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:border-cyan-200 hover:bg-cyan-50"
              >
                <Icon icon="solar:book-2-outline" width={14} className="text-slate-400" />
                <span className="font-medium text-slate-800">{c.source_id}</span>
                <span className="text-slate-400">·</span>
                <span>{c.document_name}</span>
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">
                  {c.segment_id}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
      {answer.notice && (
        <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">
          <Icon icon="solar:lightbulb-outline" width={14} className="inline mr-1" />
          {answer.notice}
        </div>
      )}
      {!answer.grounded && (
        <div className="rounded-lg bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-600">
          <Icon icon="solar:danger-triangle-outline" width={14} className="inline mr-1" />
          回答可能含非制度内容，请以引用依据为准
        </div>
      )}
    </div>
  )
}

export default function KnowledgeQA() {
  const { showToast, navigate, selectedJob } = useApp()
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [pendingIntent, setPendingIntent] = useState(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const sessionIdRef = useRef(newSessionId())
  const listRef = useRef(null)
  const requestIdRef = useRef(null)

  // 新消息或思考态变化时滚动到底部
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [messages, thinking])

  const buildHistory = () => {
    const items = []
    for (const message of messages) {
      if (message.role === 'user') {
        items.push({ question: message.text, answer: '' })
      } else if (message.role === 'assistant' && items.length) {
        items[items.length - 1].answer = message.answer?.answer || ''
      }
    }
    return items.slice(-8) // 与后端 QA_MAX_HISTORY_TURNS 对齐，超出的由后端截断/摘要
  }

  const ask = async (text) => {
    const question = (text ?? input).trim()
    if (!question || thinking) return
    const userMessage = { id: `u-${Date.now()}`, role: 'user', text: question }
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setThinking(true)
    let requestId = null
    try {
      const res = await apiFetch(`${API_BASE}/qa/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          session_id: sessionIdRef.current,
          history: buildHistory(),
          pending_intent: pendingIntent,
        }),
      })
      const json = await res.json()
      if (!res.ok || json.code !== 0) throw new Error(json.message || '提问失败')
      requestId = json.data?.request_id
      if (!requestId) throw new Error('未返回任务标识')
      requestIdRef.current = requestId
      setActiveRequestId(requestId)
      const task = await pollTask(requestId, { interval: 1500, timeout: 90000 })
      const data = task.result || {}
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          category: data.category,
          hit: Boolean(data.hit),
          answer: data.answer || {},
          job: data.job || null,
          pendingIntent: data.pending_intent || null,
        },
      ])
      setPendingIntent(data.pending_intent || null)
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          role: 'assistant',
          answer: {
            answer: `暂时无法完成本次请求：${e.message}`,
            answerable: false,
            citations: [],
            grounded: true,
          },
          pendingIntent: null,
        },
      ])
      showToast(`问答失败：${e.message}`, 'error')
    } finally {
      clearActiveRequestId(requestId)
      requestIdRef.current = null
      setThinking(false)
    }
  }

  const pickOption = (option) => {
    setInput(option)
  }

  const handleCitationClick = (citation) => {
    // 岗位分支：跳转职位要求配置；制度分支：展示文档与片段信息
    if (citation.segment_id?.startsWith('REQ-') || citation.document_id?.startsWith('JOB-')) {
      const jobId = Number(String(citation.document_id).replace('JOB-', ''))
      if (jobId) {
        navigate('requirements', { id: jobId, name: citation.document_name })
        return
      }
    }
    showToast(`${citation.document_name} · ${citation.document_id} · ${citation.segment_id}`)
  }

  const resetSession = () => {
    setConfirmOpen(false)
    if (requestIdRef.current) clearActiveRequestId(requestIdRef.current)
    setThinking(false)
    setMessages([])
    setInput('')
    setPendingIntent(null)
    sessionIdRef.current = newSessionId()
    showToast('已开启新的对话')
  }

  return (
    <section className="p-4 md:p-8 max-w-[1440px] mx-auto">
      {/* 对话区：内容占满页面，新建对话为右上角悬浮按钮 */}
      <div className="relative rounded-xl border border-slate-200 bg-white shadow-sm flex flex-col h-[calc(100vh-5.5rem)] md:h-[calc(100vh-8rem)] min-h-[440px]">
        <button
          onClick={() => setConfirmOpen(true)}
          title="新建对话"
          aria-label="新建对话"
          className="absolute right-3 top-3 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-slate-300 bg-white/95 text-slate-600 shadow-sm hover:bg-slate-50 hover:text-slate-900"
        >
          <Icon icon="solar:add-circle-outline" width={18} />
        </button>

        <div ref={listRef} className="flex-1 overflow-y-auto px-4 pb-4 pt-14 space-y-4">
          {messages.length === 0 && !thinking ? (
            <div>
              <div className="rounded-2xl rounded-tl-sm bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                您好，我可以回答招聘制度相关问题：岗位要求、面试评价、流程规则与系统操作等。
                答案会附带知识来源，检索不到依据时不会臆测。
              </div>
              <div className="mt-5 text-xs font-medium text-slate-500">可以这样问</div>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {QUICK_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    onClick={() => ask(question)}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-left text-sm text-slate-700 hover:border-cyan-200 hover:bg-cyan-50"
                  >
                    <Icon
                      icon="solar:magic-stick-3-outline"
                      width={15}
                      className="mr-1.5 text-cyan-600"
                    />
                    {question}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) =>
              message.role === 'user' ? (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-slate-900 px-4 py-2.5 text-sm leading-6 text-white">
                    {message.text}
                  </div>
                </div>
              ) : (
                <div key={message.id} className="flex justify-start">
                  <div className="max-w-[92%] rounded-2xl rounded-tl-sm border border-slate-200 bg-slate-50 px-4 py-3">
                    {message.category === 'out_of_scope' || message.category === 'ambiguous' ? (
                      <FixedBubble
                        message={{ ...message, onPickOption: pickOption }}
                      />
                    ) : (
                      <AnswerCard message={message} onCitationClick={handleCitationClick} />
                    )}
                  </div>
                </div>
              ),
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
                正在检索制度并生成回答…
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 p-3 md:p-4">
          <div className="flex items-end gap-2">
            <textarea
              rows={1}
              value={input}
              disabled={thinking}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  ask()
                }
              }}
              placeholder="输入招聘制度相关问题，Enter 发送 / Shift+Enter 换行"
              className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-xs leading-5 outline-none placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100 disabled:bg-slate-50 disabled:text-slate-400"
            />
            <button
              onClick={() => ask()}
              disabled={thinking || !input.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Icon icon="solar:send-rounded" width={17} />
              发送
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            回答由知识库生成，涉及能力判定与流程裁决请以已发布标准或最新制度文件为准。
          </p>
        </div>
      </div>

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <ModalHeader
          title="新建对话"
          subtitle="将清空当前对话与追问上下文"
          onClose={() => setConfirmOpen(false)}
        />
        <div className="px-6 py-5 text-sm leading-6 text-slate-600">
          当前对话记录与追问上下文只保存在本页内存，新建对话后无法恢复。确认开始新的对话？
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-6 py-4">
          <button
            onClick={() => setConfirmOpen(false)}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            onClick={resetSession}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            确认新建
          </button>
        </div>
      </Modal>
    </section>
  )
}
