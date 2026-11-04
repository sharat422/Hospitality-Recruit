/**
 * ReferralPortal — mobile-first India referral hub
 *
 * Features:
 *   Hindi / English toggle       persistent in localStorage
 *   Festive campaign banner       active campaign from API
 *   Employee stats card           summary from /my-referrals
 *   Prominent UPI card            save / edit UPI ID
 *   Referral status timeline      per-referral progress dots + bonus text
 *   WhatsApp share CTA            full-width green button + inline form
 *   Leaderboard                   ranked by hired count with ₹ totals
 */

import { apiClient } from '@/lib/api';
import {
AlertCircle,
Award,
BadgeCheck,
Calendar,
Check,
ChevronRight,
CreditCard,
Gift,
Globe,
IndianRupee,
Loader2,
Lock,
MessageSquare,
Sparkles,
Star,
TrendingUp,
Trophy,
Users
} from 'lucide-react';
import React,{ useCallback,useEffect,useState } from 'react';
import { Link } from 'react-router-dom';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface Campaign {
  id: string; name: string; festival_name: string
  bonus_multiplier: number; bonus_flat: number
  banner_text: string; banner_color: string
  start_date: string; end_date: string
}

interface ReferralRow {
  id: string; referral_code: string
  candidate_email: string | null; job_role_id: string
  status: string; reward_amount: number; reward_status: string
  whatsapp_shared: boolean; hire_date: string | null
  retention_bonus_amount: number; retention_bonus_status: string
  currency: string; created_at: string
}

interface Summary {
  total_referrals: number; applied_count: number
  hired_count: number; total_earned: number; total_paid: number
}


interface LeaderEntry {
  referrer_email: string; total_referrals: number
  hired_count: number; total_earned_inr: number; formatted_earned: string
}

interface BadgeCatalogEntry {
  name: string; name_en: string; name_hi: string
  description: string; description_hi: string
  icon: string; tier: 'BRONZE' | 'SILVER' | 'GOLD' | 'PLATINUM'
  milestone_type: 'hired_count' | 'whatsapp_count'; threshold: number
  reward_bonus: number; earned: boolean; earned_at: string | null
}

interface NextMilestone {
  badge_name: string; badge_name_en: string; icon: string
  tier: string; threshold: number; current: number
  progress_pct: number; reward_bonus: number
  milestone_type: 'hired_count' | 'whatsapp_count'
}

interface GamificationStatus {
  hired_count: number; whatsapp_count: number
  total_earned_inr: number; formatted_earned: string
  active_campaigns: Campaign[]; next_campaign: Campaign | null
  badges_catalog: BadgeCatalogEntry[]; badges_earned: unknown[]
  next_milestone: NextMilestone | null; newly_awarded: BadgeCatalogEntry[]
}

type Lang = 'en' | 'hi'

// ─────────────────────────────────────────────────────────────────────────────
// Bilingual strings
// ─────────────────────────────────────────────────────────────────────────────

