import { apiClient } from '@/lib/api'
import {
AlertTriangle,
BarChart2,CalendarDays,
CheckCircle2,
CreditCard,
MessageSquare,
Phone,
RefreshCw,ShieldOff,
Users,
WifiOff,
XCircle,
} from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface DashStats {
  total_whatsapp_users:  number
  unverified_users:      number
  leave_pending:         number
  leave_total:           number
  complaints_open:       number
  complaints_total:      number
  anon_complaints:       number
  payslips_this_month:   number
  payslip_req_pending:   number
  payslip_req_fulfilled: number
  payslip_req_not_found: number
}

interface CommandsToday {
  LEAVE:     number; PAYSLIP:   number; SHIFT:    number
  BALANCE:   number; COMPLAINT: number; CAREER:   number
  HELP:      number; UNKNOWN:   number; total:    number
}

interface FailedMsg  { phone: string; body: string; created_at: string }
interface Unreg      { phone: string; attempts: number; last_attempt: string }

interface DashData {
  stats:           DashStats
  commands_today:  CommandsToday
  failed_today:    number
  failed_messages: FailedMsg[]
  unregistered:    Unreg[]
}

interface LeaveReq {
  id: string; employee_id: string; leave_date: string
  leave_type: string; reason: string; status: string
  ticket_number: string; created_at: string
}

interface PayslipReq {
  id: string; employee_id: string; requested_month: number
  requested_year: number; status: string; created_at: string
}

interface Complaint {
  id: string; ticket_number: string; category: string; severity: string
  status: string; reporter_display: string; is_anonymous: boolean
  complaint_text: string; sla_status: string; created_at: string
}

// ─────────────────────────────────────────────────────────────────────────────
// Helper components
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, icon, color = 'purple',
}: {
  label: string; value: string | number; sub?: string
  icon: React.ReactNode; color?: string
}) {
  const cls: Record<string, string> = {
    purple: 'ring-purple-100 bg-purple-50',
    green:  'ring-green-100  bg-green-50',
    blue:   'ring-blue-100   bg-blue-50',
    orange: 'ring-orange-100 bg-orange-50',
    red:    'ring-red-100    bg-red-50',
    amber:  'ring-amber-100  bg-amber-50',
    pink:   'ring-pink-100   bg-pink-50',
    gray:   'ring-gray-100   bg-gray-50',
  }
  return (
    <div className={`rounded-2xl border ring-1 ${cls[color] ?? cls.purple} p-5`}>
      <div className="flex items-center gap-2 mb-2 text-gray-500">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  )
}

