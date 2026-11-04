/**
 * Diversity Dashboard — Indian Diversity Reporting
 *
 * Shows:
 *  • Applications and hires by gender
 *  • PwD applications and hire rate
 *  • Gender pay gap (Equal Remuneration Act 1976)
 *  • Blind screening mode toggle per job
 *
 * Design constraints:
 *  • Religion is never displayed or collected
 *  • SC/ST/OBC/EWS section shown only when statutory_reporting_required=true
 *  • All collection is voluntary; data marked NOT_DISCLOSED separately
 */

import { apiClient } from '@/lib/api'
import {
AlertCircle,
Award,
EyeOff,
IndianRupee,
Minus,
RefreshCw,
Shield,
TrendingDown,
TrendingUp,
UserCheck,
Users
} from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'

// ─── Types ───────────────────────────────────────────────────────────────────

interface GenderBreakdown {
  total_applications:    number
  total_hires:           number
  applications_by_gender: Record<string, number>
  hires_by_gender:       Record<string, number>
  hire_rate_by_gender:   Record<string, number | null>
}

interface PwDMetrics {
  total_applications:      number
  pwd_applications:        number
  non_pwd_applications:    number
  pwd_pct_of_applications: number
  total_hires:             number
  pwd_hires:               number
  pwd_hire_rate:           number
  law:                     string
}

interface PayGap {
  insufficient_data:    boolean
  reason?:              string
  median_male_inr?:     number
  median_female_inr?:   number
  median_pay_gap_pct?:  number
  mean_pay_gap_pct?:    number
  male_sample_size?:    number
  female_sample_size?:  number
  direction?:           string
  law:                  string
}

interface DiversitySettings {
  statutory_reporting_required: boolean
  statutory_reporting_law:      string | null
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const GENDER_COLORS: Record<string, string> = {
  MALE:              'bg-blue-500',
  FEMALE:            'bg-pink-500',
  TRANSGENDER:       'bg-purple-500',
  NON_BINARY:        'bg-teal-500',
  PREFER_NOT_TO_SAY: 'bg-gray-400',
  NOT_DISCLOSED:     'bg-gray-300',
}

const GENDER_LABELS: Record<string, string> = {
  MALE:              'Male',
  FEMALE:            'Female',
  TRANSGENDER:       'Transgender',
  NON_BINARY:        'Non-Binary',
  PREFER_NOT_TO_SAY: 'Prefer Not to Say',
  NOT_DISCLOSED:     'Not Disclosed',
}

function fmtINR(n: number | undefined) {
  if (!n) return '—'
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n)
}

function pct(value: number | null | undefined) {
  if (value == null) return '—'
  return `${value.toFixed(1)}%`
}

// ─── Components ──────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, icon, color = 'orange' }: {
  label: string; value: string | number; sub?: string
  icon: React.ReactNode; color?: string
}) {
  const ring = color === 'blue' ? 'ring-blue-100 bg-blue-50' :
               color === 'pink' ? 'ring-pink-100 bg-pink-50' :
               color === 'green'? 'ring-green-100 bg-green-50' :
               'ring-orange-100 bg-orange-50'
  return (
    <div className={`rounded-2xl border ring-1 ${ring} p-5`}>
      <div className="flex items-center gap-2 mb-2 text-gray-500">{icon}<span className="text-xs font-semibold">{label}</span></div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  )
}