const S = {
  en: {
    title: 'Referral Portal',
    sub: 'Refer friends. Earn in ₹. Get paid via UPI.',
    stats_referrals: 'Referrals',
    stats_hired: 'Hired',
    stats_earned: 'Earned',
    upi_heading: 'UPI Payment Details',
    upi_desc: 'Add your UPI ID to receive referral rewards instantly.',
    upi_placeholder: 'yourname@upi  or  9999@okaxis',
    upi_save: 'Save UPI ID',
    upi_saving: 'Saving…',
    upi_saved: 'Saved!',
    upi_verified: 'Verified ✓',
    upi_unverified: 'Not verified',
    my_referrals: 'My Referrals',
    no_referrals: 'No referrals yet.',
    no_referrals_cta: 'Create your first referral link →',
    share_heading: 'Share & Earn',
    share_sub: (reward: string) => `Invite a friend — earn ${reward} when they get hired.`,
    share_property: 'Hotel / Property name',
    share_btn: 'Share on WhatsApp',
    share_generating: 'Generating link…',
    leaderboard: 'Top Referrers',
    lb_name: 'Employee',
    lb_refs: 'Refs',
    lb_hired: 'Hired',
    lb_earned: 'Earned',
    days_remaining: (amt: string, d: number) => `₹${amt} via UPI in ${d} day${d !== 1 ? 's' : ''}`,
    days_eligible: (amt: string) => `₹${amt} bonus available now!`,
    bonus_paid: (amt: string) => `₹${amt} paid via UPI ✓`,
    s_pending: 'Pending',
    s_applied: 'Applied',
    s_shortlisted: 'Shortlisted',
    s_hired: 'Hired 🎉',
    s_rewarded: 'Rewarded',
    badges_heading:    'Your Badges',
    milestone_heading: 'Next Goal',
    milestone_hired:   'hires',
    milestone_shares:  'shares',
    milestone_bonus:   'bonus on unlock',
    upcoming_heading:  'Coming Soon',
    upcoming_in:       (d: number) => `in ${d} day${d !== 1 ? 's' : ''}`,
    all_done:          'All milestones complete! You are a Legend! 💎',
    lang_label:        'हिंदी',
  },
  hi: {
    title: 'रेफरल पोर्टल',
    sub: 'दोस्तों को Refer करें। ₹ में कमाएं। UPI पर पाएं।',
    stats_referrals: 'Referrals',
    stats_hired: 'Hired',
    stats_earned: 'कमाए',
    upi_heading: 'UPI पेमेंट Details',
    upi_desc: 'UPI ID डालें ताकि referral reward तुरंत मिले।',
    upi_placeholder: 'yourname@upi  या  9999@okaxis',
    upi_save: 'UPI ID सेव करें',
    upi_saving: 'सेव हो रहा है…',
    upi_saved: 'सेव हो गया!',
    upi_verified: 'Verified ✓',
    upi_unverified: 'Verify नहीं हुआ',
    my_referrals: 'मेरे Referrals',
    no_referrals: 'अभी कोई referral नहीं।',
    no_referrals_cta: 'पहला referral link बनाएं →',
    share_heading: 'Share करें और कमाएं',
    share_sub: (reward: string) => `दोस्त को invite करें — job मिलने पर ${reward} कमाएं।`,
    share_property: 'Hotel / Property का नाम',
    share_btn: 'WhatsApp पर Share करें',
    share_generating: 'Link बन रहा है…',
    leaderboard: 'Top Referrers',
    lb_name: 'Employee',
    lb_refs: 'Refs',
    lb_hired: 'Hired',
    lb_earned: 'कमाए',
    days_remaining: (amt: string, d: number) => `₹${amt} UPI पर मिलेगा ${d} दिन बाद`,
    days_eligible: (amt: string) => `₹${amt} bonus अभी मिलेगा!`,
    bonus_paid: (amt: string) => `₹${amt} UPI पर मिल गया ✓`,
    s_pending: 'Pending',
    s_applied: 'Apply हुआ',
    s_shortlisted: 'Shortlisted',
    s_hired: 'Hired 🎉',
    s_rewarded: 'Reward मिला',
    badges_heading:    'आपके बैज',
    milestone_heading: 'अगला लक्ष्य',
    milestone_hired:   'hire',
    milestone_shares:  'shares',
    milestone_bonus:   'unlock होने पर bonus',
    upcoming_heading:  'आने वाला campaign',
    upcoming_in:       (d: number) => `${d} दिन में शुरू`,
    all_done:          'सभी milestones पूरे! आप Legend हैं! 💎',
    lang_label:        'English',
  },
} as const

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const STAGES = ['PENDING', 'APPLIED', 'SHORTLISTED', 'HIRED', 'REWARDED'] as const
const STAGE_IDX: Record<string, number> = { PENDING: 0, APPLIED: 1, SHORTLISTED: 2, HIRED: 3, REWARDED: 4 }
const MEDALS = ['🥇', '🥈', '🥉']

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

function fmtINRNum(n: number): string {
  // returns just the number part without ₹ prefix for embedding in strings
  return fmtINR(n).slice(1)
}

function maskEmail(email: string): string {
  const local = email.split('@')[0]
  return local.length > 3 ? local.slice(0, 3) + '***' : local + '***'
}

function daysRemaining(hireDateStr: string): number {
  const hd = new Date(hireDateStr)
  const elapsed = Math.floor((Date.now() - hd.getTime()) / 86_400_000)
  return Math.max(0, 90 - elapsed)
}

function bonusText(ref: ReferralRow, lang: Lang): string | null {
  if (ref.retention_bonus_status === 'PAID') {
    return S[lang].bonus_paid(fmtINRNum(ref.retention_bonus_amount))
  }
  if (ref.status !== 'HIRED' || ref.retention_bonus_amount <= 0) return null
  const amt = fmtINRNum(ref.retention_bonus_amount)
  if (!ref.hire_date) return null
  const d = daysRemaining(ref.hire_date)
  return d > 0 ? S[lang].days_remaining(amt, d) : S[lang].days_eligible(amt)
}

