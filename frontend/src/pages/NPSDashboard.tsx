import { apiClient } from '@/lib/api'
import { X } from 'lucide-react'
import React,{ useEffect,useState } from 'react'
import {
Bar,
BarChart,
CartesianGrid,
Line,
LineChart,
ResponsiveContainer,
Tooltip,
XAxis,YAxis,
} from 'recharts'

interface ByStage {
  stage: string
  avg_score: number
  count: number
  nps: number
}

interface WeeklyTrend {
  week: string
  nps: number
  count: number
}

interface FeedbackItem {
  stage: string
  score: number
  feedback: string
  responded_at: string
}

interface Theme {
  theme: string
  count: number
  sentiment: 'positive' | 'negative' | 'neutral'
  exampleQuotes: string[]
}

interface Analytics {
  overall_nps: number
  response_rate: number
  sent_this_month: number
  total_responded: number
  by_stage: ByStage[]
  weekly_trend: WeeklyTrend[]
  recent_feedback: FeedbackItem[]
}

const SENTIMENT_DOT: Record<string, string> = {
  positive: 'bg-green-500',
  negative: 'bg-red-500',
  neutral: 'bg-gray-400',
}

const NPS_STAGES = [
  { value: 'POST_APPLICATION', label: 'Post-Application' },
  { value: 'POST_INTERVIEW', label: 'Post-Interview' },
  { value: 'POST_REJECTION', label: 'Post-Rejection' },
]

interface SendModal {
  candidateId: string
  jobRoleId: string
  stage: string
}

