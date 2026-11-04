/**
 * Privacy Centre — Candidate-facing DPDP Act 2023 dashboard
 *
 * Accessed via tokenised URL: /privacy-centre/:token
 * No Supabase auth required — authenticated by the secure 7-day token.
 *
 * Features:
 *  • Purpose-specific consent toggles (no bundled consent)
 *  • View / request erasure (with WhatsApp ack)
 *  • Legal retention notices
 *  • India data localisation banner
 *  • Bilingual (English + Hindi)
 */

import axios from 'axios'
import React,{ useCallback,useEffect,useState } from 'react'
import { useParams } from 'react-router-dom'

const API = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

// Raw axios — no JWT auth (candidate uses token)
const api = axios.create({ baseURL: API })

// ─── Types ───────────────────────────────────────────────────────────────────

interface PurposeConsent {
  purpose_code:    string
  description_en:  string
  description_hi:  string
  icon:            string
  required:        boolean
  consented:       boolean | null
  consented_at:    string | null
  can_withdraw:    boolean
  retention_years: number | null
  legal_basis:     string
  can_fully_erase: boolean
}

interface ErasureRequest {
  id:              string
  request_type:    string
  status:          string
  requested_at:    string
  response_due_at: string
  denial_reason:   string | null
  completed_at:    string | null
  days_remaining?: number
}

