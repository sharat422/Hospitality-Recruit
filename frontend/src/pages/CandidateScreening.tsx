import {
AlertTriangle,
ArrowRight,
Brain,
Briefcase,
CheckCircle2,
ChevronDown,
ChevronRight,
Clock,
DollarSign,
Eye,
EyeOff,
Languages,
MapPin,
Play,
Shuffle,
Star,
Users,
XCircle,
Zap,
} from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'
import { supabase } from '../lib/supabase'

// ─── Types ──────────────────────────────────────────────────────────────────

interface Job {
  id: string
  title: string
  department: string
  property_name: string
}

interface ScreeningResult {
  screening_result_id?: string
  rank: number
  candidate_id: string
  blind_id: string
  display_name: string
  total_score: number
  skill_score: number
  skill_explanation: string
  experience_score: number
  experience_explanation: string
  language_score: number
  language_explanation: string
  location_score: number
  location_explanation: string
  salary_score: number
  salary_explanation: string
  availability_score: number
  availability_explanation: string
  cross_industry_match: boolean
  cross_industry_source: string
  cross_industry_target: string
  cross_industry_note: string
  strengths: string[]
  gaps: string[]
  overall_recommendation: 'shortlist' | 'consider' | 'reject'
  auto_shortlisted: boolean
  recruiter_override?: 'shortlist' | 'consider' | 'reject' | null
  override_reason?: string
  explanation_source?: string
  scoring_version?: string
  recommendation_reasons?: string[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 80) return 'bg-green-500'
  if (score >= 60) return 'bg-yellow-400'
  if (score >= 40) return 'bg-orange-400'
  return 'bg-red-400'
}

function scoreTextColor(score: number): string {
  if (score >= 80) return 'text-green-700'
  if (score >= 60) return 'text-yellow-700'
  if (score >= 40) return 'text-orange-700'
  return 'text-red-700'
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-green-50 border-green-200'
  if (score >= 60) return 'bg-yellow-50 border-yellow-200'
  if (score >= 40) return 'bg-orange-50 border-orange-200'
  return 'bg-red-50 border-red-200'
}

function recommendationBadge(r: string) {
  if (r === 'shortlist') return <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-700">Shortlist</span>
  if (r === 'reject')    return <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-red-100 text-red-700">Reject</span>
  return                        <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-yellow-100 text-yellow-700">Consider</span>
}

