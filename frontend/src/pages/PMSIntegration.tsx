import { AlertTriangle, Building2, CalendarDays, Loader2, Plug, RefreshCw, TrendingUp, UserPlus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import apiClient from '../lib/api'
import { useProperty } from '../lib/PropertyContext'
import { useRBAC } from '../lib/RBACContext'

type Provider = { provider_code: string; display_name: string; mode: string; verified: boolean; notes: string }
type Connection = {
  id: string; provider_code: string; base_url?: string; property_ref?: string
  rooms_available?: number; credential_env_var?: string; is_active: boolean
  last_sync_at?: string; last_sync_status?: string; last_sync_error?: string
  credential_configured?: boolean
}
type PlanRow = {
  business_date: string; department_code: string; department_name: string
  driver: string; driver_value: number; occupancy_pct: number; rooms_sold: number
  required_headcount: number; scheduled_headcount: number; gap: number; status: string
}
type Signal = {
  department_code: string; department_name: string; short_days: number
  peak_gap: number; recommended_hires: number; urgency: string; first_short_date: string
}
type Summary = {
  days: number; total_required: number; total_scheduled: number
  total_gap: number; short_entries: number; avg_occupancy_pct: number
}

const dmy = (iso: string) => new Date(iso).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
const stamp = (iso?: string) => iso ? new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'Never'
const gapClass = (status: string) => status === 'SHORT'
  ? 'bg-red-50 text-red-700' : status === 'OVER' ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'

export default function PMSIntegration() {
  const { activeProperty } = useProperty()
  const { can } = useRBAC()
  const manage = can('properties.manage')

  const [providers, setProviders] = useState<Provider[]>([])
  const [connection, setConnection] = useState<Connection | null>(null)
  const [plan, setPlan] = useState<PlanRow[]>([])
  const [signals, setSignals] = useState<Signal[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')

  const [form, setForm] = useState({ provider_code: 'MOCK', base_url: '', property_ref: '', rooms_available: '', credential_env_var: '' })

  const propertyId = activeProperty?.id

  const load = async () => {
    if (!propertyId) { setLoading(false); return }
    setLoading(true); setError('')
    try {
      const [prov, conn, planResp] = await Promise.all([
        apiClient.get('/pms/providers'),
        apiClient.get('/pms/connections', { params: { property_id: propertyId } }),
        apiClient.get('/pms/staffing-plan', { params: { property_id: propertyId } }),
      ])
      setProviders(prov.data || [])
      setConnection(conn.data || null)
      if (conn.data) {
        setForm({
          provider_code: conn.data.provider_code,
          base_url: conn.data.base_url || '',
          property_ref: conn.data.property_ref || '',
          rooms_available: conn.data.rooms_available ? String(conn.data.rooms_available) : '',
          credential_env_var: conn.data.credential_env_var || '',
        })
      }
      setPlan(planResp.data.plan || [])
      setSignals(planResp.data.hiring_signals || [])
      setSummary(planResp.data.summary || null)
      setNotice(planResp.data.message || '')
    } catch (err: any) {
      setError(err.response?.data?.detail || 'PMS data could not be loaded.')
    } finally { setLoading(false) }
  }

  useEffect(() => { void load() }, [propertyId])

  const saveConnection = async () => {
    if (!propertyId) return
    setSyncing(true); setError('')
    try {
      await apiClient.put('/pms/connections', {
        property_id: propertyId,
        provider_code: form.provider_code,
        base_url: form.base_url || null,
        property_ref: form.property_ref || null,
        rooms_available: form.rooms_available ? Number(form.rooms_available) : null,
        credential_env_var: form.credential_env_var || null,
      })
      await load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Connection could not be saved.')
    } finally { setSyncing(false) }
  }

  const syncNow = async () => {
    if (!connection) return
    setSyncing(true); setError('')
    try {
      const { data } = await apiClient.post(`/pms/connections/${connection.id}/sync`, null, { params: { days_ahead: 30 } })
      setNotice(`Synced ${data.synced_days} days from ${data.provider}.`)
      await load()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'PMS sync failed.')
    } finally { setSyncing(false) }
  }

  // One column per department, one row per date — the shape a GM reads.
  const grid = useMemo(() => {
    const dates = [...new Set(plan.map(p => p.business_date))].sort()
    const departments = [...new Map(plan.map(p => [p.department_code, p.department_name])).entries()]
    const cell = new Map(plan.map(p => [`${p.business_date}|${p.department_code}`, p]))
    return { dates, departments, cell }
  }, [plan])

  if (!propertyId) {
    return <div className="p-8 text-slate-600">Select an active property to configure its PMS connection.</div>
  }

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 flex items-center gap-2">
            <Plug className="h-6 w-6 text-purple-600" /> Hotel PMS Integration
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Pull occupancy from your PMS and turn it into staffing demand for {activeProperty?.name}.
          </p>
        </div>
        <button onClick={() => void load()} disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </header>

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" /> {error}
        </div>
      )}
      {notice && !error && (
        <div className="rounded-lg bg-blue-50 p-3 text-sm text-blue-700">{notice}</div>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="font-medium text-slate-900 flex items-center gap-2 mb-4">
          <Building2 className="h-4 w-4 text-slate-400" /> Connection
        </h2>

        <div className="grid gap-4 md:grid-cols-3">
          <label className="text-sm">
            <span className="text-slate-600">PMS product</span>
            <select value={form.provider_code} disabled={!manage}
              onChange={e => setForm({ ...form, provider_code: e.target.value })}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50">
              {providers.map(p => <option key={p.provider_code} value={p.provider_code}>{p.display_name}</option>)}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-slate-600">API base URL</span>
            <input value={form.base_url} disabled={!manage || form.provider_code === 'MOCK'}
              onChange={e => setForm({ ...form, base_url: e.target.value })}
              placeholder={form.provider_code === 'MOCK' ? 'Not needed in sandbox' : 'https://api.vendor.com/v1'}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Property ref in PMS</span>
            <input value={form.property_ref} disabled={!manage}
              onChange={e => setForm({ ...form, property_ref: e.target.value })}
              placeholder="e.g. GOA-01"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Total rooms</span>
            <input type="number" min={1} value={form.rooms_available} disabled={!manage}
              onChange={e => setForm({ ...form, rooms_available: e.target.value })}
              placeholder="120"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 disabled:bg-slate-50" />
          </label>
          <label className="text-sm md:col-span-2">
            <span className="text-slate-600">Credential env var</span>
            <input value={form.credential_env_var} disabled={!manage || form.provider_code === 'MOCK'}
              onChange={e => setForm({ ...form, credential_env_var: e.target.value.toUpperCase() })}
              placeholder="PMS_API_KEY_GOA01"
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs disabled:bg-slate-50" />
            <span className="mt-1 block text-xs text-slate-400">
              The API key is read from this server environment variable. It is never stored in the database.
            </span>
          </label>
        </div>

        {providers.find(p => p.provider_code === form.provider_code && !p.verified) && (
          <p className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
            <strong>Unverified field map.</strong>{' '}
            {providers.find(p => p.provider_code === form.provider_code)?.notes}{' '}
            Confirm the response fields against your tenant before relying on the forecast.
          </p>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3">
          {manage && (
            <button onClick={() => void saveConnection()} disabled={syncing}
              className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm text-white hover:bg-purple-700 disabled:opacity-50">
              {syncing && <Loader2 className="h-4 w-4 animate-spin" />} Save connection
            </button>
          )}
          {connection && manage && (
            <button onClick={() => void syncNow()} disabled={syncing}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50 disabled:opacity-50">
              <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} /> Sync occupancy
            </button>
          )}
          {connection && (
            <span className="text-xs text-slate-500">
              Last sync: {stamp(connection.last_sync_at)}
              {connection.last_sync_status && (
                <span className={`ml-2 rounded px-2 py-0.5 ${connection.last_sync_status === 'OK' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'}`}>
                  {connection.last_sync_status}
                </span>
              )}
            </span>
          )}
        </div>
        {connection?.last_sync_error && (
          <p className="mt-2 text-xs text-red-600">{connection.last_sync_error}</p>
        )}
      </section>

      {summary && summary.days > 0 && (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { label: 'Avg occupancy', value: `${summary.avg_occupancy_pct}%`, icon: TrendingUp },
            { label: 'Headcount required', value: summary.total_required, icon: CalendarDays },
            { label: 'Currently rostered', value: summary.total_scheduled, icon: Building2 },
            { label: 'Shortfall (person-days)', value: summary.total_gap, icon: UserPlus },
          ].map(card => (
            <div key={card.label} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
                <card.icon className="h-3.5 w-3.5" /> {card.label}
              </div>
              <div className="mt-2 text-2xl font-semibold text-slate-900">{card.value}</div>
            </div>
          ))}
        </section>
      )}

      {signals.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="font-medium text-slate-900 flex items-center gap-2 mb-1">
            <UserPlus className="h-4 w-4 text-purple-600" /> Hiring signals
          </h2>
          <p className="text-xs text-slate-500 mb-4">
            Departments short across several days. A one-off short day is a rostering fix; a sustained
            gap is a headcount gap. Recommended hires uses the median shortfall, not the peak.
          </p>
          <div className="space-y-2">
            {signals.map(s => (
              <div key={s.department_code}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50 p-3">
                <div>
                  <div className="font-medium text-slate-900">{s.department_name}</div>
                  <div className="text-xs text-slate-500">
                    Short on {s.short_days} days from {dmy(s.first_short_date)} · peak gap {s.peak_gap}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`rounded px-2 py-1 text-xs ${s.urgency === 'HIGH' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                    {s.urgency}
                  </span>
                  <span className="text-sm font-semibold text-slate-900">
                    Hire {s.recommended_hires}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {grid.dates.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-5 overflow-x-auto">
          <h2 className="font-medium text-slate-900 mb-4">Required vs rostered headcount</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="pb-2 pr-4 font-medium">Date</th>
                <th className="pb-2 pr-4 font-medium">Occ.</th>
                {grid.departments.map(([code, name]) => (
                  <th key={code} className="pb-2 pr-4 font-medium whitespace-nowrap">{name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.dates.map(d => {
                const occ = grid.cell.get(`${d}|${grid.departments[0]?.[0]}`)?.occupancy_pct ?? 0
                return (
                  <tr key={d} className="border-t border-slate-100">
                    <td className="py-2 pr-4 whitespace-nowrap text-slate-700">{dmy(d)}</td>
                    <td className="py-2 pr-4 text-slate-500">{occ}%</td>
                    {grid.departments.map(([code]) => {
                      const c = grid.cell.get(`${d}|${code}`)
                      if (!c) return <td key={code} className="py-2 pr-4 text-slate-300">–</td>
                      return (
                        <td key={code} className="py-2 pr-4">
                          <span className={`inline-block rounded px-2 py-0.5 text-xs ${gapClass(c.status)}`}>
                            {c.scheduled_headcount}/{c.required_headcount}
                            {c.gap > 0 && <strong className="ml-1">-{c.gap}</strong>}
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-slate-400">
            Each cell is rostered / required for that department and date. Red means short.
          </p>
        </section>
      )}
    </div>
  )
}
