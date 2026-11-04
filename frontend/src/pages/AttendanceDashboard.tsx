import { AlertTriangle,Check,Clock3,Loader2,LocateFixed,RefreshCw,X } from 'lucide-react'
import { useEffect,useMemo,useState } from 'react'
import apiClient from '../lib/api'
import { useProperty } from '../lib/PropertyContext'
import { useRBAC } from '../lib/RBACContext'

type Daily = {
  id: string; attendance_date: string; first_in_at?: string; last_out_at?: string
  worked_minutes: number; late_minutes: number; early_departure_minutes: number
  overtime_minutes: number; status: string; validation_status: string; anomaly_codes?: string[]
}
type Correction = { id: string; employee_id: string; reason: string; status: string; created_at: string }

const statusClass = (value: string) => value === 'PRESENT' || value === 'VALIDATED'
  ? 'bg-emerald-50 text-emerald-700' : value === 'PENDING' || value === 'WEEKLY_OFF'
    ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
const time = (value?: string) => value ? new Date(value).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : '--'
const hours = (minutes = 0) => `${Math.floor(minutes / 60)}h ${minutes % 60}m`

export default function AttendanceDashboard() {
  const { activeProperty } = useProperty()
  const { can } = useRBAC()
  const [records, setRecords] = useState<Daily[]>([])
  const [corrections, setCorrections] = useState<Correction[]>([])
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true); setError('')
    try {
      const requests: Promise<any>[] = [apiClient.get('/attendance/me/history')]
      if (can('attendance.manage')) requests.push(apiClient.get('/attendance/corrections?status_filter=PENDING'))
      const result = await Promise.all(requests)
      setRecords(result[0].data.records || [])
      setCorrections(result[1]?.data.corrections || [])
    } catch (err: any) { setError(err.response?.data?.detail || 'Attendance could not be loaded.') }
    finally { setLoading(false) }
  }
  useEffect(() => { void load() }, [can('attendance.manage')])

  const today = useMemo(() => records.find(r => r.attendance_date === new Date().toISOString().slice(0, 10)), [records])
  const punch = (punch_type: 'IN' | 'OUT') => {
    if (!activeProperty) { setError('Select an active property before punching.'); return }
    if (!navigator.geolocation) { setError('Location is not supported by this browser.'); return }
    setWorking(true); setError('')
    navigator.geolocation.getCurrentPosition(async position => {
      try {
        await apiClient.post('/attendance/punch', {
          punch_type, property_id: activeProperty.id, source: 'MOBILE',
          latitude: position.coords.latitude, longitude: position.coords.longitude,
          gps_accuracy_m: position.coords.accuracy,
        })
        await load()
      } catch (err: any) { setError(err.response?.data?.detail || 'Punch could not be recorded.') }
      finally { setWorking(false) }
    }, () => { setError('Location permission is required for attendance.'); setWorking(false) },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 })
  }
  const review = async (id: string, action: 'APPROVE' | 'REJECT') => {
    setWorking(true)
    try { await apiClient.patch(`/attendance/corrections/${id}`, { action }); await load() }
    catch (err: any) { setError(err.response?.data?.detail || 'Correction could not be reviewed.') }
    finally { setWorking(false) }
  }

  return <main className="max-w-7xl mx-auto p-4 sm:p-6 space-y-6">
    <header className="flex items-start justify-between gap-4">
      <div><h1 className="text-2xl font-bold text-gray-950">Attendance</h1><p className="text-sm text-gray-500 mt-1">Punches, daily status and corrections</p></div>
      <button onClick={() => void load()} className="p-2 border rounded-md" title="Refresh"><RefreshCw className="w-4 h-4" /></button>
    </header>
    {error && <div className="border border-red-200 bg-red-50 text-red-700 rounded-md p-3 text-sm">{error}</div>}
    <section className="border bg-white rounded-lg p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><LocateFixed className="w-4 h-4 text-emerald-600" />{activeProperty?.name || 'No property selected'}</div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5">
        <div><p className="text-xs text-gray-500">Punch in</p><p className="text-xl font-bold mt-1">{time(today?.first_in_at)}</p></div>
        <div><p className="text-xs text-gray-500">Punch out</p><p className="text-xl font-bold mt-1">{time(today?.last_out_at)}</p></div>
        <div><p className="text-xs text-gray-500">Worked</p><p className="text-xl font-bold mt-1">{hours(today?.worked_minutes)}</p></div>
        <div><p className="text-xs text-gray-500">Validation</p><span className={`inline-flex mt-2 px-2 py-1 rounded text-xs font-semibold ${statusClass(today?.validation_status || 'PENDING')}`}>{today?.validation_status || 'PENDING'}</span></div>
      </div>
      <div className="grid grid-cols-2 gap-3 mt-6">
        <button disabled={working} onClick={() => punch('IN')} className="min-h-12 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-semibold rounded-md flex justify-center items-center gap-2"><Clock3 className="w-5 h-5" />Punch In</button>
        <button disabled={working} onClick={() => punch('OUT')} className="min-h-12 bg-gray-900 hover:bg-black disabled:opacity-50 text-white font-semibold rounded-md flex justify-center items-center gap-2"><Clock3 className="w-5 h-5" />Punch Out</button>
      </div>
      <p className="text-xs text-gray-500 mt-3">GPS is checked against your selected property. Pending attendance is not available to payroll.</p>
    </section>

    {can('attendance.manage') && <section className="border bg-white rounded-lg overflow-hidden">
      <div className="px-5 py-4 border-b"><h2 className="font-semibold">Pending corrections</h2></div>
      {!corrections.length ? <p className="p-8 text-center text-sm text-gray-500">No pending corrections.</p> : corrections.map(item => <div key={item.id} className="p-4 border-b last:border-0 flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="min-w-0 flex-1"><p className="font-medium text-sm">Employee {item.employee_id}</p><p className="text-sm text-gray-600 mt-1">{item.reason}</p></div>
        <div className="flex gap-2"><button disabled={working} onClick={() => review(item.id, 'APPROVE')} className="px-3 py-2 bg-emerald-600 text-white rounded-md text-sm flex gap-1"><Check className="w-4 h-4" />Approve</button><button disabled={working} onClick={() => review(item.id, 'REJECT')} className="px-3 py-2 border rounded-md text-sm flex gap-1"><X className="w-4 h-4" />Reject</button></div>
      </div>)}
    </section>}

    <section className="border bg-white rounded-lg overflow-x-auto">
      <div className="px-5 py-4 border-b"><h2 className="font-semibold">Attendance history</h2></div>
      {loading ? <div className="p-10 flex justify-center"><Loader2 className="animate-spin" /></div> : <table className="w-full text-sm min-w-[760px]"><thead className="bg-gray-50 text-gray-500"><tr>{['Date','Status','In','Out','Worked','Late','Early','Overtime','Validation'].map(h => <th key={h} className="text-left px-4 py-3 font-medium">{h}</th>)}</tr></thead><tbody>{records.map(row => <tr key={row.id} className="border-t"><td className="px-4 py-3">{new Date(`${row.attendance_date}T00:00:00`).toLocaleDateString('en-IN')}</td><td className="px-4 py-3"><span className={`px-2 py-1 rounded text-xs font-semibold ${statusClass(row.status)}`}>{row.status}</span></td><td className="px-4">{time(row.first_in_at)}</td><td className="px-4">{time(row.last_out_at)}</td><td className="px-4">{hours(row.worked_minutes)}</td><td className="px-4">{row.late_minutes}m</td><td className="px-4">{row.early_departure_minutes}m</td><td className="px-4">{row.overtime_minutes}m</td><td className="px-4"><span className={`px-2 py-1 rounded text-xs ${statusClass(row.validation_status)}`}>{row.validation_status}</span>{row.anomaly_codes?.length ? <AlertTriangle className="inline ml-2 w-4 h-4 text-amber-600" /> : null}</td></tr>)}</tbody></table>}
    </section>
  </main>
}
