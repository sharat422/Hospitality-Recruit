import { apiClient } from '@/lib/api'
import { ChevronRight,Plus,Trash2,X,Zap } from 'lucide-react'
import React,{ useEffect,useState } from 'react'

interface DripStep {
  step_order: number
  delay_hours: number
  channel: 'SMS' | 'WHATSAPP' | 'EMAIL'
  message_template: string
  is_ai_personalized: boolean
}

interface DripSequence {
  id: string
  name: string
  trigger_event: string
  is_active: boolean
  step_count: number
  created_at: string
}

const TRIGGER_EVENTS = [
  { value: 'OFFER_SENT', label: 'Offer Sent' },
  { value: 'INTERVIEW_SCHEDULED', label: 'Interview Scheduled' },
  { value: 'APPLICATION_RECEIVED', label: 'Application Received' },
  { value: 'REJECTED', label: 'Rejected' },
]

const TRIGGER_BADGES: Record<string, string> = {
  OFFER_SENT: 'bg-green-100 text-green-700',
  INTERVIEW_SCHEDULED: 'bg-blue-100 text-blue-700',
  APPLICATION_RECEIVED: 'bg-purple-100 text-purple-700',
  REJECTED: 'bg-red-100 text-red-700',
}

const CHANNEL_ICONS: Record<string, string> = {
  SMS: '📱',
  WHATSAPP: '💬',
  EMAIL: '✉️',
}

const DEFAULT_STEP: DripStep = {
  step_order: 1,
  delay_hours: 24,
  channel: 'SMS',
  message_template: '',
  is_ai_personalized: false,
}