function SectionCard({
  title, icon, children,
}: {
  title: string; icon: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <h3 className="font-bold text-gray-800 mb-4 flex items-center gap-2">
        {icon}{title}
      </h3>
      {children}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    PENDING:     'bg-amber-100  text-amber-700',
    APPROVED:    'bg-green-100  text-green-700',
    REJECTED:    'bg-red-100    text-red-700',
    CANCELLED:   'bg-gray-100   text-gray-600',
    FULFILLED:   'bg-green-100  text-green-700',
    NOT_FOUND:   'bg-orange-100 text-orange-700',
    ERROR:       'bg-red-100    text-red-700',
    OPEN:        'bg-amber-100  text-amber-700',
    UNDER_REVIEW:'bg-blue-100   text-blue-700',
    RESOLVED:    'bg-green-100  text-green-700',
    CLOSED:      'bg-gray-100   text-gray-600',
    ESCALATED:   'bg-red-100    text-red-700',
  }
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cfg[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function SeverityDot({ severity }: { severity: string }) {
  const col: Record<string, string> = {
    CRITICAL: 'bg-red-500',
    HIGH:     'bg-orange-400',
    MEDIUM:   'bg-amber-400',
    LOW:      'bg-green-400',
  }
  return (
    <span className="flex items-center gap-1">
      <span className={`inline-block w-2 h-2 rounded-full ${col[severity] ?? 'bg-gray-400'}`} />
      <span className="text-xs text-gray-600">{severity}</span>
    </span>
  )
}

function SlaChip({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    met:      'bg-green-50  text-green-700',
    on_track: 'bg-blue-50   text-blue-700',
    at_risk:  'bg-amber-50  text-amber-700',
    breached: 'bg-red-50    text-red-700',
  }
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${cfg[status] ?? ''}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

/** Horizontal bar showing today's command breakdown */
function CommandBar({
  cmd, count, total, color,
}: {
  cmd: string; count: number; total: number; color: string
}) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  const bar: Record<string, string> = {
    purple: 'bg-purple-400',
    blue:   'bg-blue-400',
    green:  'bg-green-400',
    orange: 'bg-orange-400',
    pink:   'bg-pink-400',
    amber:  'bg-amber-400',
    teal:   'bg-teal-400',
    red:    'bg-red-400',
  }
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-mono text-gray-500 w-20 shrink-0">{cmd}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-2">
        <div
          className={`${bar[color] ?? 'bg-purple-400'} h-2 rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-bold text-gray-700 w-8 text-right">{count}</span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main dashboard
// ─────────────────────────────────────────────────────────────────────────────

export function WhatsAppBotDashboard() {
  const [dash,     setDash]     = useState<DashData | null>(null)
  const [leaves,   setLeaves]   = useState<LeaveReq[]>([])
  const [payslips, setPayslips] = useState<PayslipReq[]>([])
  const [comps,    setComps]    = useState<Complaint[]>([])
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState('')

  // Per-row action state for leave approve/reject
  const [acting, setActing] = useState<Record<string, boolean>>({})

  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [d, l, p, c] = await Promise.all([
        apiClient.get('/hr-bot/dashboard'),
        apiClient.get('/hr-bot/leave-requests?limit=20'),
        apiClient.get('/hr-bot/payslip-requests?limit=20'),
        apiClient.get('/hr-bot/complaints?limit=20'),
      ])
      setDash(d.data)
      setLeaves(l.data || [])
      setPayslips(p.data || [])
      setComps(c.data || [])
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Approve / reject leave
  const handleLeave = async (id: string, action: 'approve' | 'reject') => {
    setActing(a => ({ ...a, [id]: true }))
    try {
      if (action === 'approve') {
        await apiClient.patch(`/hr-bot/leave-requests/${id}/approve`, { notes: '' })
      } else {
        const reason = window.prompt('Rejection reason:') || 'Declined by HR'
        await apiClient.patch(`/hr-bot/leave-requests/${id}/reject`, { rejection_reason: reason })
      }
      // Refresh leave list
      const { data } = await apiClient.get('/hr-bot/leave-requests?limit=20')
      setLeaves(data || [])
    } catch (e: any) {
      alert(e.response?.data?.detail ?? `${action} failed`)
    } finally {
      setActing(a => ({ ...a, [id]: false }))
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <RefreshCw className="w-5 h-5 animate-spin mr-2" />
        Loading bot dashboard…
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-100 rounded-2xl px-5 py-4 text-red-700 text-sm">
        <AlertTriangle className="w-4 h-4 inline mr-2" />{error}
        <button onClick={load} className="ml-3 underline">Retry</button>
      </div>
    )
  }

  const s  = dash!.stats
  const ct = dash!.commands_today
  const cmdTotal = ct.total || 1  // avoid division by zero

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">

      {/* ── Page header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <MessageSquare className="w-6 h-6 text-purple-600" />
            WhatsApp HR Bot
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Employee self-service analytics — today's activity
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-purple-700
                     bg-purple-50 hover:bg-purple-100 rounded-xl border border-purple-100 transition"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* ── Row 1: Stat cards ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-7 gap-3">
        {/* 1 — Total WhatsApp users */}
        <StatCard
          label="WhatsApp Users"
          value={s.total_whatsapp_users}
          sub={s.unverified_users > 0 ? `${s.unverified_users} unverified` : 'All verified'}
          icon={<Users className="w-4 h-4" />}
          color="green"
        />
        {/* 2 — Commands today */}
        <StatCard
          label="Commands Today"
          value={ct.total}
          sub={`${ct.UNKNOWN} unrecognised`}
          icon={<BarChart2 className="w-4 h-4" />}
          color="purple"
        />
        {/* 3 — Leave requests */}
        <StatCard
          label="Leave Pending"
          value={s.leave_pending}
          sub={`${s.leave_total} total`}
          icon={<CalendarDays className="w-4 h-4" />}
          color="blue"
        />
        {/* 4 — Payslip requests */}
        <StatCard
          label="Payslip Requests"
          value={s.payslip_req_pending}
          sub={`${s.payslip_req_fulfilled} fulfilled · ${s.payslip_req_not_found} not found`}
          icon={<CreditCard className="w-4 h-4" />}
          color="orange"
        />
        {/* 5 — Anonymous complaints */}
        <StatCard
          label="Anon Complaints"
          value={s.anon_complaints}
          sub={`${s.complaints_open} open of ${s.complaints_total}`}
          icon={<ShieldOff className="w-4 h-4" />}
          color="pink"
        />
        {/* 6 — Failed / unrecognised */}
        <StatCard
          label="Failed Commands"
          value={dash!.failed_today}
          sub="today"
          icon={<XCircle className="w-4 h-4" />}
          color="red"
        />
        {/* 7 — Verification issues */}
        <StatCard
          label="Unverified Users"
          value={s.unverified_users}
          sub={dash!.unregistered.length > 0
            ? `+${dash!.unregistered.length} unknown numbers`
            : 'No unknown numbers'}
          icon={<WifiOff className="w-4 h-4" />}
          color="amber"
        />
      </div>

      {/* ── Row 2: Command breakdown + Verification issues ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* 2 — Commands breakdown (today) */}
        <SectionCard
          title="Commands Breakdown — Today"
          icon={<BarChart2 className="w-4 h-4 text-purple-500" />}
        >
          <div className="space-y-3">
            {(
              [
                { cmd: 'LEAVE',     count: ct.LEAVE,     color: 'blue'   },
                { cmd: 'PAYSLIP',   count: ct.PAYSLIP,   color: 'orange' },
                { cmd: 'SHIFT',     count: ct.SHIFT,     color: 'green'  },
                { cmd: 'BALANCE',   count: ct.BALANCE,   color: 'teal'   },
                { cmd: 'COMPLAINT', count: ct.COMPLAINT, color: 'pink'   },
                { cmd: 'CAREER',    count: ct.CAREER,    color: 'purple' },
                { cmd: 'HELP',      count: ct.HELP,      color: 'amber'  },
                { cmd: 'UNKNOWN',   count: ct.UNKNOWN,   color: 'red'    },
              ] as const
            ).map(({ cmd, count, color }) => (
              <CommandBar
                key={cmd}
                cmd={cmd}
                count={count}
                total={cmdTotal}
                color={color}
              />
            ))}
            <p className="text-xs text-gray-400 pt-1 text-right">
              Total: {ct.total} messages received today
            </p>
          </div>
        </SectionCard>

        {/* 7 — Employee verification issues */}
        <SectionCard
          title="Verification Issues"
          icon={<WifiOff className="w-4 h-4 text-amber-500" />}
        >
          {/* Unverified registered users */}
          {s.unverified_users > 0 && (
            <div className="mb-3 bg-amber-50 border border-amber-100 rounded-xl px-4 py-3">
              <p className="text-sm font-semibold text-amber-800 flex items-center gap-1">
                <AlertTriangle className="w-4 h-4" />
                {s.unverified_users} registered user{s.unverified_users !== 1 ? 's' : ''} not verified
              </p>
              <p className="text-xs text-amber-600 mt-0.5">
                These users messaged the bot but their phone hasn't been matched to an employee record.
              </p>
            </div>
          )}

          {/* Unregistered phone numbers */}
          {dash!.unregistered.length > 0 ? (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Unknown numbers (today)
              </p>
              {dash!.unregistered.map(u => (
                <div
                  key={u.phone}
                  className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <Phone className="w-3.5 h-3.5 text-gray-400" />
                    <span className="text-sm font-mono text-gray-700">{u.phone}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-red-600 font-semibold">
                      {u.attempts} attempt{u.attempts !== 1 ? 's' : ''}
                    </span>
                    <span className="text-xs text-gray-400">
                      {new Date(u.last_attempt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-gray-400">
              <CheckCircle2 className="w-8 h-8 mb-2 text-green-400" />
              <p className="text-sm">No unknown numbers today</p>
            </div>
          )}

          {/* Failed messages */}
          {dash!.failed_messages.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Unrecognised messages (today)
              </p>
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {dash!.failed_messages.map((m, i) => (
                  <div key={i} className="flex items-start gap-2 bg-red-50 rounded-lg px-3 py-2">
                    <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-mono text-gray-500">{m.phone}</p>
                      <p className="text-xs text-gray-700 truncate">"{m.body}"</p>
                    </div>
                    <span className="text-xs text-gray-400 shrink-0 ml-auto">
                      {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Row 3: Leave requests table ──────────────────────────────────── */}
      <SectionCard
        title="Leave Requests — from WhatsApp"
        icon={<CalendarDays className="w-4 h-4 text-blue-500" />}
      >
        {leaves.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-6">No leave requests yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-100">
                  <th className="pb-3 pr-4">Ticket</th>
                  <th className="pb-3 pr-4">Date</th>
                  <th className="pb-3 pr-4">Type</th>
                  <th className="pb-3 pr-4">Reason</th>
                  <th className="pb-3 pr-4">Status</th>
                  <th className="pb-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {leaves.map(lr => (
                  <tr key={lr.id} className="hover:bg-gray-50">
                    <td className="py-2.5 pr-4 font-mono text-xs text-purple-700">
                      {lr.ticket_number}
                    </td>
                    <td className="py-2.5 pr-4 text-gray-700 whitespace-nowrap">
                      {lr.leave_date}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-semibold">
                        {lr.leave_type}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-gray-600 max-w-[180px] truncate text-xs">
                      {lr.reason}
                    </td>
                    <td className="py-2.5 pr-4">
                      <StatusBadge status={lr.status} />
                    </td>
                    <td className="py-2.5">
                      {lr.status === 'PENDING' ? (
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => handleLeave(lr.id, 'approve')}
                            disabled={acting[lr.id]}
                            className="flex items-center gap-1 px-2 py-1 text-xs font-semibold
                                       text-green-700 bg-green-50 hover:bg-green-100 rounded-lg
                                       border border-green-100 transition disabled:opacity-50"
                          >
                            <CheckCircle2 className="w-3 h-3" /> Approve
                          </button>
                          <button
                            onClick={() => handleLeave(lr.id, 'reject')}
                            disabled={acting[lr.id]}
                            className="flex items-center gap-1 px-2 py-1 text-xs font-semibold
                                       text-red-700 bg-red-50 hover:bg-red-100 rounded-lg
                                       border border-red-100 transition disabled:opacity-50"
                          >
                            <XCircle className="w-3 h-3" /> Reject
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {/* ── Row 4: Payslip requests + Anonymous complaints ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* 4 — Payslip requests */}
        <SectionCard
          title="Payslip Requests"
          icon={<CreditCard className="w-4 h-4 text-orange-500" />}
        >
          {/* Summary chips */}
          <div className="flex gap-2 mb-4">
            {[
              { label: 'Pending',    value: s.payslip_req_pending,   cls: 'bg-amber-50  text-amber-700'  },
              { label: 'Fulfilled',  value: s.payslip_req_fulfilled,  cls: 'bg-green-50  text-green-700'  },
              { label: 'Not Found',  value: s.payslip_req_not_found,  cls: 'bg-orange-50 text-orange-700' },
            ].map(({ label, value, cls }) => (
              <div key={label} className={`flex-1 rounded-xl p-3 text-center ${cls}`}>
                <p className="text-lg font-bold">{value}</p>
                <p className="text-xs font-semibold">{label}</p>
              </div>
            ))}
          </div>

          {payslips.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-4">No payslip requests yet.</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {payslips.map(pr => (
                <div
                  key={pr.id}
                  className="flex items-center justify-between bg-gray-50 rounded-xl px-3 py-2"
                >
                  <div>
                    <p className="text-xs text-gray-500">
                      {monthName(pr.requested_month)} {pr.requested_year}
                    </p>
                    <p className="text-xs font-mono text-gray-400 truncate max-w-[120px]">
                      {pr.employee_id?.slice(0, 8)}…
                    </p>
                  </div>
                  <StatusBadge status={pr.status} />
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        {/* 5 — Anonymous complaints */}
        <SectionCard
          title="Complaints (Identity Masked)"
          icon={<ShieldOff className="w-4 h-4 text-pink-500" />}
        >
          {/* Note about masking */}
          <div className="mb-3 bg-blue-50 border border-blue-100 rounded-xl px-3 py-2 text-xs text-blue-700">
            <ShieldOff className="w-3.5 h-3.5 inline mr-1" />
            Anonymous reporters show as "Anonymous Reporter". Only HR Admin can reveal identity.
          </div>

          {comps.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-4">No complaints yet.</p>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {comps.map(c => (
                <div
                  key={c.id}
                  className="rounded-xl border border-gray-100 p-3 hover:border-gray-200 transition"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-purple-700 font-semibold">
                          {c.ticket_number}
                        </span>
                        {c.is_anonymous && (
                          <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">
                            🔒 Anon
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mb-1">{c.reporter_display}</p>
                      <p className="text-xs text-gray-700 line-clamp-2">{c.complaint_text}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <StatusBadge status={c.status} />
                      <SeverityDot severity={c.severity} />
                      <SlaChip status={c.sla_status} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                      {c.category}
                    </span>
                    <span className="text-xs text-gray-400 ml-auto">
                      {new Date(c.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

function monthName(m: number): string {
  return ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m] ?? String(m)
}
