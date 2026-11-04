import { apiClient } from '@/lib/api'
import { AlertTriangle,Check,Cpu,Lock,Megaphone,Share2,Shield,X } from 'lucide-react'
import { useCallback,useEffect,useState } from 'react'

// --- Types ---
interface ErasureRequest {
  id: string
  candidate_id: string
  requested_at: string
  status: 'PENDING' | 'COMPLETED' | 'DENIED'
}

const STATUS_BADGE: Record<string, string> = {
  PENDING: 'bg-amber-100 text-amber-700',
  COMPLETED: 'bg-green-100 text-green-700',
  DENIED: 'bg-red-100 text-red-700',
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500)
    return () => clearTimeout(t)
  }, [onClose])
  return (
    <div className="fixed bottom-6 right-6 z-50 bg-purple-700 text-white px-5 py-3 rounded-xl shadow-lg text-sm flex items-center gap-3">
      <Check className="w-4 h-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}

function daysSince(dateStr: string): number {
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000)
}

// ============ ERASURE REQUESTS TAB ============
function ErasureRequestsTab() {
  const [requests, setRequests] = useState<ErasureRequest[]>([])
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState('')
  const [processModal, setProcessModal] = useState<ErasureRequest | null>(null)
  const [action, setAction] = useState<'approve' | 'deny' | null>(null)
  const [denialReason, setDenialReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/compliance/erasure/requests')
      setRequests(res.data || [])
    } catch {
      console.error('Failed to fetch erasure requests')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const handleProcess = async () => {
    if (!processModal || !action) return
    if (action === 'deny' && !denialReason.trim()) {
      setToast('Please provide a denial reason')
      return
    }
    setSubmitting(true)
    try {
      const body: Record<string, string> = { action }
      if (action === 'deny') body.denial_reason = denialReason
      await apiClient.post(`/compliance/erasure/${processModal.id}/process`, body)
      setToast(action === 'approve' ? 'Erasure approved and processed' : 'Request denied')
      setProcessModal(null)
      setAction(null)
      setDenialReason('')
      fetch()
    } catch {
      setToast('Failed to process request')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading...</div>
        ) : requests.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No erasure requests</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Candidate ID</th>
                  <th className="px-4 py-3 text-left">Requested At</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Days Since</th>
                  <th className="px-4 py-3 text-left">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {requests.map((r) => (
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-gray-700">{r.candidate_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-gray-600">
                      {new Date(r.requested_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE[r.status] || 'bg-gray-100 text-gray-600'}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{daysSince(r.requested_at)}d</td>
                    <td className="px-4 py-3">
                      {r.status === 'PENDING' && (
                        <button
                          onClick={() => { setProcessModal(r); setAction(null); setDenialReason('') }}
                          className="text-xs px-3 py-1 bg-purple-50 text-purple-700 rounded hover:bg-purple-100 transition"
                        >
                          Process
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Process Modal */}
      {processModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Process Erasure Request</h3>
              <button onClick={() => setProcessModal(null)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {!action ? (
                <div className="space-y-3">
                  <button
                    onClick={() => setAction('approve')}
                    className="w-full py-3 bg-red-600 text-white rounded-lg font-medium text-sm hover:bg-red-700 transition flex items-center justify-center gap-2"
                  >
                    <AlertTriangle className="w-4 h-4" />
                    Approve Erasure
                  </button>
                  <button
                    onClick={() => setAction('deny')}
                    className="w-full py-3 bg-gray-100 text-gray-700 rounded-lg font-medium text-sm hover:bg-gray-200 transition"
                  >
                    Deny Request
                  </button>
                </div>
              ) : action === 'approve' ? (
                <div className="space-y-4">
                  <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
                    <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-red-700">
                      This permanently anonymizes candidate data and cannot be undone.
                    </p>
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setAction(null)}
                      className="flex-1 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleProcess}
                      disabled={submitting}
                      className="flex-1 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50 transition"
                    >
                      {submitting ? 'Processing...' : 'Confirm Erasure'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Denial Reason</label>
                    <input
                      type="text"
                      value={denialReason}
                      onChange={(e) => setDenialReason(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                      placeholder="Reason for denial..."
                    />
                  </div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setAction(null)}
                      className="flex-1 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition"
                    >
                      Back
                    </button>
                    <button
                      onClick={handleProcess}
                      disabled={submitting || !denialReason.trim()}
                      className="flex-1 py-2 bg-gray-700 text-white rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50 transition"
                    >
                      {submitting ? 'Denying...' : 'Deny Request'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}

// ============ CONSENT OVERVIEW TAB ============
const CONSENT_TYPES = [
  {
    type: 'DATA_PROCESSING',
    icon: <Shield className="w-6 h-6 text-purple-600" />,
    description: 'Required for recruitment — candidates cannot opt out',
    badge: 'Required',
    badgeClass: 'bg-red-100 text-red-700',
  },
  {
    type: 'MARKETING',
    icon: <Megaphone className="w-6 h-6 text-blue-500" />,
    description: 'Optional — future job opportunity updates',
    badge: 'Optional',
    badgeClass: 'bg-gray-100 text-gray-600',
  },
  {
    type: 'THIRD_PARTY_SHARE',
    icon: <Share2 className="w-6 h-6 text-green-500" />,
    description: 'Optional — profile sharing across partner properties',
    badge: 'Optional',
    badgeClass: 'bg-gray-100 text-gray-600',
  },
  {
    type: 'AI_PROCESSING',
    icon: <Cpu className="w-6 h-6 text-indigo-500" />,
    description: 'Optional — AI-powered matching and screening',
    badge: 'Optional',
    badgeClass: 'bg-gray-100 text-gray-600',
  },
]

function ConsentOverviewTab() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {CONSENT_TYPES.map((c) => (
        <div key={c.type} className="bg-white rounded-xl border border-gray-200 p-5 flex gap-4">
          <div className="flex-shrink-0 mt-0.5">{c.icon}</div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-semibold text-gray-900 text-sm">{c.type.replace(/_/g, ' ')}</h3>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${c.badgeClass}`}>
                {c.badge}
              </span>
            </div>
            <p className="text-sm text-gray-600">{c.description}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ============ DATA RETENTION TAB ============
function DataRetentionTab() {
  const [toast, setToast] = useState('')
  const [running, setRunning] = useState(false)

  const handleRun = async () => {
    setRunning(true)
    try {
      const res = await apiClient.post('/compliance/data-retention/process')
      const count = res.data?.processed ?? res.data?.count ?? 0
      setToast(`Retention check complete — ${count} record(s) processed`)
    } catch {
      setToast('Failed to run retention check')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Retention Policy</h3>
        <div className="space-y-3">
          <div className="flex items-start gap-3 p-3 bg-red-50 rounded-lg border border-red-100">
            <div className="w-2 h-2 rounded-full bg-red-400 mt-1.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-800">Rejected candidates</p>
              <p className="text-sm text-gray-600">Anonymized after 12 months</p>
            </div>
          </div>
          <div className="flex items-start gap-3 p-3 bg-amber-50 rounded-lg border border-amber-100">
            <div className="w-2 h-2 rounded-full bg-amber-400 mt-1.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-800">Withdrawn candidates</p>
              <p className="text-sm text-gray-600">Anonymized after 6 months</p>
            </div>
          </div>
          <div className="flex items-start gap-3 p-3 bg-green-50 rounded-lg border border-green-100">
            <div className="w-2 h-2 rounded-full bg-green-400 mt-1.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-gray-800">Active candidates</p>
              <p className="text-sm text-gray-600">Retained indefinitely</p>
            </div>
          </div>
        </div>
        <div className="mt-6 pt-4 border-t border-gray-100">
          <p className="text-sm text-gray-500 mb-4">
            Run the retention check to anonymize expired candidate records according to policy.
          </p>
          <button
            onClick={handleRun}
            disabled={running}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition"
          >
            {running ? 'Running...' : 'Run Retention Check'}
          </button>
        </div>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}

// ============ MAIN PAGE ============
type Tab = 'erasure' | 'consent' | 'retention'

export default function DataPrivacyCenter() {
  const [tab, setTab] = useState<Tab>('erasure')

  const tabs: { key: Tab; label: string }[] = [
    { key: 'erasure', label: 'Erasure Requests' },
    { key: 'consent', label: 'Consent Overview' },
    { key: 'retention', label: 'Data Retention' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Lock className="w-6 h-6 text-purple-600" />
        <h1 className="text-2xl font-bold text-gray-900">Data Privacy Center</h1>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition -mb-px ${
              tab === t.key
                ? 'border-purple-600 text-purple-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'erasure' && <ErasureRequestsTab />}
      {tab === 'consent' && <ConsentOverviewTab />}
      {tab === 'retention' && <DataRetentionTab />}
    </div>
  )
}
