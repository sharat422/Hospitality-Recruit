import { apiClient } from '@/lib/api'
import { useProperty } from '@/lib/PropertyContext'
import { Building2,MapPin,Plus,RefreshCw,Save,Settings2,Users } from 'lucide-react'
import React,{ useEffect,useState } from 'react'

type Tab = 'properties' | 'departments' | 'settings' | 'report'

interface Department {
  id: string
  code: string
  name: string
  budgeted_headcount: number
  current_headcount: number
  is_active: boolean
}

const inputClass = 'w-full min-h-11 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-100'
const labelClass = 'mb-1 block text-xs font-medium text-gray-600'
const PROPERTY_TYPES = ['HOTEL', 'RESORT', 'RESTAURANT', 'EVENTS_VENUE', 'HOSTEL', 'SERVICED_APARTMENT', 'CLOUD_KITCHEN', 'OTHER']

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label><span className={labelClass}>{label}</span>{children}</label>
}

export default function HotelManagement() {
  const { properties, activeProperty, switchProperty, refreshProperties } = useProperty()
  const [tab, setTab] = useState<Tab>('properties')
  const [selectedId, setSelectedId] = useState<string | null>(activeProperty?.id ?? null)
  const [profile, setProfile] = useState<Record<string, any>>({})
  const [departments, setDepartments] = useState<Department[]>([])
  const [report, setReport] = useState<any>(null)
  const [group, setGroup] = useState<any>(null)
  const [groupCanManage, setGroupCanManage] = useState(false)
  const [canManage, setCanManage] = useState(false)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [newDepartment, setNewDepartment] = useState({ code: '', name: '', budgeted_headcount: 0, current_headcount: 0 })
  const [newProperty, setNewProperty] = useState({ name: '', code: '', type: 'HOTEL', city: '', state: '', star_rating: '' })
  const [settingsType, setSettingsType] = useState<'hr' | 'payroll' | 'compliance' | 'branding'>('hr')
  const [settingsText, setSettingsText] = useState('{}')

  const propertyId = selectedId ?? activeProperty?.id ?? null

  const loadProperty = async (id: string) => {
    setLoading(true)
    try {
      const { data } = await apiClient.get(`/hotels/properties/${id}`)
      setProfile(data.property)
      setDepartments(data.departments ?? [])
      setCanManage(Boolean(data.can_manage))
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!selectedId && activeProperty?.id) setSelectedId(activeProperty.id)
  }, [activeProperty, selectedId])

  useEffect(() => {
    apiClient.get('/hotels/group').then(({ data }) => { setGroup(data.group); setGroupCanManage(Boolean(data.can_manage)) }).catch(() => undefined)
  }, [])

  useEffect(() => { if (propertyId) void loadProperty(propertyId) }, [propertyId])

  useEffect(() => {
    if (!propertyId || tab !== 'settings') return
    apiClient.get(`/hotels/properties/${propertyId}/settings/${settingsType}`)
      .then(({ data }) => setSettingsText(JSON.stringify(data.settings ?? {}, null, 2)))
      .catch(() => setSettingsText('{}'))
  }, [propertyId, settingsType, tab])

  const notify = (text: string) => { setMessage(text); window.setTimeout(() => setMessage(''), 3000) }

  const saveProfile = async () => {
    if (!propertyId) return
    await apiClient.patch(`/hotels/properties/${propertyId}`, profile)
    await refreshProperties()
    notify('Property profile saved.')
  }

  const saveGroup = async () => {
    const { data } = await apiClient.patch('/hotels/group', group)
    setGroup(data.group)
    notify('Hotel group profile saved.')
  }

  const createProperty = async () => {
    await apiClient.post('/hotels/properties', {
      ...newProperty,
      star_rating: newProperty.star_rating ? Number(newProperty.star_rating) : null,
      country: 'India', timezone: 'Asia/Kolkata',
    })
    setNewProperty({ name: '', code: '', type: 'HOTEL', city: '', state: '', star_rating: '' })
    await refreshProperties()
    notify('Property created.')
  }

  const addDepartment = async () => {
    if (!propertyId) return
    await apiClient.post(`/hotels/properties/${propertyId}/departments`, newDepartment)
    setNewDepartment({ code: '', name: '', budgeted_headcount: 0, current_headcount: 0 })
    await loadProperty(propertyId)
    notify('Department added.')
  }

  const saveDepartment = async (department: Department) => {
    if (!propertyId) return
    await apiClient.patch(`/hotels/properties/${propertyId}/departments/${department.id}`, department)
    notify(`${department.name} updated.`)
  }

  const saveSettings = async () => {
    if (!propertyId) return
    let parsed: Record<string, unknown>
    try { parsed = JSON.parse(settingsText) } catch { notify('Settings must be valid JSON.'); return }
    await apiClient.patch(`/hotels/properties/${propertyId}/settings/${settingsType}`, { settings: parsed })
    notify(`${settingsType} settings saved.`)
  }

  const loadReport = async () => {
    setLoading(true)
    try { const { data } = await apiClient.get('/hotels/reports/group'); setReport(data) }
    finally { setLoading(false) }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Hotel & Multi-Property Management</h1>
          <p className="mt-1 text-sm text-gray-500">{group?.name ?? 'Hotel group'} · Property profiles, teams, settings and reporting</p>
        </div>
        {message && <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</div>}
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-gray-200">
        {(['properties', 'departments', 'settings', 'report'] as Tab[]).map(item => (
          <button key={item} onClick={() => { setTab(item); if (item === 'report') void loadReport() }} className={`whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium capitalize ${tab === item ? 'border-purple-600 text-purple-700' : 'border-transparent text-gray-500'}`}>{item}</button>
        ))}
      </div>

      {tab !== 'report' && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select className={`${inputClass} sm:max-w-sm`} value={propertyId ?? ''} onChange={e => setSelectedId(e.target.value)}>
            {properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}
          </select>
          {propertyId && activeProperty?.id !== propertyId && <button onClick={() => switchProperty(propertyId)} className="min-h-11 rounded-md bg-purple-600 px-4 text-sm font-medium text-white">Switch to this property</button>}
        </div>
      )}

      {loading && <div className="py-10 text-center text-gray-500"><RefreshCw className="mx-auto h-5 w-5 animate-spin" /></div>}

      {!loading && tab === 'properties' && (
        <div className="space-y-5">
        {group && <section className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="mb-4 flex items-center gap-2"><Users className="h-5 w-5 text-purple-600" /><h2 className="font-semibold">Hotel group / company profile</h2></div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Group name"><input className={inputClass} value={group.name ?? ''} onChange={e => setGroup((g: any) => ({ ...g, name: e.target.value }))} /></Field>
            <Field label="Legal name"><input className={inputClass} value={group.legal_name ?? ''} onChange={e => setGroup((g: any) => ({ ...g, legal_name: e.target.value }))} /></Field>
            <Field label="Group code"><input className={inputClass} value={group.group_code ?? ''} onChange={e => setGroup((g: any) => ({ ...g, group_code: e.target.value }))} /></Field>
            <Field label="Contact email"><input className={inputClass} type="email" value={group.contact_email ?? ''} onChange={e => setGroup((g: any) => ({ ...g, contact_email: e.target.value }))} /></Field>
            <Field label="Contact phone"><input className={inputClass} value={group.contact_phone ?? ''} onChange={e => setGroup((g: any) => ({ ...g, contact_phone: e.target.value }))} /></Field>
            <Field label="Website"><input className={inputClass} value={group.website_url ?? ''} onChange={e => setGroup((g: any) => ({ ...g, website_url: e.target.value }))} /></Field>
            <Field label="Group logo URL"><input className={inputClass} value={group.logo_url ?? ''} onChange={e => setGroup((g: any) => ({ ...g, logo_url: e.target.value }))} /></Field>
            <Field label="Group brand colour"><input className={inputClass} type="color" value={group.brand_color ?? '#7C3AED'} onChange={e => setGroup((g: any) => ({ ...g, brand_color: e.target.value }))} /></Field>
          </div>
          {groupCanManage && <button onClick={saveGroup} className="mt-4 flex min-h-11 items-center gap-2 rounded-md bg-gray-900 px-4 text-sm font-medium text-white"><Save className="h-4 w-4" />Save group profile</button>}
        </section>}
        <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
          <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-5">
            <div className="flex items-center gap-2"><Building2 className="h-5 w-5 text-purple-600" /><h2 className="font-semibold">Property profile</h2></div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Property name"><input className={inputClass} value={profile.name ?? ''} onChange={e => setProfile(p => ({ ...p, name: e.target.value }))} /></Field>
              <Field label="Property code"><input className={inputClass} value={profile.code ?? ''} onChange={e => setProfile(p => ({ ...p, code: e.target.value }))} /></Field>
              <Field label="Property type"><select className={inputClass} value={profile.type ?? 'HOTEL'} onChange={e => setProfile(p => ({ ...p, type: e.target.value }))}>{PROPERTY_TYPES.map(type => <option key={type}>{type}</option>)}</select></Field>
              <Field label="Star rating"><input className={inputClass} type="number" min="1" max="5" step="0.5" value={profile.star_rating ?? ''} onChange={e => setProfile(p => ({ ...p, star_rating: e.target.value ? Number(e.target.value) : null }))} /></Field>
              <Field label="Rooms / units"><input className={inputClass} type="number" min="0" value={profile.room_count ?? ''} onChange={e => setProfile(p => ({ ...p, room_count: e.target.value ? Number(e.target.value) : null }))} /></Field>
              <Field label="Employee capacity"><input className={inputClass} type="number" min="0" value={profile.employee_capacity ?? ''} onChange={e => setProfile(p => ({ ...p, employee_capacity: e.target.value ? Number(e.target.value) : null }))} /></Field>
              <Field label="Address line 1"><input className={inputClass} value={profile.address_line1 ?? ''} onChange={e => setProfile(p => ({ ...p, address_line1: e.target.value }))} /></Field>
              <Field label="City"><input className={inputClass} value={profile.city ?? ''} onChange={e => setProfile(p => ({ ...p, city: e.target.value }))} /></Field>
              <Field label="State"><input className={inputClass} value={profile.state ?? ''} onChange={e => setProfile(p => ({ ...p, state: e.target.value }))} /></Field>
              <Field label="PIN code"><input className={inputClass} value={profile.postal_code ?? ''} onChange={e => setProfile(p => ({ ...p, postal_code: e.target.value }))} /></Field>
              <Field label="Logo URL"><input className={inputClass} value={profile.logo_url ?? ''} onChange={e => setProfile(p => ({ ...p, logo_url: e.target.value }))} /></Field>
              <Field label="Brand colour"><input className={inputClass} type="color" value={profile.brand_color ?? '#7C3AED'} onChange={e => setProfile(p => ({ ...p, brand_color: e.target.value }))} /></Field>
            </div>
            {canManage && <button onClick={saveProfile} className="flex min-h-11 items-center gap-2 rounded-md bg-purple-600 px-4 text-sm font-medium text-white"><Save className="h-4 w-4" />Save profile</button>}
          </section>

          <aside className="rounded-lg border border-gray-200 bg-white p-5">
            <h2 className="mb-4 font-semibold">Add property</h2>
            <div className="space-y-3">
              <Field label="Name"><input className={inputClass} value={newProperty.name} onChange={e => setNewProperty(p => ({ ...p, name: e.target.value }))} /></Field>
              <Field label="Code"><input className={inputClass} value={newProperty.code} onChange={e => setNewProperty(p => ({ ...p, code: e.target.value }))} /></Field>
              <Field label="Type"><select className={inputClass} value={newProperty.type} onChange={e => setNewProperty(p => ({ ...p, type: e.target.value }))}>{PROPERTY_TYPES.map(type => <option key={type}>{type}</option>)}</select></Field>
              <div className="grid grid-cols-2 gap-2"><Field label="City"><input className={inputClass} value={newProperty.city} onChange={e => setNewProperty(p => ({ ...p, city: e.target.value }))} /></Field><Field label="State"><input className={inputClass} value={newProperty.state} onChange={e => setNewProperty(p => ({ ...p, state: e.target.value }))} /></Field></div>
              <button disabled={!newProperty.name} onClick={createProperty} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-gray-900 px-4 text-sm font-medium text-white disabled:opacity-40"><Plus className="h-4 w-4" />Create property</button>
            </div>
          </aside>
        </div>
        </div>
      )}

      {!loading && tab === 'departments' && (
        <div className="space-y-5">
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full text-sm"><thead className="bg-gray-50 text-left text-xs uppercase text-gray-500"><tr><th className="px-4 py-3">Department</th><th className="px-4 py-3">Budgeted</th><th className="px-4 py-3">Current</th><th className="px-4 py-3">Gap</th><th className="px-4 py-3"></th></tr></thead>
              <tbody>{departments.map((department, index) => <tr key={department.id} className="border-t border-gray-100"><td className="px-4 py-3"><input className={inputClass} value={department.name} onChange={e => setDepartments(rows => rows.map((row, i) => i === index ? { ...row, name: e.target.value } : row))} /><span className="mt-1 block text-xs text-gray-400">{department.code}</span></td><td className="px-4 py-3"><input className={`${inputClass} w-24`} type="number" min="0" value={department.budgeted_headcount} onChange={e => setDepartments(rows => rows.map((row, i) => i === index ? { ...row, budgeted_headcount: Number(e.target.value) } : row))} /></td><td className="px-4 py-3"><input className={`${inputClass} w-24`} type="number" min="0" value={department.current_headcount} onChange={e => setDepartments(rows => rows.map((row, i) => i === index ? { ...row, current_headcount: Number(e.target.value) } : row))} /></td><td className="px-4 py-3 font-medium">{department.budgeted_headcount - department.current_headcount}</td><td className="px-4 py-3"><button onClick={() => saveDepartment(department)} className="rounded p-2 text-purple-600 hover:bg-purple-50" title="Save department"><Save className="h-4 w-4" /></button></td></tr>)}</tbody>
            </table>
          </div>
          {canManage && <div className="grid gap-3 rounded-lg border border-gray-200 bg-white p-4 sm:grid-cols-5"><input className={inputClass} placeholder="Code" value={newDepartment.code} onChange={e => setNewDepartment(d => ({ ...d, code: e.target.value }))} /><input className={`${inputClass} sm:col-span-2`} placeholder="Department name" value={newDepartment.name} onChange={e => setNewDepartment(d => ({ ...d, name: e.target.value }))} /><input className={inputClass} type="number" min="0" placeholder="Budgeted" value={newDepartment.budgeted_headcount} onChange={e => setNewDepartment(d => ({ ...d, budgeted_headcount: Number(e.target.value) }))} /><button onClick={addDepartment} disabled={!newDepartment.code || !newDepartment.name} className="min-h-11 rounded-md bg-purple-600 px-4 text-sm font-medium text-white disabled:opacity-40">Add department</button></div>}
        </div>
      )}

      {!loading && tab === 'settings' && (
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <div className="mb-4 flex items-center gap-2"><Settings2 className="h-5 w-5 text-purple-600" /><h2 className="font-semibold">Property-specific settings</h2></div>
          <div className="mb-4 flex flex-wrap gap-2">{(['hr', 'payroll', 'compliance', 'branding'] as const).map(type => <button key={type} onClick={() => setSettingsType(type)} className={`rounded-md px-3 py-2 text-sm capitalize ${settingsType === type ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-600'}`}>{type}</button>)}</div>
          <textarea className={`${inputClass} min-h-72 font-mono`} value={settingsText} onChange={e => setSettingsText(e.target.value)} aria-label={`${settingsType} settings JSON`} />
          {canManage && <button onClick={saveSettings} className="mt-4 flex min-h-11 items-center gap-2 rounded-md bg-purple-600 px-4 text-sm font-medium text-white"><Save className="h-4 w-4" />Save settings</button>}
        </section>
      )}

      {!loading && tab === 'report' && report && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[
            ['Properties', report.summary.property_count], ['Departments', report.summary.department_count], ['Budgeted headcount', report.summary.budgeted_headcount], ['Current headcount', report.summary.current_headcount],
          ].map(([label, value]) => <div key={String(label)} className="rounded-lg border border-gray-200 bg-white p-4"><p className="text-sm text-gray-500">{label}</p><p className="mt-1 text-2xl font-bold text-gray-900">{value}</p></div>)}</div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{report.properties.map((property: any) => <div key={property.id} className="rounded-lg border border-gray-200 bg-white p-5"><div className="flex items-start justify-between"><div><h3 className="font-semibold text-gray-900">{property.name}</h3><p className="mt-1 flex items-center gap-1 text-xs text-gray-500"><MapPin className="h-3 w-3" />{[property.city, property.state].filter(Boolean).join(', ') || 'Address not set'}</p></div><span className="rounded bg-purple-50 px-2 py-1 text-xs text-purple-700">{property.type}</span></div><div className="mt-4 grid grid-cols-2 gap-3 text-sm"><div><span className="text-gray-500">Headcount</span><p className="font-semibold">{property.current_headcount}/{property.budgeted_headcount}</p></div><div><span className="text-gray-500">Open roles</span><p className="font-semibold">{property.open_jobs}</p></div><div><span className="text-gray-500">Departments</span><p className="font-semibold">{property.department_count}</p></div><div><span className="text-gray-500">Campaigns</span><p className="font-semibold">{property.active_campaigns}</p></div></div></div>)}</div>
        </div>
      )}
    </div>
  )
}
