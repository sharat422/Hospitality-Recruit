import { Activity,AlertTriangle,Briefcase,Clock,IndianRupee,TrendingDown,Users } from 'lucide-react'
import { useEffect,useState } from 'react'
import { Bar,BarChart,CartesianGrid,ResponsiveContainer,Tooltip,XAxis,YAxis } from 'recharts'
import { apiClient } from '../lib/api'
import { useProperty } from '../lib/PropertyContext'

type Summary = {
  headcount: number; vacancies: number; open_jobs: number; absence_days: number; absence_rate_pct: number | null
  overtime_hours: number; turnover_count: number; attrition_rate_pct: number | null
  engagement_score: number | null; engagement_sample: number; high_turnover_risk: number
  turnover_risk_assessed: number; productivity_score: number | null; productivity_sample: number
  payroll: null | { gross_inr: number; net_inr: number; employer_cost_inr: number; lop_inr: number; overtime_inr: number; employees_paid: number }
}
type Response = { summary: Summary; property_comparison?: any[]; department_comparison?: any[]; roles: string[]; employees: any[]; financial_visible: boolean; data_source: string; methodology: Record<string, string> }
const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

export default function WorkforceAnalytics() {
  const { properties } = useProperty()
  const [data, setData] = useState<Response | null>(null)
  const [filters, setFilters] = useState({ property_id: '', department_id: '', role: '', employee_id: '', date_from: '', date_to: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const change = (key: string, value: string) => setFilters(old => ({ ...old, [key]: value,
    ...(key === 'property_id' ? { department_id: '', role: '', employee_id: '' } : {}),
    ...(key === 'department_id' ? { role: '', employee_id: '' } : {}),
    ...(key === 'role' ? { employee_id: '' } : {}),
  }))

  useEffect(() => {
    const timer = setTimeout(async () => {
      setLoading(true); setError('')
      try {
        const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value))
        const response = await apiClient.get('/analytics/workforce', { params })
        setData(response.data)
      } catch (err: any) { setError(err.response?.data?.detail ?? 'Unable to load workforce analytics.') }
      finally { setLoading(false) }
    }, 150)
    return () => clearTimeout(timer)
  }, [filters])

  const summary = data?.summary
  const cards = summary ? [
    ['Headcount', summary.headcount, Users], ['Vacancies', summary.vacancies, Briefcase],
    ['Absence rate', summary.absence_rate_pct == null ? '—' : `${summary.absence_rate_pct}%`, TrendingDown],
    ['Overtime', `${summary.overtime_hours}h`, Clock],
    ['Attrition', summary.attrition_rate_pct == null ? '—' : `${summary.attrition_rate_pct}%`, Activity],
    ['Engagement', summary.engagement_score == null ? '—' : `${summary.engagement_score}/100`, Activity],
    ['High turnover risk', summary.high_turnover_risk, AlertTriangle],
    ['Productivity', summary.productivity_score == null ? '—' : `${summary.productivity_score}/100`, Activity],
  ] as const : []

  return <div className="min-h-screen bg-slate-50 p-4 md:p-6"><div className="mx-auto max-w-7xl space-y-5">
    <header className="flex items-end justify-between gap-3"><div><h1 className="text-2xl font-semibold text-slate-900">Workforce Analytics</h1><p className="mt-1 text-sm text-slate-500">Group to employee workforce health from validated HR records</p></div><span className="border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">{data?.data_source === 'LIVE_DATABASE' ? 'Live database' : 'Loading'}</span></header>
    <section className="grid gap-3 border-y border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
      <Select label="Property" value={filters.property_id} onChange={v => change('property_id', v)} items={properties.map(x => [x.id, x.name])}/>
      <Select label="Department" value={filters.department_id} onChange={v => change('department_id', v)} items={(data?.department_comparison ?? []).map(x => [x.id, x.name])}/>
      <Select label="Role" value={filters.role} onChange={v => change('role', v)} items={(data?.roles ?? []).map(x => [x, x])}/>
      <Select label="Employee" value={filters.employee_id} onChange={v => change('employee_id', v)} items={(data?.employees ?? []).map(x => [x.id, `${x.name || x.employee_code || x.id}`])}/>
      <DateInput label="From" value={filters.date_from} onChange={v => change('date_from', v)}/><DateInput label="To" value={filters.date_to} onChange={v => change('date_to', v)}/>
    </section>
    {error && <div className="border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
    {loading && !data ? <div className="p-16 text-center text-slate-500">Loading workforce records…</div> : summary && <>
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{cards.map(([name, value, Icon]) => <div key={name} className="rounded border border-slate-200 bg-white p-4"><Icon className="h-5 w-5 text-emerald-600"/><p className="mt-4 text-xs text-slate-500">{name}</p><p className="mt-1 text-xl font-semibold text-slate-900">{value}</p></div>)}</section>
      <section className="grid gap-4 lg:grid-cols-2">
        <Comparison title="Property comparison" data={data?.property_comparison ?? []}/>
        <Comparison title="Department comparison" data={data?.department_comparison ?? []}/>
      </section>
      {summary.payroll ? <section className="rounded border border-slate-200 bg-white p-4"><h2 className="flex items-center gap-2 font-semibold"><IndianRupee className="h-4 w-4 text-emerald-600"/>Finalized payroll</h2><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">{[['Gross',summary.payroll.gross_inr],['Net',summary.payroll.net_inr],['Employer cost',summary.payroll.employer_cost_inr],['LOP',summary.payroll.lop_inr],['Overtime pay',summary.payroll.overtime_inr]].map(([name,value]) => <div key={String(name)}><p className="text-xs text-slate-500">{name}</p><p className="mt-1 font-semibold">{inr.format(Number(value))}</p></div>)}</div></section> : <div className="border border-slate-200 bg-white p-4 text-sm text-slate-500">Payroll metrics are hidden because your role does not have financial reporting permission.</div>}
      <section className="rounded border border-slate-200 bg-white p-4"><h2 className="font-semibold">Metric integrity</h2><div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-2">{Object.entries(data?.methodology ?? {}).map(([key,value]) => <p key={key}><strong className="capitalize text-slate-800">{key.replaceAll('_',' ')}:</strong> {value}</p>)}</div></section>
    </>}
  </div></div>
}

function Select({label,value,onChange,items}:{label:string;value:string;onChange:(v:string)=>void;items:string[][]}) { return <label className="text-xs font-medium text-slate-600">{label}<select className="mt-1 h-10 w-full rounded border border-slate-300 bg-white px-2 text-sm" value={value} onChange={e=>onChange(e.target.value)}><option value="">All</option>{items.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label> }
function DateInput({label,value,onChange}:{label:string;value:string;onChange:(v:string)=>void}) { return <label className="text-xs font-medium text-slate-600">{label}<input className="mt-1 h-10 w-full rounded border border-slate-300 px-2 text-sm" type="date" value={value} onChange={e=>onChange(e.target.value)}/></label> }
function Comparison({title,data}:{title:string;data:any[]}) { return <div className="rounded border border-slate-200 bg-white p-4"><h2 className="font-semibold">{title}</h2>{data.length ? <div className="mt-3 h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={data}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="name" fontSize={11}/><YAxis allowDecimals={false}/><Tooltip/><Bar dataKey="headcount" name="Headcount" fill="#059669"/><Bar dataKey="vacancies" name="Vacancies" fill="#f59e0b"/></BarChart></ResponsiveContainer></div> : <p className="py-16 text-center text-sm text-slate-500">Select a broader level to compare.</p>}</div> }
