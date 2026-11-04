'use strict'

/**
 * referral-payout.worker.js
 *
 * Processes the daily referral retention-bonus payout queue.
 *
 * Two job types:
 *   SCAN_JOB — runs daily at 10 AM IST, queries DB for eligible referrals
 *              and enqueues an individual PAY_JOB for each one.
 *   PAY_JOB  — pays one referral's 90-day retention bonus via Razorpay,
 *              updates the DB, and sends a Hindi WhatsApp notification.
 *
 * Idempotency:
 *   1. Bull job ID = "pay-<referralId>" (deduplicates queue entries).
 *   2. On job start, re-fetches bonus_paid_at from DB and exits if already set.
 *   3. DB UPDATE uses WHERE bonus_paid_at IS NULL — a concurrent worker that
 *      arrives first will update 0 rows, signalling the race was lost safely.
 *
 * Exports (all pure functions — used directly in tests without starting Bull):
 *   findEligibleReferrals, processReferral, sendWhatsAppNotification,
 *   runScanJob, registerProcessors, hindiBonusMessage, formatINR
 */

require('dotenv').config()

const { createClient: createSupabase } = require('@supabase/supabase-js')
const twilio                           = require('twilio')
const { createRazorpayPayoutService }  = require('./razorpayPayout.service')
const queue                            = require('./referral-payout.queue')

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const RETENTION_DAYS  = 90
const BONUS_PAID_STATUS = 'BONUS_PAID'
const SCAN_JOB        = 'scan-eligible-referrals'
const PAY_JOB         = 'pay-referral'

// ─────────────────────────────────────────────────────────────────────────────
// Dependency factories (swappable in tests via registerProcessors)
// ─────────────────────────────────────────────────────────────────────────────

function makeSupabase () {
  const url = process.env.SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY   // service-role key bypasses RLS
  if (!url || !key) throw new Error('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set')
  return createSupabase(url, key)
}

function makeRazorpay () {
  return createRazorpayPayoutService(
    process.env.RAZORPAY_KEY_ID,
    process.env.RAZORPAY_KEY_SECRET,
    process.env.RAZORPAY_FUND_ACCOUNT
  )
}

