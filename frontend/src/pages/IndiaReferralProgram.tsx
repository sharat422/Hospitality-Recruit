import { apiClient } from '@/lib/api'
import {
Award,
BadgeCheck,
Building2,
Calendar,
Check,
ChevronDown,
ChevronUp,
Copy,
CreditCard,
Gift,
Hash,
IndianRupee,
Languages,
Loader2,
MessageSquare,
Share2,
Smartphone,
Trophy,
Zap
} from 'lucide-react'
import React,{ useEffect,useState } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Campaign {
  is_active: boolean
  id: string
  name: string
  festival_name: string
  start_date: string
  end_date: string
  bonus_multiplier: number
  bonus_flat: number
  banner_text: string
  banner_color: string
}

interface Badge {
  id: string
  name: string
  description: string
  icon: string
  tier: 'BRONZE' | 'SILVER' | 'GOLD' | 'PLATINUM'
  required_hires: number
  reward_bonus: number
}

interface EarnedBadge {
  id: string
  earned_at: string
  referral_count_at_award: number
  referral_badges: Badge
}

interface Program {
  id: string
  name: string
  description: string
  reward_on_hire: number
  retention_bonus: number
  retention_days: number
  currency: string
  is_active: boolean
}

interface IndiaReferral {
  id: string
  referral_code: string
  candidate_email: string | null
  job_role_id: string
  status: string
  reward_amount: number
  reward_status: string
  currency: string
  whatsapp_shared: boolean
  hire_date: string | null
  retention_bonus_amount: number
  retention_bonus_status: string
  created_at: string
}

interface LeaderEntry {
  referrer_email: string
  total_referrals: number
  hired_count: number
  total_earned_inr: number
  formatted_earned: string
}

