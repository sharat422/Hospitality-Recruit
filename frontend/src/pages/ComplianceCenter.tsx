import { apiClient } from '@/lib/api'
import { Check,FileCheck } from 'lucide-react'
import { useCallback,useEffect,useState } from 'react'

// --- Types ---
interface FairWorkweekRule {
  id: string
  jurisdiction: string
  rule_type: string
  rule_value: Record<string, unknown>
}

interface Violation {
  id: string
  violation_type: string
  severity: string
  jurisdiction: string
  shift_date?: string
  resolved: boolean
}

interface AuditEntry {
  id: string
  created_at: string
  actor_type: string
  action: string
  entity_type: string
  entity_id: string
}

interface CheckViolationResult {
  violations?: Array<{
    severity: string
    description: string
    penalty_risk?: string
  }>
}

// --- Constants ---
const JURISDICTIONS = ['NYC', 'SF', 'CHICAGO', 'SEATTLE', 'UK_NATIONAL']

const SEVERITY_COLORS: Record<string, string> = {
  WARNING: 'border-yellow-300 bg-yellow-50',
  FINE_RISK: 'border-orange-300 bg-orange-50',
  CRITICAL: 'border-red-300 bg-red-50',
}
const SEVERITY_TEXT: Record<string, string> = {
  WARNING: 'text-yellow-700',
  FINE_RISK: 'text-orange-700',
  CRITICAL: 'text-red-700',
}

const ACTOR_BADGE: Record<string, string> = {
  RECRUITER: 'bg-blue-100 text-blue-700',
  SYSTEM: 'bg-gray-100 text-gray-600',
  CANDIDATE: 'bg-purple-100 text-purple-700',
}

