import { apiClient } from '@/lib/api'
import { AlertCircle,Check,Copy,DollarSign,Gift,Loader2,Trash2,TrendingUp,UserCheck,Users } from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Referral {
  id: string
  referral_code: string
  referrer_email: string
  candidate_email: string | null
  job_role_id: string
  status: string
  reward_amount: number
  reward_status: string
  reward_paid_at: string | null
  created_at: string
  notes: string | null
}

interface ReferralSummary {
  total_referrals: number
  applied_count: number
  hired_count: number
  total_earned: number
  total_paid: number
}

interface LeaderboardEntry {
  referrer_email: string
  total_referrals: number
  hired_count: number
  total_earned: number
}

interface AllReferral {
  id: string
  referral_code: string
  referrer_email: string
  candidate_email: string | null
  job_role_id: string
  status: string
  reward_amount: number
  reward_status: string
  created_at: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function maskEmail(email: string): string {
  if (!email || email.length < 3) return '***'
  return email.substring(0, 3) + '***@***'
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case 'PENDING': return 'bg-gray-100 text-gray-700'
    case 'APPLIED': return 'bg-blue-100 text-blue-700'
    case 'SHORTLISTED': return 'bg-yellow-100 text-yellow-700'
    case 'HIRED': return 'bg-green-100 text-green-700'
    case 'REWARDED': return 'bg-purple-100 text-purple-700'
    default: return 'bg-gray-100 text-gray-600'
  }
}

function rewardBadgeClass(status: string): string {
  switch (status) {
    case 'NOT_EARNED': return 'bg-gray-100 text-gray-500'
    case 'EARNED': return 'bg-green-100 text-green-700'
    case 'PAID': return 'bg-purple-100 text-purple-700'
    default: return 'bg-gray-100 text-gray-500'
  }
}

function rankEmoji(rank: number): string {
  if (rank === 1) return '🥇'
  if (rank === 2) return '🥈'
  if (rank === 3) return '🥉'
  return `#${rank}`
}

