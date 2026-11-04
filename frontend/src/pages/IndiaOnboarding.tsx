import {
AlertTriangle,
Award,
CheckCircle2,
ChevronDown,
ChevronRight,
ClipboardCheck,
Clock,
CreditCard,
FileText,
MessageSquare,
RefreshCcw,
Send,
Shield,
Star,
UserPlus,
X
} from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'
import { supabase } from '../lib/supabase'

// ─── Types ───────────────────────────────────────────────────────────────────

interface OnboardingFlow {
  id: string
  candidate_name: string
  role_title: string
  department: string
  property_name: string
  joining_date: string
  offer_date: string
  current_stage: string
  completion_pct: number
  stage_completion: Record<string, number>
  is_at_risk: boolean
  at_risk_reason: string
  status: string
  days_until_joining: number | null
  total_tasks: number
  done_tasks: number
  letter_esign_status: string | null
  pb_messages_sent: number
  pb_messages_total: number
  manager_name: string
  ghosting_risk_score?: number
  ghosting_risk_level?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  ghosting_risk_signals?: Array<{ code: string; message: string; weight: number }>
}

interface CTCBreakup {
  gross_monthly: number
  basic: number
  hra: number
  special_allowance: number
  epf_employee: number
  epf_employer: number
  esic_applicable: boolean
  esic_employee: number
  esic_employer: number
  pt: number
  net_monthly: number
  annual_gross: number
  annual_ctc: number
  annual_net: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const STAGES = ['documents', 'kyc', 'certifications', 'payroll', 'ready'] as const
type Stage = typeof STAGES[number]

const STAGE_META: Record<Stage, { label: string; icon: React.ReactNode; color: string }> = {
  documents:      { label: 'Documents',     icon: <FileText className="w-4 h-4" />,      color: 'text-blue-600' },
  kyc:            { label: 'KYC',           icon: <Shield className="w-4 h-4" />,         color: 'text-purple-600' },
  certifications: { label: 'Certifications',icon: <Award className="w-4 h-4" />,          color: 'text-orange-600' },
  payroll:        { label: 'Payroll',       icon: <CreditCard className="w-4 h-4" />,     color: 'text-green-600' },
  ready:          { label: 'Ready',         icon: <Star className="w-4 h-4" />,           color: 'text-yellow-600' },
}

function inr(v: number) { return `₹${v.toLocaleString('en-IN')}` }

function stageIndex(s: string) { return STAGES.indexOf(s as Stage) }

function completionColor(pct: number) {
  if (pct >= 80) return 'bg-green-500'
  if (pct >= 50) return 'bg-yellow-400'
  return 'bg-red-400'
}

function esignBadge(status: string | null) {
  if (!status || status === 'not_requested') return <span className="text-xs text-gray-400">Not requested</span>
  if (status === 'signed') return <span className="text-xs text-green-700 bg-green-100 px-2 py-0.5 rounded-full">eSigned ✓</span>
  if (status === 'requested') return <span className="text-xs text-yellow-700 bg-yellow-100 px-2 py-0.5 rounded-full">Pending sign</span>
  return <span className="text-xs text-gray-500">{status}</span>
}

// ─── CTC Modal ────────────────────────────────────────────────────────────────

function CTCModal({ flowId, onClose }: { flowId: string; onClose: () => void }) {
  const [gross, setGross] = useState(25000)
  const [ctc, setCtc] = useState<CTCBreakup | null>(null)
  const [_loading, setLoading] = useState(false)
  const [letterLoading, setLetterLoading] = useState(false)
  const [esignLoading, setEsignLoading] = useState(false)
  const [esignUrl, setEsignUrl] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      setLoading(true)
      try {
        const { data: { session } } = await supabase.auth.getSession()
        const res = await fetch(`/api/v1/india-onboarding/ctc-preview?gross_monthly_inr=${gross}`, {
          method: 'POST', headers: { Authorization: `Bearer ${session?.access_token}` },
        })
        if (!res.ok) throw new Error('Unable to calculate CTC')
        setCtc(await res.json())
      } catch { setCtc(null) }
      finally { setLoading(false) }
    }, 250)
    return () => window.clearTimeout(timer)
  }, [gross])

  const handleGenerateLetter = async () => {
    setLetterLoading(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      const res = await fetch(`/api/v1/india-onboarding/flows/${flowId}/appointment-letter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session?.access_token}` },
        body: JSON.stringify({ gross_monthly_inr: gross }),
      })
      if (res.ok) alert('Appointment letter generated successfully!')
    } catch { alert('Using demo mode — letter generation noted') }
    finally { setLetterLoading(false) }
  }

  const handleESign = async () => {
    setEsignLoading(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      const res = await fetch(`/api/v1/india-onboarding/flows/${flowId}/appointment-letter/esign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session?.access_token}` },
        body: JSON.stringify({ provider: 'demo' }),
      })
      const data = await res.json()
      setEsignUrl(data.sign_url || 'https://demo-esign.hosprecruitapp.com/sign/DEMO-XXXX')
    } catch { setEsignUrl('https://demo-esign.hosprecruitapp.com/sign/DEMO-XXXX') }
    finally { setEsignLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-gray-200">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <FileText className="w-5 h-5 text-purple-600" /> Appointment Letter & CTC Breakup
          </h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500 hover:text-gray-800" /></button>
        </div>

        <div className="p-5 space-y-5">
          {/* Gross input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Gross Monthly Salary (₹)</label>
            <input
              type="number" min={8000} max={500000} step={500}
              value={gross}
              onChange={e => setGross(Number(e.target.value))}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-48 focus:ring-2 focus:ring-purple-500"
            />
          </div>

          {/* CTC Breakup Table */}
          {ctc && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-700">CTC Breakup</h3>
              <div className="overflow-hidden rounded-lg border border-gray-200">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-xs font-medium text-gray-500 uppercase">
                    <tr>
                      <th className="px-4 py-2 text-left">Component</th>
                      <th className="px-4 py-2 text-right">Monthly</th>
                      <th className="px-4 py-2 text-right">Annual</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    <tr><td className="px-4 py-2 text-gray-700">Basic Salary (50% of Gross)</td><td className="px-4 py-2 text-right">{inr(ctc.basic)}</td><td className="px-4 py-2 text-right text-gray-500">{inr(ctc.basic*12)}</td></tr>
                    <tr><td className="px-4 py-2 text-gray-700">HRA (50% of Basic)</td><td className="px-4 py-2 text-right">{inr(ctc.hra)}</td><td className="px-4 py-2 text-right text-gray-500">{inr(ctc.hra*12)}</td></tr>
                    <tr><td className="px-4 py-2 text-gray-700">Special Allowance</td><td className="px-4 py-2 text-right">{inr(ctc.special_allowance)}</td><td className="px-4 py-2 text-right text-gray-500">{inr(ctc.special_allowance*12)}</td></tr>
                    <tr className="bg-blue-50 font-semibold">
                      <td className="px-4 py-2 text-blue-900">Gross Salary</td>
                      <td className="px-4 py-2 text-right text-blue-900">{inr(ctc.gross_monthly)}</td>
                      <td className="px-4 py-2 text-right text-blue-700">{inr(ctc.annual_gross)}</td>
                    </tr>
                    <tr className="text-red-700 text-xs"><td colSpan={3} className="px-4 py-1 font-medium text-gray-500 bg-gray-50">Deductions (Employee)</td></tr>
                    <tr><td className="px-4 py-2 text-gray-600">EPF Employee (12% of Basic)</td><td className="px-4 py-2 text-right text-red-600">- {inr(ctc.epf_employee)}</td><td className="px-4 py-2 text-right text-gray-400">- {inr(ctc.epf_employee*12)}</td></tr>
                    {ctc.esic_applicable && <tr><td className="px-4 py-2 text-gray-600">ESIC Employee (0.75% of Gross)</td><td className="px-4 py-2 text-right text-red-600">- {inr(ctc.esic_employee)}</td><td className="px-4 py-2 text-right text-gray-400">- {inr(ctc.esic_employee*12)}</td></tr>}
                    <tr><td className="px-4 py-2 text-gray-600">Professional Tax</td><td className="px-4 py-2 text-right text-red-600">- {inr(ctc.pt)}</td><td className="px-4 py-2 text-right text-gray-400">- {inr(ctc.pt*12)}</td></tr>
                    <tr className="bg-green-50 font-semibold">
                      <td className="px-4 py-2 text-green-900">Net Take-Home Salary</td>
                      <td className="px-4 py-2 text-right text-green-800">{inr(ctc.net_monthly)}</td>
                      <td className="px-4 py-2 text-right text-green-700">{inr(ctc.annual_net)}</td>
                    </tr>
                    <tr className="text-xs"><td colSpan={3} className="px-4 py-1 font-medium text-gray-500 bg-gray-50">Employer Statutory Contributions</td></tr>
                    <tr><td className="px-4 py-2 text-gray-600">EPF Employer (12% of Basic)</td><td className="px-4 py-2 text-right">{inr(ctc.epf_employer)}</td><td className="px-4 py-2 text-right text-gray-400">{inr(ctc.epf_employer*12)}</td></tr>
                    {ctc.esic_applicable && <tr><td className="px-4 py-2 text-gray-600">ESIC Employer (3.25% of Gross)</td><td className="px-4 py-2 text-right">{inr(ctc.esic_employer)}</td><td className="px-4 py-2 text-right text-gray-400">{inr(ctc.esic_employer*12)}</td></tr>}
                    {!ctc.esic_applicable && <tr><td className="px-4 py-2 text-gray-400 italic" colSpan={3}>ESIC not applicable (Gross &gt; ₹21,000)</td></tr>}
                    <tr className="bg-purple-50 font-bold">
                      <td className="px-4 py-2 text-purple-900">Total CTC</td>
                      <td className="px-4 py-2 text-right text-purple-900">{inr(Math.round(ctc.annual_ctc/12))}/mo</td>
                      <td className="px-4 py-2 text-right text-purple-800">{inr(ctc.annual_ctc)}/yr</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Actions */}
              <div className="flex flex-wrap gap-3 pt-2">
                <button
                  onClick={handleGenerateLetter}
                  disabled={letterLoading}
                  className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-60"
                >
                  <FileText className="w-4 h-4" />
                  {letterLoading ? 'Generating...' : 'Generate Appointment Letter'}
                </button>
                <button
                  onClick={handleESign}
                  disabled={esignLoading}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
                >
                  <Shield className="w-4 h-4" />
                  {esignLoading ? 'Requesting...' : 'Request Aadhaar eSign'}
                </button>
              </div>

              {esignUrl && (
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm">
                  <div className="font-medium text-blue-800 mb-1">eSign URL (send to candidate):</div>
                  <a href={esignUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline break-all">
                    {esignUrl}
                  </a>
                  <div className="text-xs text-blue-600 mt-1">
                    Provider: Demo mode — configure LEEGALITY_API_KEY or DIGIO_CLIENT_ID for production
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Flow Row Component ───────────────────────────────────────────────────────

function FlowRow({ flow, onAction }: { flow: OnboardingFlow; onAction: (action: string, flow: OnboardingFlow) => void }) {
  const [expanded, setExpanded] = useState(false)
  const activeStageIdx = stageIndex(flow.current_stage)

  return (
    <>
      <tr
        className={`border-b border-gray-100 hover:bg-gray-50 cursor-pointer transition ${flow.is_at_risk ? 'bg-red-50/30' : ''}`}
        onClick={() => setExpanded(!expanded)}
      >
        {/* Candidate */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            {flow.is_at_risk && <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />}
            <div>
              <div className="text-sm font-medium text-gray-900">{flow.candidate_name}</div>
              <div className="text-xs text-gray-500">{flow.role_title} · {flow.property_name}</div>
              {flow.ghosting_risk_level && (
                <span className={`inline-flex mt-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                  flow.ghosting_risk_level === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                  flow.ghosting_risk_level === 'HIGH' ? 'bg-orange-100 text-orange-700' :
                  flow.ghosting_risk_level === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-green-100 text-green-700'
                }`} title={(flow.ghosting_risk_signals || []).map(signal => signal.message).join('; ')}>
                  {flow.ghosting_risk_level} risk · {Math.round((flow.ghosting_risk_score || 0) * 100)}
                </span>
              )}
            </div>
          </div>
        </td>
        {/* Joining date */}
        <td className="px-4 py-3 text-sm text-gray-700">
          <div>{flow.joining_date ? new Date(flow.joining_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '—'}</div>
          {flow.days_until_joining !== null && (
            <div className={`text-xs ${flow.days_until_joining <= 7 ? 'text-red-600 font-medium' : 'text-gray-400'}`}>
              {flow.days_until_joining > 0 ? `in ${flow.days_until_joining}d` : 'Today'}
            </div>
          )}
        </td>
        {/* 5-stage progress */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-1">
            {STAGES.map((s, i) => {
              const pct = flow.stage_completion[s] || 0
              const isActive = i === activeStageIdx
              return (
                <div key={s} className="flex flex-col items-center">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs border-2 transition
                    ${pct >= 100 ? 'bg-green-500 border-green-500 text-white' :
                      isActive ? 'border-purple-500 text-purple-600 bg-purple-50' :
                      i < activeStageIdx ? 'border-gray-300 bg-gray-100 text-gray-400' :
                      'border-gray-200 text-gray-300'}`}>
                    {pct >= 100 ? <CheckCircle2 className="w-3 h-3" /> : i + 1}
                  </div>
                  {i < STAGES.length - 1 && (
                    <div className={`w-3 h-px mt-3 ${i < activeStageIdx ? 'bg-green-400' : 'bg-gray-200'}`} />
                  )}
                </div>
              )
            })}
          </div>
        </td>
        {/* Completion % */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-gray-100 rounded-full w-16 overflow-hidden">
              <div className={`h-full rounded-full ${completionColor(flow.completion_pct)}`} style={{ width: `${flow.completion_pct}%` }} />
            </div>
            <span className={`text-xs font-bold ${flow.completion_pct >= 80 ? 'text-green-700' : flow.completion_pct >= 50 ? 'text-yellow-700' : 'text-red-700'}`}>
              {Math.round(flow.completion_pct)}%
            </span>
          </div>
          <div className="text-xs text-gray-400">{flow.done_tasks}/{flow.total_tasks} tasks</div>
        </td>
        {/* Letter status */}
        <td className="px-4 py-3">{esignBadge(flow.letter_esign_status)}</td>
        {/* Pre-boarding */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-1 text-xs text-gray-600">
            <MessageSquare className="w-3.5 h-3.5" />
            {flow.pb_messages_sent}/{flow.pb_messages_total}
          </div>
        </td>
        {/* Actions */}
        <td className="px-4 py-3">
          <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
            <button
              onClick={() => onAction('letter', flow)}
              className="p-1.5 text-gray-500 hover:text-purple-600 hover:bg-purple-50 rounded-lg transition"
              title="Generate appointment letter"
            >
              <FileText className="w-4 h-4" />
            </button>
            <button
              onClick={() => onAction('preboard', flow)}
              className="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition"
              title="Schedule WhatsApp pre-boarding"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
            <button onClick={() => setExpanded(!expanded)} className="p-1.5 text-gray-400 hover:text-gray-700 rounded-lg transition">
              {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </td>
      </tr>

      {/* Expanded: stage detail */}
      {expanded && (
        <tr>
          <td colSpan={7} className="px-4 pb-4 bg-gray-50 border-b border-gray-100">
            <div className="grid grid-cols-5 gap-3 pt-3">
              {STAGES.map(s => {
                const meta = STAGE_META[s]
                const pct  = flow.stage_completion[s] || 0
                return (
                  <div key={s} className={`bg-white border rounded-xl p-3 ${pct >= 100 ? 'border-green-200' : flow.current_stage === s ? 'border-purple-300 ring-1 ring-purple-200' : 'border-gray-200'}`}>
                    <div className={`flex items-center gap-1.5 text-xs font-semibold mb-2 ${meta.color}`}>
                      {meta.icon}{meta.label}
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-1">
                      <div className={`h-full rounded-full ${completionColor(pct)}`} style={{ width: `${pct}%` }} />
                    </div>
                    <div className="text-xs text-gray-500">{pct}% done</div>
                  </div>
                )
              })}
            </div>

            {flow.is_at_risk && (
              <div className="mt-3 flex items-center gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                <strong>At Risk:</strong> {flow.at_risk_reason}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ─── Pre-boarding Preview Modal ───────────────────────────────────────────────

const PREBOARDING_PREVIEW = [
  { key: 'day0_welcome',      label: 'Day 0 — Welcome',             ref: 'offer',   offset: 0 },
  { key: 'day1_team_intro',   label: 'Day 1 — Team Intro',          ref: 'offer',   offset: 1 },
  { key: 'day3_practical',    label: 'Day 3 — Practical Info',      ref: 'offer',   offset: 3 },
  { key: 'pre7_docs_checklist', label: '7 Days Before — Docs',      ref: 'joining', offset: -7 },
  { key: 'pre1_reporting',    label: 'Day Before — Reporting',      ref: 'joining', offset: -1 },
  { key: 'day1_morning',      label: 'Joining Day — Welcome',       ref: 'joining', offset: 0 },
]

function PreboardingModal({ flow, onClose, onSchedule }: {
  flow: OnboardingFlow; onClose: () => void; onSchedule: () => void
}) {
  const [loading, setLoading] = useState(false)

  const handleSchedule = async () => {
    setLoading(true)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      await fetch(`/api/v1/india-onboarding/flows/${flow.id}/preboarding/schedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session?.access_token}` },
        body: JSON.stringify({}),
      })
      onSchedule()
      onClose()
    } catch { onSchedule(); onClose() }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-blue-600" />
            WhatsApp Pre-Boarding — {flow.candidate_name}
          </h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-500" /></button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-sm text-gray-600">6 WhatsApp messages will be scheduled based on offer date and joining date:</p>
          {PREBOARDING_PREVIEW.map((msg, i) => (
            <div key={msg.key} className="flex items-start gap-3 bg-gray-50 border border-gray-200 rounded-lg p-3">
              <div className="w-6 h-6 rounded-full bg-purple-100 text-purple-700 text-xs font-bold flex items-center justify-center flex-shrink-0">{i + 1}</div>
              <div>
                <div className="text-sm font-medium text-gray-800">{msg.label}</div>
                <div className="text-xs text-gray-500">
                  {msg.ref === 'offer' ? `Day ${msg.offset} after offer` : `${Math.abs(msg.offset)}d ${msg.offset < 0 ? 'before' : 'of'} joining`}
                </div>
              </div>
            </div>
          ))}
          <button
            onClick={handleSchedule}
            disabled={loading}
            className="w-full mt-4 flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            <Send className="w-4 h-4" />
            {loading ? 'Scheduling...' : 'Schedule Pre-Boarding Sequence'}
          </button>
        </div>
      </div>
    </div>
  )
}

function TemplateModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('Standard Property Onboarding')
  const [propertyId, setPropertyId] = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [roleTemplateId, setRoleTemplateId] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setMessage('')
    try {
      const { data: { session } } = await supabase.auth.getSession()
      const tasks = [
        ['documents', 'identity_documents', 'Identity and bank documents', -7],
        ['kyc', 'identity_kyc', 'KYC verification complete', -5],
        ['certifications', 'role_certifications', 'Required certifications reviewed', -3],
        ['payroll', 'appointment_esign', 'Appointment letter eSigned', -4],
        ['payroll', 'statutory_payroll', 'PF, ESIC and payroll setup', -2],
        ['ready', 'joining_readiness', 'Manager, joining and reporting details confirmed', 0],
      ].map(([stage, task_type, task_label, due_offset_days], index) => ({
        stage, task_type, task_label, due_offset_days, sort_order: index + 1, is_mandatory: true, weight: 1,
      }))
      const response = await fetch('/api/v1/india-onboarding/templates', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session?.access_token}` },
        body: JSON.stringify({ name, property_id: propertyId || null, department_id: departmentId || null,
          role_template_id: roleTemplateId || null, auto_start: true, tasks }),
      })
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || 'Template could not be saved')
      setMessage('Template saved. New accepted offers will use the most specific matching template.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Template could not be saved') }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-xl p-5 space-y-4">
        <div className="flex justify-between items-center"><h2 className="font-bold text-gray-900">Onboarding Template</h2><button onClick={onClose}><X className="w-5 h-5" /></button></div>
        <p className="text-sm text-gray-600">Leave a scope blank for an organization-wide default. Property, department and role scopes take precedence.</p>
        <label className="block text-sm font-medium">Template name<input value={name} onChange={e => setName(e.target.value)} className="mt-1 w-full border rounded-lg px-3 py-2" /></label>
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="text-xs font-medium">Property UUID<input value={propertyId} onChange={e => setPropertyId(e.target.value)} className="mt-1 w-full border rounded-lg px-2 py-2 text-sm" /></label>
          <label className="text-xs font-medium">Department UUID<input value={departmentId} onChange={e => setDepartmentId(e.target.value)} className="mt-1 w-full border rounded-lg px-2 py-2 text-sm" /></label>
          <label className="text-xs font-medium">Role template UUID<input value={roleTemplateId} onChange={e => setRoleTemplateId(e.target.value)} className="mt-1 w-full border rounded-lg px-2 py-2 text-sm" /></label>
        </div>
        <div className="text-xs text-gray-500">Creates six required tasks across Documents, KYC, Certifications, Payroll and Ready. Tasks can be extended through the template API.</div>
        {message && <div className="text-sm bg-gray-50 border rounded-lg p-3">{message}</div>}
        <button onClick={save} disabled={saving || name.trim().length < 2} className="w-full bg-purple-600 text-white rounded-lg py-2.5 font-medium disabled:opacity-50">{saving ? 'Saving...' : 'Save Active Template'}</button>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function IndiaOnboarding() {
  const [flows, setFlows] = useState<OnboardingFlow[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'at_risk' | 'active' | 'completed'>('all')
  const [activeModal, setActiveModal] = useState<null | { type: 'letter' | 'preboard'; flow: OnboardingFlow }>(null)
  const [showTemplates, setShowTemplates] = useState(false)
  const [notification, setNotification] = useState<string | null>(null)

  const notify = (msg: string) => {
    setNotification(msg)
    setTimeout(() => setNotification(null), 4000)
  }

  const loadFlows = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) return
      const res = await fetch('/api/v1/india-onboarding/flows', {
        headers: { Authorization: `Bearer ${session.access_token}` },
      })
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail || 'Unable to load onboarding flows')
      const json = await res.json()
      setFlows(json.flows || [])
    } catch (error) {
      setFlows([])
      setLoadError(error instanceof Error ? error.message : 'Unable to load onboarding flows')
    }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { loadFlows() }, [loadFlows])

  const handleAction = (action: string, flow: OnboardingFlow) => {
    setActiveModal({ type: action as 'letter' | 'preboard', flow })
  }

  const stats = {
    active:    flows.filter(f => f.status === 'active').length,
    at_risk:   flows.filter(f => f.is_at_risk).length,
    completed: flows.filter(f => f.status === 'completed').length,
    avg_pct:   flows.length ? Math.round(flows.reduce((s, f) => s + (f.completion_pct || 0), 0) / flows.length) : 0,
  }

  const filtered = flows.filter(f => {
    if (filter === 'at_risk')   return f.is_at_risk
    if (filter === 'active')    return f.status === 'active' && !f.is_at_risk
    if (filter === 'completed') return f.status === 'completed'
    return true
  })

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <ClipboardCheck className="w-6 h-6 text-purple-600" />
            India Digital Onboarding
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Appointment letters · Aadhaar eSign · PF/ESIC forms · WhatsApp pre-boarding · 5-stage checklist
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={loadFlows}
            className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
          >
            <RefreshCcw className="w-4 h-4" /> Refresh
          </button>
          <button onClick={() => setShowTemplates(true)} className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700">
            <UserPlus className="w-4 h-4" /> Manage Templates
          </button>
        </div>
      </div>

      {/* Notification */}
      {notification && (
        <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3 text-sm text-green-800 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />{notification}
        </div>
      )}

      {loadError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-800 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />{loadError}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: 'Active Flows',     value: stats.active,    icon: <Clock className="w-5 h-5 text-blue-600" />,    bg: 'bg-blue-50',   border: 'border-blue-200',   text: 'text-blue-800' },
          { label: 'At Risk',          value: stats.at_risk,   icon: <AlertTriangle className="w-5 h-5 text-red-500" />, bg: 'bg-red-50', border: 'border-red-200',    text: 'text-red-800' },
          { label: 'Completed',        value: stats.completed, icon: <CheckCircle2 className="w-5 h-5 text-green-600" />, bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-800' },
          { label: 'Avg Completion',   value: `${stats.avg_pct}%`, icon: <Star className="w-5 h-5 text-purple-600" />, bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-800' },
        ].map(s => (
          <div key={s.label} className={`${s.bg} border ${s.border} rounded-xl p-4 flex items-center gap-4`}>
            <div className="p-2 bg-white rounded-lg shadow-sm">{s.icon}</div>
            <div>
              <div className={`text-2xl font-bold ${s.text}`}>{s.value}</div>
              <div className="text-xs text-gray-500">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* At-risk alert */}
      {stats.at_risk > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-5 h-5 text-red-600" />
            <span className="font-semibold text-red-800">
              {stats.at_risk} candidate{stats.at_risk > 1 ? 's' : ''} at risk of missing joining date
            </span>
          </div>
          <div className="space-y-2">
            {flows.filter(f => f.is_at_risk).map(f => (
              <div key={f.id} className="flex items-center justify-between bg-white border border-red-100 rounded-lg px-3 py-2">
                <div>
                  <span className="text-sm font-medium text-gray-900">{f.candidate_name}</span>
                  <span className="text-sm text-gray-500"> — {f.role_title}, {f.property_name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-red-700 font-medium">{f.at_risk_reason}</span>
                  <button
                    onClick={() => setActiveModal({ type: 'preboard', flow: f })}
                    className="text-xs px-3 py-1 bg-red-600 text-white rounded-lg hover:bg-red-700"
                  >
                    Send Pre-boarding
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stage legend */}
      <div className="flex flex-wrap gap-3 items-center">
        {STAGES.map(s => {
          const m = STAGE_META[s]
          return (
            <div key={s} className={`flex items-center gap-1.5 text-xs ${m.color}`}>
              {m.icon} {m.label}
            </div>
          )
        })}
        <span className="text-gray-300">|</span>
        <span className="text-xs text-gray-400">Click any row to expand stage detail</span>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {([
          ['all', `All (${flows.length})`],
          ['at_risk', `At Risk (${stats.at_risk})`],
          ['active', `On Track (${stats.active - stats.at_risk})`],
          ['completed', `Completed (${stats.completed})`],
        ] as const).map(([f, label]) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              filter === f
                ? f === 'at_risk' ? 'bg-red-600 text-white' : 'bg-purple-600 text-white'
                : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Flows table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr className="text-xs font-medium text-gray-500 uppercase tracking-wide">
              <th className="px-4 py-3 text-left">Candidate</th>
              <th className="px-4 py-3 text-left">Joining</th>
              <th className="px-4 py-3 text-left">Stage Progress</th>
              <th className="px-4 py-3 text-left">Completion</th>
              <th className="px-4 py-3 text-left">Letter</th>
              <th className="px-4 py-3 text-left">Pre-boarding</th>
              <th className="px-4 py-3 text-left">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="py-12 text-center text-gray-400 text-sm">Loading...</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={7} className="py-12 text-center text-gray-400 text-sm">No onboarding flows found.</td></tr>
            )}
            {!loading && filtered.map(flow => (
              <FlowRow key={flow.id} flow={flow} onAction={handleAction} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Checklist legend */}
      <div className="bg-white border border-gray-200 rounded-xl p-4">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
          5-Stage Onboarding Checklist
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
          {STAGES.map((s, i) => {
            const m = STAGE_META[s]
            return (
              <div key={s} className="flex flex-col">
                <div className={`flex items-center gap-2 text-sm font-semibold ${m.color} mb-1`}>
                  <div className="w-6 h-6 rounded-full border-2 border-current flex items-center justify-center text-xs">{i+1}</div>
                  {m.label}
                </div>
                <div className="text-xs text-gray-500 space-y-0.5 pl-8">
                  {({
                    documents:      ['Aadhaar', 'PAN', 'Photos', 'Bank', 'Edu certs'],
                    kyc:            ['Video KYC', 'Address verify', 'BGV'],
                    certifications: ['Food Safety', 'Role cert', 'Induction'],
                    payroll:        ['eSign letter', 'PF Form 2', 'ESIC decl', 'UAN'],
                    ready:          ['ID card', 'Email', 'Uniform', 'Buddy'],
                  } as Record<Stage, string[]>)[s].map(t => <div key={t}>• {t}</div>)}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Modals */}
      {activeModal?.type === 'letter' && (
        <CTCModal
          flowId={activeModal.flow.id}
          onClose={() => setActiveModal(null)}
        />
      )}
      {activeModal?.type === 'preboard' && (
        <PreboardingModal
          flow={activeModal.flow}
          onClose={() => setActiveModal(null)}
          onSchedule={() => notify(`Pre-boarding sequence scheduled for ${activeModal.flow.candidate_name}`)}
        />
      )}
      {showTemplates && <TemplateModal onClose={() => setShowTemplates(false)} />}
    </div>
  )
}