const VIOLATION_SEVERITY_BADGE: Record<string, string> = {
  WARNING: 'bg-yellow-100 text-yellow-700',
  FINE_RISK: 'bg-orange-100 text-orange-700',
  CRITICAL: 'bg-red-100 text-red-700',
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500)
    return () => clearTimeout(t)
  }, [onClose])
  return (
    <div className="fixed bottom-6 right-6 z-50 bg-purple-700 text-white px-5 py-3 rounded-xl shadow-lg text-sm flex items-center gap-3">
      <Check className="w-4 h-4 flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}

// ============ FAIR WORKWEEK TAB ============
function FairWorkweekTab() {
  const [rules, setRules] = useState<FairWorkweekRule[]>([])
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState('')

  // Check form
  const [jurisdiction, setJurisdiction] = useState('NYC')
  const [newShiftStart, setNewShiftStart] = useState('')
  const [newShiftEnd, setNewShiftEnd] = useState('')
  const [publishedAt, setPublishedAt] = useState('')
  const [lastShiftEnd, setLastShiftEnd] = useState('')
  const [checkResult, setCheckResult] = useState<CheckViolationResult | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      try {
        const res = await apiClient.get('/compliance/fair-workweek/rules')
        setRules(res.data || [])
      } catch {
        console.error('Failed to fetch rules')
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [])

  const handleCheck = async () => {
    setChecking(true)
    setCheckResult(null)
    try {
      const body: Record<string, string> = {
        jurisdiction,
        new_shift_start: newShiftStart,
        new_shift_end: newShiftEnd,
        published_at: publishedAt,
      }
      if (lastShiftEnd) body.last_shift_end = lastShiftEnd
      const res = await apiClient.post('/compliance/scheduling/check-violation', body)
      setCheckResult(res.data)
    } catch {
      setToast('Failed to check violation')
    } finally {
      setChecking(false)
    }
  }

  const rulesByJurisdiction = JURISDICTIONS.map((j) => ({
    jurisdiction: j,
    rules: rules.filter((r) => r.jurisdiction === j),
  }))

  return (
    <div className="space-y-6">
      {loading ? (
        <div className="text-center py-8 text-gray-400">Loading rules...</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {rulesByJurisdiction.map(({ jurisdiction: j, rules: jRules }) => (
            <div key={j} className="bg-white rounded-xl border border-gray-200 p-4">
              <h3 className="font-semibold text-gray-900 mb-3">{j}</h3>
              {jRules.length === 0 ? (
                <p className="text-xs text-gray-400">No rules configured</p>
              ) : (
                <div className="space-y-2">
                  {jRules.map((r) => {
                    const val = r.rule_value as Record<string, unknown>
                    return (
                      <div key={r.id} className="text-xs bg-gray-50 rounded p-2">
                        <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">
                          {r.rule_type}
                        </span>
                        {val.notice_days !== undefined && (
                          <p className="mt-1 text-gray-600">Notice: {String(val.notice_days)} days</p>
                        )}
                        {val.penalty !== undefined && (
                          <p className="text-gray-600">Penalty: {String(val.penalty)}</p>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Check New Shift form */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h3 className="font-semibold text-gray-900 mb-4">Check New Shift for Violations</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Jurisdiction</label>
            <select
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              {JURISDICTIONS.map((j) => <option key={j} value={j}>{j}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">New Shift Start</label>
            <input
              type="datetime-local"
              value={newShiftStart}
              onChange={(e) => setNewShiftStart(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">New Shift End</label>
            <input
              type="datetime-local"
              value={newShiftEnd}
              onChange={(e) => setNewShiftEnd(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Published At</label>
            <input
              type="datetime-local"
              value={publishedAt}
              onChange={(e) => setPublishedAt(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Last Shift End (optional)</label>
            <input
              type="datetime-local"
              value={lastShiftEnd}
              onChange={(e) => setLastShiftEnd(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
        </div>
        <button
          onClick={handleCheck}
          disabled={checking || !newShiftStart || !newShiftEnd || !publishedAt}
          className="mt-4 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition"
        >
          {checking ? 'Checking...' : 'Check Violations'}
        </button>

        {checkResult && (
          <div className="mt-4 space-y-3">
            {(!checkResult.violations || checkResult.violations.length === 0) ? (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
                No violations found for this shift.
              </div>
            ) : (
              checkResult.violations.map((v, i) => (
                <div
                  key={i}
                  className={`p-4 border rounded-lg ${SEVERITY_COLORS[v.severity] || 'bg-gray-50 border-gray-200'}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-bold uppercase ${SEVERITY_TEXT[v.severity] || 'text-gray-600'}`}>
                      {v.severity}
                    </span>
                  </div>
                  <p className="text-sm text-gray-800">{v.description}</p>
                  {v.penalty_risk && (
                    <p className="text-xs text-gray-500 mt-1">Penalty risk: {v.penalty_risk}</p>
                  )}
                </div>
              ))
            )}
          </div>
        )}
      </div>
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}

// ============ SCHEDULING VIOLATIONS TAB ============
function SchedulingViolationsTab() {
  const [violations, setViolations] = useState<Violation[]>([])
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState('')

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiClient.get('/compliance/scheduling/violations')
      setViolations(res.data || [])
    } catch {
      console.error('Failed to fetch violations')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const handleResolve = async (id: string, currentResolved: boolean) => {
    if (currentResolved) return
    try {
      await apiClient.patch(`/compliance/scheduling/violations/${id}/resolve`)
      setToast('Violation resolved')
      fetch()
    } catch {
      setToast('Failed to resolve')
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {loading ? (
        <div className="p-8 text-center text-gray-400">Loading...</div>
      ) : violations.length === 0 ? (
        <div className="p-8 text-center text-gray-400">No violations found</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="px-4 py-3 text-left">Violation Type</th>
                <th className="px-4 py-3 text-left">Severity</th>
                <th className="px-4 py-3 text-left">Jurisdiction</th>
                <th className="px-4 py-3 text-left">Shift Date</th>
                <th className="px-4 py-3 text-left">Resolved</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {violations.map((v) => (
                <tr key={v.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-medium">
                      {v.violation_type}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${VIOLATION_SEVERITY_BADGE[v.severity] || 'bg-gray-100 text-gray-700'}`}>
                      {v.severity}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{v.jurisdiction}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {v.shift_date ? new Date(v.shift_date).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleResolve(v.id, v.resolved)}
                      className={`text-xs px-3 py-1 rounded-full font-medium transition ${
                        v.resolved
                          ? 'bg-green-100 text-green-700 cursor-default'
                          : 'bg-gray-100 text-gray-700 hover:bg-green-50 hover:text-green-700'
                      }`}
                    >
                      {v.resolved ? 'Resolved' : 'Mark Resolved'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {toast && <Toast message={toast} onClose={() => setToast('')} />}
    </div>
  )
}

// ============ AUDIT LOG TAB ============
function AuditLogTab() {
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [entityFilter, setEntityFilter] = useState('')

  useEffect(() => {
    const fetch = async () => {
      setLoading(true)
      try {
        const res = await apiClient.get('/compliance/audit-log?limit=100')
        setEntries(res.data || [])
      } catch {
        console.error('Failed to fetch audit log')
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [])

  const entityTypes = Array.from(new Set(entries.map((e) => e.entity_type))).filter(Boolean)

  const filtered = entityFilter
    ? entries.filter((e) => e.entity_type === entityFilter)
    : entries

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <select
          value={entityFilter}
          onChange={(e) => setEntityFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
        >
          <option value="">All entity types</option>
          {entityTypes.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-400">No audit log entries</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">Time</th>
                  <th className="px-4 py-3 text-left">Actor</th>
                  <th className="px-4 py-3 text-left">Action</th>
                  <th className="px-4 py-3 text-left">Entity Type</th>
                  <th className="px-4 py-3 text-left">Entity ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filtered.map((e) => (
                  <tr key={e.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {new Date(e.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${ACTOR_BADGE[e.actor_type] || 'bg-gray-100 text-gray-600'}`}>
                        {e.actor_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{e.action}</td>
                    <td className="px-4 py-3 text-gray-600">{e.entity_type}</td>
                    <td className="px-4 py-3 font-mono text-gray-500 text-xs">
                      {e.entity_id ? e.entity_id.slice(0, 12) + '...' : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ============ MAIN PAGE ============
type Tab = 'fairworkweek' | 'violations' | 'audit'

export default function ComplianceCenter() {
  const [tab, setTab] = useState<Tab>('fairworkweek')

  const tabs: { key: Tab; label: string }[] = [
    { key: 'fairworkweek', label: 'Fair Workweek' },
    { key: 'violations', label: 'Scheduling Violations' },
    { key: 'audit', label: 'Audit Log' },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <FileCheck className="w-6 h-6 text-purple-600" />
        <h1 className="text-2xl font-bold text-gray-900">Compliance Center</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition -mb-px ${
              tab === t.key
                ? 'border-purple-600 text-purple-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'fairworkweek' && <FairWorkweekTab />}
      {tab === 'violations' && <SchedulingViolationsTab />}
      {tab === 'audit' && <AuditLogTab />}
    </div>
  )
}
