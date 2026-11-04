/**
 * DPDP Privacy Center — Admin / HR screen
 * Digital Personal Data Protection Act 2023 compliance dashboard.
 *
 * Shows per-candidate consent state across all 7 purposes.
 * Each purpose is toggled individually — no bundled consent (DPDP s.6).
 * Erasure request flow with 30-day SLA tracking (DPDP s.13).
 *
 * Mobile-first layout for hospitality HR teams.
 */

import { apiClient } from '@/lib/api'
import {
ChevronDown,ChevronRight,
Clock,
FileText,
Info,
Loader2,
Lock,RefreshCw,Search,
ShieldCheck,Trash2
} from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'

// ─── Shared styles ────────────────────────────────────────────────────────────
const inp  = 'w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white'
const btn  = 'flex items-center justify-center gap-2 px-4 py-2.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-xl transition disabled:opacity-50 active:scale-95'
const btnOutline = 'flex items-center gap-2 px-4 py-2 border border-gray-200 text-gray-600 text-sm font-medium rounded-xl hover:bg-gray-50 transition'
const card = 'bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden'

// ─── Types ───────────────────────────────────────────────────────────────────
interface Purpose {
  code:           string
  description_en: string
  description_hi: string
  icon:           string
  required:       boolean
  legal_basis:    string
  retention_years: number | null
}

interface ConsentRecord {
  legal_basis?: string
  purpose_code:  string
  consented:     boolean | null
  consented_at:  string | null
  version:       string | null
  mechanism:     string | null
  description_en: string
  description_hi: string
  icon:           string
  required:       boolean
}