function makeTwilio () {
  const sid   = process.env.TWILIO_ACCOUNT_SID
  const token = process.env.TWILIO_AUTH_TOKEN
  if (!sid || !sid.startsWith('AC') || !token) return null   // placeholder creds → mock
  return twilio(sid, token)
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** ISO timestamp for exactly 90 days ago. */
function cutoffDate () {
  return new Date(Date.now() - RETENTION_DAYS * 24 * 60 * 60 * 1000).toISOString()
}

/** Format a number using the Indian comma convention (no ₹ prefix). */
function formatINR (amount) {
  const s = Math.floor(amount).toString()
  if (s.length <= 3) return s
  const last3 = s.slice(-3)
  let rest = s.slice(0, -3)
  const groups = []
  while (rest.length > 2) { groups.unshift(rest.slice(-2)); rest = rest.slice(0, -2) }
  if (rest) groups.unshift(rest)
  return `${groups.join(',')},${last3}`
}

/**
 * Build the Hindi WhatsApp bonus-paid notification message.
 * Returned as a plain string so it can be tested independently.
 */
function hindiBonusMessage ({ name, amountINR, upiId, referralCode, payoutId }) {
  return [
    `🎉 बधाई हो ${name}!`,
    '',
    `आपका referral bonus ₹${formatINR(amountINR)} आपके UPI पर transfer हो गया है।`,
    `📱 UPI ID: ${upiId}`,
    `📋 Referral Code: ${referralCode}`,
    `🔖 Razorpay Ref: ${payoutId}`,
    '',
    'पैसे 1-3 business days में आ जाएंगे। ✨',
    '',
    '- HospRecruit Team 🙏',
  ].join('\n')
}

// ─────────────────────────────────────────────────────────────────────────────
// Core DB + API functions (exported for unit testing)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Query referrals that are eligible for the 90-day retention bonus.
 *
 * Criteria:
 *   status = 'HIRED'
 *   hire_date ≤ now − 90 days
 *   bonus_paid_at IS NULL            (not yet paid)
 *   retention_bonus_amount > 0       (a bonus amount is configured)
 */
async function findEligibleReferrals (supabase) {
  const { data, error } = await supabase
    .from('referrals')
    .select('id, referral_code, referrer_id, hire_date, retention_bonus_amount')
    .eq('status', 'HIRED')
    .lte('hire_date', cutoffDate())
    .is('bonus_paid_at', null)
    .gt('retention_bonus_amount', 0)
    .order('hire_date', { ascending: true })

  if (error) throw new Error(`findEligibleReferrals DB error: ${error.message}`)
  return data ?? []
}

/**
 * Fetch employee profile and UPI details for a referrer user ID.
 * Returns { user, upi } — either can be null if the record is missing.
 */
async function getEmployeeDetails (supabase, userId) {
  const [userRes, upiRes] = await Promise.all([
    supabase.from('users')
      .select('email, full_name, phone')
      .eq('id', userId)
      .single(),
    supabase.from('employee_upi_details')
      .select('upi_id, is_verified, razorpay_fund_account_id')
      .eq('user_id', userId)
      .single(),
  ])
  return { user: userRes.data, upi: upiRes.data }
}

/**
 * Send the Hindi WhatsApp bonus-paid notification via Twilio.
 *
 * @param  {object|null} twilioClient  Twilio REST client (null → skip)
 * @param  {string}      toPhone       Recipient phone (with or without +91)
 * @param  {object}      params        Template variables
 * @returns {boolean}    true if sent, false if skipped
 */
async function sendWhatsAppNotification (twilioClient, toPhone, params) {
  if (!twilioClient || !toPhone) return false

  const to   = toPhone.startsWith('+') ? toPhone : `+91${toPhone}`
  const from = process.env.TWILIO_WHATSAPP_NUMBER || 'whatsapp:+14155238886'
  const fromWA = from.startsWith('whatsapp:') ? from : `whatsapp:${from}`

  await twilioClient.messages.create({
    from: fromWA,
    to:   `whatsapp:${to}`,
    body: hindiBonusMessage(params),
  })
  return true
}

/**
 * Process a single referral: verify UPI → pay → update DB → notify.
 *
 * Idempotency guarantees:
 *   • Re-fetches bonus_paid_at before doing anything (handles stale job data).
 *   • DB UPDATE uses `.is('bonus_paid_at', null)` — if a concurrent worker
 *     already paid, the update returns 0 rows and we return { skipped }.
 *
 * @param  {object}      supabase    Supabase client (service role)
 * @param  {object|null} rzp         RazorpayPayoutService (null → mock mode)
 * @param  {object|null} twClient    Twilio client (null → skip WhatsApp)
 * @param  {object}      referral    Row from findEligibleReferrals
 * @param  {object}      [logger]    Optional logger (default: console)
 * @returns {object}  { success, skipped, error, payoutId, amountINR, mock }
 */
async function processReferral (supabase, rzp, twClient, referral, logger = console) {
  const { id: referralId, referral_code, referrer_id, retention_bonus_amount } = referral

  // ── Idempotency re-check ────────────────────────────────────────────────────
  const { data: fresh } = await supabase
    .from('referrals')
    .select('bonus_paid_at')
    .eq('id', referralId)
    .single()

  if (fresh?.bonus_paid_at) {
    logger.info(`[worker] Skip ${referralId} — already paid at ${fresh.bonus_paid_at}`)
    return { skipped: true, reason: 'already_paid' }
  }

  // ── Validate employee UPI ───────────────────────────────────────────────────
  const { user, upi } = await getEmployeeDetails(supabase, referrer_id)

  if (!upi?.upi_id) {
    logger.warn(`[worker] No UPI ID for referrer ${referrer_id} (referral ${referralId})`)
    return { skipped: true, reason: 'no_upi' }
  }
  if (!upi.is_verified) {
    logger.warn(`[worker] UPI not verified for referrer ${referrer_id} (referral ${referralId})`)
    return { skipped: true, reason: 'upi_not_verified' }
  }

  // ── Trigger Razorpay payout (or deterministic mock) ────────────────────────
  const employeeName = user?.full_name || user?.email || 'Employee'
  let payoutResult

  try {
    if (!rzp) {
      // Mock payouts are never allowed silently in production.
      if (process.env.NODE_ENV === 'production' && process.env.REFERRAL_PAYOUT_MOCK_MODE !== 'true') {
        return { error: true, reason: 'razorpay_not_configured', referralId }
      }
      payoutResult = {
        payoutId:       `MOCK-BONUS-${referralId.slice(0, 8).toUpperCase()}`,
        internalStatus: 'PAID',
        amountPaise:    Math.round(retention_bonus_amount * 100),
        mock:           true,
      }
    } else {
      payoutResult = await rzp.processReferralPayout({
        // Prefix "bonus-" so Razorpay idempotency key is distinct from hire payout
        referralId:            `bonus-${referralId}`,
        upiId:                 upi.upi_id,
        amountInr:             retention_bonus_amount,
        employeeName,
        employeeEmail:         user?.email ?? null,
        existingFundAccountId: upi.razorpay_fund_account_id ?? null,
      })
    }
  } catch (err) {
    logger.error(`[worker] Razorpay failed for ${referralId}: ${err.message}`)
    // Don't set bonus_paid_at — allow the job to retry tomorrow
    return { error: true, reason: 'razorpay_failed', referralId, message: err.message }
  }

  // ── Atomic DB update — prevents double-pay on race conditions ───────────────
  const now = new Date().toISOString()
  const paid = payoutResult.internalStatus === 'PAID'
  const payoutUpdate = {
    payout_status:      payoutResult.internalStatus,
    bonus_payout_id:    payoutResult.payoutId,
    razorpay_payout_id: payoutResult.payoutId,
  }
  if (paid) Object.assign(payoutUpdate, {
    status:                 BONUS_PAID_STATUS,
    retention_bonus_status: 'PAID',
    bonus_paid_at:          now,
  })
  const { data: updated, error: updateErr } = await supabase
    .from('referrals')
    .update(payoutUpdate)
    .eq('id', referralId)
    .is('bonus_paid_at', null)          // idempotency guard — the critical WHERE clause
    .select('id')

  if (updateErr) {
    logger.error(`[worker] DB update failed for ${referralId}: ${updateErr.message}`)
    throw updateErr
  }

  if (!updated?.length) {
    logger.warn(`[worker] Concurrent payment detected for ${referralId} — skipping`)
    return { skipped: true, reason: 'concurrent_payment' }
  }

  if (!paid) {
    logger.info(`[worker] Bonus payout pending: ${payoutResult.payoutId} for referral ${referralId}`)
    return { success: false, pending: true, referralId, payoutId: payoutResult.payoutId, amountINR: retention_bonus_amount }
  }
  logger.info(`[worker] Bonus paid: ${payoutResult.payoutId} for referral ${referralId}`)

  // ── WhatsApp notification (non-critical — failure never rolls back payment) ──
  try {
    const sent = await sendWhatsAppNotification(twClient, user?.phone ?? null, {
      name:         employeeName,
      amountINR:    retention_bonus_amount,
      upiId:        upi.upi_id,
      referralCode: referral_code,
      payoutId:     payoutResult.payoutId,
    })
    if (!sent) logger.warn(`[worker] WhatsApp skipped — no phone or Twilio client`)
  } catch (err) {
    // Log but swallow — the payment is already committed
    logger.warn(`[worker] WhatsApp notification failed for ${referralId}: ${err.message}`)
  }

  return {
    success:   true,
    referralId,
    payoutId:  payoutResult.payoutId,
    amountINR: retention_bonus_amount,
    mock:      payoutResult.mock ?? false,
  }
}

/**
 * Scan for eligible referrals and enqueue individual pay jobs.
 * Runs as the SCAN_JOB processor.
 */
async function runScanJob (supabase, q, logger = console) {
  logger.info('[worker] Scanning for referrals eligible for 90-day bonus...')
  const eligible = await findEligibleReferrals(supabase)
  logger.info(`[worker] Found ${eligible.length} eligible referral(s)`)

  const enqueued = await Promise.all(
    eligible.map(ref =>
      q.add(
        PAY_JOB,
        { referral: ref },
        {
          // jobId = deduplication key: Bull silently drops duplicate IDs
          jobId:   `pay-${ref.id}`,
          attempts: 3,
          backoff:  { type: 'exponential', delay: 10_000 },
        }
      )
    )
  )

  return { enqueuedCount: enqueued.length, referralIds: eligible.map(r => r.id) }
}

// ─────────────────────────────────────────────────────────────────────────────
// Queue processor registration
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Register Bull processors.  Call once at startup.
 * Pass overrides for dependency injection in integration tests.
 *
 * @param {object} [opts]
 * @param {object} [opts.supabase]     Override Supabase client
 * @param {object} [opts.rzp]          Override Razorpay service (null = mock)
 * @param {object} [opts.twilioClient] Override Twilio client
 * @param {object} [opts.logger]       Override logger
 */
function registerProcessors ({ supabase, rzp, twilioClient, logger = console } = {}) {
  const sb = supabase     ?? makeSupabase()
  const rz = rzp          ?? makeRazorpay()
  const tw = twilioClient ?? makeTwilio()

  queue.process(SCAN_JOB, async (_job) => runScanJob(sb, queue, logger))

  queue.process(PAY_JOB, async (job) => {
    const { referral } = job.data
    logger.info(`[worker] Processing PAY_JOB for referral ${referral.id}`)
    return processReferral(sb, rz, tw, referral, logger)
  })

  queue.on('completed', (job, result) => {
    if (result?.success) {
      logger.info(`[worker] Job ${job.id} ✓ paid ${result.payoutId}  ₹${result.amountINR}`)
    } else if (result?.skipped) {
      logger.info(`[worker] Job ${job.id} skipped: ${result.reason}`)
    }
  })

  queue.on('failed', (job, err) => {
    logger.error(`[worker] Job ${job.id} failed (attempt ${job.attemptsMade}): ${err.message}`)
  })

  logger.info(`[worker] Registered processors for queue "${queue.name}"`)
}

// ─────────────────────────────────────────────────────────────────────────────
// Exports
// ─────────────────────────────────────────────────────────────────────────────

module.exports = {
  // Business logic — all pure, exported for unit testing
  findEligibleReferrals,
  getEmployeeDetails,
  processReferral,
  sendWhatsAppNotification,
  runScanJob,
  hindiBonusMessage,
  formatINR,
  cutoffDate,
  // Queue processor wiring
  registerProcessors,
  // Constants
  RETENTION_DAYS,
  BONUS_PAID_STATUS,
  SCAN_JOB,
  PAY_JOB,
}