function GenderBar({ data, total }: { data: Record<string, number>; total: number }) {
  if (!total) return <p className="text-sm text-gray-400">No data</p>
  return (
    <div className="space-y-2">
      {Object.entries(data).sort((a, b) => b[1] - a[1]).map(([g, n]) => (
        <div key={g} className="flex items-center gap-3">
          <div className="w-28 text-xs text-gray-600 font-medium truncate">
            {GENDER_LABELS[g] ?? g}
          </div>
          <div className="flex-1 bg-gray-100 rounded-full h-2.5 overflow-hidden">
            <div
              className={`h-2.5 rounded-full ${GENDER_COLORS[g] ?? 'bg-gray-400'}`}
              style={{ width: `${Math.round(n / total * 100)}%` }}
            />
          </div>
          <div className="text-xs text-gray-600 w-20 text-right">
            {n} ({Math.round(n / total * 100)}%)
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Blind Screening Panel ────────────────────────────────────────────────────

function BlindScreeningPanel() {
  const [candidateId, setCandidateId] = useState('')
  const [blinded, setBlinded] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    if (!candidateId.trim()) return
    setError(''); setLoading(true); setBlinded(null)
    try {
      const r = await apiClient.post(`/diversity/blind-screening/${candidateId.trim()}`)
      setBlinded(r.data)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally { setLoading(false) }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100 bg-gradient-to-r from-purple-50 to-indigo-50">
        <EyeOff className="w-5 h-5 text-purple-500" />
        <h2 className="font-bold text-gray-800">Blind Screening</h2>
      </div>
      <div className="p-5 space-y-4">
        <p className="text-sm text-gray-600">
          Blind screening hides name, email, phone, location, and photo — keeping only skills,
          experience, and scores. The original record is <strong>not modified</strong>.
        </p>
        <div className="flex gap-2">
          <input
            value={candidateId} onChange={e => setCandidateId(e.target.value)}
            className="flex-1 border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
            placeholder="Candidate UUID"
          />
          <button
            onClick={run} disabled={loading || !candidateId.trim()}
            className="px-4 py-2.5 bg-purple-500 hover:bg-purple-600 text-white text-sm font-semibold rounded-xl transition disabled:opacity-50 flex items-center gap-2"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <EyeOff className="w-4 h-4" />}
            Blind Screen
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-100 rounded-xl px-4 py-2.5 text-sm text-red-700">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
          </div>
        )}

        {blinded && (
          <div className="bg-purple-50 border border-purple-100 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-4 h-4 text-purple-600" />
              <p className="text-sm font-semibold text-purple-700">
                Blinded view — Code: #{blinded._blind_code}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              {[
                ['Name',    `${blinded.first_name} ${blinded.last_name}`],
                ['Email',   blinded.email ?? '[hidden]'],
                ['Phone',   blinded.phone ?? '[hidden]'],
                ['Location',blinded.location ?? '[hidden]'],
                ['Stage',   blinded.pipeline_stage],
                ['Skills',  Array.isArray(blinded.parsed_skills)
                              ? blinded.parsed_skills.slice(0, 3).join(', ')
                              : '—'],
              ].map(([k, v]) => (
                <div key={k} className="flex gap-1">
                  <span className="text-gray-500 w-16 flex-shrink-0">{k}:</span>
                  <span className="text-gray-800 font-medium truncate">{String(v ?? '—')}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function DiversityDashboard() {
  const [gender, setGender]     = useState<GenderBreakdown | null>(null)
  const [pwd, setPwd]           = useState<PwDMetrics | null>(null)
  const [payGap, setPayGap]     = useState<PayGap | null>(null)
  const [settings, setSettings] = useState<DiversitySettings | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo]     = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError('')
    const params = new URLSearchParams()
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo)   params.set('date_to', dateTo)
    const q = params.toString() ? `?${params}` : ''

    try {
      const [g, p, pg, s] = await Promise.all([
        apiClient.get(`/diversity/gender-breakdown${q}`),
        apiClient.get(`/diversity/pwd-metrics${q}`),
        apiClient.get(`/diversity/pay-gap${q}`),
        apiClient.get('/diversity/settings'),
      ])
      setGender(g.data)
      setPwd(p.data)
      setPayGap(pg.data)
      setSettings(s.data)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Failed to load diversity data')
    } finally { setLoading(false) }
  }, [dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  const payGapIcon = () => {
    if (!payGap || payGap.insufficient_data || !payGap.median_pay_gap_pct) return <Minus className="w-4 h-4 text-gray-400" />
    return payGap.median_pay_gap_pct > 0
      ? <TrendingDown className="w-4 h-4 text-red-500" />
      : <TrendingUp className="w-4 h-4 text-green-500" />
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Diversity Dashboard 🇮🇳</h1>
          <p className="text-sm text-gray-500 mt-1">
            RPWD Act 2016 · Equal Remuneration Act 1976 · Transgender Persons Act 2019
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Date filters */}
      <div className="flex gap-3 flex-wrap">
        {[['From', dateFrom, setDateFrom], ['To', dateTo, setDateTo]].map(([label, val, setter]) => (
          <div key={String(label)} className="flex items-center gap-2">
            <label className="text-xs font-semibold text-gray-500">{String(label)}</label>
            <input type="date" value={String(val)}
              onChange={e => (setter as (v: string) => void)(e.target.value)}
              className="border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
        ))}
        {(dateFrom || dateTo) && (
          <button onClick={() => { setDateFrom(''); setDateTo('') }}
            className="text-xs text-orange-600 hover:underline">
            Clear filters
          </button>
        )}
      </div>

      {/* Policy notice */}
      <div className="bg-amber-50 border border-amber-100 rounded-2xl px-4 py-3 flex gap-3">
        <Shield className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-amber-800">
          <strong>Collection policy:</strong> Gender and PwD status are <strong>voluntary</strong>.
          Religion is <strong>never collected</strong>.
          SC/ST/OBC/EWS data is {settings?.statutory_reporting_required
            ? <strong>enabled</strong>
            : 'only enabled when statutory reporting is required'}.
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-2xl px-4 py-3 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />{error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-10 h-10 border-4 border-orange-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <StatCard
              label="Total Applications" icon={<Users className="w-4 h-4" />}
              value={gender?.total_applications ?? 0} color="orange"
            />
            <StatCard
              label="Total Hires" icon={<UserCheck className="w-4 h-4" />}
              value={gender?.total_hires ?? 0} color="green"
            />
            <StatCard
              label="PwD Applications" icon={<Award className="w-4 h-4" />}
              value={pwd?.pwd_applications ?? 0}
              sub={`${pct(pwd?.pwd_pct_of_applications)} of total`}
              color="blue"
            />
            <StatCard
              label="Gender Pay Gap" icon={payGapIcon()}
              value={payGap?.insufficient_data ? 'N/A' : pct(payGap?.median_pay_gap_pct)}
              sub={payGap?.insufficient_data ? 'Insufficient data' : payGap?.direction?.replace(/_/g, ' ')}
              color={payGap?.insufficient_data ? 'orange' : (payGap?.median_pay_gap_pct ?? 0) > 0 ? 'pink' : 'green'}
            />
          </div>

          {/* Gender breakdown */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
              <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
                <Users className="w-4 h-4 text-orange-500" /> Applications by Gender
              </h3>
              {gender ? (
                <GenderBar data={gender.applications_by_gender} total={gender.total_applications} />
              ) : <p className="text-sm text-gray-400">No data</p>}
            </div>

            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
              <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
                <UserCheck className="w-4 h-4 text-green-500" /> Hires by Gender
              </h3>
              {gender ? (
                gender.total_hires > 0
                  ? <GenderBar data={gender.hires_by_gender} total={gender.total_hires} />
                  : <p className="text-sm text-gray-400">No hires recorded yet</p>
              ) : <p className="text-sm text-gray-400">No data</p>}
            </div>
          </div>

          {/* Hire rate by gender */}
          {gender && Object.keys(gender.hire_rate_by_gender).length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
              <h3 className="font-bold text-gray-800 mb-4">Hire Rate by Gender</h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Object.entries(gender.hire_rate_by_gender).map(([g, rate]) => (
                  <div key={g} className="bg-gray-50 rounded-xl p-3 text-center">
                    <p className="text-xs text-gray-500 mb-1">{GENDER_LABELS[g] ?? g}</p>
                    <p className="text-lg font-bold text-gray-900">{pct(rate)}</p>
                    <div className={`mt-1 mx-auto w-3 h-3 rounded-full ${GENDER_COLORS[g] ?? 'bg-gray-400'}`} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* PwD metrics */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
              <Award className="w-4 h-4 text-blue-500" /> PwD Metrics (RPWD Act 2016)
            </h3>
            {pwd ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  ['PwD Applications',  pwd.pwd_applications,        ''],
                  ['Non-PwD Applications', pwd.non_pwd_applications,  ''],
                  ['PwD Hires',          pwd.pwd_hires,               ''],
                  ['PwD Hire Rate',      pct(pwd.pwd_hire_rate),      'of all hires'],
                ].map(([l, v, s]) => (
                  <div key={String(l)} className="bg-blue-50 rounded-xl p-4 text-center">
                    <p className="text-xs text-blue-600 font-semibold mb-1">{String(l)}</p>
                    <p className="text-xl font-bold text-blue-900">{String(v)}</p>
                    {s && <p className="text-xs text-blue-500 mt-0.5">{String(s)}</p>}
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-gray-400">No data</p>}
          </div>

          {/* Gender Pay Gap */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
            <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
              <IndianRupee className="w-4 h-4 text-orange-500" /> Gender Pay Gap (Equal Remuneration Act 1976)
            </h3>
            {payGap?.insufficient_data ? (
              <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-sm text-amber-700">
                <p className="font-semibold mb-1">⚠ Insufficient Data</p>
                <p>{payGap.reason}</p>
                <p className="mt-1 text-xs">
                  Male salary records: {payGap.male_sample_size ?? 0} · Female: {payGap.female_sample_size ?? 0}
                  {' '}(minimum 5 each required)
                </p>
                <p className="mt-2 text-xs text-amber-600">
                  Add offered_salary_inr when creating candidates to enable this metric.
                </p>
              </div>
            ) : payGap ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {[
                    ['Median Male Salary',   fmtINR(payGap.median_male_inr)],
                    ['Median Female Salary', fmtINR(payGap.median_female_inr)],
                    ['Median Pay Gap',       pct(payGap.median_pay_gap_pct)],
                    ['Mean Pay Gap',         pct(payGap.mean_pay_gap_pct)],
                  ].map(([l, v]) => (
                    <div key={String(l)} className="bg-orange-50 rounded-xl p-4 text-center">
                      <p className="text-xs text-orange-600 font-semibold mb-1">{String(l)}</p>
                      <p className="text-lg font-bold text-orange-900">{String(v)}</p>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400">
                  Sample: {payGap.male_sample_size} male · {payGap.female_sample_size} female records ·
                  {' '}Direction: {payGap.direction?.replace(/_/g, ' ')}
                </p>
              </div>
            ) : null}
          </div>

          {/* SC/ST/OBC/EWS — only when statutory reporting enabled */}
          {settings?.statutory_reporting_required && (
            <div className="bg-white rounded-2xl border border-amber-100 shadow-sm p-5">
              <h3 className="font-bold text-gray-800 mb-2 flex items-center gap-2">
                <Shield className="w-4 h-4 text-amber-500" /> Statutory Category Reporting
              </h3>
              <p className="text-xs text-gray-500 mb-3">
                Enabled per: {settings.statutory_reporting_law ?? 'Factories Act 1948'}
              </p>
              <p className="text-sm text-gray-500">
                SC/ST/OBC/EWS data visible in the full dashboard endpoint — requires HR admin access.
              </p>
            </div>
          )}

          {/* Blind screening */}
          <BlindScreeningPanel />
        </div>
      )}
    </div>
  )
}