interface ErasureRequest {
  id:              string
  request_type:    string
  status:          string
  requested_at:    string
  response_due_at: string
  denial_reason:   string | null
  days_remaining?: number
  is_overdue?:     boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function daysBetween(dateStr: string) {
  const due  = new Date(dateStr)
  const now  = new Date()
  return Math.floor((due.getTime() - now.getTime()) / 86400000)
}

const CONSENT_VERSION = 'v2.0'

const REQUEST_TYPES = [
  { value: 'ERASURE',    label: 'Data Erasure',     emoji: '🗑' },
  { value: 'CORRECTION', label: 'Data Correction',  emoji: '✏️' },
  { value: 'ACCESS',     label: 'Data Access',      emoji: '📋' },
  { value: 'NOMINATION', label: 'Nomination',       emoji: '👤' },
]

const STATUS_STYLE: Record<string, string> = {
  PENDING:     'bg-amber-100 text-amber-700',
  UNDER_REVIEW:'bg-blue-100 text-blue-700',
  COMPLETED:   'bg-green-100 text-green-700',
  REJECTED:    'bg-red-100 text-red-700',
}


// ═════════════════════════════════════════════════════════════════════════════
// Consent Toggle Row
// ═════════════════════════════════════════════════════════════════════════════
function ConsentRow({
  record, candidateId, onToggle,
}: {
  record:      ConsentRecord
  candidateId: string
  orgContext?: string
  onToggle:    (code: string, val: boolean) => void
}) {
  const [saving, setSaving] = useState(false)
  const [err, setErr]       = useState('')
  const [open, setOpen]     = useState(false)

  const isOn = record.consented === true

  const toggle = async () => {
    if (record.required && isOn) return   // can't withdraw required consent
    setSaving(true); setErr('')
    const newVal = !isOn
    try {
      await apiClient.post('/dpdp/consent', {
        candidate_id: candidateId,
        purpose_code: record.purpose_code,
        consented:    newVal,
        consent_mechanism: 'HR_PORTAL',
      })
      onToggle(record.purpose_code, newVal)
    } catch (e: any) {
      setErr(e.response?.data?.detail ?? e.message)
    } finally { setSaving(false) }
  }

  return (
    <div className={`border-b border-gray-50 last:border-0 ${err ? 'bg-red-50/30' : ''}`}>
      <div className="flex items-center gap-3 p-4">
        <span className="text-xl flex-shrink-0 w-7">{record.icon}</span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-gray-900 truncate">
              {record.description_en}
            </p>
            {record.required && (
              <span className="text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded-full font-semibold flex-shrink-0">
                Required
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{record.description_hi}</p>
          {record.consented_at && (
            <p className="text-xs text-gray-400 mt-0.5">
              {isOn ? '✓ Granted' : '✗ Withdrawn'} ·{' '}
              {new Date(record.consented_at).toLocaleDateString('en-IN')} ·{' '}
              {record.version ?? CONSENT_VERSION}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Info toggle */}
          <button onClick={() => setOpen(o => !o)} className="text-gray-300 hover:text-gray-500">
            <Info className="w-4 h-4" />
          </button>

          {/* Toggle switch */}
          {record.required ? (
            <div className="w-11 h-6 bg-orange-400 rounded-full relative cursor-not-allowed opacity-70">
              <div className="absolute right-0.5 top-0.5 w-5 h-5 bg-white rounded-full shadow" />
            </div>
          ) : (
            <button
              onClick={toggle}
              disabled={saving}
              className={`w-11 h-6 rounded-full transition-colors relative focus:outline-none focus:ring-2 focus:ring-orange-400 ${
                isOn ? 'bg-orange-500' : 'bg-gray-200'
              } ${saving ? 'opacity-50' : ''}`}
              aria-label={`${isOn ? 'Withdraw' : 'Grant'} ${record.purpose_code} consent`}
            >
              {saving
                ? <div className="absolute inset-0 flex items-center justify-center"><Loader2 className="w-3 h-3 animate-spin text-white" /></div>
                : <div className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${isOn ? 'translate-x-5' : 'translate-x-0.5'}`} />}
            </button>
          )}
        </div>
      </div>

      {/* Expandable info */}
      {open && (
        <div className="px-4 pb-4 bg-blue-50/40 border-t border-blue-50 space-y-1">
          <p className="text-xs text-blue-700 font-semibold">{record.legal_basis}</p>
          {err && <p className="text-xs text-red-600">{err}</p>}
        </div>
      )}

      {err && !open && <p className="text-xs text-red-600 px-4 pb-2">{err}</p>}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// Consent Panel
// ═════════════════════════════════════════════════════════════════════════════
function ConsentPanel({ candidateId }: { candidateId: string }) {
  const [records, setRecords] = useState<ConsentRecord[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    if (!candidateId) return
    setLoading(true)
    try {
      const r = await apiClient.get(`/dpdp/consent/${candidateId}`)
      setRecords(r.data.purposes ?? [])
    } catch { setRecords([]) }
    finally { setLoading(false) }
  }, [candidateId])

  useEffect(() => { load() }, [load])

  const handleToggle = (code: string, val: boolean) => {
    setRecords(prev => prev.map(r =>
      r.purpose_code === code
        ? { ...r, consented: val, consented_at: new Date().toISOString(), version: CONSENT_VERSION }
        : r
    ))
  }

  const granted   = records.filter(r => r.consented === true).length
  const withdrawn = records.filter(r => r.consented === false).length
  const pending   = records.filter(r => r.consented === null).length

  return (
    <div className={card}>
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-50 bg-gradient-to-r from-orange-50 to-amber-50">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-orange-500" />
          <h2 className="font-bold text-gray-800">Purpose-Specific Consents</h2>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5 text-xs">
            <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-semibold">{granted} ✓</span>
            <span className="bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-semibold">{withdrawn} ✗</span>
            <span className="bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full font-semibold">{pending} —</span>
          </div>
          <button onClick={load} disabled={loading} className="text-gray-400 hover:text-gray-600">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>
      ) : records.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-10">Enter a candidate ID above to load consents</p>
      ) : (
        <div>
          {/* Policy notice */}
          <div className="mx-4 mt-4 mb-2 bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-xs text-blue-700 flex gap-2">
            <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
            Each purpose is toggled <strong>separately</strong> — no bundled consent (DPDP Act 2023 s.6).
            Required purposes cannot be withdrawn.
          </div>
          {records.map(r => (
            <ConsentRow
              key={r.purpose_code}
              record={r}
              candidateId={candidateId}
              onToggle={handleToggle}
            />
          ))}
        </div>
      )}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// Erasure Request Form
// ═════════════════════════════════════════════════════════════════════════════
function ErasurePanel({ candidateId }: { candidateId: string }) {
  const [requests, setRequests]   = useState<ErasureRequest[]>([])
  const [loading, setLoading]     = useState(false)
  const [showForm, setShowForm]   = useState(false)
  const [form, setForm]           = useState({
    request_type: 'ERASURE', reason: '', candidate_phone: '', candidate_name: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError]         = useState('')

  const loadRequests = useCallback(async () => {
    if (!candidateId) return
    setLoading(true)
    try {
      const r = await apiClient.get('/dpdp/erasure-requests')
      const all = r.data as ErasureRequest[]
      // Annotate days_remaining
      setRequests(all.map(req => ({
        ...req,
        days_remaining: daysBetween(req.response_due_at),
        is_overdue: daysBetween(req.response_due_at) < 0 && !['COMPLETED','REJECTED'].includes(req.status),
      })))
    } catch { setRequests([]) }
    finally { setLoading(false) }
  }, [candidateId])

  useEffect(() => { loadRequests() }, [loadRequests])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(''); setSubmitting(true)
    try {
      await apiClient.post('/dpdp/erasure-request', {
        candidate_id:    candidateId,
        request_type:    form.request_type,
        reason:          form.reason || undefined,
        candidate_phone: form.candidate_phone || undefined,
        candidate_name:  form.candidate_name || undefined,
      })
      setShowForm(false)
      setForm({ request_type: 'ERASURE', reason: '', candidate_phone: '', candidate_name: '' })
      loadRequests()
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setSubmitting(false) }
  }

  const process = async (id: string, action: 'COMPLETE' | 'REJECT') => {
    const reason = action === 'REJECT' ? prompt('Denial reason (required):') : undefined
    if (action === 'REJECT' && !reason) return
    try {
      await apiClient.post(`/dpdp/erasure-requests/${id}/process?action=${action}${reason ? `&denial_reason=${encodeURIComponent(reason)}` : ''}`)
      loadRequests()
    } catch (err: any) {
      alert(err.response?.data?.detail ?? err.message)
    }
  }

  return (
    <div className={card}>
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-50 bg-gradient-to-r from-red-50 to-orange-50">
        <div className="flex items-center gap-2">
          <Trash2 className="w-5 h-5 text-red-500" />
          <h2 className="font-bold text-gray-800">Erasure / Access Requests</h2>
        </div>
        <div className="flex gap-2">
          <button onClick={loadRequests} disabled={loading} className="text-gray-400 hover:text-gray-600">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {candidateId && (
            <button onClick={() => setShowForm(v => !v)} className="text-xs px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded-lg font-semibold transition">
              + New Request
            </button>
          )}
        </div>
      </div>

      {/* New request form */}
      {showForm && (
        <div className="p-5 border-b border-gray-50 bg-red-50/30">
          <p className="text-sm font-bold text-gray-800 mb-4">New Data Rights Request</p>
          <form onSubmit={submit} className="space-y-4">
            {/* Request type pills */}
            <div className="grid grid-cols-2 gap-2">
              {REQUEST_TYPES.map(rt => (
                <button key={rt.value} type="button"
                  onClick={() => setForm(f => ({ ...f, request_type: rt.value }))}
                  className={`px-3 py-2.5 rounded-xl border text-sm font-medium transition text-left flex items-center gap-2 ${
                    form.request_type === rt.value
                      ? 'border-orange-500 bg-orange-50 text-orange-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}>
                  <span>{rt.emoji}</span>{rt.label}
                </button>
              ))}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1 block">Candidate Name</label>
                <input value={form.candidate_name}
                  onChange={e => setForm(f => ({ ...f, candidate_name: e.target.value }))}
                  className={inp} placeholder="For WhatsApp acknowledgment" required />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-600 mb-1 block">
                  Phone (for WhatsApp ack)
                </label>
                <input value={form.candidate_phone}
                  onChange={e => setForm(f => ({ ...f, candidate_phone: e.target.value }))}
                  className={inp} placeholder="+91XXXXXXXXXX" />
              </div>
              <div className="sm:col-span-2">
                <label className="text-xs font-semibold text-gray-600 mb-1 block">Reason (optional)</label>
                <textarea rows={2} value={form.reason}
                  onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
                  className={`${inp} resize-none`} placeholder="Candidate's stated reason" />
              </div>
            </div>

            {/* SLA notice */}
            <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 text-xs text-blue-700 flex gap-2">
              <Clock className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>DPDP Act 2023 s.13 — 30-day response SLA starts from submission.
              WhatsApp acknowledgment is sent automatically if phone is provided.</span>
            </div>

            {error && <p className="text-xs text-red-600 bg-red-50 rounded-xl px-3 py-2">{error}</p>}

            <div className="flex gap-2">
              <button type="submit" disabled={submitting || !form.candidate_name}
                className={`${btn} flex-1`}>
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                Submit Request
              </button>
              <button type="button" onClick={() => setShowForm(false)} className={btnOutline}>Cancel</button>
            </div>
          </form>
        </div>
      )}

      {/* Request list */}
      {loading ? (
        <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-orange-500" /></div>
      ) : requests.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-8">No requests found</p>
      ) : (
        <div className="divide-y divide-gray-50">
          {requests.map(r => (
            <div key={r.id} className={`p-4 ${r.is_overdue ? 'bg-red-50/30' : ''}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-xs font-mono text-gray-400">#{r.id.slice(0, 8).toUpperCase()}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${STATUS_STYLE[r.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {r.status}
                    </span>
                    {r.is_overdue && (
                      <span className="text-xs bg-red-600 text-white px-2 py-0.5 rounded-full font-semibold">
                        OVERDUE
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-semibold text-gray-900 mt-1">
                    {REQUEST_TYPES.find(t => t.value === r.request_type)?.emoji}{' '}
                    {REQUEST_TYPES.find(t => t.value === r.request_type)?.label}
                  </p>
                  <div className="flex flex-wrap gap-3 text-xs text-gray-500 mt-1">
                    <span>Submitted: {new Date(r.requested_at).toLocaleDateString('en-IN')}</span>
                    {r.response_due_at && (
                      <span className={`font-medium ${
                        (r.days_remaining ?? 99) < 0 ? 'text-red-600' :
                        (r.days_remaining ?? 99) < 7 ? 'text-amber-600' : ''
                      }`}>
                        {(r.days_remaining ?? 0) >= 0
                          ? `Due in ${r.days_remaining}d`
                          : `Overdue by ${Math.abs(r.days_remaining ?? 0)}d`}
                      </span>
                    )}
                  </div>
                  {r.denial_reason && (
                    <p className="text-xs text-gray-500 mt-1 italic">
                      Reason: {r.denial_reason}
                    </p>
                  )}
                </div>

                {/* Admin actions */}
                {!['COMPLETED','REJECTED'].includes(r.status) && (
                  <div className="flex flex-col gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => process(r.id, 'COMPLETE')}
                      className="text-xs px-2.5 py-1.5 bg-green-500 hover:bg-green-600 text-white rounded-lg font-semibold transition"
                    >
                      Complete
                    </button>
                    <button
                      onClick={() => process(r.id, 'REJECT')}
                      className="text-xs px-2.5 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded-lg font-semibold transition"
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// Purposes Reference Panel
// ═════════════════════════════════════════════════════════════════════════════
function PurposesPanel() {
  const [purposes, setPurposes] = useState<Purpose[]>([])
  const [open, setOpen]         = useState(false)

  useEffect(() => {
    apiClient.get('/dpdp/purposes').then(r => setPurposes(r.data)).catch(() => {})
  }, [])

  return (
    <div className={card}>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50/50 transition"
      >
        <div className="flex items-center gap-2">
          <Lock className="w-5 h-5 text-orange-500" />
          <span className="font-bold text-gray-800">DPDP Purpose Codes Reference</span>
        </div>
        {open ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
      </button>
      {open && (
        <div className="border-t border-gray-50">
          {purposes.map(p => (
            <div key={p.code} className="flex items-start gap-3 px-5 py-3 border-b border-gray-50 last:border-0">
              <span className="text-xl flex-shrink-0">{p.icon}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-gray-900">{p.description_en}</p>
                  {p.required && <span className="text-xs bg-orange-100 text-orange-700 px-1.5 py-0.5 rounded-full">Required</span>}
                </div>
                <p className="text-xs text-gray-400">{p.description_hi}</p>
                <div className="flex gap-3 mt-1 text-xs text-gray-500">
                  <span>{p.legal_basis}</span>
                  {p.retention_years !== null && (
                    <span>· Retention: {p.retention_years === 0 ? 'Erase on withdrawal' : `${p.retention_years}yr`}</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// ═════════════════════════════════════════════════════════════════════════════
// Main Page
// ═════════════════════════════════════════════════════════════════════════════
export default function DPDPPrivacyCenter() {
  const [candidateId, setCandidateId] = useState('')
  const [input, setInput]             = useState('')

  const search = () => setCandidateId(input.trim())

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">DPDP Privacy Center 🔏</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Digital Personal Data Protection Act 2023 · Per-candidate consent management
        </p>
      </div>

      {/* Candidate search */}
      <div className={`${card} p-4`}>
        <label className="text-xs font-bold text-gray-600 mb-2 block flex items-center gap-1">
          <Search className="w-3 h-3" /> Candidate ID
        </label>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
            className={`${inp} flex-1 font-mono text-xs`}
            placeholder="Paste candidate UUID…"
          />
          <button onClick={search} disabled={!input.trim()} className={btn}>
            <Search className="w-4 h-4" /> Load
          </button>
        </div>
        {candidateId && (
          <p className="text-xs text-orange-600 mt-2 font-medium">
            ✓ Viewing consent for: {candidateId}
          </p>
        )}
      </div>

      {/* Consent toggles — always show even without candidate */}
      <ConsentPanel candidateId={candidateId} />

      {/* Erasure requests */}
      <ErasurePanel candidateId={candidateId} />

      {/* Reference */}
      <PurposesPanel />
    </div>
  )
}
