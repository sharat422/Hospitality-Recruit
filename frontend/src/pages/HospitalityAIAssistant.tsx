import { Bot,Database,Send,ShieldCheck,Sparkles } from 'lucide-react'
import { useMemo,useState } from 'react'
import apiClient from '../lib/api'
import { useProperty } from '../lib/PropertyContext'

const EXAMPLES = [
  'Why did housekeeping attrition increase?',
  'Which property has the highest overtime?',
  'Which jobs are hardest to fill?',
  'Who are the highest-risk employees?',
  'What vacancies have been open for more than 30 days?',
  "Show this month's recruitment performance.",
]

interface Source { table: string; description: string; rowCount: number }
interface AssistantResponse {
  conversationId: string
  message: { content: string; tool_name: string; sources: Source[]; metrics: Record<string, unknown>; filters: Record<string, unknown>; generated_by: string }
  rows: Record<string, unknown>[]
  methodology: string
  readOnly: boolean
}

interface ChatItem { role: 'USER' | 'ASSISTANT'; content: string; response?: AssistantResponse }

function displayMetric(value: unknown): string {
  if (value === null || value === undefined) return 'Not available'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export default function HospitalityAIAssistant() {
  const { properties, activeProperty } = useProperty()
  const [question, setQuestion] = useState('')
  const [propertyId, setPropertyId] = useState(activeProperty?.id ?? '')
  const [periodDays, setPeriodDays] = useState(30)
  const [conversationId, setConversationId] = useState<string>()
  const [messages, setMessages] = useState<ChatItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const selectedProperty = useMemo(() => properties.find(item => item.id === propertyId), [properties, propertyId])

  const ask = async (text = question) => {
    const clean = text.trim()
    if (clean.length < 3 || loading) return
    setMessages(items => [...items, { role: 'USER', content: clean }])
    setQuestion(''); setLoading(true); setError('')
    try {
      const { data } = await apiClient.post<AssistantResponse>('/assistant/ask', {
        question: clean, conversation_id: conversationId,
        property_id: propertyId || null, period_days: periodDays,
      })
      setConversationId(data.conversationId)
      setMessages(items => [...items, { role: 'ASSISTANT', content: data.message.content, response: data }])
    } catch (err: any) {
      const detail = err.response?.data?.detail
      setError(typeof detail === 'string' ? detail : detail?.message ?? 'The assistant could not retrieve verified data.')
    } finally { setLoading(false) }
  }

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col">
      <header className="border-b border-gray-200 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900"><Bot className="h-6 w-6 text-purple-600" />Hospitality AI Assistant</h1>
            <p className="mt-1 text-sm text-gray-600">Read-only answers from authorized workforce and recruitment data.</p>
          </div>
          <span className="flex items-center gap-1 rounded bg-green-50 px-2 py-1 text-xs font-medium text-green-800"><ShieldCheck className="h-4 w-4" />RBAC and property scoped</span>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-medium text-gray-600">Property scope
            <select value={propertyId} onChange={event => setPropertyId(event.target.value)} className="mt-1 h-11 w-full rounded-md border border-gray-300 bg-white px-3 text-sm">
              <option value="">All authorized properties</option>
              {properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}
            </select>
          </label>
          <label className="text-xs font-medium text-gray-600">Analysis period
            <select value={periodDays} onChange={event => setPeriodDays(Number(event.target.value))} className="mt-1 h-11 w-full rounded-md border border-gray-300 bg-white px-3 text-sm">
              <option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={180}>Last 180 days</option><option value={365}>Last 365 days</option>
            </select>
          </label>
        </div>
      </header>

      <div className="flex-1 space-y-5 py-5">
        {messages.length === 0 && (
          <section>
            <h2 className="text-sm font-semibold text-gray-800">Questions you can ask</h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {EXAMPLES.map(example => <button key={example} onClick={() => void ask(example)} className="min-h-12 rounded-md border border-gray-200 bg-white px-4 py-3 text-left text-sm text-gray-700 hover:border-purple-300 hover:bg-purple-50">{example}</button>)}
            </div>
          </section>
        )}
        {messages.map((item, index) => (
          <article key={index} className={item.role === 'USER' ? 'ml-auto max-w-3xl' : 'max-w-4xl'}>
            <div className={item.role === 'USER' ? 'rounded-md bg-purple-600 px-4 py-3 text-sm text-white' : 'border-l-4 border-purple-500 bg-white px-4 py-4 text-sm text-gray-800'}>
              {item.content}
            </div>
            {item.response && (
              <div className="mt-3 space-y-4 pl-4">
                <div className="flex flex-wrap gap-2 text-xs text-gray-500">
                  <span className="rounded bg-gray-100 px-2 py-1">Tool: {item.response.message.tool_name}</span>
                  <span className="rounded bg-gray-100 px-2 py-1">{item.response.message.generated_by === 'CLAUDE_NARRATIVE' ? 'Claude wording' : 'Deterministic wording'}</span>
                  <span className="rounded bg-gray-100 px-2 py-1">Scope: {selectedProperty?.name ?? 'Authorized properties'}</span>
                </div>
                <section>
                  <h3 className="text-xs font-semibold uppercase text-gray-500">Verified metrics</h3>
                  <div className="mt-2 grid gap-2 sm:grid-cols-3">
                    {Object.entries(item.response.message.metrics).map(([key, value]) => <div key={key} className="border-l-2 border-gray-200 pl-3"><p className="text-xs text-gray-500">{key.replace(/([A-Z])/g, ' $1')}</p><p className="break-words text-sm font-semibold text-gray-900">{displayMetric(value)}</p></div>)}
                  </div>
                </section>
                {item.response.rows.length > 0 && <details className="text-sm"><summary className="cursor-pointer font-medium text-purple-700">View supporting rows ({item.response.rows.length})</summary><div className="mt-2 overflow-x-auto"><table className="min-w-full divide-y divide-gray-200 text-xs"><thead><tr>{Object.keys(item.response.rows[0]).slice(0, 6).map(key => <th key={key} className="px-2 py-2 text-left font-medium text-gray-500">{key}</th>)}</tr></thead><tbody>{item.response.rows.slice(0, 20).map((row, rowIndex) => <tr key={rowIndex} className="border-b border-gray-100">{Object.keys(item.response!.rows[0]).slice(0, 6).map(key => <td key={key} className="max-w-56 break-words px-2 py-2 text-gray-700">{displayMetric(row[key])}</td>)}</tr>)}</tbody></table></div></details>}
                <section>
                  <h3 className="flex items-center gap-1 text-xs font-semibold uppercase text-gray-500"><Database className="h-3.5 w-3.5" />Data sources</h3>
                  <ul className="mt-2 space-y-1">{item.response.message.sources.map(source => <li key={source.table} className="text-xs text-gray-600"><code className="font-semibold text-gray-800">{source.table}</code> · {source.description} · {source.rowCount} rows</li>)}</ul>
                  <p className="mt-2 text-xs text-gray-500"><strong>Method:</strong> {item.response.methodology}</p>
                </section>
              </div>
            )}
          </article>
        ))}
        {loading && <div className="flex items-center gap-2 text-sm text-gray-500"><Sparkles className="h-4 w-4 animate-pulse text-purple-500" />Reading authorized application metrics…</div>}
        {error && <p className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
      </div>

      <form onSubmit={event => { event.preventDefault(); void ask() }} className="sticky bottom-0 flex gap-2 border-t border-gray-200 bg-gray-50 py-4">
        <textarea value={question} onChange={event => setQuestion(event.target.value)} rows={2} maxLength={1000} placeholder="Ask about recruitment, overtime, attrition, vacancies, or retention risk…" className="min-h-12 flex-1 resize-none rounded-md border border-gray-300 bg-white px-3 py-3 text-sm focus:border-purple-500 focus:outline-none" />
        <button disabled={loading || question.trim().length < 3} className="flex h-12 items-center gap-2 rounded-md bg-purple-600 px-4 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"><Send className="h-4 w-4" /><span className="hidden sm:inline">Ask</span></button>
      </form>
    </div>
  )
}