function ScoreBar({ label, score, explanation, icon }: {
  label: string; score: number; explanation: string; icon: React.ReactNode
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-medium text-gray-700">
          {icon}{label}
        </span>
        <span className={`text-xs font-bold ${scoreTextColor(score)}`}>{Math.round(score)}</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${scoreColor(score)}`}
          style={{ width: `${score}%` }}
        />
      </div>
      {explanation && (
        <p className="text-xs text-gray-500 leading-snug">{explanation}</p>
      )}
    </div>
  )
}

// ─── Mock seed data (used when no API data available) ───────────────────────



// ─── Component ───────────────────────────────────────────────────────────────

export default function CandidateScreening() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selectedJobId, setSelectedJobId] = useState('')
  const [blindMode, setBlindMode] = useState(false)
  const [screenAll, setScreenAll] = useState(false)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<ScreeningResult[]>([])
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'shortlist' | 'consider' | 'reject'>('all')
  const [shortlistStatus, setShortlistStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [weights, setWeights] = useState<Record<string, number>>({ skill: .30, experience: .25, location: .15, language: .10, salary: .10, availability: .10 })

  // Fetch jobs from API (Smart Recruitment jobs)
  useEffect(() => {
    const load = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) return
        const res = await fetch('/api/v1/recruit/jobs', {
          headers: { Authorization: `Bearer ${session.access_token}` },
        })
        if (res.ok) {
          const json = await res.json()
          const fetched: Job[] = (json.jobs || []).map((j: Record<string, string>) => ({
            id: j.id, title: j.title, department: j.department, property_name: j.property_name,
          }))
          if (fetched.length > 0) {
            setJobs(fetched)
            setSelectedJobId(fetched[0].id)
          }
        }
      } catch { setError('Unable to load jobs') }
    }
    load()
  }, [])

  useEffect(() => {
    if (!selectedJobId) return
    const loadWeights = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) return
      const res = await fetch(`/api/v1/ai-screening/screen/weights?job_id=${selectedJobId}`, { headers: { Authorization: `Bearer ${session.access_token}` } })
      if (res.ok) setWeights((await res.json()).weights)
    }
    void loadWeights()
  }, [selectedJobId])

  const runScreening = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) throw new Error('Not authenticated')
      const res = await fetch(`/api/v1/ai-screening/screen/job/${selectedJobId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ blind_mode: blindMode, screen_all: screenAll }),
      })
      if (!res.ok) throw new Error(`Screening failed: ${res.status}`)
      const json = await res.json()
      setResults(json.results || [])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Screening failed')
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [selectedJobId, blindMode, screenAll])

  const runShortlist = useCallback(async () => {
    const reason = window.prompt('Why are you confirming these candidates for shortlist?')
    if (!reason || reason.trim().length < 5) return
    if (!window.confirm('Confirm shortlist? AI recommendations are advisory; you remain responsible for this decision.')) return
    setShortlistStatus('Running...')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) throw new Error('Not authenticated')
      const params = new URLSearchParams({ top_n: '10', confirmed: 'true', reason: reason.trim() })
      const res = await fetch(`/api/v1/ai-screening/screen/job/${selectedJobId}/shortlist?${params}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      if (!res.ok) throw new Error(`Shortlist failed: ${res.status}`)
      const json = await res.json()
      setShortlistStatus(`Shortlisted ${json.shortlisted ?? 0} candidates`)
      // Mark locally
      setResults(prev =>
        prev.map((r, i) => ({ ...r, auto_shortlisted: i < 10 }))
      )
    } catch (e: unknown) {
      setShortlistStatus(null)
      setError(e instanceof Error ? e.message : 'Shortlist confirmation failed')
    }
  }, [selectedJobId])

  const overrideRecommendation = useCallback(async (result: ScreeningResult) => {
    if (!result.screening_result_id) return setError('Save and reload screening results before overriding')
    const recommendation = window.prompt('Override recommendation: shortlist, consider, or reject', result.recruiter_override || result.overall_recommendation)?.toLowerCase()
    if (!recommendation || !['shortlist', 'consider', 'reject'].includes(recommendation)) return
    const reason = window.prompt('Reason for recruiter override (required)')
    if (!reason || reason.trim().length < 5) return
    const { data: { session } } = await supabase.auth.getSession()
    if (!session) return
    const res = await fetch(`/api/v1/ai-screening/screen/results/${result.screening_result_id}/override`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session.access_token}` },
      body: JSON.stringify({ recommendation, reason }),
    })
    if (!res.ok) return setError(`Override failed: ${res.status}`)
    setResults(current => current.map(item => item.candidate_id === result.candidate_id ? { ...item, recruiter_override: recommendation as ScreeningResult['recruiter_override'], override_reason: reason } : item))
  }, [])

  const filtered = results.filter(r =>
    filter === 'all' ? true : r.overall_recommendation === filter
  )


  const stats = {
    total:     results.length,
    shortlist: results.filter(r => r.overall_recommendation === 'shortlist').length,
    consider:  results.filter(r => r.overall_recommendation === 'consider').length,
    reject:    results.filter(r => r.overall_recommendation === 'reject').length,
    crossIndustry: results.filter(r => r.cross_industry_match).length,
    avgScore:  results.length ? Math.round(results.reduce((s, r) => s + r.total_score, 0) / results.length) : 0,
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Brain className="w-6 h-6 text-purple-600" />
            AI Candidate Screening
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Deterministic 6-dimension scoring · AI explanations · Recruiter-controlled decisions
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4">
        <div className="flex flex-wrap gap-3 items-end">
          {/* Job selector */}
          <div className="flex-1 min-w-[220px]">
            <label className="block text-xs font-medium text-gray-700 mb-1">Select Job</label>
            <select
              value={selectedJobId}
              onChange={e => setSelectedJobId(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            >
              {jobs.map(j => (
                <option key={j.id} value={j.id}>
                  {j.title} — {j.property_name}
                </option>
              ))}
            </select>
          </div>

          {/* Toggles */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <div
              onClick={() => setBlindMode(!blindMode)}
              className={`w-10 h-5 rounded-full transition-colors relative ${blindMode ? 'bg-purple-600' : 'bg-gray-300'}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${blindMode ? 'left-5' : 'left-0.5'}`} />
            </div>
            <span className="text-sm text-gray-700 flex items-center gap-1">
              {blindMode ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              Blind Mode
            </span>
          </label>

          <label className="flex items-center gap-2 cursor-pointer select-none">
            <div
              onClick={() => setScreenAll(!screenAll)}
              className={`w-10 h-5 rounded-full transition-colors relative ${screenAll ? 'bg-purple-600' : 'bg-gray-300'}`}
            >
              <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all ${screenAll ? 'left-5' : 'left-0.5'}`} />
            </div>
            <span className="text-sm text-gray-700">Screen All Org Candidates</span>
          </label>

          {/* Buttons */}
          <button
            onClick={runScreening}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-60 transition"
          >
            <Play className="w-4 h-4" />
            {loading ? 'Screening...' : 'Run Screening'}
          </button>

          <button
            onClick={runShortlist}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 transition"
          >
            <Star className="w-4 h-4" />
            Confirm Top 10
          </button>
        </div>

        {blindMode && (
          <div className="flex items-start gap-2 bg-purple-50 border border-purple-200 rounded-lg p-3 text-sm text-purple-800">
            <EyeOff className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>
              <strong>Blind Screening ON</strong> — Name, photo, address, and gender indicators are
              hidden from scoring. Candidates shown as anonymous IDs (e.g. C-A3F7B2).
            </span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
            <AlertTriangle className="w-4 h-4" />
            {error} — showing demo data
          </div>
        )}

        {shortlistStatus && (
          <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg p-3">
            <CheckCircle2 className="w-4 h-4" />
            {shortlistStatus}
          </div>
        )}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { label: 'Screened',      value: stats.total,          color: 'text-gray-800',  bg: 'bg-gray-50',    border: 'border-gray-200' },
          { label: 'Avg Score',     value: `${stats.avgScore}%`, color: 'text-purple-700', bg: 'bg-purple-50', border: 'border-purple-200' },
          { label: 'Shortlist',     value: stats.shortlist,       color: 'text-green-700', bg: 'bg-green-50',   border: 'border-green-200' },
          { label: 'Consider',      value: stats.consider,        color: 'text-yellow-700', bg: 'bg-yellow-50', border: 'border-yellow-200' },
          { label: 'Reject',        value: stats.reject,          color: 'text-red-700',   bg: 'bg-red-50',     border: 'border-red-200' },
          { label: 'Cross-Industry', value: stats.crossIndustry,  color: 'text-blue-700',  bg: 'bg-blue-50',    border: 'border-blue-200' },
        ].map(s => (
          <div key={s.label} className={`${s.bg} border ${s.border} rounded-xl p-3 text-center`}>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-gray-500 mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2">
        {(['all', 'shortlist', 'consider', 'reject'] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition capitalize ${
              filter === f
                ? 'bg-purple-600 text-white'
                : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'
            }`}
          >
            {f === 'all' ? `All (${stats.total})` : `${f.charAt(0).toUpperCase() + f.slice(1)} (${stats[f as keyof typeof stats]})`}
          </button>
        ))}
      </div>

      {/* Screening leaderboard */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {/* Table header */}
        <div className="grid grid-cols-[40px_1fr_80px_repeat(6,56px)_90px_80px] gap-2 px-4 py-3 bg-gray-50 border-b border-gray-200 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <div>#</div>
          <div>Candidate</div>
          <div className="text-center">Total</div>
          <div className="text-center" title="Skill Match"><Briefcase className="w-3.5 h-3.5 mx-auto" /></div>
          <div className="text-center" title="Experience"><Users className="w-3.5 h-3.5 mx-auto" /></div>
          <div className="text-center" title="Language"><Languages className="w-3.5 h-3.5 mx-auto" /></div>
          <div className="text-center" title="Location"><MapPin className="w-3.5 h-3.5 mx-auto" /></div>
          <div className="text-center" title="Salary"><DollarSign className="w-3.5 h-3.5 mx-auto" /></div>
          <div className="text-center" title="Availability"><Clock className="w-3.5 h-3.5 mx-auto" /></div>
          <div>Status</div>
          <div></div>
        </div>

        {filtered.length === 0 && (
          <div className="py-12 text-center text-gray-400 text-sm">
            No candidates match this filter.
          </div>
        )}

        {filtered.map(r => {
          const isExpanded = expandedId === r.candidate_id
          const nameDisplay = blindMode ? r.blind_id : (r.display_name || r.blind_id)
          return (
            <React.Fragment key={r.candidate_id}>
              {/* Row */}
              <div
                className={`grid grid-cols-[40px_1fr_80px_repeat(6,56px)_90px_80px] gap-2 px-4 py-3 items-center border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition ${
                  r.auto_shortlisted ? 'bg-green-50/30' : ''
                }`}
                onClick={() => setExpandedId(isExpanded ? null : r.candidate_id)}
              >
                {/* Rank */}
                <div className="text-sm font-bold text-gray-400">#{r.rank}</div>

                {/* Candidate */}
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900 truncate">{nameDisplay}</span>
                    {r.auto_shortlisted && <Star className="w-3.5 h-3.5 text-yellow-500 flex-shrink-0" />}
                    {r.cross_industry_match && (
                      <span className="px-1.5 py-0.5 text-xs rounded bg-blue-100 text-blue-700 flex-shrink-0 flex items-center gap-1">
                        <Shuffle className="w-2.5 h-2.5" />
                        {r.cross_industry_source}
                      </span>
                    )}
                  </div>
                  {!blindMode && r.blind_id && (
                    <div className="text-xs text-gray-400">{r.blind_id}</div>
                  )}
                </div>

                {/* Total score */}
                <div className="text-center">
                  <span className={`text-sm font-bold ${scoreTextColor(r.total_score)}`}>
                    {Math.round(r.total_score)}
                  </span>
                  <div className="h-1.5 bg-gray-100 rounded-full mt-1 overflow-hidden">
                    <div className={`h-full ${scoreColor(r.total_score)} rounded-full`} style={{ width: `${r.total_score}%` }} />
                  </div>
                </div>

                {/* 6 mini-scores */}
                {[r.skill_score, r.experience_score, r.language_score, r.location_score, r.salary_score, r.availability_score].map((s, i) => (
                  <div key={i} className="text-center">
                    <div className={`text-xs font-semibold ${scoreTextColor(s)}`}>{Math.round(s)}</div>
                    <div className="h-1 bg-gray-100 rounded-full mt-1 overflow-hidden">
                      <div className={`h-full ${scoreColor(s)} rounded-full`} style={{ width: `${s}%` }} />
                    </div>
                  </div>
                ))}

                {/* Recommendation */}
                <div>{recommendationBadge(r.overall_recommendation)}</div>

                {/* Expand */}
                <div className="flex justify-end">
                  {isExpanded
                    ? <ChevronDown className="w-4 h-4 text-gray-400" />
                    : <ChevronRight className="w-4 h-4 text-gray-400" />
                  }
                </div>
              </div>

              {/* Expanded detail panel */}
              {isExpanded && (
                <div className={`border-b border-gray-100 px-6 py-5 ${scoreBg(r.total_score)}`}>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    {/* Left: 6 dimension bars */}
                    <div className="space-y-4">
                      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Score Breakdown</h3>
                      <ScoreBar label="Skill Match"   score={r.skill_score}        explanation={r.skill_explanation}        icon={<Briefcase className="w-3.5 h-3.5" />} />
                      <ScoreBar label="Experience"    score={r.experience_score}   explanation={r.experience_explanation}   icon={<Users className="w-3.5 h-3.5" />} />
                      <ScoreBar label="Language Fit"  score={r.language_score}     explanation={r.language_explanation}     icon={<Languages className="w-3.5 h-3.5" />} />
                      <ScoreBar label="Location Fit"  score={r.location_score}     explanation={r.location_explanation}     icon={<MapPin className="w-3.5 h-3.5" />} />
                      <ScoreBar label="Salary Fit"    score={r.salary_score}       explanation={r.salary_explanation}       icon={<DollarSign className="w-3.5 h-3.5" />} />
                      <ScoreBar label="Availability"  score={r.availability_score} explanation={r.availability_explanation} icon={<Clock className="w-3.5 h-3.5" />} />
                    </div>

                    {/* Right: strengths / gaps / cross-industry */}
                    <div className="space-y-4">
                      {/* Cross-industry */}
                      {r.cross_industry_match && (
                        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 space-y-1">
                          <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-700">
                            <Shuffle className="w-3.5 h-3.5" />
                            Cross-Industry Match
                          </div>
                          <div className="text-xs text-blue-800">
                            <span className="font-medium capitalize">{r.cross_industry_source}</span>
                            {r.cross_industry_target && (
                              <> <ArrowRight className="w-3 h-3 inline" /> {r.cross_industry_target}</>
                            )}
                          </div>
                          {r.cross_industry_note && (
                            <p className="text-xs text-blue-700 leading-snug">{r.cross_industry_note}</p>
                          )}
                        </div>
                      )}

                      {/* Strengths */}
                      {r.strengths.length > 0 && (
                        <div>
                          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Strengths</h3>
                          <div className="flex flex-wrap gap-1.5">
                            {r.strengths.map((s, i) => (
                              <span key={i} className="flex items-center gap-1 px-2 py-0.5 text-xs bg-green-100 text-green-800 rounded-full">
                                <CheckCircle2 className="w-3 h-3" />{s}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Gaps */}
                      {r.gaps.length > 0 && (
                        <div>
                          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Gaps</h3>
                          <div className="flex flex-wrap gap-1.5">
                            {r.gaps.map((g, i) => (
                              <span key={i} className="flex items-center gap-1 px-2 py-0.5 text-xs bg-red-100 text-red-800 rounded-full">
                                <XCircle className="w-3 h-3" />{g}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Recommendation */}
                      <div className="flex items-center gap-3 pt-2">
                        <div className="flex items-center gap-1.5">
                          <Zap className="w-4 h-4 text-purple-600" />
                          <span className="text-sm font-medium text-gray-700">Deterministic recommendation:</span>
                        </div>
                        {recommendationBadge(r.recruiter_override || r.overall_recommendation)}
                      </div>
                      <p className="text-xs text-gray-500">Advisory only · {r.scoring_version || 'deterministic-v2'} · Explanation: {r.explanation_source || 'deterministic'}</p>
                      {r.recruiter_override && <p className="rounded bg-amber-50 p-2 text-xs text-amber-800">Recruiter override: {r.recruiter_override}. {r.override_reason}</p>}
                      <button onClick={() => void overrideRecommendation(r)} className="min-h-10 rounded-md border px-3 text-xs font-semibold text-gray-700">Override recommendation</button>
                    </div>
                  </div>
                </div>
              )}
            </React.Fragment>
          )
        })}
      </div>

      {/* Weights legend */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3 flex items-center gap-1.5">
          <Brain className="w-3.5 h-3.5" />Scoring Weights
        </h3>
        <div className="flex flex-wrap gap-3">
          {[
            { label: 'Skill Match', w: `${Math.round(weights.skill * 100)}%`, color: 'bg-purple-500' },
            { label: 'Experience', w: `${Math.round(weights.experience * 100)}%`, color: 'bg-blue-500' },
            { label: 'Location Fit', w: `${Math.round(weights.location * 100)}%`, color: 'bg-green-500' },
            { label: 'Language Fit', w: `${Math.round(weights.language * 100)}%`, color: 'bg-yellow-500' },
            { label: 'Salary Fit', w: `${Math.round(weights.salary * 100)}%`, color: 'bg-orange-500' },
            { label: 'Availability', w: `${Math.round(weights.availability * 100)}%`, color: 'bg-red-400' },
          ].map(w => (
            <div key={w.label} className="flex items-center gap-2 text-xs text-gray-600">
              <div className={`w-3 h-3 rounded-sm ${w.color}`} />
              {w.label} <span className="font-bold text-gray-800">{w.w}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
