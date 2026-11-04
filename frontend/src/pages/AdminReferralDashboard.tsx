/**
 * AdminReferralDashboard
 *
 * Three-tab admin panel:
 *   Overview    — Stats grid + pending 90-day payouts table with Pay-Now button
 *   All Referrals — Filterable, paginated table
 *   Campaigns   — Create festive campaigns (Diwali / Eid / Holi / Onam / Pongal / Christmas / New Year)
 *
 * ₹ INR formatting throughout.
 */

import { apiClient } from '@/lib/api'
import {
AlertCircle,
BadgeCheck,
Calendar,
Check,
CheckCircle,
ChevronLeft,ChevronRight,
Clock,
Filter,
IndianRupee,
Loader2,
MessageSquare,
PlusCircle,
RefreshCw,
TrendingUp,
Users,
Zap
} from 'lucide-react'
import React,{ useCallback,useEffect,useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface Stats {
  total_referrals: number
  hired_count: number
  pending_eligible_bonuses: number
  paid_bonuses: number
  whatsapp_shares: number
  grand_total_paid_inr: number
  formatted_grand_total: string
  formatted_reward_paid: string
  formatted_bonus_paid: string
}

interface PendingPayout {
  id: string
  referral_code: string
  referrer_email: string
  referrer_id: string
  candidate_email: string | null
  hire_date: string
  retention_bonus_amount: number
  formatted_bonus: string
  days_elapsed: number | null
  bonus_paid_at: string | null
}

interface ReferralRow {
  id: string
  referral_code: string
  referrer_email: string
  candidate_email: string | null
  status: string
  reward_amount: number
  reward_status: string
  whatsapp_shared: boolean
  hire_date: string | null
  bonus_paid_at: string | null
  retention_bonus_amount: number
  retention_bonus_status: string
  campaign_id: string | null
  created_at: string
}

interface Campaign {
  id: string; name: string; festival_name: string
  start_date: string; end_date: string
  bonus_multiplier: number; bonus_flat: number
  banner_text: string; banner_color: string; is_active: boolean
}

// ─────────────────────────────────────────────────────────────────────────────
// INR formatting
// ─────────────────────────────────────────────────────────────────────────────

function fmtINR(n: number): string {
  if (!n) return '₹0'
  const s = Math.floor(n).toString()
  if (s.length <= 3) return `₹${s}`
  const last3 = s.slice(-3)
  let rest = s.slice(0, -3)
  const groups: string[] = []
  while (rest.length > 2) { groups.unshift(rest.slice(-2)); rest = rest.slice(0, -2) }
  if (rest) groups.unshift(rest)
  return `₹${groups.join(',')},${last3}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Festival presets (auto-fill campaign form)
// ─────────────────────────────────────────────────────────────────────────────

const FESTIVAL_PRESETS: Record<string, {
  emoji: string; color: string; multiplier: number; flat: number; text: string
}> = {
  DIWALI:   { emoji: '🪔', color: '#FF6B00', multiplier: 2.0,  flat: 1000, text: '🪔 Diwali Special! Earn 2x rewards + ₹1,000 bonus on every hire!' },
  EID:      { emoji: '🌙', color: '#10B981', multiplier: 1.5,  flat: 500,  text: '🌙 Eid Mubarak! 1.5x referral bonuses this Eid!' },
  HOLI:     { emoji: '🎨', color: '#EC4899', multiplier: 1.75, flat: 750,  text: '🎨 Holi Hiring Fest! 1.75x rewards on all hires!' },
  ONAM:     { emoji: '🌸', color: '#F59E0B', multiplier: 1.75, flat: 750,  text: '🌸 Onam Special! 1.75x rewards + ₹750 bonus!' },
  PONGAL:   { emoji: '🌾', color: '#16A34A', multiplier: 1.5,  flat: 500,  text: '🌾 Pongal Harvest! 1.5x rewards + ₹500 bonus — Pongalo Pongal!' },
  CHRISTMAS:{ emoji: '🎄', color: '#DC2626', multiplier: 1.5,  flat: 500,  text: '🎄 Christmas Bonanza! 1.5x referral rewards!' },
  NEW_YEAR: { emoji: '🎆', color: '#4F46E5', multiplier: 1.5,  flat: 500,  text: '🎆 New Year, New Hires! 1.5x rewards + ₹500 bonus!' },
}

const STATUS_OPTIONS = ['', 'PENDING', 'APPLIED', 'SHORTLISTED', 'HIRED', 'REWARDED', 'BONUS_PAID']
const REWARD_STATUS_OPTIONS = ['', 'NOT_EARNED', 'EARNED', 'PAID']

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, icon, color,
}: { label: string; value: string | number; sub?: string; icon: React.ReactNode; color: string }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 flex items-start gap-4">
      <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-gray-900 leading-none">{value}</p>
        <p className="text-sm text-gray-600 mt-0.5">{label}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    PENDING:     'bg-gray-100 text-gray-600',
    APPLIED:     'bg-blue-100 text-blue-700',
    SHORTLISTED: 'bg-yellow-100 text-yellow-700',
    HIRED:       'bg-green-100 text-green-700',
    REWARDED:    'bg-purple-100 text-purple-700',
    BONUS_PAID:  'bg-emerald-100 text-emerald-700',
  }
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${map[status] ?? 'bg-gray-100 text-gray-500'}`}>
      {status}
    </span>
  )
}

function RewardBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    NOT_EARNED: 'text-gray-400',
    EARNED:     'text-green-600 font-semibold',
    PAID:       'text-purple-600 font-bold',
    FAILED:     'text-red-500',
  }
  return <span className={`text-xs ${map[status] ?? 'text-gray-400'}`}>{status.replace('_', ' ')}</span>
}

// ─────────────────────────────────────────────────────────────────────────────
// OverviewTab — stats + pending payouts
// ─────────────────────────────────────────────────────────────────────────────

function OverviewTab({
  stats, pendingPayouts, recentReferrals, onPayoutSuccess,
}: {
  stats: Stats | null
  pendingPayouts: PendingPayout[]
  recentReferrals: ReferralRow[]
  onPayoutSuccess: (id: string) => void
}) {
  const [payingId, setPayingId]   = useState<string | null>(null)
  const [paidIds, setPaidIds]     = useState<Set<string>>(new Set())
  const [error, setError]         = useState<string | null>(null)

  const triggerPayout = async (row: PendingPayout) => {
    setPayingId(row.id)
    setError(null)
    try {
      await apiClient.post('/referrals/trigger-upi-payout', { referral_id: row.id })
      setPaidIds(prev => new Set([...prev, row.id]))
      onPayoutSuccess(row.id)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message)
    } finally {
      setPayingId(null)
    }
  }

  return (
    <div className="space-y-6">
      {/* Stats grid */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          <StatCard label="Total Referrals" value={stats.total_referrals}
            icon={<Users className="w-5 h-5 text-blue-600" />} color="bg-blue-50" />
          <StatCard label="Hired" value={stats.hired_count}
            icon={<CheckCircle className="w-5 h-5 text-green-600" />} color="bg-green-50" />
          <StatCard label="Pending 90-Day Bonuses" value={stats.pending_eligible_bonuses}
            sub="eligible for payout"
            icon={<Clock className="w-5 h-5 text-amber-600" />} color="bg-amber-50" />
          <StatCard label="Paid Bonuses" value={stats.paid_bonuses}
            icon={<BadgeCheck className="w-5 h-5 text-purple-600" />} color="bg-purple-50" />
          <StatCard label="WhatsApp Shares" value={stats.whatsapp_shares}
            icon={<MessageSquare className="w-5 h-5 text-[#25D366]" />} color="bg-green-50" />
          <StatCard label="₹ Total Paid" value={stats.formatted_grand_total}
            sub={`Rewards: ${stats.formatted_reward_paid} · Bonuses: ${stats.formatted_bonus_paid}`}
            icon={<IndianRupee className="w-5 h-5 text-orange-600" />} color="bg-orange-50" />
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex items-center gap-2 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">×</button>
        </div>
      )}

      {/* Pending 90-day payouts */}
      <div className="bg-white rounded-2xl border border-amber-200 shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-amber-100 bg-amber-50">
          <Clock className="w-5 h-5 text-amber-600" />
          <h2 className="font-bold text-gray-800">Pending 90-Day Bonuses</h2>
          <span className="ml-auto text-xs bg-amber-200 text-amber-800 font-semibold px-2 py-0.5 rounded-full">
            {pendingPayouts.filter(p => !paidIds.has(p.id)).length} pending
          </span>
        </div>

        {pendingPayouts.length === 0 ? (
          <div className="py-10 text-center text-gray-400 text-sm">
            <CheckCircle className="w-8 h-8 mx-auto mb-2 text-green-300" />
            All 90-day bonuses have been paid! 🎉
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  {['Code', 'Referrer', 'Candidate', 'Hire Date', 'Days', 'Bonus', 'Action'].map(h => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {pendingPayouts.map(row => {
                  const paid    = paidIds.has(row.id)
                  const paying  = payingId === row.id
                  return (
                    <tr key={row.id} className={paid ? 'bg-green-50' : 'hover:bg-gray-50'}>
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{row.referral_code}</td>
                      <td className="px-4 py-3 text-gray-700 truncate max-w-[160px]">{row.referrer_email}</td>
                      <td className="px-4 py-3 text-gray-500 truncate max-w-[140px]">
                        {row.candidate_email ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                        {new Date(row.hire_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' })}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`font-bold ${(row.days_elapsed ?? 0) >= 90 ? 'text-green-600' : 'text-amber-600'}`}>
                          {row.days_elapsed ?? '?'}d
                        </span>
                      </td>
                      <td className="px-4 py-3 font-bold text-orange-600 whitespace-nowrap">
                        {fmtINR(row.retention_bonus_amount)}
                      </td>
                      <td className="px-4 py-3">
                        {paid ? (
                          <span className="flex items-center gap-1 text-green-600 text-xs font-semibold">
                            <Check className="w-4 h-4" /> Paid
                          </span>
                        ) : (
                          <button
                            onClick={() => triggerPayout(row)}
                            disabled={!!payingId}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white text-xs font-semibold rounded-lg transition active:scale-95"
                          >
                            {paying
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <IndianRupee className="w-3.5 h-3.5" />}
                            {paying ? 'Paying…' : 'Pay Now'}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent referrals */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100">
          <TrendingUp className="w-5 h-5 text-orange-500" />
          <h2 className="font-bold text-gray-800">Recent Referrals</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                {['Code', 'Referrer', 'Candidate', 'Status', 'Reward', 'WA', 'Date'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {recentReferrals.map(r => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{r.referral_code}</td>
                  <td className="px-4 py-3 text-gray-700 truncate max-w-[160px]">{r.referrer_email}</td>
                  <td className="px-4 py-3 text-gray-500 truncate max-w-[140px]">{r.candidate_email ?? '—'}</td>
                  <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                  <td className="px-4 py-3 font-medium text-gray-800">{fmtINR(r.reward_amount)}</td>
                  <td className="px-4 py-3">
                    {r.whatsapp_shared
                      ? <span className="text-[#25D366] text-lg">✓</span>
                      : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">
                    {new Date(r.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// AllReferralsTab — filters + paginated table
// ─────────────────────────────────────────────────────────────────────────────

function AllReferralsTab({ campaigns }: { campaigns: Campaign[] }) {
  const [rows, setRows]       = useState<ReferralRow[]>([])
  const [total, setTotal]     = useState(0)
  const [pages, setPages]     = useState(1)
  const [page, setPage]       = useState(1)
  const [loading, setLoading] = useState(false)

  const [filters, setFilters] = useState({
    status: '', reward_status: '', campaign_id: '', date_from: '', date_to: '',
  })
  const [applied, setApplied] = useState(filters)

  const fetchPage = useCallback(async (pg: number, f: typeof filters) => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(pg), limit: '25' })
      if (f.status)       params.set('status', f.status)
      if (f.reward_status) params.set('reward_status', f.reward_status)
      if (f.campaign_id)  params.set('campaign_id', f.campaign_id)
      if (f.date_from)    params.set('date_from', f.date_from)
      if (f.date_to)      params.set('date_to', f.date_to)
      const r = await apiClient.get(`/admin-referrals/referrals?${params}`)
      setRows(r.data.referrals)
      setTotal(r.data.total)
      setPages(r.data.pages)
    } catch {
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchPage(1, applied) }, [])

  const applyFilters = () => {
    setApplied(filters)
    setPage(1)
    fetchPage(1, filters)
  }
  const changePage = (pg: number) => {
    setPage(pg)
    fetchPage(pg, applied)
  }
  const resetFilters = () => {
    const empty = { status: '', reward_status: '', campaign_id: '', date_from: '', date_to: '' }
    setFilters(empty)
    setApplied(empty)
    setPage(1)
    fetchPage(1, empty)
  }

  const inp = "border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white"

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="w-4 h-4 text-orange-500" />
          <h3 className="font-semibold text-gray-700 text-sm">Filters</h3>
          <button onClick={resetFilters} className="ml-auto flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700">
            <RefreshCw className="w-3.5 h-3.5" /> Reset
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <div>
            <label className="text-xs text-gray-500 font-medium mb-1 block">Status</label>
            <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))} className={inp}>
              {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s || 'All Statuses'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 font-medium mb-1 block">Reward Status</label>
            <select value={filters.reward_status} onChange={e => setFilters(f => ({ ...f, reward_status: e.target.value }))} className={inp}>
              {REWARD_STATUS_OPTIONS.map(s => <option key={s} value={s}>{s || 'All'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 font-medium mb-1 block">Campaign</label>
            <select value={filters.campaign_id} onChange={e => setFilters(f => ({ ...f, campaign_id: e.target.value }))} className={inp}>
              <option value="">All Campaigns</option>
              {campaigns.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 font-medium mb-1 block">From Date</label>
            <input type="date" value={filters.date_from} onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))} className={inp} />
          </div>
          <div>
            <label className="text-xs text-gray-500 font-medium mb-1 block">To Date</label>
            <input type="date" value={filters.date_to} onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))} className={inp} />
          </div>
        </div>
        <button
          onClick={applyFilters}
          className="mt-3 px-5 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold rounded-lg transition"
        >
          Apply Filters
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-gray-100">
          <span className="text-sm font-semibold text-gray-700">{total.toLocaleString()} referrals</span>
          {loading && <Loader2 className="w-4 h-4 animate-spin text-orange-500 ml-1" />}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                {['Code', 'Referrer', 'Candidate', 'Status', 'Reward', 'Reward Status', 'Bonus', 'WA', 'Created'].map(h => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {rows.length === 0 && !loading ? (
                <tr>
                  <td colSpan={9} className="px-4 py-10 text-center text-gray-400">
                    No referrals match the current filters.
                  </td>
                </tr>
              ) : rows.map(r => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600 whitespace-nowrap">{r.referral_code}</td>
                  <td className="px-4 py-3 text-gray-700 truncate max-w-[150px]">{r.referrer_email}</td>
                  <td className="px-4 py-3 text-gray-500 truncate max-w-[130px]">{r.candidate_email ?? '—'}</td>
                  <td className="px-4 py-3 whitespace-nowrap"><StatusBadge status={r.status} /></td>
                  <td className="px-4 py-3 font-medium text-gray-800 whitespace-nowrap">{fmtINR(r.reward_amount)}</td>
                  <td className="px-4 py-3 whitespace-nowrap"><RewardBadge status={r.reward_status} /></td>
                  <td className="px-4 py-3 text-orange-600 font-medium whitespace-nowrap">
                    {r.retention_bonus_amount > 0 ? fmtINR(r.retention_bonus_amount) : '—'}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {r.whatsapp_shared ? <span className="text-[#25D366]">✓</span> : <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                    {new Date(r.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-gray-100 bg-gray-50">
            <p className="text-xs text-gray-500">
              Page {page} of {pages} · {total.toLocaleString()} total
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => changePage(page - 1)}
                disabled={page === 1 || loading}
                className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-white transition"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => changePage(page + 1)}
                disabled={page === pages || loading}
                className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-white transition"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CampaignsTab — create form + active campaigns list
// ─────────────────────────────────────────────────────────────────────────────

const defaultYear = new Date().getFullYear()

const defaultForm = {
  festival_name:    'DIWALI',
  name:             `Diwali Dhamaka ${defaultYear}`,
  start_date:       '',
  end_date:         '',
  bonus_multiplier: '2.0',
  bonus_flat:       '1000',
  banner_text:      FESTIVAL_PRESETS['DIWALI'].text,
  banner_color:     FESTIVAL_PRESETS['DIWALI'].color,
  is_active:        true,
}

function CampaignsTab({ campaigns, onCreated }: { campaigns: Campaign[]; onCreated: () => void }) {
  const [form, setForm]       = useState(defaultForm)
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [formError, setFormError] = useState('')

  const onFestivalChange = (festival: string) => {
    const preset = FESTIVAL_PRESETS[festival] ?? FESTIVAL_PRESETS['DIWALI']
    const yr = defaultYear
    const names: Record<string, string> = {
      DIWALI: `Diwali Dhamaka ${yr}`, EID: `Eid Bonanza ${yr}`,
      HOLI: `Holi Hiring Fest ${yr}`, ONAM: `Onam Bonanza ${yr}`,
      PONGAL: `Pongal Harvest ${yr}`, CHRISTMAS: `Christmas Bonanza ${yr}`,
      NEW_YEAR: `New Year Bonanza ${yr}`,
    }
    setForm(f => ({
      ...f,
      festival_name:    festival,
      name:             names[festival] ?? `${festival} ${yr}`,
      bonus_multiplier: String(preset.multiplier),
      bonus_flat:       String(preset.flat),
      banner_text:      preset.text,
      banner_color:     preset.color,
    }))
  }

  const saveCampaign = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError('')
    if (!form.start_date || !form.end_date) {
      setFormError('Start and end dates are required.')
      return
    }
    if (new Date(form.end_date) <= new Date(form.start_date)) {
      setFormError('End date must be after start date.')
      return
    }
    setSaving(true)
    try {
      await apiClient.post('/admin-referrals/campaigns', {
        ...form,
        bonus_multiplier: parseFloat(form.bonus_multiplier),
        bonus_flat:       parseFloat(form.bonus_flat),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      onCreated()
    } catch (err: any) {
      setFormError(err.response?.data?.detail ?? 'Failed to create campaign.')
    } finally {
      setSaving(false)
    }
  }

  const inp = "w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400 bg-white"
  const preset = FESTIVAL_PRESETS[form.festival_name] ?? FESTIVAL_PRESETS['DIWALI']

  return (
    <div className="grid md:grid-cols-2 gap-6">
      {/* Create form */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100 bg-gradient-to-r from-orange-50 to-amber-50">
          <PlusCircle className="w-5 h-5 text-orange-500" />
          <h2 className="font-bold text-gray-800">Create Festive Campaign</h2>
        </div>

        <form onSubmit={saveCampaign} className="p-5 space-y-4">
          {/* Festival picker */}
          <div>
            <label className="text-xs font-semibold text-gray-600 mb-2 block">Festival</label>
            <div className="grid grid-cols-4 gap-2">
              {Object.entries(FESTIVAL_PRESETS).map(([code, p]) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => onFestivalChange(code)}
                  className={`flex flex-col items-center p-2 rounded-xl border-2 text-xs font-medium transition ${
                    form.festival_name === code
                      ? 'border-orange-400 bg-orange-50 text-orange-700'
                      : 'border-gray-200 hover:border-gray-300 text-gray-600'
                  }`}
                >
                  <span className="text-xl mb-0.5">{p.emoji}</span>
                  {code.replace('_', '\n')}
                </button>
              ))}
            </div>
          </div>

          {/* Preview banner */}
          <div
            className="rounded-xl p-3 text-white text-sm font-medium flex items-center gap-2"
            style={{ background: form.banner_color }}
          >
            <span className="text-2xl">{preset.emoji}</span>
            <p className="text-xs opacity-90 line-clamp-2">{form.banner_text}</p>
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Campaign Name</label>
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              required className={inp} placeholder="e.g. Diwali Dhamaka 2026" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Start Date</label>
              <input type="date" value={form.start_date}
                onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
                required className={inp} />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">End Date</label>
              <input type="date" value={form.end_date}
                onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))}
                required className={inp} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">
                Bonus Multiplier
                <span className="ml-1 font-bold text-orange-600">{form.bonus_multiplier}×</span>
              </label>
              <input
                type="range" min="1" max="3" step="0.25"
                value={form.bonus_multiplier}
                onChange={e => setForm(f => ({ ...f, bonus_multiplier: e.target.value }))}
                className="w-full accent-orange-500"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>1×</span><span>2×</span><span>3×</span>
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-600 mb-1 block">Flat Bonus (₹)</label>
              <input
                type="number" value={form.bonus_flat} min="0" step="100"
                onChange={e => setForm(f => ({ ...f, bonus_flat: e.target.value }))}
                className={inp} placeholder="e.g. 1000"
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-gray-600 mb-1 block">Banner Text</label>
            <textarea
              value={form.banner_text}
              onChange={e => setForm(f => ({ ...f, banner_text: e.target.value }))}
              rows={2} className={`${inp} resize-none`}
              placeholder="Banner message shown to employees…"
            />
          </div>

          <div className="flex items-center gap-2">
            <input type="checkbox" id="is_active" checked={form.is_active}
              onChange={e => setForm(f => ({ ...f, is_active: e.target.checked }))}
              className="accent-orange-500" />
            <label htmlFor="is_active" className="text-sm text-gray-700">Active immediately</label>
          </div>

          {formError && (
            <p className="text-sm text-red-600 flex items-center gap-1">
              <AlertCircle className="w-4 h-4" /> {formError}
            </p>
          )}

          <button
            type="submit" disabled={saving}
            className="w-full flex items-center justify-center gap-2 py-3 bg-orange-500 hover:bg-orange-600 disabled:opacity-60 text-white font-bold rounded-xl transition active:scale-[0.98]"
          >
            {saving
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Creating…</>
              : saved
                ? <><Check className="w-4 h-4" /> Campaign Created!</>
                : <><Zap className="w-4 h-4" /> Create Campaign</>}
          </button>
        </form>
      </div>

      {/* Existing campaigns */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-gray-100">
          <Calendar className="w-5 h-5 text-orange-500" />
          <h2 className="font-bold text-gray-800">All Campaigns</h2>
        </div>
        <div className="divide-y divide-gray-50 max-h-[600px] overflow-y-auto">
          {campaigns.length === 0 ? (
            <p className="px-5 py-8 text-center text-gray-400 text-sm">No campaigns yet.</p>
          ) : campaigns.map(c => {
            const now   = new Date()
            const start = new Date(c.start_date)
            const end   = new Date(c.end_date)
            const isActive  = c.is_active && now >= start && now <= end
            const isUpcoming = start > now
            const preset2 = FESTIVAL_PRESETS[c.festival_name] ?? { emoji: '🎉', color: '#6B7280' }
            return (
              <div key={c.id} className="px-5 py-4 flex items-start gap-3">
                <span className="text-2xl flex-shrink-0">{preset2.emoji}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold text-gray-800 text-sm">{c.name}</p>
                    {isActive && <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-semibold">LIVE</span>}
                    {isUpcoming && <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">Upcoming</span>}
                    {!isActive && !isUpcoming && <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Ended</span>}
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {new Date(c.start_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                    {' – '}
                    {new Date(c.end_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' })}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs font-bold text-orange-600">{c.bonus_multiplier}×</span>
                    {c.bonus_flat > 0 && (
                      <span className="text-xs text-gray-500">+ {fmtINR(c.bonus_flat)}</span>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'overview',   label: 'Overview',      icon: <TrendingUp className="w-4 h-4" /> },
  { id: 'referrals',  label: 'All Referrals', icon: <Users className="w-4 h-4" /> },
  { id: 'campaigns',  label: 'Campaigns',     icon: <Zap className="w-4 h-4" /> },
]

export default function AdminReferralDashboard() {
  const [tab, setTab]           = useState('overview')
  const [loading, setLoading]   = useState(true)
  const [stats, setStats]       = useState<Stats | null>(null)
  const [pending, setPending]   = useState<PendingPayout[]>([])
  const [recent, setRecent]     = useState<ReferralRow[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])

  const loadDashboard = useCallback(async () => {
    try {
      const [dashRes, campsRes] = await Promise.all([
        apiClient.get('/admin-referrals/dashboard'),
        apiClient.get('/india-referrals/campaigns'),
      ])
      setStats(dashRes.data.stats)
      setPending(dashRes.data.pending_payouts ?? [])
      setRecent(dashRes.data.recent_referrals ?? [])
      setCampaigns(campsRes.data ?? [])
    } catch (err: any) {
      console.error('Dashboard load failed:', err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadDashboard() }, [loadDashboard])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="w-8 h-8 animate-spin text-orange-500" />
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Referral Admin Dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">Manage referrals, bonuses, and festive campaigns</p>
        </div>
        <button
          onClick={loadDashboard}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition"
        >
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-xl mb-6 w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
              tab === t.id ? 'bg-white text-orange-600 shadow-sm' : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <OverviewTab
          stats={stats}
          pendingPayouts={pending}
          recentReferrals={recent}
          onPayoutSuccess={(id) => setPending(prev => prev.filter(p => p.id !== id))}
        />
      )}
      {tab === 'referrals' && <AllReferralsTab campaigns={campaigns} />}
      {tab === 'campaigns' && (
        <CampaignsTab campaigns={campaigns} onCreated={() => { loadDashboard() }} />
      )}
    </div>
  )
}