interface UPIDetails {
  upi_id?: string
  bank_account_number?: string
  bank_ifsc?: string
  bank_name?: string
  account_holder_name?: string
  is_verified: boolean
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TIER_COLORS: Record<string, string> = {
  BRONZE:   'bg-orange-100 text-orange-800 border-orange-300',
  SILVER:   'bg-gray-100 text-gray-700 border-gray-300',
  GOLD:     'bg-yellow-100 text-yellow-800 border-yellow-300',
  PLATINUM: 'bg-purple-100 text-purple-800 border-purple-300',
}

function formatINR(amount: number): string {
  if (!amount) return '₹0'
  const s = Math.floor(amount).toString()
  if (s.length <= 3) return `₹${s}`
  const last3 = s.slice(-3)
  let rest = s.slice(0, -3)
  const groups: string[] = []
  while (rest.length > 2) { groups.unshift(rest.slice(-2)); rest = rest.slice(0, -2) }
  if (rest) groups.unshift(rest)
  return `₹${groups.join(',')},${last3}`
}

function statusColor(status: string): string {
  switch (status) {
    case 'PENDING':     return 'bg-gray-100 text-gray-600'
    case 'APPLIED':     return 'bg-blue-100 text-blue-700'
    case 'SHORTLISTED': return 'bg-yellow-100 text-yellow-700'
    case 'HIRED':       return 'bg-green-100 text-green-700'
    case 'REWARDED':    return 'bg-purple-100 text-purple-700'
    default:            return 'bg-gray-100 text-gray-600'
  }
}

function rewardStatusColor(rs: string): string {
  switch (rs) {
    case 'NOT_EARNED': return 'text-gray-400'
    case 'EARNED':     return 'text-green-600 font-medium'
    case 'PAID':       return 'text-purple-600 font-bold'
    default:           return 'text-gray-400'
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CampaignBanner({ campaign }: { campaign: Campaign }) {
  return (
    <div
      className="rounded-xl p-4 mb-6 text-white flex items-center gap-3 shadow"
      style={{ background: `linear-gradient(135deg, ${campaign.banner_color}, ${campaign.banner_color}cc)` }}
    >
      <Zap className="w-6 h-6 flex-shrink-0" />
      <div>
        <p className="font-bold text-lg">{campaign.name}</p>
        <p className="text-sm opacity-90">{campaign.banner_text}</p>
        <p className="text-xs opacity-75 mt-1">
          Valid: {new Date(campaign.start_date).toLocaleDateString('en-IN')} – {new Date(campaign.end_date).toLocaleDateString('en-IN')}
          {' · '}{campaign.bonus_multiplier}x rewards{campaign.bonus_flat > 0 && ` + ${formatINR(campaign.bonus_flat)} bonus`}
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: My Referrals
// ---------------------------------------------------------------------------

// Default share form state
const DEFAULT_SHARE_FORM = { lang: 'en', property_name: '', salary_min: '', salary_max: '' }

function MyReferralsTab() {
  const [referrals, setReferrals]     = useState<IndiaReferral[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState('')
  const [copied, setCopied]           = useState<string | null>(null)
  // share panel state
  const [sharePanel, setSharePanel]   = useState<string | null>(null)  // referral id
  const [shareForm, setShareForm]     = useState(DEFAULT_SHARE_FORM)
  const [sharing, setSharing]         = useState(false)
  const [sharedIds, setSharedIds]     = useState<Set<string>>(new Set())

  useEffect(() => {
    apiClient.get('/referrals/my-referrals').then(r => {
      setReferrals(r.data.referrals || [])
      const alreadyShared = new Set<string>(
        (r.data.referrals || []).filter((x: IndiaReferral) => x.whatsapp_shared).map((x: IndiaReferral) => x.id)
      )
      setSharedIds(alreadyShared)
    }).catch(() => setError('Failed to load referrals')).finally(() => setLoading(false))
  }, [])

  const copy = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  const toggleSharePanel = (id: string) => {
    setSharePanel(prev => (prev === id ? null : id))
    setShareForm(DEFAULT_SHARE_FORM)
  }

  const handleWhatsAppShare = async (referralId: string) => {
    setSharing(true)
    try {
      const payload: Record<string, unknown> = {
        lang: shareForm.lang,
        property_name: shareForm.property_name || 'our property',
      }
      if (shareForm.salary_min) payload.salary_min = parseInt(shareForm.salary_min, 10)
      if (shareForm.salary_max) payload.salary_max = parseInt(shareForm.salary_max, 10)

      const r = await apiClient.post(`/referrals/${referralId}/share/whatsapp`, payload)
      window.open(r.data.whatsapp_url, '_blank', 'noopener,noreferrer')
      setSharedIds(prev => new Set([...prev, referralId]))
      setSharePanel(null)
    } catch (err: any) {
      alert('Failed to generate WhatsApp link: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSharing(false)
    }
  }

  const checkRetention = async (id: string) => {
    const r = await apiClient.post(`/india-referrals/referrals/${id}/check-retention`)
    alert(r.data.eligible ? `✅ ${r.data.message}` : `⏳ ${r.data.reason}`)
  }

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>
  if (error) return <div className="text-red-600 text-center py-8">{error}</div>
  if (referrals.length === 0) return (
    <div className="text-center py-12 text-gray-500">
      <Gift className="w-12 h-12 mx-auto mb-3 text-gray-300" />
      <p>No referrals yet. Create your first referral link!</p>
    </div>
  )

  return (
    <div className="space-y-3">
      {referrals.map(ref => {
        const isShared = sharedIds.has(ref.id)
        const panelOpen = sharePanel === ref.id
        return (
          <div key={ref.id} className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
            {/* Card header */}
            <div className="p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${statusColor(ref.status)}`}>{ref.status}</span>
                    {isShared && (
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                        <MessageSquare className="w-3 h-3" /> Shared on WhatsApp
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-700 font-mono">{ref.referral_code}</p>
                  {ref.candidate_email && <p className="text-xs text-gray-500 truncate">{ref.candidate_email}</p>}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className={`text-sm font-bold ${rewardStatusColor(ref.reward_status)}`}>
                    {formatINR(ref.reward_amount)}
                  </p>
                  <p className="text-xs text-gray-400">{ref.reward_status.replace('_', ' ')}</p>
                </div>
              </div>

              {ref.retention_bonus_amount > 0 && (
                <div className="mt-2 text-xs bg-blue-50 text-blue-700 px-3 py-1 rounded-lg">
                  Retention bonus: {formatINR(ref.retention_bonus_amount)} — {ref.retention_bonus_status.replace('_', ' ')}
                </div>
              )}

              {/* ── Primary CTA: WhatsApp Share ── */}
              <button
                onClick={() => toggleSharePanel(ref.id)}
                className={`mt-3 w-full flex items-center justify-center gap-2 py-3 rounded-xl font-semibold text-sm transition active:scale-[0.98] shadow-sm ${
                  isShared
                    ? 'bg-green-50 text-green-700 border border-green-200'
                    : 'bg-[#25D366] hover:bg-[#1fb959] text-white'
                }`}
              >
                <MessageSquare className="w-5 h-5" />
                {isShared ? 'Share Again on WhatsApp' : 'Share on WhatsApp'}
                {panelOpen
                  ? <ChevronUp className="w-4 h-4 ml-auto" />
                  : <ChevronDown className="w-4 h-4 ml-auto" />}
              </button>

              {/* ── Secondary actions ── */}
              <div className="mt-2 flex gap-2 flex-wrap">
                <button
                  onClick={() => copy(`${window.location.origin}/apply/${ref.job_role_id}?ref=${ref.referral_code}`, ref.id)}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg transition"
                >
                  {copied === ref.id ? <Check className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3" />}
                  {copied === ref.id ? 'Copied!' : 'Copy Link'}
                </button>
                {ref.status === 'HIRED' && ref.retention_bonus_status === 'NOT_ELIGIBLE' && (
                  <button
                    onClick={() => checkRetention(ref.id)}
                    className="flex items-center gap-1 text-xs px-3 py-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-lg transition"
                  >
                    <Calendar className="w-3 h-3" /> Check 90-Day Bonus
                  </button>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-2">{new Date(ref.created_at).toLocaleDateString('en-IN')}</p>
            </div>

            {/* ── Inline WhatsApp share panel ── */}
            {panelOpen && (
              <div className="border-t border-green-100 bg-green-50 px-4 py-4 space-y-3">
                <p className="text-xs font-semibold text-green-800 flex items-center gap-1">
                  <Languages className="w-3.5 h-3.5" /> Personalise your message
                </p>

                {/* Language toggle */}
                <div className="flex gap-2">
                  {[
                    { code: 'en', label: '🇬🇧 English' },
                    { code: 'hi', label: '🇮🇳 हिंदी' },
                  ].map(l => (
                    <button
                      key={l.code}
                      onClick={() => setShareForm(f => ({ ...f, lang: l.code }))}
                      className={`px-3 py-1.5 text-xs rounded-full font-medium border transition ${
                        shareForm.lang === l.code
                          ? 'bg-green-600 text-white border-green-600'
                          : 'bg-white text-gray-700 border-gray-300 hover:border-green-400'
                      }`}
                    >
                      {l.label}
                    </button>
                  ))}
                </div>

                {/* Property name */}
                <input
                  value={shareForm.property_name}
                  onChange={e => setShareForm(f => ({ ...f, property_name: e.target.value }))}
                  placeholder="🏨 Hotel / Property name (optional)"
                  className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
                />

                {/* Salary range */}
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={shareForm.salary_min}
                    onChange={e => setShareForm(f => ({ ...f, salary_min: e.target.value }))}
                    placeholder="₹ Min salary/month"
                    className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
                  />
                  <input
                    type="number"
                    value={shareForm.salary_max}
                    onChange={e => setShareForm(f => ({ ...f, salary_max: e.target.value }))}
                    placeholder="₹ Max salary/month"
                    className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400"
                  />
                </div>

                {/* Generate & open button */}
                <button
                  onClick={() => handleWhatsAppShare(ref.id)}
                  disabled={sharing}
                  className="w-full flex items-center justify-center gap-2 py-3 bg-[#25D366] hover:bg-[#1fb959] text-white rounded-xl font-bold text-sm transition disabled:opacity-60 shadow"
                >
                  {sharing
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <MessageSquare className="w-4 h-4" />}
                  {sharing ? 'Generating link…' : 'Generate & Open in WhatsApp'}
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// CreateSharePanel — reusable WhatsApp share panel (used in CreateReferralTab)
// ---------------------------------------------------------------------------

function CreateSharePanel({ referralId, jobTitle }: { referralId: string; jobTitle: string }) {
  const [lang, setLang]           = useState('en')
  const [property, setProperty]   = useState('')
  const [salaryMin, setSalaryMin] = useState('')
  const [salaryMax, setSalaryMax] = useState('')
  const [sharing, setSharing]     = useState(false)
  const [done, setDone]           = useState(false)

  const handleShare = async () => {
    setSharing(true)
    try {
      const payload: Record<string, unknown> = {
        lang,
        property_name: property || 'our property',
        role_title: jobTitle || undefined,
      }
      if (salaryMin) payload.salary_min = parseInt(salaryMin, 10)
      if (salaryMax) payload.salary_max = parseInt(salaryMax, 10)

      const r = await apiClient.post(`/referrals/${referralId}/share/whatsapp`, payload)
      window.open(r.data.whatsapp_url, '_blank', 'noopener,noreferrer')
      setDone(true)
    } catch (err: any) {
      alert('Failed to generate WhatsApp link: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSharing(false)
    }
  }

  return (
    <div className="border-t border-green-100 bg-green-50 px-5 py-4 space-y-3">
      <p className="text-xs font-semibold text-green-800 flex items-center gap-1">
        <Languages className="w-3.5 h-3.5" /> Personalise your WhatsApp message
      </p>

      {/* Language toggle */}
      <div className="flex gap-2">
        {[{ code: 'en', label: '🇬🇧 English' }, { code: 'hi', label: '🇮🇳 हिंदी' }].map(l => (
          <button key={l.code} onClick={() => setLang(l.code)}
            className={`px-3 py-1.5 text-xs rounded-full font-medium border transition ${
              lang === l.code ? 'bg-green-600 text-white border-green-600' : 'bg-white text-gray-700 border-gray-300 hover:border-green-400'
            }`}>{l.label}</button>
        ))}
      </div>

      <input value={property} onChange={e => setProperty(e.target.value)}
        placeholder="🏨 Hotel / Property name (optional)"
        className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400" />

      <div className="flex gap-2">
        <input type="number" value={salaryMin} onChange={e => setSalaryMin(e.target.value)}
          placeholder="₹ Min/month"
          className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400" />
        <input type="number" value={salaryMax} onChange={e => setSalaryMax(e.target.value)}
          placeholder="₹ Max/month"
          className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400" />
      </div>

      <button onClick={handleShare} disabled={sharing}
        className="w-full flex items-center justify-center gap-2 py-3 bg-[#25D366] hover:bg-[#1fb959] text-white rounded-xl font-bold text-sm transition disabled:opacity-60 shadow active:scale-[0.98]">
        {sharing
          ? <Loader2 className="w-4 h-4 animate-spin" />
          : done
            ? <Check className="w-4 h-4" />
            : <MessageSquare className="w-4 h-4" />}
        {sharing ? 'Generating…' : done ? 'Opened! Share again?' : 'Generate & Open in WhatsApp'}
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Create Referral Link
// ---------------------------------------------------------------------------

function CreateReferralTab({ campaign }: { campaign: Campaign | null }) {
  const [programs, setPrograms] = useState<Program[]>([])
  const [form, setForm] = useState({ job_role_id: '', job_title: '', candidate_email: '', program_id: '', notes: '' })
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    apiClient.get('/india-referrals/programs').then(r => setPrograms(r.data || [])).catch(() => {})
  }, [])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.job_role_id || !form.job_title) return
    setLoading(true)
    try {
      const r = await apiClient.post('/india-referrals/create', {
        job_role_id: form.job_role_id,
        job_title: form.job_title,
        candidate_email: form.candidate_email || undefined,
        program_id: form.program_id || undefined,
        notes: form.notes || undefined,
      })
      setResult(r.data)
    } catch (err: any) {
      alert('Failed to create referral: ' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

  const copyLink = (link: string) => {
    navigator.clipboard.writeText(link)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div>
      {campaign && <CampaignBanner campaign={campaign} />}
      <form onSubmit={submit} className="space-y-4 bg-white border border-gray-200 rounded-xl p-5 shadow-sm mb-6">
        <h3 className="font-semibold text-gray-800">Create Referral Link</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-gray-600">Job Role ID *</label>
            <input
              value={form.job_role_id}
              onChange={e => setForm(f => ({ ...f, job_role_id: e.target.value }))}
              placeholder="UUID from jobs table"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
              required
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600">Job Title *</label>
            <input
              value={form.job_title}
              onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))}
              placeholder="e.g. Hotel Manager"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
              required
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600">Candidate Email (optional)</label>
            <input
              type="email"
              value={form.candidate_email}
              onChange={e => setForm(f => ({ ...f, candidate_email: e.target.value }))}
              placeholder="friend@email.com"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600">Program</label>
            <select
              value={form.program_id}
              onChange={e => setForm(f => ({ ...f, program_id: e.target.value }))}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              <option value="">Default (₹5,000 on hire)</option>
              {programs.filter(p => p.is_active).map(p => (
                <option key={p.id} value={p.id}>{p.name} — {formatINR(p.reward_on_hire)} on hire</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600">Notes (optional)</label>
          <input
            value={form.notes}
            onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            placeholder="Any notes about this referral"
            className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
          />
        </div>

        {campaign && (
          <div className="text-sm bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 text-orange-800">
            🎉 <strong>{campaign.name}</strong> is active! Your reward will be{' '}
            {campaign.bonus_multiplier}x base{campaign.bonus_flat > 0 && ` + ${formatINR(campaign.bonus_flat)} flat bonus`}.
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-orange-500 text-white rounded-lg font-medium text-sm hover:bg-orange-600 disabled:opacity-50 transition"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Gift className="w-4 h-4" />}
          Generate Referral Link
        </button>
      </form>

      {result && (
        <div className="bg-white border border-green-200 rounded-xl shadow-sm overflow-hidden">
          <div className="p-5 space-y-4">
            <div className="flex items-center gap-2 text-green-700 font-semibold">
              <Check className="w-5 h-5" /> Referral Link Created!
            </div>

            {result.active_campaign && (
              <div className="text-sm bg-orange-50 border border-orange-200 rounded-lg px-4 py-2 text-orange-800">
                Campaign applied: <strong>{result.active_campaign.name}</strong>
              </div>
            )}

            {result.reward_breakdown && (
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500">Base Reward</p>
                  <p className="font-bold text-gray-800">{formatINR(result.reward_breakdown.base_amount)}</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500">Multiplier</p>
                  <p className="font-bold text-orange-600">{result.reward_breakdown.campaign_multiplier}x</p>
                </div>
                <div className="bg-green-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500">Total Reward</p>
                  <p className="font-bold text-green-700">{result.reward_breakdown.formatted}</p>
                </div>
              </div>
            )}

            <div>
              <label className="text-xs font-medium text-gray-600">Referral Link</label>
              <div className="flex gap-2 mt-1">
                <input readOnly value={result.referral_link}
                  className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm bg-gray-50 font-mono text-gray-700" />
                <button onClick={() => copyLink(result.referral_link)}
                  className="px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition">
                  {copied ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                </button>
              </div>
            </div>
          </div>

          {/* ── Primary CTA: rich WhatsApp share using the new endpoint ── */}
          {result.referralId && (
            <CreateSharePanel referralId={result.referralId} jobTitle={form.job_title} />
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Campaigns
// ---------------------------------------------------------------------------

function CampaignsTab() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get('/india-referrals/campaigns').then(r => setCampaigns(r.data || [])).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>

  const now = new Date()
  return (
    <div className="space-y-3">
      {campaigns.map(c => {
        const start = new Date(c.start_date)
        const end = new Date(c.end_date)
        const isActive = now >= start && now <= end && c.is_active
        const isUpcoming = start > now
        return (
          <div key={c.id} className={`bg-white border rounded-xl p-4 shadow-sm ${isActive ? 'border-orange-300 ring-1 ring-orange-200' : 'border-gray-200'}`}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xl">{c.festival_name === 'DIWALI' ? '🪔' : c.festival_name === 'HOLI' ? '🎨' : c.festival_name === 'EID' ? '🌙' : c.festival_name === 'CHRISTMAS' ? '🎄' : c.festival_name === 'NEW_YEAR' ? '🎆' : c.festival_name === 'INDEPENDENCE_DAY' ? '🇮🇳' : '🎉'}</span>
                  <h4 className="font-semibold text-gray-800">{c.name}</h4>
                  {isActive && <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">LIVE</span>}
                  {isUpcoming && <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">Upcoming</span>}
                  {!isActive && !isUpcoming && <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Ended</span>}
                </div>
                <p className="text-sm text-gray-600">{c.banner_text}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {start.toLocaleDateString('en-IN')} – {end.toLocaleDateString('en-IN')}
                </p>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-lg font-bold text-orange-600">{c.bonus_multiplier}x</p>
                {c.bonus_flat > 0 && <p className="text-xs text-gray-500">+ {formatINR(c.bonus_flat)}</p>}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: Badges
// ---------------------------------------------------------------------------

function BadgesTab() {
  const [catalog, setCatalog] = useState<Badge[]>([])
  const [earned, setEarned] = useState<EarnedBadge[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      apiClient.get('/india-referrals/badges'),
      apiClient.get('/india-referrals/my-badges'),
    ]).then(([b, e]) => {
      setCatalog(b.data || [])
      setEarned(e.data || [])
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const earnedBadgeIds = new Set(earned.map(e => e.referral_badges?.id))

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>

  return (
    <div>
      {earned.length > 0 && (
        <div className="mb-6">
          <h3 className="font-semibold text-gray-700 mb-3 flex items-center gap-2"><Trophy className="w-4 h-4 text-yellow-500" /> Your Badges</h3>
          <div className="flex flex-wrap gap-3">
            {earned.map(eb => (
              <div key={eb.id} className="flex flex-col items-center bg-white border border-yellow-200 rounded-xl p-3 shadow-sm w-28">
                <span className="text-3xl mb-1">{eb.referral_badges?.icon}</span>
                <p className="text-xs font-semibold text-center text-gray-800">{eb.referral_badges?.name}</p>
                <span className={`text-xs mt-1 px-2 py-0.5 rounded-full border ${TIER_COLORS[eb.referral_badges?.tier || 'BRONZE']}`}>
                  {eb.referral_badges?.tier}
                </span>
                <p className="text-xs text-gray-400 mt-1">{new Date(eb.earned_at).toLocaleDateString('en-IN')}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <h3 className="font-semibold text-gray-700 mb-3 flex items-center gap-2"><Award className="w-4 h-4 text-gray-500" /> All Badges</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {catalog.map(b => {
          const isEarned = earnedBadgeIds.has(b.id)
          return (
            <div key={b.id} className={`flex items-center gap-3 p-3 rounded-xl border ${isEarned ? 'bg-yellow-50 border-yellow-200' : 'bg-white border-gray-200'}`}>
              <span className={`text-2xl ${!isEarned ? 'grayscale opacity-40' : ''}`}>{b.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-gray-800">{b.name}</p>
                  {isEarned && <BadgeCheck className="w-4 h-4 text-green-600" />}
                </div>
                <p className="text-xs text-gray-500">{b.description}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${TIER_COLORS[b.tier]}`}>{b.tier}</span>
                  <span className="text-xs text-gray-400">{b.required_hires} hire{b.required_hires !== 1 ? 's' : ''}</span>
                  {b.reward_bonus > 0 && <span className="text-xs text-green-600 font-medium">{formatINR(b.reward_bonus)} bonus</span>}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab: UPI Details
// ---------------------------------------------------------------------------

function UPITab() {
  const [details, setDetails] = useState<UPIDetails | null>(null)
  const [form, setForm] = useState({ upi_id: '', bank_account_number: '', bank_ifsc: '', bank_name: '', account_holder_name: '' })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get('/india-referrals/upi').then(r => {
      if (r.data.upi_details) {
        const d = r.data.upi_details
        setDetails(d)
        setForm({
          upi_id: d.upi_id || '',
          bank_account_number: d.bank_account_number || '',
          bank_ifsc: d.bank_ifsc || '',
          bank_name: d.bank_name || '',
          account_holder_name: d.account_holder_name || '',
        })
      }
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await apiClient.post('/india-referrals/upi', form)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err: any) {
      alert('Failed to save: ' + (err.response?.data?.detail || err.message))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>

  return (
    <form onSubmit={save} className="space-y-5 bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-1">
        <CreditCard className="w-5 h-5 text-orange-500" />
        <h3 className="font-semibold text-gray-800">UPI / Bank Details for INR Payouts</h3>
      </div>
      {details?.is_verified && (
        <div className="flex items-center gap-2 text-green-600 text-sm bg-green-50 border border-green-200 rounded-lg px-3 py-2">
          <BadgeCheck className="w-4 h-4" /> Verified — payouts will go to this account.
        </div>
      )}

      <div>
        <label className="text-xs font-medium text-gray-600 flex items-center gap-1"><Smartphone className="w-3 h-3" /> UPI ID</label>
        <input
          value={form.upi_id}
          onChange={e => setForm(f => ({ ...f, upi_id: e.target.value }))}
          placeholder="yourname@upi or 9999999999@okaxis"
          className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
        />
      </div>

      <div className="border-t border-gray-100 pt-4">
        <p className="text-xs font-medium text-gray-500 mb-3 uppercase tracking-wide">Or Bank Account</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-gray-600 flex items-center gap-1"><Building2 className="w-3 h-3" /> Account Holder Name</label>
            <input
              value={form.account_holder_name}
              onChange={e => setForm(f => ({ ...f, account_holder_name: e.target.value }))}
              placeholder="As on bank account"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 flex items-center gap-1"><IndianRupee className="w-3 h-3" /> Account Number</label>
            <input
              value={form.bank_account_number}
              onChange={e => setForm(f => ({ ...f, bank_account_number: e.target.value }))}
              placeholder="12-digit account number"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 flex items-center gap-1"><Hash className="w-3 h-3" /> IFSC Code</label>
            <input
              value={form.bank_ifsc}
              onChange={e => setForm(f => ({ ...f, bank_ifsc: e.target.value.toUpperCase() }))}
              placeholder="HDFC0001234"
              maxLength={11}
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 flex items-center gap-1"><Building2 className="w-3 h-3" /> Bank Name</label>
            <input
              value={form.bank_name}
              onChange={e => setForm(f => ({ ...f, bank_name: e.target.value }))}
              placeholder="HDFC Bank"
              className="mt-1 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
        </div>
      </div>

      <button
        type="submit"
        disabled={saving}
        className="flex items-center gap-2 px-5 py-2.5 bg-orange-500 text-white rounded-lg font-medium text-sm hover:bg-orange-600 disabled:opacity-50 transition"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : saved ? <Check className="w-4 h-4" /> : <CreditCard className="w-4 h-4" />}
        {saved ? 'Saved!' : 'Save Payout Details'}
      </button>

      <p className="text-xs text-gray-400">
        Your details are encrypted and used only for referral reward payouts. Payouts processed via UPI or NEFT within 7 business days of approval.
      </p>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tab: Leaderboard
// ---------------------------------------------------------------------------

function LeaderboardTab() {
  const [board, setBoard] = useState<LeaderEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient.get('/india-referrals/leaderboard').then(r => setBoard(r.data || [])).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const medals = ['🥇', '🥈', '🥉']

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-orange-500" /></div>
  if (board.length === 0) return <div className="text-center py-12 text-gray-500">No referrals yet. Be the first on the leaderboard!</div>

  return (
    <div className="space-y-2">
      {board.map((entry, i) => (
        <div key={i} className={`flex items-center gap-4 bg-white border rounded-xl px-4 py-3 shadow-sm ${i === 0 ? 'border-yellow-300 bg-yellow-50' : 'border-gray-200'}`}>
          <span className="text-xl w-7 text-center">{medals[i] || `#${i + 1}`}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-gray-800 truncate">{entry.referrer_email.replace(/(.{3}).*@/, '$1***@')}</p>
            <p className="text-xs text-gray-500">{entry.total_referrals} referred · {entry.hired_count} hired</p>
          </div>
          <div className="text-right">
            <p className="font-bold text-green-700 text-sm">{entry.formatted_earned}</p>
            <p className="text-xs text-gray-400">earned</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'my',         label: 'My Referrals',   icon: <Gift className="w-4 h-4" /> },
  { id: 'create',     label: 'Create Link',    icon: <Share2 className="w-4 h-4" /> },
  { id: 'campaigns',  label: 'Campaigns',      icon: <Zap className="w-4 h-4" /> },
  { id: 'badges',     label: 'Badges',         icon: <Award className="w-4 h-4" /> },
  { id: 'upi',        label: 'UPI / Bank',     icon: <CreditCard className="w-4 h-4" /> },
  { id: 'leaderboard',label: 'Leaderboard',    icon: <Trophy className="w-4 h-4" /> },
]

export default function IndiaReferralProgram() {
  const [tab, setTab] = useState('my')
  const [campaign, setCampaign] = useState<Campaign | null>(null)

  useEffect(() => {
    apiClient.get('/india-referrals/campaigns/active').then(r => setCampaign(r.data.campaign)).catch(() => {})
  }, [])

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2.5 bg-orange-100 rounded-xl">
          <Gift className="w-6 h-6 text-orange-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Referral Program <span className="text-orange-500">🇮🇳</span></h1>
          <p className="text-sm text-gray-500">Refer, earn in ₹, share via WhatsApp. Festive bonuses included.</p>
        </div>
      </div>

      {/* Active campaign banner */}
      {campaign && tab !== 'create' && <CampaignBanner campaign={campaign} />}

      {/* Tabs */}
      <div className="flex overflow-x-auto gap-1 bg-gray-100 p-1 rounded-xl mb-6 scrollbar-hide">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition flex-shrink-0 ${
              tab === t.id ? 'bg-white text-orange-600 shadow-sm' : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'my'          && <MyReferralsTab />}
      {tab === 'create'      && <CreateReferralTab campaign={campaign} />}
      {tab === 'campaigns'   && <CampaignsTab />}
      {tab === 'badges'      && <BadgesTab />}
      {tab === 'upi'         && <UPITab />}
      {tab === 'leaderboard' && <LeaderboardTab />}
    </div>
  )
}
