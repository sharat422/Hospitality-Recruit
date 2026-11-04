/**
 * Smart Recruitment Dashboard — Indian hotel hiring.
 * Tabs: Jobs | Pipeline | Candidates | Analytics
 * Mobile-first, bilingual (Hindi + English labels).
 */

import { apiClient } from '@/lib/api';
import { useProperty } from '@/lib/PropertyContext';
import {
AlertCircle,
ArrowRight,
BarChart2,
Briefcase,
Building2,
CheckCircle2,
ChevronDown,
Clock,
Copy,
Download,
Edit3,
ExternalLink,Eye,
IndianRupee,
LockKeyhole,
MapPin,
MessageSquare,
Phone,
Plus,
QrCode,
RefreshCw,
RotateCcw,
Search,
Send,
Share2,
ThumbsUp,
Users,
XCircle,
Zap
} from 'lucide-react';
import React,{ useCallback,useEffect,useRef,useState } from 'react';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface Job {
  id: string; title: string; property_name?: string; department?: string
  location_city?: string; location_state?: string
  status: string; is_urgent: boolean; openings_count: number
  salary_min_inr?: number; salary_max_inr?: number
  experience_min_years?: number; source_stats?: Record<string, number>
  apply_url?: string; qr_url?: string; created_at: string
  jd_english?: string; jd_hindi?: string
  approval_status?: string; property_id?: string; department_id?: string
  hiring_manager_id?: string; recruiter_id?: string; urgency_level?: string
  pipeline_counts?: Record<string, number>; total_applicants?: number
}

interface CandidateCard {
  id: string; name: string; phone?: string; email?: string
  source: string; source_detail?: string; stage: string
  qualified: boolean; score?: number; applied_via_qr: boolean
  offer_salary?: number; rejection_reason?: string; applied_at?: string
}

interface Pipeline { [stage: string]: CandidateCard[] }

interface RoleTemplate {
  role_key: string; display_name: string; display_name_hindi?: string
  category: string; department?: string
  jd_english: string; jd_hindi: string
  required_skills?: string[]; preferred_certs?: string[]
  min_experience_years?: number; salary_min_inr?: number; salary_max_inr?: number
}

const STAGES = [
  { key: 'applied',   label: 'Applied',   labelHi: 'आवेदित',    color: 'blue'   },
  { key: 'screened',  label: 'Screened',  labelHi: 'स्क्रीन',   color: 'purple' },
  { key: 'shortlisted', label: 'Shortlisted', labelHi: 'शॉर्टलिस्ट', color: 'purple' },
  { key: 'interview', label: 'Interview', labelHi: 'इंटरव्यू',  color: 'amber'  },
  { key: 'selected', label: 'Selected', labelHi: 'चयनित', color: 'amber' },
  { key: 'offer',     label: 'Offer',     labelHi: 'ऑफर',       color: 'green'  },
  { key: 'offer_accepted', label: 'Offer Accepted', labelHi: 'ऑफर स्वीकार', color: 'green' },
  { key: 'onboarding', label: 'Onboarding', labelHi: 'ऑनबोर्डिंग', color: 'teal' },
  { key: 'hired',     label: 'Hired',     labelHi: 'नियुक्त',   color: 'teal'   },
]

const SOURCES: Record<string, { label: string; color: string }> = {
  naukri:       { label: 'Naukri',     color: 'bg-blue-100   text-blue-700'   },
  apna:         { label: 'Apna',       color: 'bg-green-100  text-green-700'  },
  workindia:    { label: 'WorkIndia',  color: 'bg-orange-100 text-orange-700' },
  shine:        { label: 'Shine',      color: 'bg-yellow-100 text-yellow-700' },
  indeed_india: { label: 'Indeed',     color: 'bg-indigo-100 text-indigo-700' },
  linkedin:     { label: 'LinkedIn',    color: 'bg-blue-100 text-blue-700' },
  hospitality_board: { label: 'Hospitality Board', color: 'bg-cyan-100 text-cyan-700' },
  whatsapp:     { label: 'WhatsApp',   color: 'bg-green-100  text-green-700'  },
  referral:     { label: 'Referral',   color: 'bg-pink-100   text-pink-700'   },
  walk_in:      { label: 'Walk-in',    color: 'bg-gray-100   text-gray-700'   },
  qr_code:      { label: 'QR Code',   color: 'bg-purple-100 text-purple-700' },
  job_fair:     { label: 'Job Fair',  color: 'bg-teal-100   text-teal-700'   },
  placement:    { label: 'Placement', color: 'bg-amber-100  text-amber-700'  },
  other:        { label: 'Other',     color: 'bg-gray-100   text-gray-700'   },
}

const STAGE_COLORS: Record<string, string> = {
  blue:   'bg-blue-50   border-blue-200   text-blue-800',
  purple: 'bg-purple-50 border-purple-200 text-purple-800',
  amber:  'bg-amber-50  border-amber-200  text-amber-800',
  green:  'bg-green-50  border-green-200  text-green-800',
  teal:   'bg-teal-50   border-teal-200   text-teal-800',
}

// ─────────────────────────────────────────────────────────────────────────────
// Utility components
// ─────────────────────────────────────────────────────────────────────────────

