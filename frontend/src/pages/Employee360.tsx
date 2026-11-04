import {
AlertTriangle,
Award,
Briefcase,
CalendarOff,
ChevronRight,
Clock3,
Files,
GraduationCap,
History,
IndianRupee,
Loader2,
Mail,Phone,
RefreshCw,
Route,
ShieldCheck,
TrendingUp,
User
} from 'lucide-react'
import React,{ useEffect,useMemo,useState } from 'react'
import { useParams } from 'react-router-dom'
import apiClient from '../lib/api'
import LanguagePicker from '../components/LanguagePicker'

type SectionKey = 'personal' | 'employment' | 'financial' | 'statutory' | 'documents' |
  'certifications' | 'performance' | 'attendance' | 'leave' | 'payroll' | 'training' |
  'career' | 'disciplinary' | 'timeline'

interface Employee360Data {
  employee_id: string
  candidate_id?: string
  self_view: boolean
  visible_sections: SectionKey[]
  sections: Record<string, any>
  generated_at: string
}

const TABS: Array<{ key: SectionKey; label: string; icon: React.ReactNode }> = [
  { key: 'personal', label: 'Personal', icon: <User className="w-4 h-4" /> },
  { key: 'employment', label: 'Employment', icon: <Briefcase className="w-4 h-4" /> },
  { key: 'financial', label: 'Financial', icon: <IndianRupee className="w-4 h-4" /> },
  { key: 'statutory', label: 'Statutory', icon: <ShieldCheck className="w-4 h-4" /> },
  { key: 'documents', label: 'Documents', icon: <Files className="w-4 h-4" /> },
  { key: 'certifications', label: 'Certifications', icon: <Award className="w-4 h-4" /> },
  { key: 'performance', label: 'Performance', icon: <TrendingUp className="w-4 h-4" /> },
  { key: 'attendance', label: 'Attendance', icon: <Clock3 className="w-4 h-4" /> },
  { key: 'leave', label: 'Leave', icon: <CalendarOff className="w-4 h-4" /> },
  { key: 'payroll', label: 'Payroll', icon: <IndianRupee className="w-4 h-4" /> },
  { key: 'training', label: 'Training', icon: <GraduationCap className="w-4 h-4" /> },
  { key: 'career', label: 'Career', icon: <Route className="w-4 h-4" /> },
  { key: 'disciplinary', label: 'HR Events', icon: <AlertTriangle className="w-4 h-4" /> },
  { key: 'timeline', label: 'Lifecycle', icon: <History className="w-4 h-4" /> },
]

const fmtDate = (value?: string) => value ? new Date(value).toLocaleDateString('en-IN', {
  day: '2-digit', month: 'short', year: 'numeric',
}) : 'Not set'
const fmtMoney = (value?: number) => value == null ? 'Not set' : new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 0,
}).format(value)
const title = (value?: string) => value ? value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase()) : 'Not set'

function Empty({ label }: { label: string }) {
  return <div className="py-12 text-center text-sm text-gray-500">No {label.toLowerCase()} records yet.</div>
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return <div className="border-b border-gray-100 py-3 min-w-0">
    <div className="text-xs font-medium text-gray-500">{label}</div>
    <div className="text-sm text-gray-900 mt-1 break-words">{value || 'Not set'}</div>
  </div>
}

function Status({ value }: { value?: string }) {
  return <span className="inline-flex px-2 py-1 rounded-md text-xs font-semibold bg-gray-100 text-gray-700">{title(value)}</span>
}

function ListRows({ rows, render }: { rows: any[]; render: (row: any) => React.ReactNode }) {
  if (!rows?.length) return <Empty label="records" />
  return <div className="divide-y divide-gray-100">{rows.map((row, i) => <div key={row.id || i} className="py-4">{render(row)}</div>)}</div>
}