function formatDate(ts: string | null): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleDateString()
  } catch {
    return ts
  }
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3000)
    return () => clearTimeout(t)
  }, [onClose])
  return (
    <div className="fixed bottom-6 right-6 z-50 bg-purple-700 text-white px-5 py-3 rounded-xl shadow-lg text-sm flex items-center gap-3">
      <Check className="w-4 h-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Summary Cards
// ---------------------------------------------------------------------------

function SummaryCards({ summary }: { summary: ReferralSummary }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <div className="bg-white border border-gray-200 rounded-xl p-5 flex items-center gap-4">
        <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center">
          <Users className="w-5 h-5 text-gray-600" />
        </div>
        <div>
          <p className="text-2xl font-bold text-gray-900">{summary.total_referrals}</p>
          <p className="text-xs text-gray-500">Total Referrals</p>
        </div>
      </div>
      <div className="bg-white border border-gray-200 rounded-xl p-5 flex items-center gap-4">
        <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
          <TrendingUp className="w-5 h-5 text-blue-600" />
        </div>
        <div>
          <p className="text-2xl font-bold text-blue-700">{summary.applied_count}</p>
          <p className="text-xs text-gray-500">Applied</p>
        </div>
      </div>
      <div className="bg-white border border-gray-200 rounded-xl p-5 flex items-center gap-4">
        <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center">
          <UserCheck className="w-5 h-5 text-green-600" />
        </div>
        <div>
          <p className="text-2xl font-bold text-green-700">{summary.hired_count}</p>
          <p className="text-xs text-gray-500">Hired</p>
        </div>
      </div>
      <div className="bg-white border border-gray-200 rounded-xl p-5 flex items-center gap-4">
        <div className="w-10 h-10 bg-purple-50 rounded-lg flex items-center justify-center">
          <DollarSign className="w-5 h-5 text-purple-600" />
        </div>
        <div>
          <p className="text-2xl font-bold text-purple-700">${summary.total_earned.toFixed(2)}</p>
          <p className="text-xs text-gray-500">Total Earned</p>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Update Status Modal
// ---------------------------------------------------------------------------

const VALID_NEXT: Record<string, string[]> = {
  APPLIED: ['SHORTLISTED'],
  SHORTLISTED: ['HIRED'],
  HIRED: ['REWARDED'],
}

function UpdateStatusModal({
  referral,
  onClose,
  onUpdated,
  showToast,
}: {
  referral: Referral
  onClose: () => void
  onUpdated: () => void
  showToast: (msg: string) => void
}) {
  const allowed = VALID_NEXT[referral.status] || []
  const [newStatus, setNewStatus] = useState(allowed[0] || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSave = async () => {
    if (!newStatus) return
    setLoading(true)
    setError('')
    try {
      await apiClient.patch(`/referrals/${referral.id}/update-status`, { status: newStatus })
      showToast(`Status updated to ${newStatus}`)
      onUpdated()
      onClose()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update status')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm mx-4">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Update Status</h3>
        <p className="text-sm text-gray-500 mb-3">
          Current status: <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusBadgeClass(referral.status)}`}>{referral.status}</span>
        </p>
        {allowed.length === 0 ? (
          <p className="text-sm text-gray-500">No valid transitions available from {referral.status}.</p>
        ) : (
          <>
            <label className="block text-sm font-medium text-gray-700 mb-1">New Status</label>
            <select
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-purple-500"
              value={newStatus}
              onChange={e => setNewStatus(e.target.value)}
            >
              {allowed.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </>
        )}
        {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition"
          >
            Cancel
          </button>
          {allowed.length > 0 && (
            <button
              onClick={handleSave}
              disabled={loading}
              className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition disabled:opacity-50 flex items-center gap-2"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              Save
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 1: My Referrals
// ---------------------------------------------------------------------------

function MyReferralsTab({ showToast }: { showToast: (msg: string) => void }) {
  const [referrals, setReferrals] = useState<Referral[]>([])
  const [summary, setSummary] = useState<ReferralSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [updateModal, setUpdateModal] = useState<Referral | null>(null)

  const fetchReferrals = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await apiClient.get('/referrals/my-referrals')
      setReferrals(res.data.referrals || [])
      setSummary(res.data.summary || null)
    } catch {
      setError('Failed to load referrals')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchReferrals() }, [fetchReferrals])

  const copyLink = (ref: Referral) => {
    const link = `${window.location.origin}/apply/${ref.job_role_id}?ref=${ref.referral_code}`
    navigator.clipboard.writeText(link).then(() => {
      setCopiedId(ref.id)
      showToast('Link copied to clipboard!')
      setTimeout(() => setCopiedId(null), 2000)
    })
  }

  const copyCode = (ref: Referral) => {
    navigator.clipboard.writeText(ref.referral_code).then(() => {
      setCopiedId(ref.id + '-code')
      showToast('Code copied!')
      setTimeout(() => setCopiedId(null), 2000)
    })
  }

  const markPaid = async (ref: Referral) => {
    try {
      await apiClient.post(`/referrals/${ref.id}/mark-paid`)
      showToast('Marked as paid!')
      fetchReferrals()
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Failed to mark paid')
    }
  }

  const deleteReferral = async (ref: Referral) => {
    if (!window.confirm(`Delete referral ${ref.referral_code}? This cannot be undone.`)) return
    try {
      await apiClient.delete(`/referrals/${ref.id}`)
      showToast('Referral deleted')
      fetchReferrals()
    } catch (err: any) {
      showToast(err?.response?.data?.detail || 'Failed to delete referral')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-purple-600" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-red-600 py-8">
        <AlertCircle className="w-5 h-5" />
        <span>{error}</span>
      </div>
    )
  }

  return (
    <div>
      {summary && <SummaryCards summary={summary} />}

      {referrals.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <Gift className="w-12 h-12 mx-auto mb-4 text-gray-300" />
          <p className="text-lg font-medium">No referrals yet</p>
          <p className="text-sm mt-1">Create your first referral link in the Create Link tab.</p>
        </div>
      ) : (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Code</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Candidate</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Job Role</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Reward</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Reward Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {referrals.map(ref => (
                  <tr key={ref.id} className="hover:bg-gray-50 transition">
                    <td className="px-4 py-3">
                      <button
                        onClick={() => copyCode(ref)}
                        className="font-mono text-xs bg-gray-100 px-2 py-1 rounded hover:bg-gray-200 transition flex items-center gap-1"
                        title="Click to copy code"
                      >
                        {copiedId === ref.id + '-code' ? <Check className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3 text-gray-400" />}
                        {ref.referral_code}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      {ref.candidate_email || <span className="text-gray-400 italic">Not yet applied</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      {ref.job_role_id ? ref.job_role_id.substring(0, 8) + '...' : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusBadgeClass(ref.status)}`}>
                        {ref.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700">
                      ${(ref.reward_amount || 0).toFixed(2)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${rewardBadgeClass(ref.reward_status)}`}>
                        {ref.reward_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {formatDate(ref.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1 flex-wrap">
                        <button
                          onClick={() => copyLink(ref)}
                          className="px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 transition flex items-center gap-1"
                        >
                          {copiedId === ref.id ? <Check className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3" />}
                          {copiedId === ref.id ? 'Copied!' : 'Copy Link'}
                        </button>
                        {VALID_NEXT[ref.status]?.length > 0 && (
                          <button
                            onClick={() => setUpdateModal(ref)}
                            className="px-2 py-1 text-xs bg-blue-50 text-blue-700 border border-blue-200 rounded hover:bg-blue-100 transition"
                          >
                            Update Status
                          </button>
                        )}
                        {ref.reward_status === 'EARNED' && (
                          <button
                            onClick={() => markPaid(ref)}
                            className="px-2 py-1 text-xs bg-green-50 text-green-700 border border-green-200 rounded hover:bg-green-100 transition"
                          >
                            Mark Paid
                          </button>
                        )}
                        {ref.status === 'PENDING' && (
                          <button
                            onClick={() => deleteReferral(ref)}
                            className="px-2 py-1 text-xs bg-red-50 text-red-600 border border-red-200 rounded hover:bg-red-100 transition flex items-center gap-1"
                          >
                            <Trash2 className="w-3 h-3" />
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {updateModal && (
        <UpdateStatusModal
          referral={updateModal}
          onClose={() => setUpdateModal(null)}
          onUpdated={fetchReferrals}
          showToast={showToast}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 2: Create Referral Link
// ---------------------------------------------------------------------------

interface CreateResult {
  referral_id: string
  referral_code: string
  referral_link: string
  reward_amount: number
}

function CreateLinkTab({ showToast }: { showToast: (msg: string) => void }) {
  const [jobRoleId, setJobRoleId] = useState('')
  const [candidateEmail, setCandidateEmail] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<CreateResult | null>(null)
  const [linkCopied, setLinkCopied] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!jobRoleId.trim()) {
      setError('Job Role ID is required')
      return
    }
    setLoading(true)
    setError('')
    try {
      const payload: Record<string, string> = { job_role_id: jobRoleId.trim() }
      if (candidateEmail.trim()) payload.candidate_email = candidateEmail.trim()
      if (notes.trim()) payload.notes = notes.trim()
      const res = await apiClient.post('/referrals/create', payload)
      setResult(res.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to create referral link')
    } finally {
      setLoading(false)
    }
  }

  const copyLink = () => {
    if (!result) return
    navigator.clipboard.writeText(result.referral_link).then(() => {
      setLinkCopied(true)
      showToast('Link copied to clipboard!')
      setTimeout(() => setLinkCopied(false), 2000)
    })
  }

  const shareViaWhatsApp = () => {
    if (!result) return
    const text = encodeURIComponent(`I thought you'd be great for this job: ${result.referral_link}`)
    window.open(`https://wa.me/?text=${text}`, '_blank')
  }

  const shareViaSMS = () => {
    if (!result) return
    const body = encodeURIComponent(`I thought you'd be great for this job: ${result.referral_link}`)
    window.open(`sms:?body=${body}`)
  }

  const shareViaEmail = () => {
    if (!result) return
    const subject = encodeURIComponent('Job Opportunity')
    const body = encodeURIComponent(`Hi,\n\nI thought you'd be great for this job. Apply using my referral link:\n\n${result.referral_link}\n\nGood luck!`)
    window.open(`mailto:?subject=${subject}&body=${body}`)
  }

  const reset = () => {
    setResult(null)
    setJobRoleId('')
    setCandidateEmail('')
    setNotes('')
    setError('')
  }

  if (result) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
              <Check className="w-5 h-5 text-green-600" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900">Referral Link Created!</h2>
          </div>

          <div className="mb-4">
            <p className="text-xs text-gray-500 mb-1">Your referral code</p>
            <p className="font-mono text-lg font-bold text-purple-700 bg-purple-50 px-4 py-2 rounded-lg inline-block">
              {result.referral_code}
            </p>
          </div>

          <div className="mb-5">
            <p className="text-xs text-gray-500 mb-1">Share this link</p>
            <div className="flex gap-2">
              <input
                readOnly
                value={result.referral_link}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm bg-gray-50 text-gray-700 font-mono truncate"
              />
              <button
                onClick={copyLink}
                className="px-3 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition flex items-center gap-1 text-sm whitespace-nowrap"
              >
                {linkCopied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                {linkCopied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 mb-5">
            <button
              onClick={shareViaWhatsApp}
              className="flex-1 min-w-[120px] px-3 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition text-sm font-medium"
            >
              WhatsApp
            </button>
            <button
              onClick={shareViaSMS}
              className="flex-1 min-w-[120px] px-3 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition text-sm font-medium"
            >
              SMS
            </button>
            <button
              onClick={shareViaEmail}
              className="flex-1 min-w-[120px] px-3 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-800 transition text-sm font-medium"
            >
              Share via Email
            </button>
          </div>

          <div className="bg-purple-50 border border-purple-100 rounded-lg px-4 py-3 mb-5 text-sm text-purple-800">
            You'll earn <span className="font-bold">${result.reward_amount.toFixed(2)}</span> when your referral is hired
          </div>

          <button
            onClick={reset}
            className="w-full py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition text-sm font-medium text-gray-700"
          >
            Create Another
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-lg mx-auto">
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-5">Generate a Referral Link</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Job Role ID <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={jobRoleId}
              onChange={e => setJobRoleId(e.target.value)}
              placeholder="e.g. 3f6d1234-..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <p className="text-xs text-gray-400 mt-1">
              Get this from the job posting URL or the Candidate Pipeline page
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Candidate Email <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="email"
              value={candidateEmail}
              onChange={e => setCandidateEmail(e.target.value)}
              placeholder="candidate@example.com"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <p className="text-xs text-gray-400 mt-1">
              Leave blank to share a general link for any candidate
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Notes <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={3}
              placeholder="Any notes about this referral..."
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 text-red-600 text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition font-medium text-sm disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            Generate Referral Link
          </button>
        </form>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 3: Leaderboard
// ---------------------------------------------------------------------------

function LeaderboardTab() {
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([])
  const [allReferrals, setAllReferrals] = useState<AllReferral[]>([])
  const [loadingLb, setLoadingLb] = useState(true)
  const [loadingAll, setLoadingAll] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    const fetchLeaderboard = async () => {
      try {
        const res = await apiClient.get('/referrals/leaderboard')
        setLeaderboard(res.data || [])
      } catch {
        console.error('Failed to fetch leaderboard')
      } finally {
        setLoadingLb(false)
      }
    }
    const fetchAll = async () => {
      try {
        const res = await apiClient.get('/referrals/all')
        setAllReferrals(res.data || [])
      } catch {
        console.error('Failed to fetch all referrals')
      } finally {
        setLoadingAll(false)
      }
    }
    fetchLeaderboard()
    fetchAll()
  }, [])

  const filtered = statusFilter
    ? allReferrals.filter(r => r.status === statusFilter)
    : allReferrals

  return (
    <div className="space-y-8">
      {/* Leaderboard */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Top Referrers</h2>
        </div>
        {loadingLb ? (
          <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-purple-600" /></div>
        ) : leaderboard.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-10">No data yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Rank</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Referrer</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Total Referrals</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Hired</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Total Earned</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {leaderboard.map((entry, idx) => (
                  <tr key={entry.referrer_email} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-lg">{rankEmoji(idx + 1)}</td>
                    <td className="px-4 py-3 text-gray-700">{maskEmail(entry.referrer_email)}</td>
                    <td className="px-4 py-3 text-gray-700">{entry.total_referrals}</td>
                    <td className="px-4 py-3 font-semibold text-green-700">{entry.hired_count}</td>
                    <td className="px-4 py-3 text-purple-700 font-semibold">${entry.total_earned.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* All Referrals */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between flex-wrap gap-3">
          <h2 className="text-lg font-semibold text-gray-900">All Referrals</h2>
          <select
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="PENDING">PENDING</option>
            <option value="APPLIED">APPLIED</option>
            <option value="SHORTLISTED">SHORTLISTED</option>
            <option value="HIRED">HIRED</option>
            <option value="REWARDED">REWARDED</option>
          </select>
        </div>
        {loadingAll ? (
          <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-purple-600" /></div>
        ) : filtered.length === 0 ? (
          <p className="text-gray-500 text-sm text-center py-10">No referrals found</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Code</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Referrer</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Candidate</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Reward</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map(ref => (
                  <tr key={ref.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs text-gray-600">{ref.referral_code}</td>
                    <td className="px-4 py-3 text-gray-600">{maskEmail(ref.referrer_email || '')}</td>
                    <td className="px-4 py-3 text-gray-600">{ref.candidate_email ? maskEmail(ref.candidate_email) : <span className="text-gray-400 italic">—</span>}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusBadgeClass(ref.status)}`}>
                        {ref.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700">${(ref.reward_amount || 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

type Tab = 'my-referrals' | 'create' | 'leaderboard'

const TABS: { id: Tab; label: string }[] = [
  { id: 'my-referrals', label: 'My Referrals' },
  { id: 'create', label: 'Create Link' },
  { id: 'leaderboard', label: 'Leaderboard' },
]

export default function ReferralProgram() {
  const [activeTab, setActiveTab] = useState<Tab>('my-referrals')
  const [toast, setToast] = useState('')

  const showToast = (msg: string) => setToast(msg)

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center">
          <Gift className="w-5 h-5 text-purple-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Referral Program</h1>
          <p className="text-sm text-gray-500">Earn rewards by referring great candidates to open roles</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-6 gap-1">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition -mb-px ${
              activeTab === tab.id
                ? 'border-purple-600 text-purple-700'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'my-referrals' && <MyReferralsTab showToast={showToast} />}
      {activeTab === 'create' && <CreateLinkTab showToast={showToast} />}
      {activeTab === 'leaderboard' && <LeaderboardTab />}

      {/* Toast */}
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}
