import { apiClient } from '@/lib/api'
import { Check,Copy,Shield,X } from 'lucide-react'
import { useCallback,useEffect,useState } from 'react'

interface RTWCheck {
  id: string
  candidate_id: string
  check_type: string
  status: string
  expiry_date?: string
  documents?: unknown
  notes?: string
}

const STATUS_COLORS: Record<string, string> = {
  PENDING: 'bg-gray-100 text-gray-700',
  DOCUMENTS_UPLOADED: 'bg-blue-100 text-blue-700',
  VERIFIED: 'bg-green-100 text-green-700',
  FAILED: 'bg-red-100 text-red-700',
  EXPIRED: 'bg-red-100 text-red-700',
}

const CHECK_TYPES = [
  'UK_RTW',
  'US_I9',
  'EU_WORK_PERMIT',
  'H2B_VISA',
  'J1_VISA',
  'TIER2_VISA',
]

function getExpiryColor(expiry?: string): string {
  if (!expiry) return 'text-gray-500'
  const days = Math.floor((new Date(expiry).getTime() - Date.now()) / 86400000)
  if (days < 0) return 'text-red-600 font-semibold'
  if (days < 7) return 'text-red-600 font-semibold'
  if (days < 30) return 'text-amber-600 font-semibold'
  return 'text-green-600'
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

export default function RTWManager() {
  const [checks, setChecks] = useState<RTWCheck[]>([])
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState('')

  // Modals
  const [viewDocsCheck, setViewDocsCheck] = useState<RTWCheck | null>(null)
  const [verifyCheck, setVerifyCheck] = useState<RTWCheck | null>(null)
  const [rejectCheck, setRejectCheck] = useState<RTWCheck | null>(null)
  const [requestOpen, setRequestOpen] = useState(false)

  // Verify form
  const [verifyExpiry, setVerifyExpiry] = useState('')
  const [verifyNotes, setVerifyNotes] = useState('')

  // Reject form
  const [rejectReason, setRejectReason] = useState('')

  // Request form
  const [reqCandidateId, setReqCandidateId] = useState('')
  const [reqCheckType, setReqCheckType] = useState('UK_RTW')
  const [reqUploadUrl, setReqUploadUrl] = useState('')
  const [reqLoading, setReqLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const [submitting, setSubmitting] = useState(false)

  const fetchChecks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/compliance/rtw/expiring?days_ahead=365')
      setChecks(res.data || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchChecks()
  }, [fetchChecks])

  const pendingCount = checks.filter((c) => c.status === 'PENDING').length
  const expiringSoonCount = checks.filter((c) => {
    if (!c.expiry_date) return false
    const days = Math.floor((new Date(c.expiry_date).getTime() - Date.now()) / 86400000)
    return days >= 0 && days <= 30
  }).length

  const handleCheckAlerts = async () => {
    try {
      const res = await apiClient.post('/compliance/rtw/check-expiry')
      const count = res.data?.alerts_sent ?? res.data?.count ?? 0
      setToast(`${count} alert(s) sent`)
    } catch {
      setToast('Failed to send alerts')
    }
  }

  const handleVerify = async () => {
    if (!verifyCheck) return
    setSubmitting(true)
    try {
      await apiClient.patch(`/compliance/rtw/${verifyCheck.id}/verify`, {
        expiry_date: verifyExpiry || undefined,
        notes: verifyNotes || undefined,
      })
      setToast('Check verified')
      setVerifyCheck(null)
      fetchChecks()
    } catch {
      setToast('Failed to verify')
    } finally {
      setSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!rejectCheck) return
    setSubmitting(true)
    try {
      await apiClient.patch(`/compliance/rtw/${rejectCheck.id}/reject`, {
        reason: rejectReason,
      })
      setToast('Check rejected')
      setRejectCheck(null)
      fetchChecks()
    } catch {
      setToast('Failed to reject')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRequest = async () => {
    setReqLoading(true)
    try {
      const res = await apiClient.post('/compliance/rtw/request', {
        candidate_id: reqCandidateId,
        check_type: reqCheckType,
      })
      setReqUploadUrl(res.data?.upload_url || '')
      fetchChecks()
    } catch {
      setToast('Failed to request check')
    } finally {
      setReqLoading(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(reqUploadUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="w-6 h-6 text-purple-600" />
          <h1 className="text-2xl font-bold text-gray-900">Right to Work Manager</h1>
        </div>
        <button
          onClick={() => { setRequestOpen(true); setReqUploadUrl(''); setReqCandidateId(''); setReqCheckType('UK_RTW') }}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition"
        >
          Request Check
        </button>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">Pending Checks</p>
          <p className="text-3xl font-bold text-gray-900 mt-1">{pendingCount}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">Expiring Within 30 Days</p>
          <p className="text-3xl font-bold text-amber-600 mt-1">{expiringSoonCount}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 flex flex-col justify-between">
          <p className="text-sm text-gray-500">Expiry Alerts</p>
          <button
            onClick={handleCheckAlerts}
            className="mt-3 w-full px-3 py-2 bg-amber-50 border border-amber-200 text-amber-700 rounded-lg text-sm font-medium hover:bg-amber-100 transition"
          >
            Check Alerts
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">RTW Checks (Next 12 Months)</h2>
        </div>
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading...</div>
        ) : checks.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No checks found</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Check ID</th>
                  <th className="px-4 py-3 text-left">Type</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Expiry Date</th>
                  <th className="px-4 py-3 text-left">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {checks.map((c) => (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-gray-700">{c.id.slice(0, 8)}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 bg-purple-50 text-purple-700 rounded text-xs font-medium">
                        {c.check_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[c.status] || 'bg-gray-100 text-gray-700'}`}>
                        {c.status}
                      </span>
                    </td>
                    <td className={`px-4 py-3 ${getExpiryColor(c.expiry_date)}`}>
                      {c.expiry_date ? new Date(c.expiry_date).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setViewDocsCheck(c)}
                          className="text-xs px-2 py-1 bg-gray-100 rounded hover:bg-gray-200 transition"
                        >
                          View Docs
                        </button>
                        <button
                          onClick={() => { setVerifyCheck(c); setVerifyExpiry(''); setVerifyNotes('') }}
                          className="text-xs px-2 py-1 bg-green-50 text-green-700 rounded hover:bg-green-100 transition"
                        >
                          Verify
                        </button>
                        <button
                          onClick={() => { setRejectCheck(c); setRejectReason('') }}
                          className="text-xs px-2 py-1 bg-red-50 text-red-700 rounded hover:bg-red-100 transition"
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* View Docs Modal */}
      {viewDocsCheck && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Documents — {viewDocsCheck.id.slice(0, 8)}</h3>
              <button onClick={() => setViewDocsCheck(null)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5">
              <pre className="bg-gray-50 rounded-lg p-4 text-xs overflow-auto max-h-80 text-gray-700 whitespace-pre-wrap">
                {JSON.stringify(viewDocsCheck.documents ?? null, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Verify Modal */}
      {verifyCheck && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Verify Check</h3>
              <button onClick={() => setVerifyCheck(null)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Expiry Date</label>
                <input
                  type="date"
                  value={verifyExpiry}
                  onChange={(e) => setVerifyExpiry(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                <textarea
                  value={verifyNotes}
                  onChange={(e) => setVerifyNotes(e.target.value)}
                  rows={3}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Optional notes..."
                />
              </div>
              <button
                onClick={handleVerify}
                disabled={submitting}
                className="w-full py-2 bg-green-600 text-white rounded-lg font-medium text-sm hover:bg-green-700 disabled:opacity-50 transition"
              >
                {submitting ? 'Verifying...' : 'Confirm Verify'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {rejectCheck && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Reject Check</h3>
              <button onClick={() => setRejectCheck(null)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Reason</label>
                <input
                  type="text"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="Reason for rejection..."
                />
              </div>
              <button
                onClick={handleReject}
                disabled={submitting}
                className="w-full py-2 bg-red-600 text-white rounded-lg font-medium text-sm hover:bg-red-700 disabled:opacity-50 transition"
              >
                {submitting ? 'Rejecting...' : 'Confirm Reject'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Request Modal */}
      {requestOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
              <h3 className="font-semibold text-gray-900">Request RTW Check</h3>
              <button onClick={() => setRequestOpen(false)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Candidate ID</label>
                <input
                  type="text"
                  value={reqCandidateId}
                  onChange={(e) => setReqCandidateId(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="e.g. cand_abc123"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Check Type</label>
                <select
                  value={reqCheckType}
                  onChange={(e) => setReqCheckType(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                >
                  {CHECK_TYPES.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleRequest}
                disabled={reqLoading || !reqCandidateId}
                className="w-full py-2 bg-purple-600 text-white rounded-lg font-medium text-sm hover:bg-purple-700 disabled:opacity-50 transition"
              >
                {reqLoading ? 'Requesting...' : 'Submit Request'}
              </button>
              {reqUploadUrl && (
                <div className="mt-3">
                  <p className="text-xs text-gray-500 mb-1">Upload URL (share with candidate):</p>
                  <div className="flex items-center gap-2">
                    <input
                      readOnly
                      value={reqUploadUrl}
                      className="flex-1 bg-gray-50 border border-gray-200 rounded px-2 py-1.5 text-xs font-mono text-gray-700 truncate"
                    />
                    <button
                      onClick={handleCopy}
                      className="p-1.5 bg-gray-100 rounded hover:bg-gray-200 transition"
                    >
                      {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4 text-gray-600" />}
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