function SourceBadge({ source }: { source: string }) {
  const s = SOURCES[source] ?? SOURCES.other
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${s.color}`}>
      {s.label}
    </span>
  )
}

function UrgentBadge() {
  return (
    <span className="text-[10px] font-bold bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full flex items-center gap-0.5">
      <Zap className="w-2.5 h-2.5" /> Urgent
    </span>
  )
}

function SalaryRange({ min, max }: { min?: number; max?: number }) {
  if (!min && !max) return null
  const fmt = (n: number) => `₹${(n / 1000).toFixed(0)}k`
  return (
    <span className="flex items-center gap-1 text-xs text-gray-600">
      <IndianRupee className="w-3 h-3" />
      {min && max ? `${fmt(min)}–${fmt(max)}` : min ? `From ${fmt(min)}` : `Up to ${fmt(max!)}`}
    </span>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

type Tab = 'jobs' | 'pipeline' | 'candidates' | 'analytics'

export function SmartRecruitment() {
  const [tab,          setTab]          = useState<Tab>('jobs')
  const [jobs,         setJobs]         = useState<Job[]>([])
  const [pipeline,     setPipeline]     = useState<Pipeline>({})
  const [selectedJob,  setSelectedJob]  = useState<string>('')
  const [templates,    setTemplates]    = useState<RoleTemplate[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState('')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [searchQ,      setSearchQ]      = useState('')
  const [filterStatus, setFilterStatus] = useState('open')

  // Bulk selection
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [j, t] = await Promise.all([
        apiClient.get(`/recruit/jobs?status=${filterStatus}`),
        apiClient.get('/recruit/role-templates'),
      ])
      setJobs(j.data || [])
      setTemplates(t.data || [])
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Failed to load')
    } finally {
      setLoading(false) }
  }, [filterStatus])

  const loadPipeline = useCallback(async (jobId?: string) => {
    try {
      const url = `/recruit/pipeline${jobId ? `?job_id=${jobId}` : ''}`
      const { data } = await apiClient.get(url)
      setPipeline(data)
    } catch { setPipeline({}) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (tab === 'pipeline') loadPipeline(selectedJob || undefined)
  }, [tab, selectedJob, loadPipeline])

  const filteredJobs = jobs.filter(j =>
    !searchQ ||
    j.title.toLowerCase().includes(searchQ.toLowerCase()) ||
    (j.property_name || '').toLowerCase().includes(searchQ.toLowerCase())
  )

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const bulkAction = async (action: string, extra: Record<string, unknown> = {}) => {
    if (!selected.size) return
    try {
      await apiClient.post('/recruit/bulk-action', {
        candidate_ids: [...selected],
        action,
        ...extra,
      })
      setSelected(new Set())
      if (tab === 'pipeline') loadPipeline(selectedJob || undefined)
    } catch (e: any) {
      alert(e.response?.data?.detail ?? `${action} failed`)
    }
  }

  const moveCandidate = async (candidateId: string, newStage: string) => {
    try {
      await apiClient.patch(`/recruit/candidates/${candidateId}/stage`, { new_stage: newStage })
      loadPipeline(selectedJob || undefined)
    } catch (e: any) {
      alert(e.response?.data?.detail ?? 'Stage update failed')
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Briefcase className="w-6 h-6 text-purple-600" /> Smart Recruitment
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Indian hotel hiring — बेहतर भर्ती, तेज़ परिणाम
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            className="p-2 text-gray-500 hover:text-purple-600 hover:bg-purple-50 rounded-xl transition"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700
                       text-white text-sm font-semibold rounded-xl transition"
          >
            <Plus className="w-4 h-4" /> New Job
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-100 rounded-xl px-4 py-3 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 inline mr-2" />{error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl w-fit">
        {([
          { key: 'jobs',      label: 'Jobs',     icon: <Briefcase className="w-3.5 h-3.5" /> },
          { key: 'pipeline',  label: 'Pipeline', icon: <ArrowRight className="w-3.5 h-3.5" /> },
          { key: 'candidates', label: 'Candidates', icon: <Users className="w-3.5 h-3.5" /> },
          { key: 'analytics', label: 'Analytics',icon: <BarChart2 className="w-3.5 h-3.5" /> },
        ] as const).map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition
              ${tab === t.key
                ? 'bg-white text-purple-700 shadow-sm'
                : 'text-gray-600 hover:text-gray-900'}`}
          >
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {/* ── JOBS TAB ─────────────────────────────────────────────────────── */}
      {tab === 'jobs' && (
        <div className="space-y-4">
          {/* Search + filter bar */}
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                value={searchQ}
                onChange={e => setSearchQ(e.target.value)}
                placeholder="Search jobs…"
                className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>
            <select
              value={filterStatus}
              onChange={e => setFilterStatus(e.target.value)}
              className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                         focus:outline-none focus:ring-2 focus:ring-purple-400"
            >
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="draft">Draft</option>
            </select>
          </div>

          {/* Jobs grid */}
          {loading ? (
            <div className="text-center py-12 text-gray-400">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />Loading…
            </div>
          ) : filteredJobs.length === 0 ? (
            <div className="text-center py-12">
              <Briefcase className="w-10 h-10 text-gray-200 mx-auto mb-3" />
              <p className="text-gray-500">No jobs yet.</p>
              <button
                onClick={() => setShowCreateForm(true)}
                className="mt-3 px-4 py-2 bg-purple-600 text-white text-sm font-semibold rounded-xl"
              >
                Create your first job
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {filteredJobs.map(job => (
                <JobCard
                  key={job.id}
                  job={job}
                  onViewPipeline={() => {
                    setSelectedJob(job.id)
                    setTab('pipeline')
                  }}
                  onChanged={load}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── PIPELINE TAB ──────────────────────────────────────────────────── */}
      {tab === 'pipeline' && (
        <div className="space-y-4">
          {/* Job selector */}
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={selectedJob}
              onChange={e => { setSelectedJob(e.target.value); setSelected(new Set()) }}
              className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                         focus:outline-none focus:ring-2 focus:ring-purple-400 min-w-[200px]"
            >
              <option value="">All jobs</option>
              {jobs.map(j => (
                <option key={j.id} value={j.id}>
                  {j.title}{j.property_name ? ` — ${j.property_name}` : ''}
                </option>
              ))}
            </select>
            {selectedJob && (
              <button
                onClick={() => loadPipeline(selectedJob)}
                className="p-2 text-gray-500 hover:text-purple-600 rounded-lg"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Bulk action bar — floats when selection active */}
          {selected.size > 0 && (
            <div className="flex flex-wrap items-center gap-2 bg-purple-900 text-white
                            px-4 py-3 rounded-2xl">
              <span className="text-sm font-semibold">{selected.size} selected</span>
              <div className="flex-1" />
              <BulkBtn icon={<CheckCircle2 className="w-4 h-4" />} label="Shortlist"
                       onClick={() => bulkAction('shortlist')} color="green" />
              <BulkBtn icon={<MessageSquare className="w-4 h-4" />} label="WhatsApp Invite"
                       onClick={() => {
                         const date = window.prompt('Interview date/time (e.g. 10 June 10AM)?') || ''
                         bulkAction('invite', {
                           interview_date: date,
                           job_title: jobs.find(j => j.id === selectedJob)?.title,
                           property_name: jobs.find(j => j.id === selectedJob)?.property_name,
                         })
                       }} color="blue" />
              <BulkBtn icon={<XCircle className="w-4 h-4" />} label="Reject"
                       onClick={() => {
                         const reason = window.prompt('Rejection reason?') || 'Not selected'
                         bulkAction('reject', { reason })
                       }} color="red" />
              <button onClick={() => setSelected(new Set())}
                className="text-xs text-purple-300 hover:text-white ml-2">Clear</button>
            </div>
          )}

          {/* Kanban columns — horizontal scroll on mobile */}
          <div className="overflow-x-auto pb-4">
            <div className="flex gap-4 min-w-max">
              {STAGES.map(stage => {
                const cards = pipeline[stage.key] || []
                const cls   = STAGE_COLORS[stage.color]
                return (
                  <div key={stage.key} className="w-64 flex-shrink-0">
                    {/* Column header */}
                    <div className={`flex items-center justify-between px-3 py-2 rounded-xl border mb-3 ${cls}`}>
                      <div>
                        <p className="text-xs font-bold uppercase tracking-wide">{stage.label}</p>
                        <p className="text-[10px] opacity-70">{stage.labelHi}</p>
                      </div>
                      <span className="text-lg font-bold">{cards.length}</span>
                    </div>

                    {/* Cards */}
                    <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
                      {cards.map(c => (
                        <CandidateKanbanCard
                          key={c.id}
                          candidate={c}
                          selected={selected.has(c.id)}
                          stages={STAGES}
                          currentStage={stage.key}
                          onToggleSelect={() => toggleSelect(c.id)}
                          onMove={(newStage) => moveCandidate(c.id, newStage)}
                        />
                      ))}
                      {cards.length === 0 && (
                        <div className="text-center text-xs text-gray-400 py-6 border-2 border-dashed border-gray-200 rounded-xl">
                          No candidates
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {tab === 'candidates' && <CandidateDirectory jobs={jobs} />}

      {/* ── ANALYTICS TAB ────────────────────────────────────────────────── */}
      {tab === 'analytics' && <SourceAnalytics selectedJob={selectedJob} jobs={jobs} />}

      {/* ── Create job modal ─────────────────────────────────────────────── */}
      {showCreateForm && (
        <CreateJobModal
          templates={templates}
          onClose={() => setShowCreateForm(false)}
          onCreated={() => { setShowCreateForm(false); load() }}
        />
      )}
    </div>
  )
}

function CandidateDirectory({ jobs }: { jobs: Job[] }) {
  const [rows, setRows] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [stage, setStage] = useState('')
  const [source, setSource] = useState('')
  const [jobId, setJobId] = useState('')
  const [location, setLocation] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [loading, setLoading] = useState(false)
  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search); if (stage) params.set('stage', stage)
      if (source) params.set('source', source); if (jobId) params.set('job_id', jobId)
      if (location) params.set('location', location)
      const response = await apiClient.get(`/ats/candidates?${params}`)
      setRows(response.data.candidates || [])
    } finally { setLoading(false) }
  }, [search, stage, source, jobId, location])
  useEffect(() => { const timer = setTimeout(() => void load(), 250); return () => clearTimeout(timer) }, [load])
  return <div className="space-y-4">
    <div className="grid grid-cols-1 gap-2 rounded-lg border bg-white p-3 sm:grid-cols-5">
      <label className="relative sm:col-span-2"><Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name, phone, email..." className="min-h-11 w-full rounded-md border pl-9 pr-3 text-sm" /></label>
      <select value={jobId} onChange={e => setJobId(e.target.value)} className="min-h-11 rounded-md border px-3 text-sm"><option value="">All jobs</option>{jobs.map(job => <option key={job.id} value={job.id}>{job.title}</option>)}</select>
      <select value={stage} onChange={e => setStage(e.target.value)} className="min-h-11 rounded-md border px-3 text-sm"><option value="">All stages</option>{[...STAGES, { key: 'rejected', label: 'Rejected' }, { key: 'withdrawn', label: 'Withdrawn' }].map(item => <option key={item.key} value={item.key}>{item.label}</option>)}</select>
      <select value={source} onChange={e => setSource(e.target.value)} className="min-h-11 rounded-md border px-3 text-sm"><option value="">All sources</option>{Object.entries(SOURCES).map(([key, item]) => <option key={key} value={key}>{item.label}</option>)}</select>
      <input value={location} onChange={e => setLocation(e.target.value)} placeholder="Location" className="min-h-11 rounded-md border px-3 text-sm" />
    </div>
    <div className="overflow-x-auto rounded-lg border bg-white"><table className="w-full min-w-[850px] text-left text-sm"><thead><tr className="border-b bg-gray-50 text-xs text-gray-500"><th className="p-3">Candidate</th><th>Location</th><th>Experience</th><th>Skills</th><th>Source</th><th>Stage</th><th>Tags</th><th></th></tr></thead><tbody>{rows.map(row => { const skills = Array.isArray(row.parsed_skills) ? row.parsed_skills : row.parsed_skills?.skills || []; return <tr key={row.id} className="border-b"><td className="p-3"><strong>{row.first_name} {row.last_name}</strong><div className="text-xs text-gray-500">{row.phone} · {row.email}</div></td><td>{row.city || row.location || '—'}</td><td>{row.years_experience || 0} yrs</td><td className="max-w-48 truncate">{skills.slice(0, 3).join(', ') || '—'}</td><td><SourceBadge source={row.source || 'other'} /></td><td className="capitalize">{(row.pipeline_stage || 'applied').replace('_', ' ')}</td><td>{(row.tags || []).slice(0, 2).map((tag: string) => <span key={tag} className="mr-1 rounded bg-gray-100 px-2 py-1 text-xs">{tag}</span>)}</td><td><button onClick={() => setSelectedId(row.id)} className="rounded p-2 text-purple-600 hover:bg-purple-50" title="Open profile"><Eye className="h-4 w-4" /></button></td></tr>})}</tbody></table>{loading && <p className="p-5 text-center text-sm text-gray-500">Loading candidates...</p>}{!loading && !rows.length && <p className="p-8 text-center text-sm text-gray-500">No candidates match these filters.</p>}</div>
    {selectedId && <CandidateProfileModal candidateId={selectedId} onClose={() => setSelectedId('')} onChanged={load} />}
  </div>
}

function CandidateProfileModal({ candidateId, onClose, onChanged }: { candidateId: string; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<any>(null)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const load = useCallback(() => apiClient.get(`/ats/candidates/${candidateId}`).then(r => setData(r.data)).catch((e: any) => setError(e.response?.data?.detail || 'Unable to load candidate')), [candidateId])
  useEffect(() => { void load() }, [load])
  const addNote = async () => { if (!note.trim()) return; await apiClient.post(`/ats/candidates/${candidateId}/notes`, { body: note }); setNote(''); await load(); onChanged() }
  if (!data) return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"><div className="rounded-lg bg-white p-6">{error || 'Loading profile...'}</div></div>
  const c = data.candidate; const skills = Array.isArray(c.parsed_skills) ? c.parsed_skills : c.parsed_skills?.skills || []
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"><div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl">
    <div className="mb-4 flex justify-between"><div><h2 className="text-xl font-semibold">{c.first_name} {c.last_name}</h2><p className="text-sm text-gray-500">{c.phone} · {c.email} · {c.city || c.location || 'Location unavailable'}</p></div><button onClick={onClose} className="text-xl" aria-label="Close">×</button></div>
    <div className="grid gap-4 lg:grid-cols-3"><section className="space-y-3 lg:col-span-2"><div className="grid grid-cols-2 gap-2 rounded-md border p-3 text-sm sm:grid-cols-4"><div><span className="block text-xs text-gray-500">Experience</span>{c.years_experience || 0} years</div><div><span className="block text-xs text-gray-500">Expected salary</span>{c.expected_salary_inr ? `₹${Number(c.expected_salary_inr).toLocaleString('en-IN')}` : '—'}</div><div><span className="block text-xs text-gray-500">Notice period</span>{c.notice_period || '—'}</div><div><span className="block text-xs text-gray-500">Availability</span>{c.availability ? 'Recorded' : '—'}</div></div>
      <div className="rounded-md border p-3"><h3 className="mb-2 font-semibold">Skills & languages</h3><div className="flex flex-wrap gap-1">{[...skills, ...(c.languages || [])].map((value: string) => <span key={value} className="rounded bg-purple-50 px-2 py-1 text-xs text-purple-700">{value}</span>)}</div>{c.resume_url && <a href={c.resume_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1 text-sm text-purple-700"><ExternalLink className="h-4 w-4" />Open resume</a>}</div>
      <div className="rounded-md border p-3"><h3 className="mb-2 font-semibold">Applications</h3>{data.applications.map((app: any) => <div key={app.id} className="mb-2 flex justify-between border-b pb-2 text-sm"><span>{app.job_id || app.job_role_id}</span><strong className="capitalize">{String(app.status).replace('_', ' ')}</strong></div>)}</div>
      <div className="rounded-md border p-3"><h3 className="mb-2 font-semibold">Interview history</h3>{[...data.interviews, ...data.video_interviews].map((item: any) => <div key={item.id} className="mb-2 border-b pb-2 text-sm"><strong>{item.interview_type || 'Interview'} · {item.status}</strong><p className="text-gray-500">{item.scheduled_at || item.created_at}{item.interview_rating ? ` · ${item.interview_rating}/5` : ''}</p>{item.interview_notes && <p>{item.interview_notes}</p>}</div>)}{!data.interviews.length && !data.video_interviews.length && <p className="text-sm text-gray-500">No interviews recorded.</p>}</div>
    </section><aside className="space-y-3"><div className="rounded-md border p-3"><h3 className="mb-2 font-semibold">Notes</h3><textarea value={note} onChange={e => setNote(e.target.value)} placeholder="Add recruiter note" className="min-h-20 w-full rounded border p-2 text-sm" /><button onClick={addNote} className="mt-2 min-h-10 w-full rounded bg-purple-600 text-sm font-semibold text-white">Add note</button>{data.notes.map((item: any) => <div key={item.id} className="mt-3 border-t pt-2 text-sm"><p>{item.body}</p><span className="text-xs text-gray-400">{new Date(item.created_at).toLocaleString()}</span></div>)}</div>
      <div className="rounded-md border p-3"><h3 className="mb-2 font-semibold">Documents</h3>{data.documents.map((doc: any) => <a key={doc.id} href={doc.file_url || '#'} className="mb-2 block text-sm text-purple-700">{doc.document_type}: {doc.file_name}</a>)}{!data.documents.length && <p className="text-sm text-gray-500">No general documents.</p>}</div>
      <div className="rounded-md border p-3"><h3 className="mb-2 font-semibold">Timeline</h3>{data.timeline.map((event: any, index: number) => <div key={`${event.type}-${index}`} className="border-l-2 border-purple-200 pb-3 pl-3 text-sm"><strong className="capitalize">{event.type}</strong><p className="text-xs text-gray-500">{event.at ? new Date(event.at).toLocaleString() : '—'}</p></div>)}</div></aside></div>
  </div></div>
}

// ─────────────────────────────────────────────────────────────────────────────
// Job card
// ─────────────────────────────────────────────────────────────────────────────

function JobCard({ job, onViewPipeline, onChanged }: { job: Job; onViewPipeline: () => void; onChanged: () => void }) {
  const [showQR, setShowQR] = useState(false)
  const [editing, setEditing] = useState(false)
  const [distributing, setDistributing] = useState(false)
  const total = job.total_applicants ?? 0

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 hover:border-purple-200 transition">
      {/* Top row */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="font-bold text-gray-900 text-sm truncate">{job.title}</h3>
            {job.is_urgent && <UrgentBadge />}
          </div>
          {(job.property_name || job.department) && (
            <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
              <Building2 className="w-3 h-3" />
              {[job.property_name, job.department].filter(Boolean).join(' · ')}
            </p>
          )}
          {job.location_city && (
            <p className="text-xs text-gray-400 flex items-center gap-1 mt-0.5">
              <MapPin className="w-3 h-3" />{job.location_city}
              {job.location_state ? `, ${job.location_state}` : ''}
            </p>
          )}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold flex-shrink-0
          ${job.status === 'open' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'}`}>
          {job.status}
        </span>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-3 mb-3 text-xs text-gray-600">
        <SalaryRange min={job.salary_min_inr} max={job.salary_max_inr} />
        {job.experience_min_years !== undefined && (
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {job.experience_min_years === 0 ? 'Fresher OK' : `${job.experience_min_years}+ yrs`}
          </span>
        )}
        <span className="flex items-center gap-1">
          <Users className="w-3 h-3" />{job.openings_count} opening{job.openings_count !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Pipeline mini-bar */}
      {total > 0 && (
        <div className="mb-3">
          <div className="flex h-1.5 rounded-full overflow-hidden gap-0.5">
            {STAGES.map(s => {
              const cnt = job.pipeline_counts?.[s.key] ?? 0
              const w = total > 0 ? Math.round(cnt / total * 100) : 0
              const bg: Record<string, string> = {
                blue: 'bg-blue-400', purple: 'bg-purple-400',
                amber: 'bg-amber-400', green: 'bg-green-400', teal: 'bg-teal-400',
              }
              return w > 0 ? (
                <div key={s.key} className={`${bg[s.color]} rounded-full`} style={{ width: `${w}%` }} />
              ) : null
            })}
          </div>
          <p className="text-[10px] text-gray-400 mt-1">{total} applicant{total !== 1 ? 's' : ''}</p>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={onViewPipeline}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs font-semibold
                     text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-xl transition"
        >
          <ArrowRight className="w-3.5 h-3.5" /> View Pipeline
        </button>
        <button
          onClick={() => setShowQR(!showQR)}
          className="p-2 text-gray-500 hover:text-purple-600 hover:bg-purple-50 rounded-xl transition"
          title="QR Code"
        >
          <QrCode className="w-4 h-4" />
        </button>
        {job.apply_url && (
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-xl transition"
            title="Apply link"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
        <button onClick={() => setEditing(true)} className="p-2 text-gray-500 hover:bg-gray-100 rounded-xl" title="Edit job"><Edit3 className="w-4 h-4" /></button>
        <button onClick={() => setDistributing(true)} className="p-2 text-purple-600 hover:bg-purple-50 rounded-xl" title="Distribute job"><Share2 className="w-4 h-4" /></button>
        <button onClick={async () => { await apiClient.post(`/recruit/jobs/${job.id}/duplicate`, {}); onChanged() }} className="p-2 text-gray-500 hover:bg-gray-100 rounded-xl" title="Duplicate"><Copy className="w-4 h-4" /></button>
        {job.approval_status === 'DRAFT' || job.approval_status === 'REJECTED' ? (
          <button onClick={async () => { await apiClient.post(`/recruit/jobs/${job.id}/submit-approval`, {}); onChanged() }} className="p-2 text-blue-600 hover:bg-blue-50 rounded-xl" title="Submit for approval"><Send className="w-4 h-4" /></button>
        ) : job.approval_status === 'PENDING_APPROVAL' ? (
          <button onClick={async () => { await apiClient.post(`/recruit/jobs/${job.id}/approval`, { decision: 'APPROVE' }); onChanged() }} className="p-2 text-green-600 hover:bg-green-50 rounded-xl" title="Approve"><ThumbsUp className="w-4 h-4" /></button>
        ) : null}
        {job.status === 'open' ? (
          <button onClick={async () => { await apiClient.post(`/recruit/jobs/${job.id}/close`, {}); onChanged() }} className="p-2 text-red-600 hover:bg-red-50 rounded-xl" title="Close"><LockKeyhole className="w-4 h-4" /></button>
        ) : job.status === 'closed' ? (
          <button onClick={async () => { await apiClient.post(`/recruit/jobs/${job.id}/reopen`); onChanged() }} className="p-2 text-green-600 hover:bg-green-50 rounded-xl" title="Reopen"><RotateCcw className="w-4 h-4" /></button>
        ) : null}
      </div>
      {editing && <EditJobModal jobId={job.id} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); onChanged() }} />}
      {distributing && <DistributionModal job={job} onClose={() => setDistributing(false)} />}

      {/* QR code panel */}
      {showQR && job.qr_url && (
        <div className="mt-3 pt-3 border-t border-gray-100 flex flex-col items-center gap-2">
          <img src={job.qr_url} alt="Apply QR" className="w-32 h-32 rounded-xl" />
          <p className="text-[10px] text-gray-400 text-center">
            Scan to apply — noticeboard या payslip पर लगाएं
          </p>
          <a
            href={job.qr_url}
            download={`${job.title}-qr.png`}
            className="flex items-center gap-1 text-xs text-purple-700 font-semibold"
          >
            <Download className="w-3.5 h-3.5" /> Download QR
          </a>
        </div>
      )}
    </div>
  )
}

interface DistributionChannel { channel_key: string; display_name: string; delivery_mode: string; classification: string; is_enabled?: boolean }
interface DistributionRow { id: string; channel_key: string; delivery_mode: string; status: string; posting_url?: string; expires_at?: string; click_count: number; application_count: number; hire_count: number }

function DistributionModal({ job, onClose }: { job: Job; onClose: () => void }) {
  const [channels, setChannels] = useState<DistributionChannel[]>([])
  const [rows, setRows] = useState<DistributionRow[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(async () => {
    try {
      const [c, d] = await Promise.all([apiClient.get('/distribution/channels'), apiClient.get(`/distribution/jobs/${job.id}`)])
      setChannels(c.data || []); setRows(d.data || [])
    } catch (e: any) { setError(e.response?.data?.detail || 'Unable to load distribution channels') }
  }, [job.id])
  useEffect(() => { void load() }, [load])
  const prepare = async () => {
    if (!selected.size) return
    setBusy(true); setError('')
    try { await apiClient.post(`/distribution/jobs/${job.id}/prepare`, { channels: [...selected], expiry_days: 30 }); await load() }
    catch (e: any) { setError(e.response?.data?.detail || 'Preparation failed') }
    finally { setBusy(false) }
  }
  const changeStatus = async (row: DistributionRow, action: 'publish' | 'unpublish') => {
    try { await apiClient.post(`/distribution/${row.id}/${action}`, {}); await load() }
    catch (e: any) { setError(e.response?.data?.detail || `${action} failed`) }
  }
  const download = async () => {
    const response = await apiClient.get(`/distribution/export.csv?job_id=${job.id}`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data); const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${job.title}-distribution.csv`; anchor.click(); URL.revokeObjectURL(url)
  }
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"><div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-lg bg-white p-5 shadow-xl">
    <div className="mb-4 flex items-center justify-between"><div><h2 className="text-lg font-semibold">Distribute: {job.title}</h2><p className="text-xs text-gray-500">External boards use manual CSV export unless a verified API adapter exists.</p></div><button onClick={onClose} aria-label="Close" className="text-xl">×</button></div>
    {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{channels.map(channel => <label key={channel.channel_key} className="flex min-h-16 cursor-pointer items-start gap-2 rounded-md border p-3 text-sm"><input type="checkbox" disabled={channel.is_enabled === false} checked={selected.has(channel.channel_key)} onChange={() => setSelected(current => { const next = new Set(current); next.has(channel.channel_key) ? next.delete(channel.channel_key) : next.add(channel.channel_key); return next })} /><span><strong className="block">{channel.display_name}</strong><span className="text-[11px] text-gray-500">{channel.delivery_mode === 'MANUAL_EXPORT' ? 'CSV/manual export' : channel.delivery_mode.replace('_', ' ')}</span></span></label>)}</div>
    <div className="my-4 flex gap-2"><button disabled={busy || !selected.size} onClick={prepare} className="min-h-11 rounded-md bg-purple-600 px-4 text-sm font-semibold text-white disabled:opacity-50">Prepare selected</button><button onClick={download} className="min-h-11 rounded-md border px-4 text-sm font-semibold"><Download className="mr-1 inline h-4 w-4" />Export CSV</button></div>
    <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm"><thead><tr className="border-b text-xs text-gray-500"><th className="p-2">Channel</th><th>Status</th><th>Delivery</th><th>Clicks</th><th>Applications</th><th>Hires</th><th>Expires</th><th>Actions</th></tr></thead><tbody>{rows.map(row => <tr key={row.id} className="border-b"><td className="p-2 font-medium">{channels.find(c => c.channel_key === row.channel_key)?.display_name || row.channel_key}</td><td><span className="rounded bg-gray-100 px-2 py-1 text-xs">{row.status}</span></td><td className="text-xs">{row.delivery_mode === 'MANUAL_EXPORT' ? 'Manual export' : row.delivery_mode}</td><td>{row.click_count || 0}</td><td>{row.application_count || 0}</td><td>{row.hire_count || 0}</td><td className="text-xs">{row.expires_at ? new Date(row.expires_at).toLocaleDateString() : '—'}</td><td><div className="flex gap-1">{row.status !== 'PUBLISHED' ? <button onClick={() => changeStatus(row, 'publish')} className="rounded bg-green-50 px-2 py-1 text-xs text-green-700">Publish</button> : <button onClick={() => changeStatus(row, 'unpublish')} className="rounded bg-red-50 px-2 py-1 text-xs text-red-700">Unpublish</button>}{row.posting_url && <a href={row.posting_url} target="_blank" rel="noreferrer" className="rounded border px-2 py-1 text-xs">Open</a>}</div></td></tr>)}</tbody></table>{!rows.length && <p className="py-8 text-center text-sm text-gray-500">Prepare one or more channels to create tracked postings.</p>}</div>
  </div></div>
}

// ─────────────────────────────────────────────────────────────────────────────
// Kanban candidate card
// ─────────────────────────────────────────────────────────────────────────────

function CandidateKanbanCard({
  candidate, selected, stages, currentStage, onToggleSelect, onMove,
}: {
  candidate:    CandidateCard
  selected:     boolean
  stages:       typeof STAGES
  currentStage: string
  onToggleSelect: () => void
  onMove: (stage: string) => void
}) {
  const [showMove, setShowMove] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setShowMove(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  return (
    <div
      className={`bg-white rounded-xl border p-3 hover:shadow-md transition cursor-pointer
        ${selected ? 'border-purple-400 ring-1 ring-purple-300' : 'border-gray-100'}`}
    >
      {/* Checkbox + Name row */}
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          onClick={e => e.stopPropagation()}
          className="mt-0.5 accent-purple-600"
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{candidate.name}</p>
          {candidate.phone && (
            <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
              <Phone className="w-3 h-3" />{candidate.phone}
            </p>
          )}
        </div>
        {candidate.score && (
          <span className="text-[10px] bg-purple-50 text-purple-700 font-bold px-1.5 py-0.5 rounded-full flex-shrink-0">
            {Math.round(candidate.score * 100)}%
          </span>
        )}
      </div>

      {/* Badges */}
      <div className="flex flex-wrap gap-1.5 mt-2">
        <SourceBadge source={candidate.source} />
        {candidate.applied_via_qr && (
          <span className="text-[10px] bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded-full font-semibold">
            QR
          </span>
        )}
        {candidate.qualified && (
          <span className="text-[10px] bg-green-50 text-green-700 px-1.5 py-0.5 rounded-full font-semibold">
            ✓ Qualified
          </span>
        )}
      </div>

      {/* Move stage dropdown */}
      <div ref={ref} className="relative mt-2">
        <button
          onClick={() => setShowMove(!showMove)}
          className="w-full flex items-center justify-between px-2 py-1.5 text-[11px]
                     font-semibold text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-lg transition"
        >
          Move to… <ChevronDown className="w-3 h-3" />
        </button>
        {showMove && (
          <div className="absolute left-0 right-0 top-full mt-1 bg-white rounded-xl shadow-lg border border-gray-100 z-10 py-1">
            {stages
              .filter(s => s.key !== currentStage)
              .map(s => (
                <button
                  key={s.key}
                  onClick={() => { onMove(s.key); setShowMove(false) }}
                  className="w-full text-left px-3 py-1.5 text-xs hover:bg-purple-50 text-gray-700 hover:text-purple-700"
                >
                  {s.label} <span className="text-gray-400">({s.labelHi})</span>
                </button>
              ))}
            <button
              onClick={() => { onMove('rejected'); setShowMove(false) }}
              className="w-full text-left px-3 py-1.5 text-xs hover:bg-red-50 text-red-600"
            >
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Bulk action button
// ─────────────────────────────────────────────────────────────────────────────

function BulkBtn({
  icon, label, onClick, color,
}: {
  icon: React.ReactNode; label: string
  onClick: () => void; color: 'green' | 'blue' | 'red'
}) {
  const cls = {
    green: 'bg-green-600  hover:bg-green-700',
    blue:  'bg-blue-600   hover:bg-blue-700',
    red:   'bg-red-600    hover:bg-red-700',
  }
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition ${cls[color]}`}
    >
      {icon}{label}
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Create Job Modal
// ─────────────────────────────────────────────────────────────────────────────

function EditJobModal({ jobId, onClose, onSaved }: { jobId: string; onClose: () => void; onSaved: () => void }) {
  const { properties } = useProperty()
  const [form, setForm] = useState<any>(null)
  const [departments, setDepartments] = useState<{ id: string; name: string }[]>([])
  const [templates, setTemplates] = useState<RoleTemplate[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    apiClient.get('/recruit/role-templates').then(r => setTemplates(r.data || [])).catch(() => setTemplates([]))
    apiClient.get(`/recruit/jobs/${jobId}`).then(r => setForm({
      ...r.data,
      required_skills: (r.data.required_skills || []).join(', '),
      preferred_skills: (r.data.preferred_skills || []).join(', '),
      required_languages: (r.data.required_languages || []).join(', '),
    })).catch(() => setError('Unable to load job'))
  }, [jobId])
  useEffect(() => {
    if (!form?.property_id) { setDepartments([]); return }
    apiClient.get(`/hotels/properties/${form.property_id}/departments`)
      .then(r => setDepartments(r.data.departments || [])).catch(() => setDepartments([]))
  }, [form?.property_id])
  if (!form) return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"><div className="rounded-lg bg-white p-6">{error || 'Loading...'}</div></div>
  const set = (key: string, value: unknown) => setForm((current: any) => ({ ...current, [key]: value }))
  const save = async () => {
    try {
      await apiClient.patch(`/recruit/jobs/${jobId}`, {
        title: form.title, openings_count: Number(form.openings_count),
        property_id: form.property_id || undefined, department_id: form.department_id || undefined,
        role_template: form.role_template || undefined,
        salary_min_inr: form.salary_min_inr ? Number(form.salary_min_inr) : undefined,
        salary_max_inr: form.salary_max_inr ? Number(form.salary_max_inr) : undefined,
        ctc_min_inr: form.ctc_min_inr ? Number(form.ctc_min_inr) : undefined,
        ctc_max_inr: form.ctc_max_inr ? Number(form.ctc_max_inr) : undefined,
        experience_min_years: Number(form.experience_min_years || 0),
        experience_max_years: form.experience_max_years ? Number(form.experience_max_years) : undefined,
        education_level: form.education_level || undefined,
        required_skills: form.required_skills.split(',').map((v: string) => v.trim()).filter(Boolean),
        preferred_skills: form.preferred_skills.split(',').map((v: string) => v.trim()).filter(Boolean),
        required_languages: form.required_languages.split(',').map((v: string) => v.trim()).filter(Boolean),
        shift_requirements: form.shift_requirements || {},
        accommodation_provided: Boolean(form.accommodation_provided), food_provided: Boolean(form.food_provided),
        transportation_provided: Boolean(form.transportation_provided), urgency_level: form.urgency_level,
        hiring_manager_id: form.hiring_manager_id || undefined, recruiter_id: form.recruiter_id || undefined,
        jd_english: form.jd_english, jd_hindi: form.jd_hindi,
      })
      await apiClient.post(`/recruit/jobs/${jobId}/job-board-versions`)
      onSaved()
    } catch (e: any) { setError(e.response?.data?.detail || 'Save failed') }
  }
  const fields: [string, string, string][] = [
    ['title', 'Job title', 'text'], ['openings_count', 'Vacancies', 'number'],
    ['salary_min_inr', 'Monthly salary min', 'number'], ['salary_max_inr', 'Monthly salary max', 'number'],
    ['ctc_min_inr', 'Annual CTC min', 'number'], ['ctc_max_inr', 'Annual CTC max', 'number'],
    ['experience_min_years', 'Experience min', 'number'], ['experience_max_years', 'Experience max', 'number'],
    ['education_level', 'Education', 'text'], ['required_languages', 'Languages', 'text'],
    ['required_skills', 'Required skills', 'text'], ['preferred_skills', 'Preferred skills', 'text'],
  ]
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"><div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
    <div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">Edit job</h2><button onClick={onClose} aria-label="Close">×</button></div>
    {error && <p className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}
    <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <label className="text-sm">Property<select value={form.property_id || ''} onChange={e => setForm((current: any) => ({ ...current, property_id: e.target.value, department_id: '' }))} className="mt-1 min-h-11 w-full rounded-md border border-gray-300 px-3"><option value="">Select property</option>{properties.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label className="text-sm">Department<select value={form.department_id || ''} onChange={e => set('department_id', e.target.value)} className="mt-1 min-h-11 w-full rounded-md border border-gray-300 px-3"><option value="">No department</option>{departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <label className="text-sm">Hospitality role<select value={form.role_template || ''} onChange={e => set('role_template', e.target.value)} className="mt-1 min-h-11 w-full rounded-md border border-gray-300 px-3"><option value="">Custom role</option>{templates.map(t => <option key={t.role_key} value={t.role_key}>{t.display_name}</option>)}</select></label>
    </div>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{fields.map(([key, label, type]) => <label key={key} className={key.includes('skills') ? 'sm:col-span-2 text-sm' : 'text-sm'}>{label}<input type={type} value={form[key] ?? ''} onChange={e => set(key, e.target.value)} className="mt-1 min-h-11 w-full rounded-md border border-gray-300 px-3" /></label>)}</div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2"><label className="text-sm">English JD<textarea value={form.jd_english || ''} onChange={e => set('jd_english', e.target.value)} className="mt-1 min-h-32 w-full rounded-md border p-3" /></label><label className="text-sm">Hindi JD<textarea value={form.jd_hindi || ''} onChange={e => set('jd_hindi', e.target.value)} className="mt-1 min-h-32 w-full rounded-md border p-3" /></label></div>
    <div className="mt-4 flex flex-wrap gap-4">{[['accommodation_provided','Accommodation'],['food_provided','Food'],['transportation_provided','Transportation']].map(([key,label]) => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form[key])} onChange={e => set(key,e.target.checked)} />{label}</label>)}</div>
    <div className="mt-6 flex justify-end gap-2"><button onClick={onClose} className="min-h-11 rounded-md border px-4">Cancel</button><button onClick={save} className="min-h-11 rounded-md bg-purple-600 px-4 text-white">Save changes</button></div>
  </div></div>
}

function CreateJobModal({
  templates, onClose, onCreated,
}: {
  templates: RoleTemplate[]
  onClose: () => void
  onCreated: () => void
}) {
  const { properties, activeProperty } = useProperty()
  const [departments, setDepartments] = useState<{ id: string; name: string }[]>([])
  const [members, setMembers] = useState<{ user_id: string; user?: { full_name?: string; email?: string } }[]>([])
  const [form, setForm] = useState({
    title: '', role_template: '', property_id: activeProperty?.id || '', department_id: '',
    location_city: '', location_state: '', openings_count: 1, is_urgent: false,
    salary_min_inr: '', salary_max_inr: '', experience_min_years: 0,
    experience_max_years: '', ctc_min_inr: '', ctc_max_inr: '', education_level: '',
    required_skills: '', preferred_skills: '', required_languages: 'Hindi, English',
    shift_type: 'ROTATIONAL', accommodation_provided: false, food_provided: false,
    transportation_provided: false, urgency_level: 'NORMAL', hiring_manager_id: '', recruiter_id: '',
    generate_jd: true,
  })
  const [jdPreview, setJdPreview] = useState<{ english: string; hindi: string } | null>(null)
  const [saving,    setSaving]    = useState(false)
  const [error,     setError]     = useState('')

  const categories = [...new Set(templates.map(t => t.category))]

  useEffect(() => {
    if (!form.property_id) { setDepartments([]); setMembers([]); return }
    Promise.all([
      apiClient.get(`/hotels/properties/${form.property_id}/departments`),
      apiClient.get(`/hotels/properties/${form.property_id}/members`),
    ]).then(([d, m]) => {
      setDepartments(d.data.departments || [])
      setMembers(m.data.members || [])
    }).catch(() => { setDepartments([]); setMembers([]) })
  }, [form.property_id])

  // When template selected, pre-fill form
  const selectTemplate = (key: string) => {
    const t = templates.find(x => x.role_key === key)
    if (!t) return
    setForm(f => ({
      ...f,
      role_template: key,
      title: t.display_name,
      required_skills: (t.required_skills || []).join(', '),
      salary_min_inr: String(t.salary_min_inr || ''),
      salary_max_inr: String(t.salary_max_inr || ''),
      experience_min_years: t.min_experience_years || 0,
    }))
    setJdPreview({ english: t.jd_english, hindi: t.jd_hindi })
  }

  const previewJD = async () => {
    try {
      const { data } = await apiClient.post('/recruit/jobs/preview-jd', {
        ...form,
        salary_min_inr: Number(form.salary_min_inr) || undefined,
        salary_max_inr: Number(form.salary_max_inr) || undefined,
        ctc_min_inr: Number(form.ctc_min_inr) || undefined,
        ctc_max_inr: Number(form.ctc_max_inr) || undefined,
        experience_max_years: Number(form.experience_max_years) || undefined,
        required_skills: form.required_skills.split(',').map(v => v.trim()).filter(Boolean),
        preferred_skills: form.preferred_skills.split(',').map(v => v.trim()).filter(Boolean),
        required_languages: form.required_languages.split(',').map(v => v.trim()).filter(Boolean),
        shift_requirements: { type: form.shift_type },
        generate_jd: true,
        status: 'draft',
      })
      setJdPreview({ english: data.english, hindi: data.hindi })
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Preview failed')
    }
  }

  const submit = async () => {
    if (!form.title) { setError('Job title is required'); return }
    setSaving(true); setError('')
    try {
      await apiClient.post('/recruit/jobs', {
        ...form,
        salary_min_inr: Number(form.salary_min_inr) || undefined,
        salary_max_inr: Number(form.salary_max_inr) || undefined,
        ctc_min_inr: Number(form.ctc_min_inr) || undefined,
        ctc_max_inr: Number(form.ctc_max_inr) || undefined,
        experience_max_years: Number(form.experience_max_years) || undefined,
        required_skills: form.required_skills.split(',').map(v => v.trim()).filter(Boolean),
        preferred_skills: form.preferred_skills.split(',').map(v => v.trim()).filter(Boolean),
        required_languages: form.required_languages.split(',').map(v => v.trim()).filter(Boolean),
        shift_requirements: { type: form.shift_type },
        status: 'draft',
      })
      onCreated()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Failed to create job')
    } finally {
      setSaving(false)
    }
  }

  const set = (k: string, v: unknown) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="font-bold text-gray-900 text-lg flex items-center gap-2">
            <Plus className="w-5 h-5 text-purple-600" /> Create New Job
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl font-bold">×</button>
        </div>

        <div className="p-6 space-y-5">
          {error && (
            <div className="bg-red-50 text-red-700 text-sm px-4 py-2 rounded-xl border border-red-100">
              {error}
            </div>
          )}

          {/* Role template */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Role Template (optional)
            </label>
            <div className="flex flex-wrap gap-2">
              {categories.map(cat => (
                <div key={cat} className="w-full">
                  <p className="text-xs font-bold text-gray-400 uppercase mb-1">{cat}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {templates.filter(t => t.category === cat).map(t => (
                      <button
                        key={t.role_key}
                        onClick={() => selectTemplate(t.role_key)}
                        className={`text-xs px-2.5 py-1 rounded-lg border transition font-medium
                          ${form.role_template === t.role_key
                            ? 'bg-purple-600 text-white border-purple-600'
                            : 'border-gray-200 text-gray-700 hover:border-purple-400'}`}
                      >
                        {t.display_name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Core fields */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Job Title *</label>
              <input
                value={form.title}
                onChange={e => set('title', e.target.value)}
                placeholder="e.g. Banquet Waiter"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Property *</label>
              <select
                value={form.property_id}
                onChange={e => set('property_id', e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              ><option value="">Select property</option>{properties.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Department</label>
              <select
                value={form.department_id}
                onChange={e => set('department_id', e.target.value)}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              ><option value="">Select department</option>{departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">City</label>
              <input
                value={form.location_city}
                onChange={e => set('location_city', e.target.value)}
                placeholder="e.g. Mumbai, Delhi, Bengaluru"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Salary Min (₹/month)</label>
              <input
                type="number"
                value={form.salary_min_inr}
                onChange={e => set('salary_min_inr', e.target.value)}
                placeholder="e.g. 12000"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Salary Max (₹/month)</label>
              <input
                type="number"
                value={form.salary_max_inr}
                onChange={e => set('salary_max_inr', e.target.value)}
                placeholder="e.g. 20000"
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Openings</label>
              <input
                type="number"
                min={1}
                value={form.openings_count}
                onChange={e => set('openings_count', Number(e.target.value))}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Min Experience</label>
              <select
                value={form.experience_min_years}
                onChange={e => set('experience_min_years', Number(e.target.value))}
                className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm
                           focus:outline-none focus:ring-2 focus:ring-purple-400"
              >
                <option value={0}>Fresher OK</option>
                <option value={1}>1+ year</option>
                <option value={2}>2+ years</option>
                <option value={3}>3+ years</option>
                <option value={5}>5+ years</option>
              </select>
            </div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Max Experience</label><input type="number" min={0} value={form.experience_max_years} onChange={e => set('experience_max_years', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm" /></div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Annual CTC Min (₹)</label><input type="number" min={0} value={form.ctc_min_inr} onChange={e => set('ctc_min_inr', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm" /></div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Annual CTC Max (₹)</label><input type="number" min={0} value={form.ctc_max_inr} onChange={e => set('ctc_max_inr', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm" /></div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Education</label><select value={form.education_level} onChange={e => set('education_level', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm"><option value="">No minimum</option><option>10th Pass</option><option>12th Pass</option><option>Diploma</option><option>Graduate</option><option>Postgraduate</option></select></div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Shift</label><select value={form.shift_type} onChange={e => set('shift_type', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm"><option value="ROTATIONAL">Rotational</option><option value="MORNING">Morning</option><option value="EVENING">Evening</option><option value="NIGHT">Night</option><option value="FLEXIBLE">Flexible</option></select></div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Urgency</label><select value={form.urgency_level} onChange={e => set('urgency_level', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm"><option>NORMAL</option><option>HIGH</option><option>URGENT</option><option>CRITICAL</option></select></div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Hiring Manager</label><select value={form.hiring_manager_id} onChange={e => set('hiring_manager_id', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm"><option value="">Unassigned</option>{members.map(m => <option key={m.user_id} value={m.user_id}>{m.user?.full_name || m.user?.email || m.user_id}</option>)}</select></div>
            <div><label className="block text-xs font-semibold text-gray-600 mb-1">Recruiter</label><select value={form.recruiter_id} onChange={e => set('recruiter_id', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm"><option value="">Current user</option>{members.map(m => <option key={m.user_id} value={m.user_id}>{m.user?.full_name || m.user?.email || m.user_id}</option>)}</select></div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="sm:col-span-3"><label className="block text-xs font-semibold text-gray-600 mb-1">Required Skills (comma separated)</label><input value={form.required_skills} onChange={e => set('required_skills', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm" /></div>
            <div className="sm:col-span-3"><label className="block text-xs font-semibold text-gray-600 mb-1">Preferred Skills</label><input value={form.preferred_skills} onChange={e => set('preferred_skills', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm" /></div>
            <div className="sm:col-span-3"><label className="block text-xs font-semibold text-gray-600 mb-1">Languages</label><input value={form.required_languages} onChange={e => set('required_languages', e.target.value)} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm" /></div>
          </div>

          {/* Toggles */}
          <div className="flex gap-6">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_urgent}
                onChange={e => set('is_urgent', e.target.checked)}
                className="accent-red-500"
              />
              <span className="text-sm text-gray-700">Mark as Urgent</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.generate_jd}
                onChange={e => set('generate_jd', e.target.checked)}
                className="accent-purple-600"
              />
              <span className="text-sm text-gray-700">Auto-generate bilingual JD</span>
            </label>
          </div>
          <div className="flex flex-wrap gap-5">
            {[['accommodation_provided', 'Accommodation'], ['food_provided', 'Food'], ['transportation_provided', 'Transportation']].map(([key, label]) => <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(form[key as keyof typeof form])} onChange={e => set(key, e.target.checked)} />{label} provided</label>)}
          </div>

          {/* JD preview */}
          {jdPreview && (
            <div className="space-y-3">
              <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
                <p className="text-xs font-bold text-blue-700 uppercase tracking-wide mb-2">
                  English JD Preview
                </p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{jdPreview.english}</p>
              </div>
              <div className="bg-orange-50 border border-orange-100 rounded-xl p-4">
                <p className="text-xs font-bold text-orange-700 uppercase tracking-wide mb-2">
                  Hindi JD Preview (हिंदी JD)
                </p>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{jdPreview.hindi}</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 px-6 py-4 border-t border-gray-100">
          <button
            onClick={onClose}
            className="flex-1 py-2.5 border border-gray-200 text-sm font-semibold text-gray-700
                       rounded-xl hover:bg-gray-50 transition"
          >
            Cancel
          </button>
          <button
            onClick={previewJD}
            className="flex-1 py-2.5 border border-purple-200 text-sm font-semibold text-purple-700
                       bg-purple-50 hover:bg-purple-100 rounded-xl transition"
          >
            Preview JD
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="flex-1 py-2.5 bg-purple-600 hover:bg-purple-700 text-white text-sm
                       font-semibold rounded-xl transition disabled:opacity-50"
          >
            {saving ? 'Creating…' : 'Create Job + QR'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Source analytics panel
// ─────────────────────────────────────────────────────────────────────────────

function SourceAnalytics({ selectedJob }: { selectedJob: string; jobs: Job[] }) {
  const [data,   setData]   = useState<{ total: number; sources: { source: string; count: number; pct: number }[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const url = `/recruit/analytics/sources${selectedJob ? `?job_id=${selectedJob}` : ''}`
    apiClient.get(url)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [selectedJob])

  if (loading) return <div className="text-center py-10 text-gray-400"><RefreshCw className="w-5 h-5 animate-spin mx-auto" /></div>
  if (!data || data.total === 0) return <div className="text-center py-10 text-gray-400">No applicant data yet.</div>

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
      <h3 className="font-bold text-gray-800 mb-5 flex items-center gap-2">
        <BarChart2 className="w-4 h-4 text-purple-500" />
        Source Breakdown — {data.total} total applicants
      </h3>
      <div className="space-y-3">
        {data.sources.map(s => {
          const src = SOURCES[s.source] ?? SOURCES.other
          return (
            <div key={s.source} className="flex items-center gap-3">
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full w-24 text-center ${src.color}`}>
                {src.label}
              </span>
              <div className="flex-1 bg-gray-100 rounded-full h-2">
                <div
                  className="bg-purple-500 h-2 rounded-full transition-all"
                  style={{ width: `${s.pct}%` }}
                />
              </div>
              <span className="text-xs font-bold text-gray-700 w-16 text-right">
                {s.count} ({s.pct}%)
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
