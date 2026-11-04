import { BarChart3,Clock,IndianRupee,RefreshCw,Target,UserCheck,Users } from 'lucide-react'
import { useEffect,useMemo,useState } from 'react'
import { Bar,BarChart,CartesianGrid,ResponsiveContainer,Tooltip,XAxis,YAxis } from 'recharts'
import { apiClient } from '../lib/api'
import { useProperty } from '../lib/PropertyContext'

type Option = { id: string; title?: string; name?: string; full_name?: string; email?: string; property_id?: string }
type Metrics = {
  applications: number; hires: number; active_jobs: number; time_to_hire_days: number | null
  time_to_hire_sample: number; time_to_fill_days: number | null; time_to_fill_sample: number
  interview_conversion_pct: number; offer_acceptance_pct: number
  funnel: { stage: string; count: number; conversion_from_applied_pct: number }[]
  source_performance: { source: string; applications: number; hires: number; conversion_pct: number }[]
  ghosting: { high_or_critical: number; assessed: number; rate_pct: number }
  referrals: { applied: number; hired: number; conversion_pct: number }
  cost: { total_inr: number; cost_per_hire_inr: number | null; entries: number }
  quality_of_hire: { average_score: number | null; reviewed_hires: number; method: string }
  data_source: string
}

const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const label = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase())

