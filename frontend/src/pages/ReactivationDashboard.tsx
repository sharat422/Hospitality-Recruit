/**
 * ReactivationDashboard — Discover passive candidates and send reactivation messages.
 */

import { Button } from '@/components/ui/button'
import { Card,CardContent,CardDescription,CardHeader,CardTitle } from '@/components/ui/card'
import { apiClient } from '@/lib/api'
import { useCallback,useEffect,useState } from 'react'

// ─── Types ───────────────────────────────────────────────────────────────────

interface JobRole {
  id: string
  title: string
  location?: string
}

interface PassiveCandidate {
  candidate_id: string
  name: string
  email?: string
  days_since_active: number
  passive_score: number
  match_score: number
  combined_score: number
  suggested_outreach_message: string
  reactivation_sent?: boolean
}

// ─── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({ sent }: { sent?: boolean }) {
  return sent ? (
    <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-green-100 text-green-800">
      Sent
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold bg-gray-100 text-gray-600">
      Not sent
    </span>
  )
}

// ─── Score badge ──────────────────────────────────────────────────────────────

function ScorePill({ score, label }: { score: number; label: string }) {
  const color =
    score >= 70
      ? 'bg-green-50 text-green-700 border-green-200'
      : score >= 45
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-red-50 text-red-700 border-red-200'

  return (
    <div className={`text-center rounded-lg border px-3 py-1.5 ${color}`}>
      <div className="text-lg font-bold">{Math.round(score)}</div>
      <div className="text-xs opacity-75">{label}</div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function ReactivationDashboard() {
  const [jobRoles, setJobRoles] = useState<JobRole[]>([])
  const [selectedRoleId, setSelectedRoleId] = useState<string>('')
  const [candidates, setCandidates] = useState<PassiveCandidate[]>([])
  const [loading, setLoading] = useState(false)
  const [rolesLoading, setRolesLoading] = useState(true)
  const [error, setError] = useState('')
  const [sentIds, setSentIds] = useState<Set<string>>(new Set())
  const [sendingIds, setSendingIds] = useState<Set<string>>(new Set())
  const [bulkSending, setBulkSending] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Load job roles
  useEffect(() => {
    setRolesLoading(true)
    apiClient
      .get('/ai-screening/job-roles')
      .then((res) => {
        const roles = res.data.job_roles || []
        setJobRoles(roles)
        if (roles.length > 0) setSelectedRoleId(roles[0].id)
      })
      .catch(() => setError('Failed to load job roles'))
      .finally(() => setRolesLoading(false))
  }, [])

  // Load passive candidates when role changes
  const loadPassiveCandidates = useCallback(async () => {
    if (!selectedRoleId) return
    setLoading(true)
    setError('')
    setCandidates([])
    setSentIds(new Set())
    setSelectedIds(new Set())
    try {
      const res = await apiClient.get(`/ai-screening/passive-discovery?job_role_id=${selectedRoleId}`)
      setCandidates(res.data.passive_candidates || [])
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load passive candidates')
    } finally {
      setLoading(false)
    }
  }, [selectedRoleId])

  useEffect(() => {
    loadPassiveCandidates()
  }, [loadPassiveCandidates])

  // Send reactivation to single candidate
  const sendSingle = async (candidateId: string) => {
    setSendingIds((prev) => new Set(prev).add(candidateId))
    try {
      await apiClient.post('/ai-screening/reactivation/send', {
        candidate_ids: [candidateId],
        job_role_id: selectedRoleId,
        channel: 'sms',
      })
      setSentIds((prev) => new Set(prev).add(candidateId))
    } catch {
      setError(`Failed to send message to candidate ${candidateId}`)
    } finally {
      setSendingIds((prev) => {
        const next = new Set(prev)
        next.delete(candidateId)
        return next
      })
    }
  }

  // Bulk send
  const sendBulk = async () => {
    const toSend = Array.from(selectedIds).filter((id) => !sentIds.has(id))
    if (toSend.length === 0) return
    setBulkSending(true)
    try {
      await apiClient.post('/ai-screening/reactivation/send', {
        candidate_ids: toSend,
        job_role_id: selectedRoleId,
        channel: 'sms',
      })
      setSentIds((prev) => {
        const next = new Set(prev)
        toSend.forEach((id) => next.add(id))
        return next
      })
      setSelectedIds(new Set())
    } catch {
      setError('Failed to send bulk reactivation messages')
    } finally {
      setBulkSending(false)
    }
  }

  // Toggle selection
  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const selectAll = () => setSelectedIds(new Set(candidates.map((c) => c.candidate_id)))
  const clearAll = () => setSelectedIds(new Set())

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-3xl font-bold">Reactivation Dashboard</h1>
        <p className="mt-1 opacity-90 text-sm">
          Discover passive candidates and send personalized re-engagement messages
        </p>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Job role selector */}
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex flex-wrap gap-4 items-end">
              <div className="min-w-[240px]">
                <label className="block text-xs font-medium text-gray-600 mb-1">Job Role</label>
                {rolesLoading ? (
                  <div className="h-10 bg-gray-100 rounded-md animate-pulse" />
                ) : (
                  <select
                    className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    value={selectedRoleId}
                    onChange={(e) => setSelectedRoleId(e.target.value)}
                  >
                    {jobRoles.length === 0 && <option value="">No job roles found</option>}
                    {jobRoles.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.title}{r.location ? ` — ${r.location}` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <Button
                onClick={loadPassiveCandidates}
                disabled={loading || !selectedRoleId}
                className="bg-purple-600 hover:bg-purple-700 text-white"
              >
                {loading ? 'Loading...' : 'Refresh'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Bulk action bar */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-4 bg-purple-50 border border-purple-200 rounded-lg px-4 py-3">
            <span className="text-sm font-medium text-purple-800">
              {selectedIds.size} selected
            </span>
            <Button
              onClick={sendBulk}
              disabled={bulkSending}
              className="bg-purple-600 hover:bg-purple-700 text-white text-sm py-1.5 px-3"
            >
              {bulkSending ? 'Sending...' : `Send Reactivation (${selectedIds.size})`}
            </Button>
            <button onClick={clearAll} className="text-xs text-purple-600 hover:text-purple-800">
              Clear
            </button>
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Candidates list */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Passive Candidates ({candidates.length})
            </CardTitle>
            <CardDescription>
              Sorted by combined passive + match score. Top candidates are most likely to re-engage.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-24 bg-gray-100 rounded-lg animate-pulse" />
                ))}
              </div>
            ) : candidates.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-gray-500 text-sm">
                  {selectedRoleId
                    ? 'No passive candidates found. Try selecting a different job role.'
                    : 'Select a job role to discover passive candidates.'}
                </p>
              </div>
            ) : (
              <div className="space-y-1">
                {/* Select all row */}
                <div className="flex items-center gap-3 px-3 py-2 border-b">
                  <input
                    type="checkbox"
                    checked={selectedIds.size === candidates.length && candidates.length > 0}
                    onChange={selectedIds.size === candidates.length ? clearAll : selectAll}
                    className="rounded accent-purple-600"
                  />
                  <span className="text-xs text-gray-500">Select all</span>
                </div>

                {candidates.map((c) => {
                  const isSent = sentIds.has(c.candidate_id) || c.reactivation_sent
                  const isSending = sendingIds.has(c.candidate_id)
                  const isSelected = selectedIds.has(c.candidate_id)

                  return (
                    <div
                      key={c.candidate_id}
                      className={`rounded-lg border p-4 transition ${
                        isSelected ? 'border-purple-200 bg-purple-50' : 'hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        {/* Checkbox */}
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(c.candidate_id)}
                          className="mt-1 rounded accent-purple-600 flex-shrink-0"
                        />

                        {/* Info */}
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-3 mb-2">
                            <span className="font-semibold text-gray-900">{c.name}</span>
                            {c.email && (
                              <span className="text-xs text-gray-500">{c.email}</span>
                            )}
                            <StatusBadge sent={isSent} />
                          </div>

                          <div className="text-xs text-gray-500 mb-3">
                            Inactive for {c.days_since_active} day{c.days_since_active !== 1 ? 's' : ''}
                          </div>

                          {/* Score pills */}
                          <div className="flex gap-3 flex-wrap mb-3">
                            <ScorePill score={c.passive_score} label="Passive" />
                            <ScorePill score={c.match_score} label="Match" />
                            <ScorePill score={c.combined_score} label="Combined" />
                          </div>

                          {/* Message preview */}
                          {c.suggested_outreach_message && (
                            <div className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                              <p className="text-xs font-semibold text-gray-500 mb-1">
                                Suggested SMS Message
                              </p>
                              <p className="text-sm text-gray-700 italic">
                                "{c.suggested_outreach_message}"
                              </p>
                              <p className="text-xs text-gray-400 mt-1">
                                {c.suggested_outreach_message.length} / 160 chars
                              </p>
                            </div>
                          )}
                        </div>

                        {/* Send button */}
                        <div className="flex-shrink-0">
                          <Button
                            onClick={() => sendSingle(c.candidate_id)}
                            disabled={isSending || isSent}
                            className={
                              isSent
                                ? 'bg-green-50 text-green-700 border border-green-200 cursor-default text-sm'
                                : 'bg-purple-600 hover:bg-purple-700 text-white text-sm'
                            }
                          >
                            {isSending ? 'Sending...' : isSent ? 'Sent' : 'Send'}
                          </Button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
