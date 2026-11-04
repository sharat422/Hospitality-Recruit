import { apiClient } from '@/lib/api'
import { Bell,CalendarDays,Plus,Send,X } from 'lucide-react'
import React,{ useEffect,useState } from 'react'

interface JobRole {
  id: string
  title: string
  location?: string
}

interface InterviewSlot {
  id: string
  job_role_id: string
  start_time: string
  end_time: string
  status: string
  confirmation_token?: string
  candidate?: { name?: string; full_name?: string; email?: string; phone?: string } | null
  candidate_id?: string
}

interface InviteModal {
  slot: InterviewSlot
  candidateId: string
  phone: string
}

function formatDT(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true,
  })
}

function candidateName(slot: InterviewSlot): string {
  const c = slot.candidate
  if (!c) return 'Unassigned'
  return c.name || c.full_name || c.email || 'Unknown'
}

const STATUS_BADGE: Record<string, string> = {
  AVAILABLE: 'bg-green-100 text-green-700',
  INVITED: 'bg-yellow-100 text-yellow-700',
  BOOKED: 'bg-blue-100 text-blue-700',
  CANCELLED: 'bg-red-100 text-red-700',
}

export const InterviewScheduler: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'create' | 'upcoming'>('create')
  const [jobRoles, setJobRoles] = useState<JobRole[]>([])
  const [slots, setSlots] = useState<InterviewSlot[]>([])

  // Create form
  const [jobRoleId, setJobRoleId] = useState('')
  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [createdSlots, setCreatedSlots] = useState<InterviewSlot[]>([])
  const [creating, setCreating] = useState(false)

  // Invite modal
  const [inviteModal, setInviteModal] = useState<InviteModal | null>(null)
  const [sendingInvite, setSendingInvite] = useState(false)

  // Reminders
  const [sendingReminders, setSendingReminders] = useState(false)

  useEffect(() => {
    apiClient.get('/ai-screening/job-roles')
      .then(res => setJobRoles(res.data?.job_roles || []))
      .catch(() => {})
  }, [])

  const fetchUpcoming = () => {
    apiClient.get('/engagement/interviews/slots', { params: { status: 'BOOKED' } })
      .then(res => setSlots(res.data || []))
      .catch(() => {})
  }

  useEffect(() => {
    if (activeTab === 'upcoming') fetchUpcoming()
  }, [activeTab])

  const createSlot = async () => {
    if (!jobRoleId || !date || !startTime || !endTime) {
      alert('Please fill in all fields.')
      return
    }
    setCreating(true)
    try {
      const start = `${date}T${startTime}:00`
      const end = `${date}T${endTime}:00`
      const res = await apiClient.post('/engagement/interviews/slots', {
        job_role_id: jobRoleId,
        slots: [{ start_time: start, end_time: end }],
      })
      const ids: string[] = res.data?.slot_ids || []
      if (ids.length > 0) {
        const newSlot: InterviewSlot = {
          id: ids[0],
          job_role_id: jobRoleId,
          start_time: start,
          end_time: end,
          status: 'AVAILABLE',
          candidate: null,
        }
        setCreatedSlots(prev => [newSlot, ...prev])
        setStartTime('')
        setEndTime('')
      }
    } catch (e) {
      console.error('Create slot failed', e)
    } finally {
      setCreating(false)
    }
  }

  const openInvite = (slot: InterviewSlot) => {
    setInviteModal({ slot, candidateId: '', phone: '' })
  }

  const sendInvite = async () => {
    if (!inviteModal) return
    if (!inviteModal.candidateId || !inviteModal.phone) {
      alert('Please enter candidate ID and phone number.')
      return
    }
    setSendingInvite(true)
    try {
      await apiClient.post('/engagement/interviews/invite', {
        candidate_id: inviteModal.candidateId,
        slot_id: inviteModal.slot.id,
        phone: inviteModal.phone,
      })
      alert('Invite sent successfully!')
      setInviteModal(null)
      setCreatedSlots(prev =>
        prev.map(s => s.id === inviteModal.slot.id ? { ...s, status: 'INVITED' } : s)
      )
    } catch (e) {
      console.error('Invite failed', e)
      alert('Failed to send invite.')
    } finally {
      setSendingInvite(false)
    }
  }

  const sendReminders = async () => {
    setSendingReminders(true)
    try {
      const res = await apiClient.post('/engagement/interviews/reminders')
      alert(`Sent ${res.data.reminders_24h_sent} 24h reminders and ${res.data.reminders_1h_sent} 1h reminders.`)
    } catch (e) {
      console.error('Reminders failed', e)
    } finally {
      setSendingReminders(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Interview Scheduler</h1>
          <p className="text-gray-500 text-sm mt-1">Create slots, send invites, and manage confirmations</p>
        </div>
        <button
          onClick={sendReminders}
          disabled={sendingReminders}
          className="flex items-center gap-2 border border-gray-200 text-gray-700 hover:bg-gray-50 px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          <Bell className="w-4 h-4" />
          {sendingReminders ? 'Sending...' : 'Send Reminders'}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit mb-6">
        <button
          onClick={() => setActiveTab('create')}
          className={`px-5 py-2 rounded-md text-sm font-medium transition ${
            activeTab === 'create' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Create Slots
        </button>
        <button
          onClick={() => setActiveTab('upcoming')}
          className={`px-5 py-2 rounded-md text-sm font-medium transition ${
            activeTab === 'upcoming' ? 'bg-white shadow text-gray-900' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          Upcoming Interviews
        </button>
      </div>

      {activeTab === 'create' ? (
        <div>
          {/* Create form */}
          <div className="bg-white rounded-xl border border-gray-100 p-6 mb-6">
            <h2 className="font-semibold text-gray-900 mb-4">Add Interview Slot</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs text-gray-500 mb-1 font-medium">Job Role</label>
                <select
                  value={jobRoleId}
                  onChange={e => setJobRoleId(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                >
                  <option value="">Select a job role</option>
                  {jobRoles.map(r => (
                    <option key={r.id} value={r.id}>{r.title}{r.location ? ` — ${r.location}` : ''}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className="block text-xs text-gray-500 mb-1 font-medium">Date</label>
                <input
                  type="date"
                  value={date}
                  onChange={e => setDate(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Start Time</label>
                <input
                  type="time"
                  value={startTime}
                  onChange={e => setStartTime(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">End Time</label>
                <input
                  type="time"
                  value={endTime}
                  onChange={e => setEndTime(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
            </div>
            <button
              onClick={createSlot}
              disabled={creating}
              className="mt-4 flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              {creating ? 'Creating...' : 'Add Slot'}
            </button>
          </div>

          {/* Created slots */}
          {createdSlots.length > 0 && (
            <div>
              <h3 className="font-semibold text-gray-700 text-sm mb-3">Created Slots</h3>
              <div className="space-y-2">
                {createdSlots.map(slot => (
                  <div key={slot.id} className="bg-white border border-gray-100 rounded-xl px-5 py-4 flex items-center justify-between">
                    <div>
                      <div className="font-medium text-gray-900 text-sm">{formatDT(slot.start_time)}</div>
                      <div className="text-xs text-gray-400">until {formatDT(slot.end_time)}</div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_BADGE[slot.status] || 'bg-gray-100 text-gray-600'}`}>
                        {slot.status}
                      </span>
                      {slot.status === 'AVAILABLE' && (
                        <button
                          onClick={() => openInvite(slot)}
                          className="flex items-center gap-1 bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition"
                        >
                          <Send className="w-3 h-3" />
                          Send Invite
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-700 text-sm">Upcoming Booked Interviews</h3>
            <button onClick={fetchUpcoming} className="text-xs text-purple-600 hover:underline">Refresh</button>
          </div>
          {slots.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <CalendarDays className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">No upcoming interviews</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                    <th className="py-3 pr-4 font-medium">Candidate</th>
                    <th className="py-3 pr-4 font-medium">Start</th>
                    <th className="py-3 pr-4 font-medium">End</th>
                    <th className="py-3 pr-4 font-medium">Status</th>
                    <th className="py-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {slots.map(slot => (
                    <tr key={slot.id} className="hover:bg-gray-50">
                      <td className="py-3 pr-4 font-medium text-gray-900">{candidateName(slot)}</td>
                      <td className="py-3 pr-4 text-gray-600">{formatDT(slot.start_time)}</td>
                      <td className="py-3 pr-4 text-gray-600">{formatDT(slot.end_time)}</td>
                      <td className="py-3 pr-4">
                        <span className={`text-xs px-2 py-1 rounded-full font-medium ${STATUS_BADGE[slot.status] || 'bg-gray-100 text-gray-600'}`}>
                          {slot.status}
                        </span>
                      </td>
                      <td className="py-3">
                        <button
                          onClick={sendReminders}
                          className="text-xs text-purple-600 hover:underline mr-3"
                        >
                          Send Reminders
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Invite modal */}
      {inviteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-gray-900">Send Interview Invite</h3>
              <button onClick={() => setInviteModal(null)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Slot: <span className="font-medium text-gray-700">{formatDT(inviteModal.slot.start_time)}</span>
            </p>
            <div className="space-y-3 mb-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Candidate ID</label>
                <input
                  type="text"
                  value={inviteModal.candidateId}
                  onChange={e => setInviteModal(m => m ? { ...m, candidateId: e.target.value } : m)}
                  placeholder="UUID..."
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1 font-medium">Candidate Phone</label>
                <input
                  type="tel"
                  value={inviteModal.phone}
                  onChange={e => setInviteModal(m => m ? { ...m, phone: e.target.value } : m)}
                  placeholder="+1234567890"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                />
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setInviteModal(null)}
                className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                onClick={sendInvite}
                disabled={sendingInvite}
                className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
              >
                <Send className="w-4 h-4" />
                {sendingInvite ? 'Sending...' : 'Send Invite'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default InterviewScheduler