export default function RecruitmentAnalytics() {
  const { properties, activeProperty } = useProperty()
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [options, setOptions] = useState<{ jobs: Option[]; departments: Option[]; recruiters: Option[]; sources: string[] }>({ jobs: [], departments: [], recruiters: [], sources: [] })
  const [filters, setFilters] = useState({ property_id: '', department_id: '', job_id: '', recruiter_id: '', source: '', date_from: '', date_to: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => { if (activeProperty?.id) setFilters(old => ({ ...old, property_id: activeProperty.id })) }, [activeProperty?.id])
  useEffect(() => { apiClient.get('/analytics/filters').then(r => setOptions(r.data)).catch(() => undefined) }, [])
  useEffect(() => {
    const timer = setTimeout(async () => {
      setLoading(true); setError('')
      try {
        const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value))
        const { data } = await apiClient.get('/analytics/recruitment', { params })
        setMetrics(data)
      } catch (err: any) {
        setError(err.response?.data?.detail ?? 'Unable to load recruitment analytics.')
      } finally { setLoading(false) }
    }, 150)
    return () => clearTimeout(timer)
  }, [filters])

  const departments = useMemo(() => options.departments.filter(item => !filters.property_id || item.property_id === filters.property_id), [options.departments, filters.property_id])
  const jobs = useMemo(() => options.jobs.filter(item => (!filters.property_id || item.property_id === filters.property_id) && (!filters.department_id || (item as any).department_id === filters.department_id)), [options.jobs, filters.property_id, filters.department_id])
  const update = (key: string, value: string) => setFilters(old => ({ ...old, [key]: value, ...(key === 'property_id' ? { department_id: '', job_id: '' } : {}), ...(key === 'department_id' ? { job_id: '' } : {}) }))

  const cards = metrics ? [
    ['Applications', metrics.applications.toLocaleString('en-IN'), Users],
    ['Hired', metrics.hires.toLocaleString('en-IN'), UserCheck],
    ['Time to hire', metrics.time_to_hire_days == null ? '—' : `${metrics.time_to_hire_days} days`, Clock],
    ['Time to fill', metrics.time_to_fill_days == null ? '—' : `${metrics.time_to_fill_days} days`, Target],
    ['Cost per hire', metrics.cost.cost_per_hire_inr == null ? '—' : money.format(metrics.cost.cost_per_hire_inr), IndianRupee],
    ['Quality of hire', metrics.quality_of_hire.average_score == null ? '—' : `${metrics.quality_of_hire.average_score}/100`, BarChart3],
  ] as const : []

  return <div className="min-h-screen bg-slate-50 p-4 md:p-6">
    <div className="mx-auto max-w-7xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-semibold text-slate-900">Recruitment Analytics</h1><p className="mt-1 text-sm text-slate-500">Live ATS conversion, speed, cost and quality metrics</p></div>
        <span className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700">{metrics?.data_source === 'LIVE_DATABASE' ? 'Live database' : 'Loading'}</span>
      </header>

      <section className="grid gap-3 border-y border-slate-200 bg-white px-3 py-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        <Filter label="Property" value={filters.property_id} onChange={v => update('property_id', v)} options={properties.map(x => ({ value: x.id, text: x.name }))} />
        <Filter label="Department" value={filters.department_id} onChange={v => update('department_id', v)} options={departments.map(x => ({ value: x.id, text: x.name ?? '' }))} />
        <Filter label="Job" value={filters.job_id} onChange={v => update('job_id', v)} options={jobs.map(x => ({ value: x.id, text: x.title ?? '' }))} />
        <Filter label="Recruiter" value={filters.recruiter_id} onChange={v => update('recruiter_id', v)} options={options.recruiters.map(x => ({ value: x.id, text: x.full_name ?? x.email ?? '' }))} />
        <Filter label="Source" value={filters.source} onChange={v => update('source', v)} options={options.sources.map(x => ({ value: x, text: label(x) }))} />
        <DateFilter label="From" value={filters.date_from} onChange={v => update('date_from', v)} />
        <DateFilter label="To" value={filters.date_to} onChange={v => update('date_to', v)} />
      </section>

      {error && <div className="border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {loading && !metrics ? <div className="flex h-64 items-center justify-center text-slate-500"><RefreshCw className="mr-2 h-4 w-4 animate-spin" />Loading analytics</div> : metrics && <>
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">{cards.map(([title, value, Icon]) => <div key={title} className="rounded border border-slate-200 bg-white p-4"><Icon className="mb-4 h-5 w-5 text-emerald-600"/><p className="text-xs text-slate-500">{title}</p><p className="mt-1 text-xl font-semibold text-slate-900">{value}</p></div>)}</section>
        <section className="grid gap-4 lg:grid-cols-3">
          <div className="rounded border border-slate-200 bg-white p-4 lg:col-span-2"><h2 className="font-semibold text-slate-900">Recruitment funnel</h2><div className="mt-4 h-72"><ResponsiveContainer width="100%" height="100%"><BarChart data={metrics.funnel}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="stage" tickFormatter={label} fontSize={11}/><YAxis allowDecimals={false}/><Tooltip labelFormatter={label}/><Bar dataKey="count" fill="#059669" radius={[3,3,0,0]}/></BarChart></ResponsiveContainer></div></div>
          <div className="rounded border border-slate-200 bg-white p-4"><h2 className="font-semibold text-slate-900">Conversion health</h2><div className="mt-4 space-y-4"><Metric label="Interview conversion" value={metrics.interview_conversion_pct}/><Metric label="Offer acceptance" value={metrics.offer_acceptance_pct}/><Metric label="Referral conversion" value={metrics.referrals.conversion_pct}/><Metric label="High ghosting risk" value={metrics.ghosting.rate_pct} danger/></div></div>
        </section>
        <section className="overflow-hidden rounded border border-slate-200 bg-white"><div className="border-b border-slate-200 px-4 py-3"><h2 className="font-semibold text-slate-900">Source performance</h2></div><div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-sm"><thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Source</th><th>Applications</th><th>Hired</th><th>Conversion</th></tr></thead><tbody>{metrics.source_performance.map(row => <tr key={row.source} className="border-t border-slate-100"><td className="px-4 py-3 font-medium">{label(row.source)}</td><td>{row.applications}</td><td>{row.hires}</td><td>{row.conversion_pct}%</td></tr>)}{!metrics.source_performance.length && <tr><td colSpan={4} className="p-8 text-center text-slate-500">No applications match these filters.</td></tr>}</tbody></table></div></section>
        <p className="text-xs text-slate-500">Time metrics use completed persisted timestamps. Cost per hire uses {metrics.cost.entries} recorded INR cost entries. Quality uses {metrics.quality_of_hire.reviewed_hires} hired employees with completed performance reviews.</p>
      </>}
    </div>
  </div>
}

function Filter({ label: title, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; text: string }[] }) {
  return <label className="text-xs font-medium text-slate-600">{title}<select value={value} onChange={e => onChange(e.target.value)} className="mt-1 h-10 w-full rounded border border-slate-300 bg-white px-2 text-sm"><option value="">All</option>{options.map(x => <option key={x.value} value={x.value}>{x.text}</option>)}</select></label>
}
function DateFilter({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) { return <label className="text-xs font-medium text-slate-600">{label}<input type="date" value={value} onChange={e => onChange(e.target.value)} className="mt-1 h-10 w-full rounded border border-slate-300 px-2 text-sm" /></label> }
function Metric({ label: title, value, danger=false }: { label: string; value: number; danger?: boolean }) { return <div><div className="flex justify-between text-sm"><span className="text-slate-600">{title}</span><strong>{value}%</strong></div><div className="mt-1 h-2 bg-slate-100"><div className={`h-2 ${danger ? 'bg-red-500' : 'bg-emerald-600'}`} style={{ width: `${Math.min(100, value)}%` }}/></div></div> }