export const NPSDashboard: React.FC = () => {
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [themes, setThemes] = useState<Theme[]>([])
  const [themeStage, setThemeStage] = useState('POST_INTERVIEW')
  const [loadingThemes, setLoadingThemes] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sendModal, setSendModal] = useState<SendModal | null>(null)
  const [sending, setSending] = useState(false)

  const fetchAnalytics = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/engagement/nps/analytics')
      setAnalytics(res.data)
    } catch (e) {
      console.error('Failed to fetch NPS analytics', e)
    } finally {
      setLoading(false)
    }
  }

  const fetchThemes = async (stage: string) => {
    setLoadingThemes(true)
    try {
      const res = await apiClient.get('/engagement/nps/themes', { params: { stage } })
      setThemes(res.data?.themes || [])
    } catch (e) {
      console.error('Failed to fetch themes', e)
    } finally {
      setLoadingThemes(false)
    }
  }

  useEffect(() => {
    fetchAnalytics()
    fetchThemes('POST_INTERVIEW')
  }, [])

  const handleThemeStageChange = (stage: string) => {
    setThemeStage(stage)
    fetchThemes(stage)
  }

  const sendSurvey = async () => {
    if (!sendModal) return
    if (!sendModal.candidateId || !sendModal.jobRoleId || !sendModal.stage) {
      alert('Please fill all fields.')
      return
    }
    setSending(true)
    try {
      const res = await apiClient.post('/engagement/nps/send', {
        candidate_id: sendModal.candidateId,
        job_role_id: sendModal.jobRoleId,
        stage: sendModal.stage,
      })
      alert(`Survey sent! Token: ${res.data.response_token}`)
      setSendModal(null)
      fetchAnalytics()
    } catch (e) {
      console.error('Send survey failed', e)
      alert('Failed to send survey.')
    } finally {
      setSending(false)
    }
  }

  const npsColor = (nps: number) => nps > 0 ? 'text-green-600' : nps < 0 ? 'text-red-600' : 'text-gray-600'

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">NPS Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Track candidate experience across the hiring journey</p>
        </div>
        <button
          onClick={() => setSendModal({ candidateId: '', jobRoleId: '', stage: 'POST_INTERVIEW' })}
          className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition"
        >
          Send NPS Survey
        </button>
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-400 text-sm">Loading analytics...</div>
      ) : !analytics ? null : (
        <>
          {/* Metric cards */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <div className="text-sm text-gray-500 mb-1">Overall NPS</div>
              <div className={`text-4xl font-bold ${npsColor(analytics.overall_nps)}`}>
                {analytics.overall_nps > 0 ? '+' : ''}{analytics.overall_nps.toFixed(1)}
              </div>
              <div className="text-xs text-gray-400 mt-1">Net Promoter Score</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <div className="text-sm text-gray-500 mb-1">Response Rate</div>
              <div className="text-4xl font-bold text-gray-800">{analytics.response_rate}%</div>
              <div className="text-xs text-gray-400 mt-1">{analytics.total_responded} responded</div>
            </div>
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <div className="text-sm text-gray-500 mb-1">Surveys Sent</div>
              <div className="text-4xl font-bold text-gray-800">{analytics.sent_this_month}</div>
              <div className="text-xs text-gray-400 mt-1">This month</div>
            </div>
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-2 gap-6 mb-6">
            {/* Bar chart */}
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <h3 className="font-semibold text-gray-800 mb-4 text-sm">Avg Score by Stage</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={analytics.by_stage}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="stage"
                    tick={{ fontSize: 10 }}
                    tickFormatter={s => s.replace('POST_', '')}
                  />
                  <YAxis domain={[0, 10]} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v: number) => v.toFixed(1)} />
                  <Bar dataKey="avg_score" fill="#7c3aed" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Line chart */}
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <h3 className="font-semibold text-gray-800 mb-4 text-sm">NPS Trend (12 weeks)</h3>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={analytics.weekly_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="week" tick={{ fontSize: 9 }} />
                  <YAxis domain={[-100, 100]} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v: number) => v.toFixed(1)} />
                  <Line type="monotone" dataKey="nps" stroke="#7c3aed" strokeWidth={2} dot={{ fill: '#7c3aed', r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Themes panel */}
          <div className="bg-white rounded-xl border border-gray-100 p-5 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-800 text-sm">Feedback Themes</h3>
              <select
                value={themeStage}
                onChange={e => handleThemeStageChange(e.target.value)}
                className="border border-gray-200 rounded-lg px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-purple-400"
              >
                {NPS_STAGES.map(s => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            {loadingThemes ? (
              <div className="text-sm text-gray-400 text-center py-4">Analyzing themes...</div>
            ) : themes.length === 0 ? (
              <div className="text-sm text-gray-400 text-center py-4">No themes yet — need more feedback data.</div>
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {themes.map((theme, i) => (
                  <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${SENTIMENT_DOT[theme.sentiment]}`}></div>
                      <span className="font-semibold text-gray-900 text-sm">{theme.theme}</span>
                      <span className="ml-auto text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded-full">{theme.count}</span>
                    </div>
                    {theme.exampleQuotes?.[0] && (
                      <p className="text-xs text-gray-500 italic">"{theme.exampleQuotes[0]}"</p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Verbatim feed */}
          {analytics.recent_feedback.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <h3 className="font-semibold text-gray-800 text-sm mb-4">Recent Feedback</h3>
              <div className="space-y-3 max-h-64 overflow-y-auto">
                {analytics.recent_feedback.map((fb, i) => (
                  <div key={i} className="flex items-start gap-3 text-sm py-2 border-b border-gray-50">
                    <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 font-medium ${
                      fb.stage === 'POST_APPLICATION' ? 'bg-purple-100 text-purple-700' :
                      fb.stage === 'POST_INTERVIEW' ? 'bg-blue-100 text-blue-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {fb.stage?.replace('POST_', '')}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 font-bold ${
                      fb.score >= 9 ? 'bg-green-100 text-green-700' :
                      fb.score >= 7 ? 'bg-yellow-100 text-yellow-700' :
                      'bg-red-100 text-red-700'
                    }`}>
                      {fb.score}/10
                    </span>
                    <p className="text-gray-600 leading-relaxed">{fb.feedback}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Send modal */}
      {sendModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-gray-900">Send NPS Survey</h3>
              <button onClick={() => setSendModal(null)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3 mb-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Candidate ID</label>
                <input
                  type="text"
                  value={sendModal.candidateId}
                  onChange={e => setSendModal(m => m ? { ...m, candidateId: e.target.value } : m)}
                  placeholder="UUID..."
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Job Role ID</label>
                <input
                  type="text"
                  value={sendModal.jobRoleId}
                  onChange={e => setSendModal(m => m ? { ...m, jobRoleId: e.target.value } : m)}
                  placeholder="UUID..."
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Stage</label>
                <select
                  value={sendModal.stage}
                  onChange={e => setSendModal(m => m ? { ...m, stage: e.target.value } : m)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                >
                  {NPS_STAGES.map(s => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setSendModal(null)}
                className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                onClick={sendSurvey}
                disabled={sending}
                className="bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
              >
                {sending ? 'Sending...' : 'Send Survey'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default NPSDashboard