export const DripSequenceBuilder: React.FC = () => {
  const [sequences, setSequences] = useState<DripSequence[]>([])
  const [loading, setLoading] = useState(false)
  const [showDrawer, setShowDrawer] = useState(false)

  // Form state
  const [name, setName] = useState('')
  const [triggerEvent, setTriggerEvent] = useState('OFFER_SENT')
  const [steps, setSteps] = useState<DripStep[]>([{ ...DEFAULT_STEP }])
  const [creating, setCreating] = useState(false)
  const [drawerStep, setDrawerStep] = useState(1)

  const fetchSequences = async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/engagement/drip/sequences')
      setSequences(res.data || [])
    } catch (e) {
      console.error('Failed to fetch sequences', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSequences()
  }, [])

  const addStep = () => {
    setSteps(prev => [
      ...prev,
      { ...DEFAULT_STEP, step_order: prev.length + 1, delay_hours: (prev.at(-1)?.delay_hours || 0) + 24 },
    ])
  }

  const removeStep = (idx: number) => {
    setSteps(prev => prev.filter((_, i) => i !== idx).map((s, i) => ({ ...s, step_order: i + 1 })))
  }

  const updateStep = (idx: number, field: keyof DripStep, value: unknown) => {
    setSteps(prev => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s))
  }

  const createSequence = async () => {
    if (!name.trim()) { alert('Please enter a sequence name.'); return }
    if (steps.some(s => !s.message_template.trim())) { alert('All steps must have a message template.'); return }
    setCreating(true)
    try {
      await apiClient.post('/engagement/drip/sequences', { name, trigger_event: triggerEvent, steps })
      setShowDrawer(false)
      setName('')
      setTriggerEvent('OFFER_SENT')
      setSteps([{ ...DEFAULT_STEP }])
      setDrawerStep(1)
      fetchSequences()
    } catch (e) {
      console.error('Create sequence failed', e)
      alert('Failed to create sequence.')
    } finally {
      setCreating(false)
    }
  }

  const openDrawer = () => {
    setShowDrawer(true)
    setDrawerStep(1)
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Drip Sequences</h1>
          <p className="text-gray-500 text-sm mt-1">Automate candidate nurturing with timed message sequences</p>
        </div>
        <button
          onClick={openDrawer}
          className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition"
        >
          <Plus className="w-4 h-4" />
          New Sequence
        </button>
      </div>

      {/* Sequences table */}
      {loading ? (
        <div className="text-center py-12 text-gray-400 text-sm">Loading sequences...</div>
      ) : sequences.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <Zap className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg font-medium">No sequences yet</p>
          <p className="text-sm">Create your first drip sequence to automate candidate engagement.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                <th className="py-3 px-5 font-medium">Name</th>
                <th className="py-3 px-4 font-medium">Trigger</th>
                <th className="py-3 px-4 font-medium">Steps</th>
                <th className="py-3 px-4 font-medium">Status</th>
                <th className="py-3 px-4 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {sequences.map(seq => (
                <tr key={seq.id} className="hover:bg-gray-50">
                  <td className="py-3 px-5 font-medium text-gray-900">{seq.name}</td>
                  <td className="py-3 px-4">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${TRIGGER_BADGES[seq.trigger_event] || 'bg-gray-100 text-gray-600'}`}>
                      {TRIGGER_EVENTS.find(t => t.value === seq.trigger_event)?.label || seq.trigger_event}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-gray-600">{seq.step_count} step{seq.step_count !== 1 ? 's' : ''}</td>
                  <td className="py-3 px-4">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${seq.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                      {seq.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <button
                      onClick={() => alert(`Enroll candidate in "${seq.name}": use the Enroll API with sequence_id=${seq.id}`)}
                      className="text-xs text-purple-600 hover:underline font-medium"
                    >
                      Enroll Candidate
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Drawer overlay */}
      {showDrawer && (
        <div className="fixed inset-0 bg-black/40 z-50 flex justify-end">
          <div className="bg-white w-full max-w-xl flex flex-col h-full shadow-2xl">
            {/* Drawer header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-gray-200">
              <h2 className="font-bold text-gray-900 text-lg">New Drip Sequence</h2>
              <button onClick={() => setShowDrawer(false)} className="p-1 hover:bg-gray-100 rounded">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Stepper indicator */}
            <div className="flex items-center gap-2 px-6 py-3 bg-gray-50 border-b border-gray-100">
              {[1, 2, 3].map(s => (
                <React.Fragment key={s}>
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                    drawerStep === s ? 'bg-purple-600 text-white' :
                    drawerStep > s ? 'bg-green-500 text-white' :
                    'bg-gray-200 text-gray-500'
                  }`}>
                    {drawerStep > s ? '✓' : s}
                  </div>
                  {s < 3 && <ChevronRight className="w-4 h-4 text-gray-300" />}
                </React.Fragment>
              ))}
              <span className="ml-2 text-xs text-gray-500">
                {drawerStep === 1 ? 'Basic Info' : drawerStep === 2 ? 'Build Steps' : 'Timeline Preview'}
              </span>
            </div>

            {/* Drawer body */}
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {drawerStep === 1 && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Sequence Name</label>
                    <input
                      type="text"
                      value={name}
                      onChange={e => setName(e.target.value)}
                      placeholder="e.g. Post-Offer Nurture"
                      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Trigger Event</label>
                    <select
                      value={triggerEvent}
                      onChange={e => setTriggerEvent(e.target.value)}
                      className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                    >
                      {TRIGGER_EVENTS.map(t => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-400 mt-1">This sequence will start automatically when this event occurs.</p>
                  </div>
                </div>
              )}

              {drawerStep === 2 && (
                <div>
                  <div className="space-y-4">
                    {steps.map((step, idx) => (
                      <div key={idx} className="bg-gray-50 rounded-xl p-4 border border-gray-100">
                        <div className="flex items-center justify-between mb-3">
                          <span className="text-sm font-semibold text-gray-700">Step {idx + 1}</span>
                          {steps.length > 1 && (
                            <button onClick={() => removeStep(idx)} className="p-1 text-red-400 hover:text-red-600">
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                        <div className="grid grid-cols-2 gap-3 mb-3">
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">Delay (hours)</label>
                            <input
                              type="number"
                              min={0}
                              value={step.delay_hours}
                              onChange={e => updateStep(idx, 'delay_hours', parseInt(e.target.value) || 0)}
                              className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                            />
                          </div>
                          <div>
                            <label className="block text-xs text-gray-500 mb-1">Channel</label>
                            <select
                              value={step.channel}
                              onChange={e => updateStep(idx, 'channel', e.target.value)}
                              className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-400"
                            >
                              <option value="SMS">SMS</option>
                              <option value="WHATSAPP">WhatsApp</option>
                              <option value="EMAIL">Email</option>
                            </select>
                          </div>
                        </div>
                        <div className="mb-2">
                          <label className="block text-xs text-gray-500 mb-1">
                            Message Template
                            <span className="ml-2 text-gray-400">Variables: &#123;&#123;name&#125;&#125;, &#123;&#123;role&#125;&#125;, &#123;&#123;property&#125;&#125;</span>
                          </label>
                          <textarea
                            rows={3}
                            value={step.message_template}
                            onChange={e => updateStep(idx, 'message_template', e.target.value)}
                            placeholder="Hi {{name}}, we wanted to follow up about your application for {{role}}..."
                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-purple-400"
                          />
                        </div>
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={step.is_ai_personalized}
                            onChange={e => updateStep(idx, 'is_ai_personalized', e.target.checked)}
                            className="rounded text-purple-600"
                          />
                          <span className="text-xs text-gray-600">AI-personalize this message</span>
                        </label>
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={addStep}
                    className="mt-4 flex items-center gap-2 text-sm text-purple-600 hover:text-purple-700 font-medium"
                  >
                    <Plus className="w-4 h-4" />
                    Add Step
                  </button>
                </div>
              )}

              {drawerStep === 3 && (
                <div>
                  <h3 className="font-semibold text-gray-700 mb-4">Timeline Preview</h3>
                  <div className="relative">
                    <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200"></div>
                    <div className="space-y-6">
                      <div className="flex items-center gap-4 ml-1">
                        <div className="w-6 h-6 rounded-full bg-green-500 border-2 border-white shadow flex items-center justify-center text-white text-xs">0</div>
                        <div className="bg-green-50 border border-green-100 rounded-lg px-3 py-2">
                          <div className="text-xs font-semibold text-green-700">Trigger: {TRIGGER_EVENTS.find(t => t.value === triggerEvent)?.label}</div>
                        </div>
                      </div>
                      {steps.map((step, idx) => (
                        <div key={idx} className="flex items-start gap-4 ml-1">
                          <div className="w-6 h-6 rounded-full bg-purple-600 border-2 border-white shadow flex items-center justify-center text-white text-xs flex-shrink-0">
                            {idx + 1}
                          </div>
                          <div className="bg-purple-50 border border-purple-100 rounded-lg px-3 py-2 flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-semibold text-purple-700">{CHANNEL_ICONS[step.channel]} {step.channel}</span>
                              <span className="text-xs text-gray-400">+{step.delay_hours}h after {idx === 0 ? 'trigger' : `step ${idx}`}</span>
                              {step.is_ai_personalized && <span className="text-xs bg-purple-100 text-purple-600 px-1.5 rounded">AI</span>}
                            </div>
                            <p className="text-xs text-gray-600 line-clamp-2">{step.message_template || 'No template set'}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Drawer footer */}
            <div className="border-t border-gray-100 px-6 py-4 flex gap-3 justify-end">
              {drawerStep > 1 && (
                <button
                  onClick={() => setDrawerStep(s => s - 1)}
                  className="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition"
                >
                  Back
                </button>
              )}
              {drawerStep < 3 ? (
                <button
                  onClick={() => setDrawerStep(s => s + 1)}
                  className="bg-purple-600 hover:bg-purple-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition"
                >
                  Next
                </button>
              ) : (
                <button
                  onClick={createSequence}
                  disabled={creating}
                  className="bg-purple-600 hover:bg-purple-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
                >
                  {creating ? 'Creating...' : 'Create Sequence'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default DripSequenceBuilder
