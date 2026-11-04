'use strict'

/**
 * referral-payout.scheduler.js
 *
 * Entry point.  Run with: node referral-payout.scheduler.js
 *
 * Registers processors on the Bull queue, then adds a repeating cron job
 * that fires every day at 10:00 AM IST (04:30 UTC).
 *
 * Required environment variables (copy from backend/.env):
 *   REDIS_URL                — Redis connection string
 *   SUPABASE_URL             — Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY — Service-role key (bypasses RLS)
 *   RAZORPAY_KEY_ID          — Razorpay live key ID      (optional: mock if absent)
 *   RAZORPAY_KEY_SECRET      — Razorpay live key secret  (optional: mock if absent)
 *   RAZORPAY_FUND_ACCOUNT    — RazorpayX account number  (optional: mock if absent)
 *   TWILIO_ACCOUNT_SID       — Twilio SID                (optional: skip WhatsApp if absent)
 *   TWILIO_AUTH_TOKEN        — Twilio auth token          (optional)
 *   TWILIO_WHATSAPP_NUMBER   — Twilio WhatsApp sender    (default: whatsapp:+14155238886)
 */

require('dotenv').config()

const queue               = require('./referral-payout.queue')
const { registerProcessors, SCAN_JOB } = require('./referral-payout.worker')

// 10:00 AM IST = 04:30 UTC
// Bull cron uses cron-parser which supports the `tz` option in Bull 4+.
const CRON_EXPRESSION = '0 10 * * *'
const TIMEZONE        = 'Asia/Kolkata'
const CRON_JOB_ID     = 'daily-bonus-scan'   // stable ID prevents duplicate cron entries

async function start () {
  console.log('[scheduler] Starting referral-payout scheduler...')

  // Register SCAN_JOB and PAY_JOB processors
  registerProcessors()

  // Remove any stale repeatable job with the same cron expression, then add fresh
  await queue.removeRepeatable(SCAN_JOB, { cron: CRON_EXPRESSION, tz: TIMEZONE })
  await queue.add(
    SCAN_JOB,
    {},
    {
      repeat:  { cron: CRON_EXPRESSION, tz: TIMEZONE },
      jobId:   CRON_JOB_ID,
      priority: 1,
    }
  )

  console.log(`[scheduler] Cron registered: "${CRON_EXPRESSION}" (${TIMEZONE}) for job "${SCAN_JOB}"`)
  console.log('[scheduler] Waiting for jobs...')
}

start().catch(err => {
  console.error('[scheduler] Fatal startup error:', err)
  process.exit(1)
})

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('[scheduler] SIGTERM received — closing queue...')
  await queue.close()
  process.exit(0)
})
process.on('SIGINT', async () => {
  console.log('[scheduler] SIGINT received — closing queue...')
  await queue.close()
  process.exit(0)
})