interface PrivacyCentreData {
  candidate_id:      string
  consent_version:   string
  consents:          PurposeConsent[]
  requests:          ErasureRequest[]
  data_region:       string
  data_fiduciary:    string
  grievance_officer: string
  dpbi_url:          string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const statusColor = (s: string) =>
  s === 'COMPLETED' ? 'text-green-700 bg-green-100' :
  s === 'REJECTED'  ? 'text-red-700 bg-red-100' :
  'text-amber-700 bg-amber-100'

const reqTypeLabel: Record<string, string> = {
  ERASURE:    'Data Erasure / डेटा मिटाना',
  CORRECTION: 'Data Correction / सुधार',
  ACCESS:     'Data Access / डेटा देखना',
  NOMINATION: 'Nomination / नामांकन',
}

// ─── Consent Toggle ──────────────────────────────────────────────────────────

function ConsentToggle({
  purpose, token, onUpdate,
}: {
  purpose: PurposeConsent
  token:   string
  onUpdate: (code: string, newVal: boolean) => void
}) {
  const [saving, setSaving] = useState(false)
  const [error,  setError]  = useState('')

  const toggle = async () => {
    if (purpose.required && purpose.consented) return
    setSaving(true); setError('')
    const newVal = !purpose.consented
    try {
      await api.post(`/dpdp/privacy-centre/${token}/consent`, {
        purpose_code: purpose.purpose_code,
        consented:    newVal,
      })
      onUpdate(purpose.purpose_code, newVal)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setSaving(false) }
  }

  const isOn = purpose.consented === true

  return (
    <div className={`rounded-2xl border p-4 transition-all ${
      isOn ? 'border-orange-200 bg-orange-50' : 'border-gray-100 bg-white'
    }`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <span className="text-2xl flex-shrink-0">{purpose.icon}</span>
          <div className="min-w-0">
            <p className="font-semibold text-gray-900 text-sm leading-snug">
              {purpose.description_en}
            </p>
            <p className="text-xs text-gray-500 mt-0.5 leading-snug">
              {purpose.description_hi}
            </p>
            <p className="text-xs text-blue-600 mt-1">{purpose.legal_basis}</p>
            {purpose.retention_years !== null && (
              <p className="text-xs text-gray-400 mt-0.5">
                Retention: {purpose.retention_years === 0 ? 'Erased on withdrawal' :
                  `${purpose.retention_years} year${purpose.retention_years !== 1 ? 's' : ''}`}
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-col items-center gap-1 flex-shrink-0">
          {purpose.required ? (
            <div className="flex flex-col items-center">
              <div className="w-11 h-6 rounded-full bg-orange-400 relative">
                <div className="absolute right-0.5 top-0.5 w-5 h-5 rounded-full bg-white shadow" />
              </div>
              <span className="text-xs text-orange-600 font-semibold mt-1">Required</span>
            </div>
          ) : (
            <button
              onClick={toggle}
              disabled={saving}
              className={`w-11 h-6 rounded-full transition-colors relative focus:outline-none focus:ring-2 focus:ring-orange-400 ${
                isOn ? 'bg-orange-500' : 'bg-gray-200'
              } ${saving ? 'opacity-50' : ''}`}
              aria-label={`${isOn ? 'Withdraw' : 'Grant'} consent for ${purpose.purpose_code}`}
            >
              <div className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${
                isOn ? 'translate-x-5' : 'translate-x-0.5'
              }`} />
            </button>
          )}

          {purpose.consented_at && (
            <p className="text-xs text-gray-400 text-center max-w-[80px]">
              {isOn ? '✓' : '✗'} {new Date(purpose.consented_at).toLocaleDateString('en-IN')}
            </p>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-1.5">{error}</p>
      )}

      {!purpose.can_fully_erase && (
        <p className="mt-2 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-1.5">
          ⚠ Some data in this category must be retained under Indian law even after withdrawal
        </p>
      )}
    </div>
  )
}

// ─── Erasure Form ─────────────────────────────────────────────────────────────

function ErasureForm({ token, onSubmitted }: { token: string; onSubmitted: () => void }) {
  const [open,    setOpen]    = useState(false)
  const [type,    setType]    = useState('ERASURE')
  const [reason,  setReason]  = useState('')
  const [phone,   setPhone]   = useState('')
  const [name,    setName]    = useState('')
  const [saving,  setSaving]  = useState(false)
  const [error,   setError]   = useState('')
  const [success, setSuccess] = useState('')

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setSaving(true)
    try {
      const resp = await api.post(`/dpdp/privacy-centre/${token}/erasure`, {
        request_type: type, reason, phone: phone || undefined,
        name: name || undefined,
      })
      setSuccess(
        `Request #${resp.data.id?.slice(0, 8).toUpperCase()} submitted. ` +
        (resp.data.whatsapp_ack_sent ? 'WhatsApp confirmation sent. ' : '') +
        `Response by ${resp.data.response_due_at?.slice(0, 10) ?? '30 days'}.`
      )
      onSubmitted()
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setSaving(false) }
  }

  if (!open) return (
    <button
      onClick={() => setOpen(true)}
      className="w-full py-3 rounded-2xl border-2 border-dashed border-gray-200 text-sm text-gray-500 hover:border-orange-300 hover:text-orange-600 transition font-medium"
    >
      + Submit Erasure / Correction / Access Request
    </button>
  )

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <h3 className="font-bold text-gray-900 mb-4">
        Submit a Data Rights Request / डेटा अधिकार अनुरोध
      </h3>

      {success ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-700">
          ✅ {success}
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Request Type</label>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(reqTypeLabel).map(([val, label]) => (
                <button key={val} type="button"
                  onClick={() => setType(val)}
                  className={`text-left px-3 py-2 rounded-xl border text-xs font-medium transition ${
                    type === val
                      ? 'border-orange-500 bg-orange-50 text-orange-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Your Name</label>
            <input
              value={name} onChange={e => setName(e.target.value)} required
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
              placeholder="Full name for acknowledgment"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">
              WhatsApp Number (optional — for acknowledgment)
            </label>
            <input
              value={phone} onChange={e => setPhone(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
              placeholder="+91XXXXXXXXXX"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">
              Reason (optional)
            </label>
            <textarea
              value={reason} onChange={e => setReason(e.target.value)} rows={3}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 resize-none"
              placeholder="Why are you requesting this? (optional)"
            />
          </div>

          <div className="bg-blue-50 rounded-xl p-3 text-xs text-blue-700">
            <strong>30-day SLA:</strong> Under DPDP Act 2023 Section 13, we must respond within 30 days.
            If we fail, you can appeal to the Data Protection Board of India.
          </div>

          {error && <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-1.5">{error}</p>}

          <div className="flex gap-2">
            <button type="submit" disabled={saving || !name}
              className="flex-1 py-2.5 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-xl transition disabled:opacity-50">
              {saving ? 'Submitting…' : 'Submit Request'}
            </button>
            <button type="button" onClick={() => setOpen(false)}
              className="px-4 py-2.5 border border-gray-200 text-gray-600 text-sm rounded-xl hover:bg-gray-50 transition">
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function PrivacyCenter() {
  const { token } = useParams<{ token: string }>()
  const [data,    setData]    = useState<PrivacyCentreData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState('')
  const [tab,     setTab]     = useState<'consents' | 'requests' | 'retention'>('consents')

  const load = useCallback(async () => {
    if (!token) { setError('No privacy token in URL'); setLoading(false); return }
    try {
      const resp = await api.get(`/dpdp/privacy-centre/${token}`)
      setData(resp.data)
    } catch (err: any) {
      setError(
        err.response?.status === 401
          ? 'This privacy link has expired or is invalid. Please request a new one from your recruiter.'
          : (err.response?.data?.detail ?? 'Failed to load Privacy Centre')
      )
    } finally { setLoading(false) }
  }, [token])

  useEffect(() => { load() }, [load])

  const handleConsentUpdate = (code: string, newVal: boolean) => {
    setData(prev => {
      if (!prev) return prev
      return {
        ...prev,
        consents: prev.consents.map(c =>
          c.purpose_code === code
            ? { ...c, consented: newVal, consented_at: new Date().toISOString() }
            : c
        ),
      }
    })
  }

  // ── Loading / Error ──────────────────────────────────────────────────────
  if (loading) return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-amber-50 flex items-center justify-center">
      <div className="text-center">
        <div className="w-10 h-10 border-4 border-orange-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-gray-500">Loading Privacy Centre…</p>
      </div>
    </div>
  )

  if (error || !data) return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-amber-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-sm border border-red-100 p-8 max-w-md w-full text-center">
        <p className="text-4xl mb-4">🔒</p>
        <h2 className="font-bold text-gray-900 mb-2">Access Denied / एक्सेस अस्वीकृत</h2>
        <p className="text-sm text-gray-500">{error}</p>
        <p className="text-xs text-gray-400 mt-4">
          Contact your recruiter for a new privacy link.
        </p>
      </div>
    </div>
  )

  const pendingRequests = data.requests.filter(r => !['COMPLETED','REJECTED'].includes(r.status))
  const grantedCount   = data.consents.filter(c => c.consented === true).length

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-amber-50">
      <div className="max-w-2xl mx-auto px-4 py-6">

        {/* Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-orange-500 rounded-2xl mb-3 shadow-sm">
            <span className="text-2xl">🔐</span>
          </div>
          <h1 className="text-xl font-bold text-gray-900">Privacy Centre</h1>
          <p className="text-sm text-gray-500">गोपनीयता केंद्र</p>
          <p className="text-xs text-gray-400 mt-1">
            DPDP Act 2023 · {data.data_fiduciary}
          </p>
        </div>

        {/* India data localisation banner */}
        <div className="bg-green-50 border border-green-100 rounded-2xl px-4 py-3 mb-4 flex items-center gap-3">
          <span className="text-xl">🇮🇳</span>
          <div>
            <p className="text-xs font-semibold text-green-700">
              India Data Localisation — Your data is stored in India
            </p>
            <p className="text-xs text-green-600">
              Region: {data.data_region} (Mumbai) · DPDP Act 2023 s.16
            </p>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          {[
            { label: 'Consents Given', value: grantedCount, emoji: '✅' },
            { label: 'Pending Requests', value: pendingRequests.length, emoji: '⏳' },
            { label: 'SLA Days', value: 30, emoji: '📅' },
          ].map(s => (
            <div key={s.label} className="bg-white rounded-2xl border border-gray-100 p-3 text-center shadow-sm">
              <p className="text-xl">{s.emoji}</p>
              <p className="text-lg font-bold text-gray-900">{s.value}</p>
              <p className="text-xs text-gray-500">{s.label}</p>
            </div>
          ))}
        </div>

        {/* Tab bar */}
        <div className="flex bg-white rounded-xl border border-gray-100 p-1 mb-5 shadow-sm">
          {([
            { id: 'consents',  label: 'My Consents' },
            { id: 'requests',  label: 'My Requests' },
            { id: 'retention', label: 'Data Retained' },
          ] as const).map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition ${
                tab === t.id
                  ? 'bg-orange-500 text-white shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Consents Tab ─────────────────────────────────────────────── */}
        {tab === 'consents' && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 bg-white rounded-xl border border-gray-100 px-4 py-2.5">
              Each consent is <strong>separate</strong> — toggle them individually.
              Required consents (🔒) are needed for the core recruitment service.
            </p>
            {data.consents.map(p => (
              <ConsentToggle
                key={p.purpose_code}
                purpose={p}
                token={token!}
                onUpdate={handleConsentUpdate}
              />
            ))}
          </div>
        )}

        {/* ── Requests Tab ─────────────────────────────────────────────── */}
        {tab === 'requests' && (
          <div className="space-y-4">
            <ErasureForm token={token!} onSubmitted={load} />

            {data.requests.length === 0 ? (
              <p className="text-center text-sm text-gray-400 py-6">
                No requests submitted yet.
              </p>
            ) : (
              <div className="space-y-3">
                {data.requests.map(r => (
                  <div key={r.id} className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-xs font-mono text-gray-400">#{r.id.slice(0, 8).toUpperCase()}</p>
                        <p className="font-semibold text-sm text-gray-900 mt-0.5">
                          {reqTypeLabel[r.request_type] ?? r.request_type}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          Submitted: {new Date(r.requested_at).toLocaleDateString('en-IN')}
                        </p>
                        {r.response_due_at && (
                          <p className={`text-xs mt-0.5 font-medium ${
                            (r.days_remaining ?? 99) < 0 ? 'text-red-600' :
                            (r.days_remaining ?? 99) < 7 ? 'text-amber-600' : 'text-gray-500'
                          }`}>
                            {(r.days_remaining ?? 0) >= 0
                              ? `Response due in ${r.days_remaining}d (${r.response_due_at.slice(0, 10)})`
                              : `⚠ Overdue by ${Math.abs(r.days_remaining ?? 0)}d`}
                          </p>
                        )}
                        {r.denial_reason && (
                          <p className="text-xs text-gray-500 mt-1 italic">
                            Reason: {r.denial_reason}
                          </p>
                        )}
                      </div>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${statusColor(r.status)}`}>
                        {r.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4 text-xs text-blue-700">
              <p className="font-semibold mb-1">Your Rights under DPDP Act 2023</p>
              <ul className="space-y-1">
                <li>✅ Right to access your personal data (Section 11)</li>
                <li>✅ Right to correction and erasure (Section 12)</li>
                <li>✅ Right to grievance redressal (Section 14)</li>
                <li>✅ Right to nominate a representative (Section 15)</li>
              </ul>
              <p className="mt-2">
                Unresolved? Appeal to{' '}
                <a href={data.dpbi_url} target="_blank" rel="noopener noreferrer"
                  className="underline font-semibold">
                  Data Protection Board of India
                </a>
              </p>
            </div>
          </div>
        )}

        {/* ── Retention Tab ────────────────────────────────────────────── */}
        {tab === 'retention' && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 bg-white rounded-xl border border-gray-100 px-4 py-2.5">
              Some data must be retained under Indian law even after you request erasure.
              This table explains what is kept and why.
            </p>

            {data.consents.map(p => (
              <div key={p.purpose_code} className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-lg">{p.icon}</span>
                  <p className="font-semibold text-sm text-gray-900">{p.description_en}</p>
                </div>
                <div className="space-y-1 text-xs text-gray-600">
                  <div className="flex justify-between">
                    <span>Retention period</span>
                    <span className="font-medium">
                      {p.retention_years === null ? 'Statutory — varies'
                       : p.retention_years === 0 ? 'Deleted when withdrawn'
                       : `${p.retention_years} year${p.retention_years !== 1 ? 's' : ''}`}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Legal basis</span>
                    <span className="font-medium text-blue-700 text-right max-w-[55%]">
                      {p.legal_basis}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Can fully erase</span>
                    <span className={p.can_fully_erase ? 'text-green-600 font-medium' : 'text-amber-600 font-medium'}>
                      {p.can_fully_erase ? '✓ Yes' : '⚠ Partial (statutory records kept)'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-gray-400 space-y-1">
          <p>Consent version: {data.consent_version} · Data region: {data.data_region}</p>
          <p>
            Questions?{' '}
            <a href={`mailto:${data.grievance_officer}`} className="text-orange-600 underline">
              {data.grievance_officer}
            </a>
          </p>
          <p>Powered by DPDP Act 2023 — India's Digital Personal Data Protection Law</p>
        </div>
      </div>
    </div>
  )
}