export default function Employee360() {
  const { employeeId } = useParams<{ employeeId?: string }>()
  const [data, setData] = useState<Employee360Data | null>(null)
  const [active, setActive] = useState<SectionKey>('personal')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const path = employeeId ? `/employees/${employeeId}/360` : '/employees/me/360'
      const response = await apiClient.get(path)
      setData(response.data)
      if (!response.data.visible_sections.includes(active)) setActive('personal')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Employee profile could not be loaded.')
    } finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [employeeId])
  const tabs = useMemo(() => TABS.filter(tab => data?.visible_sections.includes(tab.key)), [data])
  const s = data?.sections || {}

  if (loading) return <div className="min-h-[60vh] flex items-center justify-center"><Loader2 className="w-7 h-7 animate-spin text-purple-600" /></div>
  if (error || !data) return <div className="p-6"><div className="border border-red-200 bg-red-50 text-red-700 p-4 rounded-lg">{error}</div></div>

  const renderSection = () => {
    if (active === 'personal') return <div className="grid sm:grid-cols-2 gap-x-8">
      <Field label="Full name" value={s.personal?.full_name} /><Field label="Preferred language" value={title(s.personal?.preferred_language)} />
      <Field label="Email" value={s.personal?.email} /><Field label="Phone" value={s.personal?.phone} />
      <Field label="Location" value={s.personal?.location} /><Field label="Employee ID" value={data.employee_id} />
    </div>
    if (active === 'employment') return <div className="grid sm:grid-cols-2 gap-x-8">
      <Field label="Employee code" value={s.employment?.employee_code} /><Field label="Job title" value={s.employment?.job_title} />
      <Field label="Employment type" value={title(s.employment?.employment_type)} /><Field label="Status" value={<Status value={s.employment?.employment_status} />} />
      <Field label="Joining date" value={fmtDate(s.employment?.joining_date)} /><Field label="System role" value={title(s.employment?.role)} />
      <Field label="Property" value={s.employment?.property?.name} /><Field label="Department" value={s.employment?.department?.name} />
      <Field label="Manager" value={s.employment?.manager?.full_name} />
    </div>
    if (active === 'financial') return <div className="grid sm:grid-cols-2 gap-x-8">
      <Field label="Current CTC" value={fmtMoney(s.financial?.current_ctc_inr)} />
      <Field label="UPI ID" value={s.financial?.upi?.upi_id} /><Field label="UPI verification" value={<Status value={s.financial?.upi?.is_verified ? 'VERIFIED' : 'PENDING'} />} />
    </div>
    if (active === 'statutory') return <div>
      <div className="grid sm:grid-cols-2 gap-x-8">
        <Field label="EPF UAN" value={s.statutory?.epf_esic?.epf_uan_masked} /><Field label="EPF member ID" value={s.statutory?.epf_esic?.epf_member_id_masked} />
        <Field label="ESIC IP number" value={s.statutory?.epf_esic?.esic_ip_number_masked} /><Field label="Registration status" value={<Status value={s.statutory?.epf_esic?.status} />} />
      </div>
      <ListRows rows={s.statutory?.identity_verifications || []} render={row => <div className="flex items-center justify-between gap-3"><div><div className="font-medium text-sm">{title(row.doc_type)}</div><div className="text-xs text-gray-500 mt-1">{row.aadhaar_masked || row.pan_masked || 'Identifier protected'}</div></div><Status value={row.status} /></div>} />
    </div>
    if (active === 'documents') return <ListRows rows={s.documents || []} render={row => <div className="flex items-center justify-between gap-3"><div><div className="font-medium text-sm">{row.file_name}</div><div className="text-xs text-gray-500 mt-1">{title(row.document_type)} · {fmtDate(row.created_at)}</div></div><Status value={row.status} /></div>} />
    if (active === 'certifications') return <ListRows rows={s.certifications || []} render={row => <div className="flex items-center justify-between gap-3"><div><div className="font-medium text-sm">{row.certification_name || title(row.cert_type)}</div><div className="text-xs text-gray-500 mt-1">Expires {fmtDate(row.expiry_date)} · {row.source_type || 'CERTIFICATE'}</div></div><Status value={row.status} /></div>} />
    if (active === 'performance') return <ListRows rows={s.performance || []} render={row => <div><div className="flex justify-between"><div className="font-medium text-sm">{fmtDate(row.review_period_start)} – {fmtDate(row.review_period_end)}</div><span className="font-bold text-purple-700">{row.overall_score != null ? `${row.overall_score}/100` : row.rating ? `${row.rating}/5` : 'Not rated'}</span></div><p className="text-sm text-gray-600 mt-2">{row.strengths || row.manager_comments || 'Review in progress'}</p><div className="mt-2 flex gap-2 text-xs text-gray-500">{row.promotion_eligible&&<span>Promotion eligible</span>}{row.increment_eligible&&<span>Increment eligible</span>}<span>{row.status}</span></div></div>} />
    if (active === 'attendance') return <div><div className="text-sm font-semibold mb-2">Daily attendance</div><ListRows rows={s.attendance?.daily_records || []} render={row => <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-sm"><span>{fmtDate(row.attendance_date)}</span><Status value={row.status} /><span>{Math.floor((row.worked_minutes || 0) / 60)}h {(row.worked_minutes || 0) % 60}m</span><span>Late {row.late_minutes || 0}m</span><Status value={row.validation_status} /></div>} /><div className="text-sm font-semibold mt-6 mb-2">Corrections</div><ListRows rows={s.attendance?.corrections || []} render={row => <div className="flex justify-between gap-3 text-sm"><span>{row.reason}</span><Status value={row.status} /></div>} /><div className="text-sm font-semibold mt-6 mb-2">Working-hours compliance</div><ListRows rows={s.attendance?.working_hours || []} render={row => <div className="grid grid-cols-3 gap-2 text-sm"><span>{fmtDate(row.shift_date)}</span><span>{row.actual_hours || 0} hours</span><span className={row.violation_type ? 'text-red-600' : 'text-green-700'}>{row.violation_type ? title(row.violation_type) : 'Compliant'}</span></div>} /><div className="text-sm font-semibold mt-6 mb-2">Assigned shifts</div><ListRows rows={s.attendance?.shifts || []} render={row => <div className="flex justify-between text-sm"><span>{row.role || 'Shift'} · {fmtDate(row.start_date)}</span><Status value={row.assignment_status} /></div>} /></div>
    if (active === 'leave') return <div><div className="grid grid-cols-3 gap-3 mb-5">{['casual', 'sick', 'earned'].map(kind => <div key={kind} className="border border-gray-200 rounded-lg p-3"><div className="text-xs text-gray-500">{title(kind)}</div><div className="text-xl font-bold mt-1">{s.leave?.balances?.[0]?.[`${kind}_remaining`] ?? '—'}</div></div>)}</div><ListRows rows={s.leave?.requests || []} render={row => <div className="flex justify-between gap-3"><div><div className="font-medium text-sm">{title(row.leave_type)} · {fmtDate(row.leave_date)}</div><div className="text-xs text-gray-500 mt-1">{row.reason}</div></div><Status value={row.status} /></div>} /></div>
    if (active === 'payroll') return <ListRows rows={s.payroll || []} render={row => <div className="grid grid-cols-3 gap-3 items-center"><div><div className="font-medium text-sm">{row.month}/{row.year}</div><div className="text-xs text-gray-500">Payslip</div></div><div className="text-sm">Gross {fmtMoney(row.gross_salary_inr)}</div><div className="font-semibold text-right">Net {fmtMoney(row.net_salary_inr)}</div></div>} />
    if (active === 'training') return <ListRows rows={s.training || []} render={row => <div className="flex justify-between gap-3"><div><div className="font-medium text-sm">{row.training_name}</div><div className="text-xs text-gray-500 mt-1">{row.provider || title(row.category)} · Due {fmtDate(row.due_date)}</div></div><Status value={row.status} /></div>} />
    if (active === 'career') return <div><div className="mb-5"><div className="text-sm font-semibold">Skills</div><div className="text-sm text-gray-600 mt-2">{Array.isArray(s.career?.skills) ? s.career.skills.join(', ') : Object.keys(s.career?.skills || {}).join(', ') || 'No parsed skills'}</div></div><div className="text-sm font-semibold">Application history</div><ListRows rows={s.career?.applications || []} render={row => <div className="flex justify-between text-sm"><span>{row.job_id}</span><Status value={row.status} /></div>} /></div>
    if (active === 'disciplinary') return <ListRows rows={s.disciplinary || []} render={row => <div><div className="flex justify-between"><div className="font-medium text-sm">{row.title}</div><Status value={row.status} /></div><div className="text-xs text-gray-500 mt-1">{title(row.event_type)} · {fmtDate(row.event_date)} · {title(row.severity)}</div><p className="text-sm text-gray-600 mt-2">{row.description}</p></div>} />
    return <ListRows rows={s.timeline || []} render={row => <div className="flex gap-3"><div className="w-2 h-2 mt-2 rounded-full bg-purple-500 flex-none" /><div><div className="font-medium text-sm">{row.title}</div><div className="text-xs text-gray-500 mt-1">{title(row.event_type)} · {fmtDate(row.event_at)}</div>{row.description && <p className="text-sm text-gray-600 mt-1">{row.description}</p>}</div></div>} />
  }

  return <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
      <div className="flex items-center gap-4 min-w-0">
        <div className="w-14 h-14 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-lg flex-none">{(s.personal?.full_name || 'E').split(' ').map((x: string) => x[0]).slice(0, 2).join('')}</div>
        <div className="min-w-0"><h1 className="text-xl font-bold text-gray-900 truncate">{s.personal?.full_name || 'Employee'}</h1><p className="text-sm text-gray-500 mt-1 truncate">{s.employment?.job_title || 'Role not assigned'}{s.employment?.property?.name ? ` · ${s.employment.property.name}` : ''}</p><div className="flex gap-3 mt-2 text-xs text-gray-500"><span className="flex gap-1"><Mail className="w-3.5 h-3.5" />{s.personal?.email}</span>{s.personal?.phone && <span className="hidden md:flex gap-1"><Phone className="w-3.5 h-3.5" />{s.personal.phone}</span>}</div></div>
      </div>
      <button onClick={() => void load()} className="min-h-11 px-4 border border-gray-200 rounded-lg bg-white text-sm font-semibold flex items-center justify-center gap-2"><RefreshCw className="w-4 h-4" />Refresh</button>
    </div>
    <div className="border-y border-gray-200 bg-white overflow-x-auto"><div className="flex min-w-max">{tabs.map(tab => <button key={tab.key} onClick={() => setActive(tab.key)} className={`min-h-12 px-4 flex items-center gap-2 text-sm font-medium border-b-2 ${active === tab.key ? 'border-purple-600 text-purple-700' : 'border-transparent text-gray-600 hover:text-gray-900'}`}>{tab.icon}{tab.label}</button>)}</div></div>
    <div className="bg-white py-5 sm:px-2"><div className="flex items-center gap-2 mb-4"><span className="text-purple-600">{TABS.find(t => t.key === active)?.icon}</span><h2 className="font-semibold text-gray-900">{TABS.find(t => t.key === active)?.label}</h2><ChevronRight className="w-4 h-4 text-gray-300" /></div>{renderSection()}</div>
    {/* Language sits outside the tab set: the tabs come from the API's
        visible_sections and this is a per-person app setting, not employee data. */}
    <div className="bg-white border border-gray-200 rounded-lg p-5 mt-6 max-w-md">
      <LanguagePicker variant="profile" />
    </div>
  </div>
}