function stageLabel(stage: string, lang: Lang): string {
  const s = S[lang]
  switch (stage) {
    case 'PENDING':     return s.s_pending
    case 'APPLIED':     return s.s_applied
    case 'SHORTLISTED': return s.s_shortlisted
    case 'HIRED':       return s.s_hired
    case 'REWARDED':    return s.s_rewarded
    default:            return stage
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// LanguageToggle
// ─────────────────────────────────────────────────────────────────────────────

function LanguageToggle({ lang, onToggle }: { lang: Lang; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-full text-sm font-medium text-gray-700 hover:bg-gray-50 shadow-sm transition active:scale-95"
    >
      <Globe className="w-3.5 h-3.5 text-orange-500" />
      {S[lang].lang_label}
    </button>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CampaignBannerSection
// ─────────────────────────────────────────────────────────────────────────────


// ─────────────────────────────────────────────────────────────────────────────
// StatsCard
// ─────────────────────────────────────────────────────────────────────────────

function StatsCard({ summary, lang }: { summary: Summary; lang: Lang }) {
  const s = S[lang]
  const stats = [
    { label: s.stats_referrals, value: summary.total_referrals, icon: <Users className="w-5 h-5 text-blue-500" />, bg: 'bg-blue-50' },
    { label: s.stats_hired,     value: summary.hired_count,     icon: <Star className="w-5 h-5 text-yellow-500" />, bg: 'bg-yellow-50' },
    { label: s.stats_earned,    value: fmtINR(summary.total_earned), icon: <IndianRupee className="w-5 h-5 text-green-600" />, bg: 'bg-green-50' },
  ]
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
      <div className="grid grid-cols-3 gap-3">
        {stats.map(st => (
          <div key={st.label} className={`${st.bg} rounded-xl p-3 text-center`}>
            <div className="flex justify-center mb-1">{st.icon}</div>
            <p className="font-bold text-gray-900 text-base leading-none">
              {typeof st.value === 'number' ? st.value : st.value}
            </p>
            <p className="text-xs text-gray-500 mt-1">{st.label}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// UPICard
// ─────────────────────────────────────────────────────────────────────────────

function UPICard({ lang }: { lang: Lang }) {
  const s = S[lang]
  const [upiId, setUpiId]     = useState('')
  const [isVerified, setVerified] = useState(false)
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get('/india-referrals/upi').then(r => {
      if (r.data.upi_details?.upi_id) {
        setUpiId(r.data.upi_details.upi_id)
        setVerified(r.data.upi_details.is_verified)
      }
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const save = async () => {
    if (!upiId.trim()) return
    setSaving(true)
    try {
      await apiClient.post('/india-referrals/upi', { upi_id: upiId.trim() })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-white rounded-2xl border-2 border-orange-100 shadow-sm overflow-hidden">
      {/* Header strip */}
      <div className="bg-gradient-to-r from-orange-500 to-orange-400 px-4 py-3 flex items-center gap-2">
        <CreditCard className="w-5 h-5 text-white" />
        <p className="font-bold text-white text-sm">{s.upi_heading}</p>
        {isVerified && (
          <span className="ml-auto flex items-center gap-1 text-xs font-semibold bg-white text-green-600 px-2 py-0.5 rounded-full">
            <BadgeCheck className="w-3.5 h-3.5" /> {s.upi_verified}
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        <p className="text-xs text-gray-500">{s.upi_desc}</p>

        {loading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="w-5 h-5 animate-spin text-orange-400" />
          </div>
        ) : (
          <>
            {/* UPI input — large touch target */}
            <div className="relative">
              <IndianRupee className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                value={upiId}
                onChange={e => { setUpiId(e.target.value); setVerified(false) }}
                placeholder={s.upi_placeholder}
                className="w-full pl-9 pr-4 py-3.5 text-sm border-2 border-gray-200 rounded-xl focus:outline-none focus:border-orange-400 transition font-mono bg-gray-50 placeholder:font-sans placeholder:text-gray-400"
              />
              {isVerified && (
                <BadgeCheck className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-green-500" />
              )}
            </div>

            {!isVerified && upiId && (
              <p className="text-xs text-amber-600 flex items-center gap-1">
                <AlertCircle className="w-3.5 h-3.5" /> {s.upi_unverified}
              </p>
            )}

            <button
              onClick={save}
              disabled={saving || !upiId.trim()}
              className="w-full flex items-center justify-center gap-2 py-3.5 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white rounded-xl font-bold text-sm transition active:scale-[0.98]"
            >
              {saving
                ? <><Loader2 className="w-4 h-4 animate-spin" /> {s.upi_saving}</>
                : saved
                  ? <><Check className="w-4 h-4" /> {s.upi_saved}</>
                  : <><CreditCard className="w-4 h-4" /> {s.upi_save}</>}
            </button>
          </>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// StatusDots — horizontal progress timeline
// ─────────────────────────────────────────────────────────────────────────────

function StatusDots({ status, lang }: { status: string; lang: Lang }) {
  const current = STAGE_IDX[status] ?? 0
  return (
    <div className="mt-3 mb-1">
      {/* dots + connecting lines */}
      <div className="flex items-center">
        {STAGES.map((st, i) => {
          const active = i <= current
          const isCur  = i === current
          return (
            <React.Fragment key={st}>
              <div className={`w-3 h-3 rounded-full flex-shrink-0 transition-colors duration-300 ${
                active ? 'bg-green-500' : 'bg-gray-200'
              } ${isCur ? 'ring-2 ring-green-200 ring-offset-1 scale-125' : ''}`} />
              {i < STAGES.length - 1 && (
                <div className={`flex-1 h-0.5 transition-colors duration-300 ${i < current ? 'bg-green-500' : 'bg-gray-200'}`} />
              )}
            </React.Fragment>
          )
        })}
      </div>
      {/* labels */}
      <div className="flex justify-between mt-1.5">
        {STAGES.map((st, i) => (
          <p key={st} className={`text-center text-[10px] leading-tight w-12 -mx-1 ${
            i === current ? 'text-green-600 font-semibold' : 'text-gray-400'
          }`} style={{ fontSize: '9px' }}>
            {stageLabel(st, lang)}
          </p>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ReferralTimelineSection
// ─────────────────────────────────────────────────────────────────────────────

function ReferralTimelineSection({ referrals, lang }: { referrals: ReferralRow[]; lang: Lang }) {
  const s = S[lang]

  if (referrals.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 text-center">
        <Gift className="w-10 h-10 text-gray-200 mx-auto mb-3" />
        <p className="text-sm text-gray-500">{s.no_referrals}</p>
        <Link to="/india-referrals" className="mt-2 inline-flex items-center gap-1 text-sm text-orange-500 font-medium">
          {s.no_referrals_cta} <ChevronRight className="w-4 h-4" />
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {referrals.map(ref => {
        const bonus = bonusText(ref, lang)
        return (
          <div key={ref.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-xs font-mono text-gray-500">{ref.referral_code}</p>
                {ref.candidate_email && (
                  <p className="text-sm font-medium text-gray-800 truncate mt-0.5">
                    {ref.candidate_email.replace(/(.{3}).*@/, '$1***@')}
                  </p>
                )}
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-base font-bold text-green-600">{fmtINR(ref.reward_amount)}</p>
                <p className="text-xs text-gray-400">{ref.reward_status.replace('_', ' ')}</p>
              </div>
            </div>

            <StatusDots status={ref.status} lang={lang} />

            {/* Bonus countdown text */}
            {bonus && (
              <div className={`mt-3 text-xs font-semibold px-3 py-2 rounded-lg flex items-center gap-2 ${
                ref.retention_bonus_status === 'PAID'
                  ? 'bg-purple-50 text-purple-700'
                  : daysRemaining(ref.hire_date ?? '') === 0
                    ? 'bg-green-50 text-green-700'
                    : 'bg-amber-50 text-amber-700'
              }`}>
                <IndianRupee className="w-3.5 h-3.5 flex-shrink-0" />
                {bonus}
              </div>
            )}

            <p className="text-xs text-gray-400 mt-2">
              {new Date(ref.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
            </p>
          </div>
        )
      })}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// WhatsAppShareSection
// ─────────────────────────────────────────────────────────────────────────────

function WhatsAppShareSection({
  referrals, campaign, lang,
}: {
  referrals: ReferralRow[]; campaign: Campaign | null; lang: Lang
}) {
  const s = S[lang]
  const [property, setProperty] = useState('')
  const [sharing, setSharing]   = useState(false)
  const [done, setDone]         = useState(false)

  // Pick the most recent pending referral, or any referral
  const targetRef = referrals.find(r => r.status === 'PENDING') ?? referrals[0] ?? null

  const defaultReward = campaign
    ? fmtINR(5000 * campaign.bonus_multiplier + campaign.bonus_flat)
    : fmtINR(5000)

  const handleShare = async () => {
    if (!targetRef) return
    setSharing(true)
    try {
      const payload: Record<string, unknown> = {
        lang,
        property_name: property.trim() || 'our property',
      }
      const r = await apiClient.post(`/referrals/${targetRef.id}/share/whatsapp`, payload)
      window.open(r.data.whatsapp_url, '_blank', 'noopener,noreferrer')
      setDone(true)
      setTimeout(() => setDone(false), 4000)
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to generate link')
    } finally {
      setSharing(false)
    }
  }

  return (
    <div className="rounded-2xl overflow-hidden shadow-md">
      {/* Green header */}
      <div className="bg-[#25D366] px-5 pt-5 pb-4">
        <div className="flex items-center gap-2 mb-1">
          <MessageSquare className="w-6 h-6 text-white" />
          <h2 className="text-xl font-bold text-white">{s.share_heading}</h2>
        </div>
        <p className="text-sm text-green-50">{s.share_sub(defaultReward)}</p>
      </div>

      {/* Form area */}
      <div className="bg-[#f0fdf4] border border-green-100 px-5 py-4 space-y-3">
        <input
          value={property}
          onChange={e => setProperty(e.target.value)}
          placeholder={`🏨 ${s.share_property}`}
          className="w-full bg-white border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#25D366] transition"
        />

        {!targetRef ? (
          <div className="text-center py-2">
            <p className="text-sm text-gray-500 mb-2">{s.no_referrals}</p>
            <Link
              to="/india-referrals"
              className="inline-flex items-center gap-1 text-sm text-orange-500 font-semibold"
            >
              {s.no_referrals_cta} <ChevronRight className="w-4 h-4" />
            </Link>
          </div>
        ) : (
          <button
            onClick={handleShare}
            disabled={sharing}
            className="w-full flex items-center justify-center gap-2 py-4 bg-[#25D366] hover:bg-[#1fb959] disabled:opacity-60 text-white rounded-xl font-bold text-base transition active:scale-[0.97] shadow"
          >
            {sharing
              ? <><Loader2 className="w-5 h-5 animate-spin" /> {s.share_generating}</>
              : done
                ? <><Check className="w-5 h-5" /> Opened WhatsApp!</>
                : <><MessageSquare className="w-5 h-5" /> {s.share_btn}</>}
          </button>
        )}

        {targetRef && (
          <p className="text-xs text-center text-gray-400">
            Code: <span className="font-mono text-gray-600">{targetRef.referral_code}</span>
          </p>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tier colour map
// ─────────────────────────────────────────────────────────────────────────────

const TIER_STYLES: Record<string, { badge: string; glow: string; ring: string }> = {
  BRONZE:   { badge: 'bg-orange-100 text-orange-700',  glow: 'from-orange-50 to-amber-50',   ring: 'border-orange-200' },
  SILVER:   { badge: 'bg-gray-100 text-gray-600',      glow: 'from-gray-50 to-slate-50',     ring: 'border-gray-200' },
  GOLD:     { badge: 'bg-yellow-100 text-yellow-700',  glow: 'from-yellow-50 to-amber-50',   ring: 'border-yellow-300' },
  PLATINUM: { badge: 'bg-purple-100 text-purple-700',  glow: 'from-purple-50 to-violet-50',  ring: 'border-purple-300' },
}

// ─────────────────────────────────────────────────────────────────────────────
// MilestoneProgress — next badge goal with progress bar
// ─────────────────────────────────────────────────────────────────────────────

function MilestoneProgress({ milestone, lang }: { milestone: NextMilestone; lang: Lang }) {
  const s  = S[lang]
  const ts = TIER_STYLES[milestone.tier] ?? TIER_STYLES.BRONZE
  const unit = milestone.milestone_type === 'hired_count' ? s.milestone_hired : s.milestone_shares

  return (
    <div className={`bg-white rounded-2xl border-2 ${ts.ring} shadow-sm overflow-hidden`}>
      <div className={`bg-gradient-to-r ${ts.glow} px-4 pt-4 pb-3`}>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-3xl">{milestone.icon}</span>
          <div className="flex-1 min-w-0">
            <p className="font-bold text-gray-900 text-base leading-tight">{milestone.badge_name}</p>
            <p className="text-xs text-gray-500">{milestone.badge_name_en}</p>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-sm font-bold text-green-600">{fmtINR(milestone.reward_bonus)}</p>
            <p className="text-xs text-gray-400">{s.milestone_bonus}</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-3 bg-white bg-opacity-70 rounded-full overflow-hidden shadow-inner">
          <div
            className="h-full bg-gradient-to-r from-orange-400 to-orange-600 rounded-full transition-all duration-700"
            style={{ width: `${milestone.progress_pct}%` }}
          />
        </div>
        <div className="flex justify-between mt-1.5">
          <p className="text-xs font-semibold text-gray-700">
            {milestone.current} / {milestone.threshold} {unit}
          </p>
          <p className="text-xs text-gray-500">{milestone.progress_pct}%</p>
        </div>
      </div>

      <div className="px-4 py-2 border-t border-gray-100 bg-white">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${ts.badge}`}>
          {milestone.tier}
        </span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// BadgeGrid — earned/locked badge cards with Hindi names
// ─────────────────────────────────────────────────────────────────────────────

function BadgeGrid({ catalog, lang }: { catalog: BadgeCatalogEntry[]; lang: Lang }) {
  const s = S[lang]

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-orange-50 to-amber-50">
        <Award className="w-5 h-5 text-orange-500" />
        <h2 className="font-bold text-gray-800">{s.badges_heading}</h2>
      </div>

      <div className="grid grid-cols-3 gap-3 p-4">
        {catalog.map(badge => {
          const ts = TIER_STYLES[badge.tier] ?? TIER_STYLES.BRONZE
          return (
            <div
              key={badge.name}
              className={`relative flex flex-col items-center p-3 rounded-2xl border-2 transition-all ${
                badge.earned
                  ? `bg-gradient-to-b ${ts.glow} ${ts.ring} shadow-sm`
                  : 'bg-gray-50 border-gray-200 opacity-60'
              }`}
            >
              {/* Earned tick */}
              {badge.earned && (
                <BadgeCheck className="absolute top-1.5 right-1.5 w-4 h-4 text-green-500" />
              )}
              {/* Lock for unearned */}
              {!badge.earned && (
                <Lock className="absolute top-1.5 right-1.5 w-3.5 h-3.5 text-gray-400" />
              )}

              {/* Icon */}
              <span className={`text-3xl mb-1.5 ${!badge.earned ? 'grayscale' : ''}`}>
                {badge.icon}
              </span>

              {/* Hindi name */}
              <p className="text-xs font-bold text-gray-900 text-center leading-tight">
                {badge.name_hi}
              </p>

              {/* Tier chip */}
              <span className={`mt-1 text-[10px] px-1.5 py-0.5 rounded-full font-semibold ${ts.badge}`}>
                {badge.tier}
              </span>

              {/* Progress hint for unearned */}
              {!badge.earned && (
                <p className="mt-1 text-[9px] text-gray-400 text-center">
                  {badge.threshold} {badge.milestone_type === 'hired_count' ? 'hires' : 'shares'}
                </p>
              )}

              {/* Earned date */}
              {badge.earned && badge.earned_at && (
                <p className="mt-1 text-[9px] text-gray-400">
                  {new Date(badge.earned_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// UpcomingCampaignTeaser — shown when no campaign is currently active
// ─────────────────────────────────────────────────────────────────────────────

function UpcomingCampaignTeaser({ campaign, lang }: { campaign: Campaign & { days_until?: number; festival_meta?: Record<string, string> }; lang: Lang }) {
  const s     = S[lang]
  const meta  = campaign.festival_meta ?? {}
  const emoji = meta.emoji ?? '🎉'
  const color = campaign.banner_color ?? '#FF6B00'

  return (
    <div className="rounded-2xl border-2 border-dashed overflow-hidden" style={{ borderColor: color }}>
      <div className="px-4 py-3 flex items-center gap-3" style={{ background: `${color}15` }}>
        <Calendar className="w-5 h-5" style={{ color }} />
        <p className="text-sm font-semibold" style={{ color }}>{s.upcoming_heading}</p>
        {campaign.days_until !== undefined && (
          <span
            className="ml-auto text-xs font-bold px-2 py-0.5 rounded-full text-white"
            style={{ background: color }}
          >
            {s.upcoming_in(campaign.days_until)}
          </span>
        )}
      </div>
      <div className="px-4 py-3 bg-white flex items-start gap-3">
        <span className="text-3xl">{emoji}</span>
        <div className="flex-1 min-w-0">
          <p className="font-bold text-gray-900 text-sm">{campaign.name}</p>
          <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{campaign.banner_text}</p>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs font-semibold text-white px-2 py-0.5 rounded-full"
              style={{ background: color }}
            >
              {campaign.bonus_multiplier}x rewards
            </span>
            {campaign.bonus_flat > 0 && (
              <span className="text-xs text-gray-600">+ {fmtINR(campaign.bonus_flat)}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MultipleCampaignBanner — when >1 campaigns overlap
// ─────────────────────────────────────────────────────────────────────────────

function MultipleCampaignBanner({ campaigns }: { campaigns: Campaign[] }) {
  const top = campaigns[0]
  if (!top) return null

  const meta = (top as any).festival_meta ?? {}
  return (
    <div
      className="rounded-2xl p-4 text-white shadow-md relative overflow-hidden"
      style={{ background: `linear-gradient(135deg, ${top.banner_color} 0%, ${top.banner_color}cc 100%)` }}
    >
      {/* Shimmer layer */}
      <div
        className="absolute inset-0 opacity-20 pointer-events-none"
        style={{
          background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.6) 50%, transparent 100%)',
          backgroundSize: '200% 100%',
          animation: 'shimmer 3s infinite linear',
        }}
      />
      <div className="relative">
        <div className="flex items-start gap-3">
          <span className="text-4xl">{meta.emoji ?? '🎉'}</span>
          <div className="flex-1 min-w-0">
            <p className="font-bold text-lg leading-tight">{top.name}</p>
            <p className="text-sm opacity-90 mt-0.5">{top.banner_text}</p>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="bg-white bg-opacity-25 rounded-full px-3 py-1 text-sm font-bold">
            {top.bonus_multiplier}x rewards
          </span>
          {top.bonus_flat > 0 && (
            <span className="bg-white bg-opacity-25 rounded-full px-3 py-1 text-sm font-bold">
              + {fmtINR(top.bonus_flat)} bonus
            </span>
          )}
          {campaigns.length > 1 && (
            <span className="bg-white bg-opacity-15 rounded-full px-3 py-1 text-xs">
              +{campaigns.length - 1} more festival{campaigns.length > 2 ? 's' : ''}!
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// LeaderboardSection
// ─────────────────────────────────────────────────────────────────────────────

function LeaderboardSection({ entries, lang }: { entries: LeaderEntry[]; lang: Lang }) {
  const s = S[lang]
  if (entries.length === 0) return null

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 bg-gradient-to-r from-yellow-50 to-orange-50">
        <Trophy className="w-5 h-5 text-yellow-500" />
        <h2 className="font-bold text-gray-800">{s.leaderboard}</h2>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-4 gap-2 px-4 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wide border-b border-gray-50">
        <span className="col-span-2">{s.lb_name}</span>
        <span className="text-center">{s.lb_hired}</span>
        <span className="text-right">{s.lb_earned}</span>
      </div>

      {/* Rows */}
      <div className="divide-y divide-gray-50">
        {entries.map((entry, i) => (
          <div
            key={i}
            className={`grid grid-cols-4 gap-2 px-4 py-3 items-center ${
              i === 0 ? 'bg-yellow-50' : i === 1 ? 'bg-gray-50' : ''
            }`}
          >
            <div className="col-span-2 flex items-center gap-2 min-w-0">
              <span className="text-xl flex-shrink-0 w-7">{MEDALS[i] ?? `#${i + 1}`}</span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-gray-800 truncate">
                  {maskEmail(entry.referrer_email)}
                </p>
                <p className="text-xs text-gray-400">{entry.total_referrals} refs</p>
              </div>
            </div>

            <div className="text-center">
              <span className={`text-sm font-bold ${
                i === 0 ? 'text-yellow-600' : 'text-gray-700'
              }`}>
                {entry.hired_count}
              </span>
              <p className="text-xs text-gray-400">{s.stats_hired}</p>
            </div>

            <div className="text-right">
              <p className="text-sm font-bold text-green-600">{entry.formatted_earned}</p>
              <p className="text-xs text-gray-400">{s.lb_earned}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function ReferralPortal() {
  const storedLang = (localStorage.getItem('referral_portal_lang') as Lang) ?? 'en'
  const [lang, setLang] = useState<Lang>(storedLang)

  const [referrals, setReferrals]   = useState<ReferralRow[]>([])
  const [summary, setSummary]       = useState<Summary>({ total_referrals: 0, applied_count: 0, hired_count: 0, total_earned: 0, total_paid: 0 })
  const [leaderboard, setBoard]     = useState<LeaderEntry[]>([])
  const [gamification, setGami]     = useState<GamificationStatus | null>(null)
  const [newBadges, setNewBadges]   = useState<BadgeCatalogEntry[]>([])
  const [loading, setLoading]       = useState(true)

  const toggleLang = useCallback(() => {
    setLang(prev => {
      const next: Lang = prev === 'en' ? 'hi' : 'en'
      localStorage.setItem('referral_portal_lang', next)
      return next
    })
  }, [])

  useEffect(() => {
    Promise.allSettled([
      apiClient.get('/india-referrals/gamification/status'),
      apiClient.get('/referrals/my-referrals'),
      apiClient.get('/india-referrals/leaderboard'),
    ]).then(([gamiRes, refRes, lbRes]) => {
      if (gamiRes.status === 'fulfilled') {
        const g = gamiRes.value.data as GamificationStatus
        setGami(g)
        if (g.newly_awarded?.length) setNewBadges(g.newly_awarded)
      }
      if (refRes.status === 'fulfilled') {
        setReferrals(refRes.value.data.referrals ?? [])
        setSummary(refRes.value.data.summary ?? summary)
      }
      if (lbRes.status === 'fulfilled') setBoard(lbRes.value.data ?? [])
    }).finally(() => setLoading(false))
  }, [])

  const s = S[lang]

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Loader2 className="w-8 h-8 animate-spin text-orange-500" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Shimmer keyframe for festive banners */}
      <style>{`@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}`}</style>
      <div className="max-w-md mx-auto px-4 pb-12">

        {/* ── Page header ── */}
        <div className="pt-6 pb-4 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{s.title}</h1>
            <p className="text-sm text-gray-500 mt-0.5">{s.sub}</p>
          </div>
          <div className="flex-shrink-0 pt-1">
            <LanguageToggle lang={lang} onToggle={toggleLang} />
          </div>
        </div>

        {/* ── Newly awarded badges toast ── */}
        {newBadges.length > 0 && (
          <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-xs w-full px-4">
            {newBadges.map(b => (
              <div
                key={b.name}
                className="bg-gradient-to-r from-yellow-400 to-orange-500 text-white rounded-2xl px-4 py-3 mb-2 shadow-xl flex items-center gap-3"
              >
                <span className="text-3xl">{b.icon}</span>
                <div className="flex-1">
                  <p className="font-bold text-sm">🎉 New Badge Unlocked!</p>
                  <p className="text-xs opacity-90">{b.name_hi} — {b.name_en}</p>
                </div>
                <button onClick={() => setNewBadges(prev => prev.filter(x => x.name !== b.name))}>
                  <span className="text-white opacity-70 text-lg leading-none">×</span>
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="space-y-4">

          {/* ── Festive campaign banner (multi-campaign aware) ── */}
          {gamification?.active_campaigns?.length
            ? <MultipleCampaignBanner campaigns={gamification.active_campaigns} />
            : gamification?.next_campaign
              ? <UpcomingCampaignTeaser campaign={gamification.next_campaign as any} lang={lang} />
              : null
          }

          {/* ── Stats (sourced from gamification for accuracy) ── */}
          <StatsCard summary={gamification
            ? { ...summary, hired_count: gamification.hired_count, total_earned: gamification.total_earned_inr }
            : summary
          } lang={lang} />

          {/* ── Milestone progress ── */}
          {gamification?.next_milestone ? (
            <div>
              <h2 className="text-base font-bold text-gray-800 mb-2 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-orange-500" />
                {s.milestone_heading}
              </h2>
              <MilestoneProgress milestone={gamification.next_milestone} lang={lang} />
            </div>
          ) : gamification && (
            <div className="bg-gradient-to-r from-purple-50 to-violet-50 border border-purple-200 rounded-2xl p-4 text-center">
              <p className="text-sm font-bold text-purple-700">💎 {s.all_done}</p>
            </div>
          )}

          {/* ── UPI card (prominent) ── */}
          <UPICard lang={lang} />

          {/* ── Badge grid ── */}
          {gamification?.badges_catalog?.length ? (
            <BadgeGrid catalog={gamification.badges_catalog} lang={lang} />
          ) : null}

          {/* ── My referrals / timeline ── */}
          <div>
            <h2 className="text-base font-bold text-gray-800 mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-orange-500" />
              {s.my_referrals}
            </h2>
            <ReferralTimelineSection referrals={referrals} lang={lang} />
          </div>

          {/* ── WhatsApp CTA ── */}
          <WhatsAppShareSection referrals={referrals} campaign={gamification?.active_campaigns?.[0] ?? null} lang={lang} />

          {/* ── Leaderboard ── */}
          {leaderboard.length > 0 && <LeaderboardSection entries={leaderboard} lang={lang} />}

        </div>
      </div>
    </div>
  )
}
