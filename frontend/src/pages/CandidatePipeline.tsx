/**
 * CandidatePipeline — Full candidate pipeline view with job role selector,
 * filtering, sorting, and bulk actions.
 */

import { Button } from '@/components/ui/button'
import { Card,CardContent,CardHeader,CardTitle } from '@/components/ui/card'
import { apiClient } from '@/lib/api'
import { useCallback,useEffect,useState } from 'react'

// ─── Types ───────────────────────────────────────────────────────────────────

interface JobRole {
  id: string
  title: string
  location?: string
  property_type?: string
}

interface CandidateMatch {
  candidate_id: string
  name: string
  email?: string
  overall_score: number
  skill_match_score: number
  experience_score: number
  source?: string
  status?: string
  job_role_id?: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 75
      ? 'bg-green-100 text-green-800'
      : score >= 50
      ? 'bg-amber-100 text-amber-800'
      : 'bg-red-100 text-red-800'
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-sm font-semibold ${color}`}>
      {Math.round(score)}
    </span>
  )
}

function EmptyState() {
  return (
    <div className="text-center py-16">
      <div className="mx-auto w-16 h-16 rounded-full bg-purple-50 flex items-center justify-center mb-4">
        <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-1">No candidates yet</h3>
      <p className="text-sm text-gray-500">
        Select a job role and upload resumes to see matched candidates here.
      </p>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function CandidatePipeline() {
  const [jobRoles, setJobRoles] = useState<JobRole[]>([])
  const [selectedRoleId, setSelectedRoleId] = useState<string>('')
  const [candidates, setCandidates] = useState<CandidateMatch[]>([])
  const [loading, setLoading] = useState(false)
  const [rolesLoading, setRolesLoading] = useState(true)
  const [error, setError] = useState('')

  // Filters & sorting
  const [sortBy, setSortBy] = useState<'score' | 'name' | 'date'>('score')
  const [minScore, setMinScore] = useState(0)
  const [sourceFilter, setSourceFilter] = useState<string>('all')
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

  // Load candidates for selected role
  const loadCandidates = useCallback(async () => {
    if (!selectedRoleId) return
    setLoading(true)
    setError('')
    try {
      // Fetch candidate_matches for this role from candidates endpoint
      const res = await apiClient.get(`/candidates?job_role_id=${selectedRoleId}`)
      setCandidates(res.data.candidates || [])
    } catch {
      // Fallback: fetch all candidates from supabase via existing endpoint
      try {
        const res = await apiClient.get('/candidates')
        setCandidates(res.data.candidates || [])
      } catch {
        setError('Failed to load candidates')
      }
    } finally {
      setLoading(false)
    }
  }, [selectedRoleId])

  useEffect(() => {
    loadCandidates()
  }, [loadCandidates])

  // Filter and sort candidates
  const filtered = candidates
    .filter((c) => (c.overall_score ?? 0) >= minScore)
    .filter((c) => sourceFilter === 'all' || c.source === sourceFilter)
    .sort((a, b) => {
      if (sortBy === 'score') return (b.overall_score ?? 0) - (a.overall_score ?? 0)
      if (sortBy === 'name') return (a.name || '').localeCompare(b.name || '')
      return 0
    })

  // Bulk selection
  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }
  const selectAll = () => setSelectedIds(new Set(filtered.map((c) => c.candidate_id)))
  const clearAll = () => setSelectedIds(new Set())

  const handleBulkReactivation = async () => {
    if (!selectedRoleId || selectedIds.size === 0) return
    try {
      await apiClient.post('/ai-screening/reactivation/send', {
        candidate_ids: Array.from(selectedIds),
        job_role_id: selectedRoleId,
        channel: 'sms',
      })
      alert(`Reactivation messages sent to ${selectedIds.size} candidates`)
      setSelectedIds(new Set())
    } catch {
      setError('Failed to send reactivation messages')
    }
  }

  const sources = ['all', ...Array.from(new Set(candidates.map((c) => c.source).filter(Boolean)))] as string[]

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-3xl font-bold">Candidate Pipeline</h1>
        <p className="mt-1 opacity-90 text-sm">
          AI-matched candidates ranked by fit score
        </p>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Job role selector + filters */}
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex flex-wrap gap-4 items-end">
              {/* Job role dropdown */}
              <div className="min-w-[220px]">
                <label className="block text-xs font-medium text-gray-600 mb-1">Job Role</label>
                {rolesLoading ? (
                  <div className="h-10 bg-gray-100 rounded-md animate-pulse" />
                ) : (
                  <select
                    className="w-full h-10 rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    value={selectedRoleId}
                    onChange={(e) => setSelectedRoleId(e.target.value)}
                  >
                    {jobRoles.length === 0 && (
                      <option value="">No job roles found</option>
                    )}
                    {jobRoles.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.title}{r.location ? ` — ${r.location}` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Sort */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Sort by</label>
                <select
                  className="h-10 rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'score' | 'name' | 'date')}
                >
                  <option value="score">Score</option>
                  <option value="name">Name</option>
                  <option value="date">Date</option>
                </select>
              </div>

              {/* Source filter */}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Source</label>
                <select
                  className="h-10 rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={sourceFilter}
                  onChange={(e) => setSourceFilter(e.target.value)}
                >
                  {sources.map((s) => (
                    <option key={s} value={s}>{s === 'all' ? 'All Sources' : s}</option>
                  ))}
                </select>
              </div>

              {/* Score range */}
              <div className="flex-1 min-w-[180px]">
                <label className="block text-xs font-medium text-gray-600 mb-1">
                  Min Score: <span className="text-purple-600 font-bold">{minScore}</span>
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  className="w-full h-2 accent-purple-600"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Bulk action bar */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-4 bg-purple-50 border border-purple-200 rounded-lg px-4 py-3">
            <span className="text-sm font-medium text-purple-800">
              {selectedIds.size} candidate{selectedIds.size !== 1 ? 's' : ''} selected
            </span>
            <Button
              onClick={handleBulkReactivation}
              className="bg-purple-600 hover:bg-purple-700 text-white text-sm py-1.5 px-3"
            >
              Send Reactivation
            </Button>
            <button
              onClick={clearAll}
              className="text-xs text-purple-600 hover:text-purple-800"
            >
              Clear selection
            </button>
          </div>
        )}

        {error && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
            {error}
          </div>
        )}

        {/* Candidates table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Candidates ({filtered.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-12 bg-gray-100 rounded-md animate-pulse" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <EmptyState />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="pb-3 pr-3 w-8">
                        <input
                          type="checkbox"
                          checked={selectedIds.size === filtered.length && filtered.length > 0}
                          onChange={selectedIds.size === filtered.length ? clearAll : selectAll}
                          className="rounded accent-purple-600"
                        />
                      </th>
                      <th className="pb-3 pr-4">Name</th>
                      <th className="pb-3 pr-4">Email</th>
                      <th className="pb-3 pr-4">Overall Score</th>
                      <th className="pb-3 pr-4">Skill Match</th>
                      <th className="pb-3 pr-4">Experience</th>
                      <th className="pb-3 pr-4">Source</th>
                      <th className="pb-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((c) => (
                      <tr key={c.candidate_id} className="border-b hover:bg-gray-50">
                        <td className="py-3 pr-3">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(c.candidate_id)}
                            onChange={() => toggleSelect(c.candidate_id)}
                            className="rounded accent-purple-600"
                          />
                        </td>
                        <td className="py-3 pr-4 font-medium text-gray-900">
                          {c.name || 'Unknown'}
                        </td>
                        <td className="py-3 pr-4 text-gray-500 text-xs">
                          {c.email || '—'}
                        </td>
                        <td className="py-3 pr-4">
                          <ScoreBadge score={c.overall_score ?? 0} />
                        </td>
                        <td className="py-3 pr-4 text-gray-600">
                          {Math.round(c.skill_match_score ?? 0)}
                        </td>
                        <td className="py-3 pr-4 text-gray-600">
                          {Math.round(c.experience_score ?? 0)}
                        </td>
                        <td className="py-3 pr-4">
                          {c.source ? (
                            <span className="text-xs bg-blue-50 text-blue-700 rounded-full px-2 py-0.5">
                              {c.source}
                            </span>
                          ) : '—'}
                        </td>
                        <td className="py-3">
                          <div className="flex gap-2">
                            <button
                              className="text-xs text-green-700 hover:text-green-900 font-medium"
                              onClick={() => {/* shortlist handler */}}
                            >
                              Shortlist
                            </button>
                            <button
                              className="text-xs text-red-600 hover:text-red-800 font-medium"
                              onClick={() => {/* reject handler */}}
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
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
