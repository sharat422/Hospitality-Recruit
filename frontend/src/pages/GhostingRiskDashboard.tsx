import { apiClient } from '@/lib/api'
import { AlertTriangle,RefreshCw,Send,X } from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'

interface GhostingRisk {
  candidate_id: string
  name: string
  email?: string
  phone?: string
  pipeline_stage?: string
  role_title?: string
  job_role_id?: string
  risk_score: number
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  risk_signals: string[]
  last_message_date?: string
}

type LevelFilter = 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM'

const LEVEL_COLORS: Record<string, string> = {
  CRITICAL: 'text-red-600 bg-red-50 border-red-200',
  HIGH: 'text-orange-600 bg-orange-50 border-orange-200',
  MEDIUM: 'text-yellow-600 bg-yellow-50 border-yellow-200',
  LOW: 'text-green-600 bg-green-50 border-green-200',
}

const SCORE_COLORS: Record<string, string> = {
  CRITICAL: 'text-red-600',
  HIGH: 'text-orange-500',
  MEDIUM: 'text-yellow-500',
  LOW: 'text-green-500',
}

interface OutreachModal {
  candidate: GhostingRisk
  generatedMessage: string
  loading: boolean
}

export const GhostingRiskDashboard: React.FC = () => {
  const [risks, setRisks] = useState<GhostingRisk[]>([])
  const [loading, setLoading] = useState(false)
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('ALL')
  const [outreachModal, setOutreachModal] = useState<OutreachModal | null>(null)
  const [editableMessage, setEditableMessage] = useState('')
  
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const fetchRisks = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, string> = {}
      if (levelFilter !== 'ALL') params.min_level = levelFilter
      const res = await apiClient.get('/engagement/ghosting-risk', { params })
      setRisks(res.data || [])
    } catch (e) {
      console.error('Failed to fetch ghosting risks', e)
    } finally {
      setLoading(false)
    }
  }, [levelFilter])

  useEffect(() => {
    fetchRisks()
  }, [fetchRisks])

  const recalculateAll = async () => {
    if (!window.confirm('Recalculate ghosting risk for all candidates? This may take a moment.')) return
    try {
      const res = await apiClient.post('/engagement/ghosting-risk/calculate-all')
      alert(`Processed ${res.data.processed} candidates`)
      fetchRisks()
    } catch (e) {
      console.error('Recalculate failed', e)
    }
  }

  const openOutreach = async (candidate: GhostingRisk) => {
    if (!candidate.phone) {
      alert('No phone number on file for this candidate.')
      return
    }
    setOutreachModal({ candidate, generatedMessage: '', loading: true })
    setEditableMessage('')
    try {
      const res = await apiClient.post(`/engagement/ghosting-risk/${candidate.candidate_id}/outreach`, {
        job_role_id: candidate.job_role_id || '',
        phone: candidate.phone,
      })
      const msg = res.data.message || ''
      setOutreachModal({ candidate, generatedMessage: msg, loading: false })
      setEditableMessage(msg)
    } catch (e) {
      setOutreachModal({ candidate, generatedMessage: 'Could not generate message.', loading: false })
    }
  }


  const criticalCount = risks.filter(r => r.risk_level === 'CRITICAL').length
  const highCount = risks.filter(r => r.risk_level === 'HIGH').length
  const attention = criticalCount + highCount

  const displayed = risks.filter(r => !dismissed.has(r.candidate_id))

  return (
    <div className="max-w-5xl mx-auto">
      {/* Attention banner */}
      {attention > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 mb-6 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
          <span className="font-semibold text-amber-800">
            {attention} candidate{attention !== 1 ? 's' : ''} need attention
          </span>
          <span className="text-amber-600 text-sm">
            ({criticalCount} critical, {highCount} high risk)
          </span>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ghosting Risk Dashboard</h1>
          <p className="text-gray-500 text-sm mt-1">Identify candidates at risk of ghosting before it happens</p>
        </div>
        <button
          onClick={recalculateAll}
          disabled={loading}
          className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Recalculate
        </button>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 mb-6">
        {(['ALL', 'CRITICAL', 'HIGH', 'MEDIUM'] as LevelFilter[]).map(tab => (
          <button
            key={tab}
            onClick={() => setLevelFilter(tab)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              levelFilter === tab
                ? 'bg-purple-600 text-white'
                : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Cards grid */}
      {loading ? (
        <div className="grid md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="bg-white rounded-xl border border-gray-100 p-5 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/2 mb-3"></div>
              <div className="h-8 bg-gray-100 rounded w-16 mb-3"></div>
              <div className="h-3 bg-gray-100 rounded w-3/4"></div>
            </div>
          ))}
        </div>
      ) : displayed.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <AlertTriangle className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg font-medium">No candidates at risk</p>
          <p className="text-sm">Great news — everyone is engaged!</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {displayed.map(risk => (
            <div
              key={risk.candidate_id}
              className={`bg-white rounded-xl border p-5 ${LEVEL_COLORS[risk.risk_level]}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-bold text-gray-900 text-base">{risk.name}</h3>
                  {risk.role_title && (
                    <p className="text-sm text-gray-500">{risk.role_title}</p>
                  )}
                </div>
                <div className="text-right">
                  <div className={`text-3xl font-bold ${SCORE_COLORS[risk.risk_level]}`}>
                    {Math.round(risk.risk_score * 100)}
                  </div>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    risk.risk_level === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                    risk.risk_level === 'HIGH' ? 'bg-orange-100 text-orange-700' :
                    risk.risk_level === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                    'bg-green-100 text-green-700'
                  }`}>
                    {risk.risk_level}
                  </span>
                </div>
              </div>

              {risk.pipeline_stage && (
                <div className="text-xs text-gray-500 mb-2">
                  Stage: <span className="font-medium text-gray-700">{risk.pipeline_stage.replace(/_/g, ' ')}</span>
                </div>
              )}

              {risk.risk_signals.length > 0 && (
                <ul className="text-sm text-gray-600 space-y-1 mb-4">
                  {risk.risk_signals.map((signal, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-red-400 flex-shrink-0 mt-0.5">•</span>
                      {signal}
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => openOutreach(risk)}
                  className="flex items-center gap-1.5 bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition"
                >
                  <Send className="w-3 h-3" />
                  Send Check-in
                </button>
                <button
                  onClick={() => setDismissed(prev => new Set([...prev, risk.candidate_id]))}
                  className="flex items-center gap-1.5 border border-gray-200 text-gray-600 hover:bg-gray-50 px-3 py-1.5 rounded-lg text-xs font-medium transition"
                >
                  <X className="w-3 h-3" />
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Outreach modal */}
      {outreachModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-gray-900">AI Check-in Message</h3>
              <button onClick={() => setOutreachModal(null)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-sm text-gray-500 mb-3">
              Sending to <span className="font-medium text-gray-700">{outreachModal.candidate.name}</span>
              {outreachModal.candidate.phone && <span className="text-gray-500"> ({outreachModal.candidate.phone})</span>}
            </p>

            {outreachModal.loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin w-6 h-6 border-4 border-purple-600 border-t-transparent rounded-full"></div>
              </div>
            ) : (
              <>
                <textarea
                  rows={4}
                  value={editableMessage}
                  onChange={e => setEditableMessage(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400 mb-1"
                />
                <p className="text-xs text-gray-400 mb-4">{editableMessage.length}/160 characters</p>

                <div className="text-xs text-green-600 bg-green-50 rounded-lg px-3 py-2 mb-4">
                  Message has been sent via the AI outreach endpoint.
                </div>

                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setOutreachModal(null)}
                    className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition"
                  >
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default GhostingRiskDashboard
