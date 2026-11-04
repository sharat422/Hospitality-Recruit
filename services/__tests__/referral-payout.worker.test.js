'use strict'

// ── Mock external modules before any require ─────────────────────────────────

jest.mock('../referral-payout.queue', () => ({
  add:   jest.fn().mockResolvedValue({ id: 'mock-job-id' }),
  process: jest.fn(),
  on:    jest.fn(),
  name:  'referral-payout',
}))

jest.mock('../razorpayPayout.service', () => ({
  createRazorpayPayoutService: jest.fn().mockReturnValue(null),  // mock mode by default
  RazorpayPayoutService: jest.fn(),
}))

// ─────────────────────────────────────────────────────────────────────────────

const {
  findEligibleReferrals,
  processReferral,
  sendWhatsAppNotification,
  runScanJob,
  hindiBonusMessage,
  formatINR,
  cutoffDate,
  RETENTION_DAYS,
  BONUS_PAID_STATUS,
} = require('../referral-payout.worker')

const mockQueue = require('../referral-payout.queue')

// ─────────────────────────────────────────────────────────────────────────────
// Shared fixtures
// ─────────────────────────────────────────────────────────────────────────────

const NINETY_FIVE_DAYS_AGO = new Date(
  Date.now() - 95 * 24 * 60 * 60 * 1000
).toISOString()

const REFERRAL = {
  id:                       'ref-uuid-001',
  referral_code:            'REF-BONUS001',
  referrer_id:              'user-uuid-001',
  hire_date:                NINETY_FIVE_DAYS_AGO,
  retention_bonus_amount:   2000,
  retention_bonus_status:   'ELIGIBLE',
  bonus_paid_at:            null,
}

const USER = { email: 'rahul@hotel.in', full_name: 'Rahul Kumar', phone: '+919876543210' }
const UPI  = { upi_id: 'rahul@okaxis', is_verified: true, razorpay_fund_account_id: null }
const PAID_PAYOUT = {
  payoutId:       'pout_bonus_001',
  internalStatus: 'PAID',
  amountPaise:    200_000,
  mock:           false,
}

// ─────────────────────────────────────────────────────────────────────────────
// Supabase mock factory
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Build a Supabase client mock where each `from(table)` call pops the next
 * result from the configured list for that table.
 *
 * Per-result keys:
 *   order  — result of .select()...order()    (list queries)
 *   single — result of .select()...single()   (single-row queries + re-checks)
 *   update — result of .update()...select()   (atomic UPDATE)
 */
function makeSupabase (tableResults = {}) {
  const callIndex = {}

  function makeUpdateChain (val) {
    return {
      eq:     jest.fn().mockReturnThis(),
      is:     jest.fn().mockReturnThis(),
      select: jest.fn().mockResolvedValue(val),
    }
  }

  function makeChain (val) {
    return {
      select: jest.fn().mockReturnThis(),
      eq:     jest.fn().mockReturnThis(),
      lte:    jest.fn().mockReturnThis(),
      is:     jest.fn().mockReturnThis(),
      gt:     jest.fn().mockReturnThis(),
      order:  jest.fn().mockResolvedValue(val.order   ?? { data: [], error: null }),
      single: jest.fn().mockResolvedValue(val.single  ?? { data: null, error: null }),
      update: jest.fn().mockReturnValue(makeUpdateChain(val.update ?? { data: [], error: null })),
    }
  }

  return {
    from: jest.fn().mockImplementation(table => {
      callIndex[table] = (callIndex[table] ?? -1) + 1
      const list = tableResults[table] ?? [{}]
      const cfg  = list[callIndex[table]] ?? list[list.length - 1] ?? {}
      return makeChain(cfg)
    }),
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

/** Build a mock Razorpay service that resolves to PAID_PAYOUT. */
function makeMockRzp (override = {}) {
  return { processReferralPayout: jest.fn().mockResolvedValue({ ...PAID_PAYOUT, ...override }) }
}

/** Build a minimal Twilio mock. */
function makeMockTwilio () {
  return { messages: { create: jest.fn().mockResolvedValue({ sid: 'SM001' }) } }
}

/** Silent logger for tests. */
const silentLogger = { info: jest.fn(), warn: jest.fn(), error: jest.fn() }

// ─────────────────────────────────────────────────────────────────────────────
// formatINR
// ─────────────────────────────────────────────────────────────────────────────

describe('formatINR', () => {
  it.each([
    [0,         '0'],
    [100,       '100'],
    [1000,      '1,000'],
    [2000,      '2,000'],
    [50000,     '50,000'],
    [100000,    '1,00,000'],
    [1500000,   '15,00,000'],
  ])('formats %d → "%s"', (n, expected) => {
    expect(formatINR(n)).toBe(expected)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// hindiBonusMessage
// ─────────────────────────────────────────────────────────────────────────────

describe('hindiBonusMessage', () => {
  const msg = hindiBonusMessage({
    name:         'Rahul Kumar',
    amountINR:    2000,
    upiId:        'rahul@okaxis',
    referralCode: 'REF-BONUS001',
    payoutId:     'pout_bonus_001',
  })

  it('contains the employee name', ()        => expect(msg).toContain('Rahul Kumar'))
  it('contains the ₹ amount',    ()          => expect(msg).toContain('2,000'))
  it('contains the UPI ID',      ()          => expect(msg).toContain('rahul@okaxis'))
  it('contains the referral code', ()        => expect(msg).toContain('REF-BONUS001'))
  it('contains the Razorpay payout ID', ()   => expect(msg).toContain('pout_bonus_001'))
  it('contains Hindi text',      ()          => expect(msg).toContain('बधाई हो'))
  it('mentions UPI transfer in Hindi', ()    => expect(msg).toContain('UPI पर transfer'))
  it('mentions days in Hindi', ()            => expect(msg).toContain('business days'))
  it('includes HospRecruit branding', ()     => expect(msg).toContain('HospRecruit'))
})

// ─────────────────────────────────────────────────────────────────────────────
// cutoffDate
// ─────────────────────────────────────────────────────────────────────────────

describe('cutoffDate', () => {
  it(`returns a date ${RETENTION_DAYS} days in the past`, () => {
    const d     = new Date(cutoffDate())
    const diff  = Date.now() - d.getTime()
    const days  = diff / (24 * 60 * 60 * 1000)
    expect(days).toBeCloseTo(RETENTION_DAYS, 0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// findEligibleReferrals
// ─────────────────────────────────────────────────────────────────────────────

describe('findEligibleReferrals', () => {
  it('returns eligible rows from DB', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: [REFERRAL], error: null } }],
    })
    const result = await findEligibleReferrals(supa)
    expect(result).toHaveLength(1)
    expect(result[0].id).toBe(REFERRAL.id)
  })

  it('passes correct filters (eq, lte, is, gt)', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: [], error: null } }],
    })
    await findEligibleReferrals(supa)

    const chain = supa.from.mock.results[0].value
    expect(chain.eq).toHaveBeenCalledWith('status', 'HIRED')
    expect(chain.lte).toHaveBeenCalledWith('hire_date', expect.any(String))
    expect(chain.is).toHaveBeenCalledWith('bonus_paid_at', null)
    expect(chain.gt).toHaveBeenCalledWith('retention_bonus_amount', 0)
  })

  it('returns [] when there are no eligible referrals', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: [], error: null } }],
    })
    expect(await findEligibleReferrals(supa)).toEqual([])
  })

  it('throws when Supabase returns an error', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: null, error: { message: 'DB down' } } }],
    })
    await expect(findEligibleReferrals(supa)).rejects.toThrow('DB down')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// sendWhatsAppNotification
// ─────────────────────────────────────────────────────────────────────────────

describe('sendWhatsAppNotification', () => {
  const params = {
    name: 'Rahul', amountINR: 2000, upiId: 'r@upi',
    referralCode: 'REF-1', payoutId: 'pout_1',
  }

  it('sends via Twilio when client and phone are provided', async () => {
    const tw = makeMockTwilio()
    const sent = await sendWhatsAppNotification(tw, '+919876543210', params)
    expect(sent).toBe(true)
    expect(tw.messages.create).toHaveBeenCalledWith(
      expect.objectContaining({
        to: 'whatsapp:+919876543210',
        body: expect.stringContaining('Rahul'),
      })
    )
  })

  it('adds +91 prefix when number lacks country code', async () => {
    const tw = makeMockTwilio()
    await sendWhatsAppNotification(tw, '9876543210', params)
    const call = tw.messages.create.mock.calls[0][0]
    expect(call.to).toBe('whatsapp:+919876543210')
  })

  it('returns false and does not call Twilio when client is null', async () => {
    const sent = await sendWhatsAppNotification(null, '+91123', params)
    expect(sent).toBe(false)
  })

  it('returns false and does not call Twilio when phone is null', async () => {
    const tw = makeMockTwilio()
    const sent = await sendWhatsAppNotification(tw, null, params)
    expect(sent).toBe(false)
    expect(tw.messages.create).not.toHaveBeenCalled()
  })

  it('propagates Twilio errors', async () => {
    const tw = { messages: { create: jest.fn().mockRejectedValue(new Error('Twilio error')) } }
    await expect(sendWhatsAppNotification(tw, '+91999', params)).rejects.toThrow('Twilio error')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// processReferral
// ─────────────────────────────────────────────────────────────────────────────

describe('processReferral', () => {
  // Common setup: referrals (re-check + update), users, upi
  function makeSupa ({ recheck = null, updateRows = [{ id: REFERRAL.id }] } = {}) {
    return makeSupabase({
      referrals: [
        { single: { data: { bonus_paid_at: recheck }, error: null } },    // re-check
        { update: { data: updateRows, error: null } },                     // atomic update
      ],
      users:                 [{ single: { data: USER, error: null } }],
      employee_upi_details:  [{ single: { data: UPI,  error: null } }],
    })
  }

  it('happy path — pays, updates DB, sends WhatsApp, returns success', async () => {
    const supa = makeSupa()
    const rzp  = makeMockRzp()
    const tw   = makeMockTwilio()

    const result = await processReferral(supa, rzp, tw, REFERRAL, silentLogger)

    expect(result.success).toBe(true)
    expect(result.payoutId).toBe('pout_bonus_001')
    expect(result.amountINR).toBe(2000)
    expect(rzp.processReferralPayout).toHaveBeenCalledWith(
      expect.objectContaining({
        upiId:     'rahul@okaxis',
        amountInr: 2000,
      })
    )
    expect(tw.messages.create).toHaveBeenCalled()
  })

  it('uses "bonus-" prefix in Razorpay referenceId for idempotency separation', async () => {
    const supa = makeSupa()
    const rzp  = makeMockRzp()
    await processReferral(supa, rzp, null, REFERRAL, silentLogger)

    const arg = rzp.processReferralPayout.mock.calls[0][0]
    expect(arg.referralId).toMatch(/^bonus-/)
  })

  it('idempotency — skips when re-check finds bonus_paid_at already set', async () => {
    const supa = makeSupa({ recheck: '2026-04-01T00:00:00Z' })
    const rzp  = makeMockRzp()
    const result = await processReferral(supa, rzp, null, REFERRAL, silentLogger)

    expect(result.skipped).toBe(true)
    expect(result.reason).toBe('already_paid')
    expect(rzp.processReferralPayout).not.toHaveBeenCalled()
  })

  it('concurrent guard — skips when update returns 0 rows', async () => {
    const supa = makeSupa({ updateRows: [] })   // 0 rows updated = concurrent win
    const rzp  = makeMockRzp()
    const result = await processReferral(supa, rzp, null, REFERRAL, silentLogger)

    expect(result.skipped).toBe(true)
    expect(result.reason).toBe('concurrent_payment')
  })

  it('skips with no_upi when UPI details are missing', async () => {
    const supa = makeSupabase({
      referrals:            [{ single: { data: { bonus_paid_at: null }, error: null } }],
      users:                [{ single: { data: USER, error: null } }],
      employee_upi_details: [{ single: { data: null, error: null } }],  // no UPI
    })
    const result = await processReferral(supa, null, null, REFERRAL, silentLogger)
    expect(result.skipped).toBe(true)
    expect(result.reason).toBe('no_upi')
  })

  it('skips with upi_not_verified when UPI is unverified', async () => {
    const supa = makeSupabase({
      referrals:            [{ single: { data: { bonus_paid_at: null }, error: null } }],
      users:                [{ single: { data: USER, error: null } }],
      employee_upi_details: [{ single: { data: { ...UPI, is_verified: false }, error: null } }],
    })
    const result = await processReferral(supa, null, null, REFERRAL, silentLogger)
    expect(result.skipped).toBe(true)
    expect(result.reason).toBe('upi_not_verified')
  })

  it('mock mode — returns PAID without calling Razorpay when rzp is null', async () => {
    const supa = makeSupa()
    const result = await processReferral(supa, null, null, REFERRAL, silentLogger)
    expect(result.success).toBe(true)
    expect(result.mock).toBe(true)
    expect(result.payoutId).toMatch(/^MOCK-BONUS-/)
  })

  it('returns error when Razorpay throws — does not update bonus_paid_at', async () => {
    const supa = makeSupa()
    const rzp  = { processReferralPayout: jest.fn().mockRejectedValue(new Error('Network')) }
    const result = await processReferral(supa, rzp, null, REFERRAL, silentLogger)

    expect(result.error).toBe(true)
    expect(result.reason).toBe('razorpay_failed')
    // .update() must not have been called on any chain — early return before that step
    const updateWasCalled = supa.from.mock.results.some(r => r.value.update.mock.calls.length > 0)
    expect(updateWasCalled).toBe(false)
  })

  it('updates DB with correct status fields on success', async () => {
    const supa = makeSupa()
    await processReferral(supa, makeMockRzp(), null, REFERRAL, silentLogger)

    // The last chain that had .update() called should have received the right payload
    const updateChain = supa.from.mock.results
      .map(r => r.value)
      .find(chain => chain.update.mock.calls.length > 0)
    expect(updateChain.update).toHaveBeenCalledWith(
      expect.objectContaining({
        status:                 BONUS_PAID_STATUS,
        retention_bonus_status: 'PAID',
        bonus_payout_id:        'pout_bonus_001',
      })
    )
    expect(updateChain.update.mock.calls[0][0].bonus_paid_at).toBeTruthy()
  })

  it('WhatsApp failure does not prevent payment success', async () => {
    const supa = makeSupa()
    const rzp  = makeMockRzp()
    const tw   = { messages: { create: jest.fn().mockRejectedValue(new Error('Twilio down')) } }

    const result = await processReferral(supa, rzp, tw, REFERRAL, silentLogger)

    // Payment still succeeds even though WhatsApp threw
    expect(result.success).toBe(true)
    expect(silentLogger.warn).toHaveBeenCalledWith(
      expect.stringContaining('WhatsApp notification failed')
    )
  })

  it('throws when DB update itself errors', async () => {
    const supa = makeSupabase({
      referrals: [
        { single: { data: { bonus_paid_at: null }, error: null } },
        { update: { data: null, error: { message: 'DB constraint violated' } } },
      ],
      users:                [{ single: { data: USER, error: null } }],
      employee_upi_details: [{ single: { data: UPI,  error: null } }],
    })

    await expect(
      processReferral(supa, makeMockRzp(), null, REFERRAL, silentLogger)
    ).rejects.toMatchObject({ message: 'DB constraint violated' })
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// runScanJob
// ─────────────────────────────────────────────────────────────────────────────

describe('runScanJob', () => {
  beforeEach(() => mockQueue.add.mockClear())

  it('enqueues one PAY_JOB per eligible referral', async () => {
    const referrals = [
      { ...REFERRAL, id: 'ref-001' },
      { ...REFERRAL, id: 'ref-002' },
    ]
    const supa = makeSupabase({
      referrals: [{ order: { data: referrals, error: null } }],
    })

    const result = await runScanJob(supa, mockQueue, silentLogger)

    expect(result.enqueuedCount).toBe(2)
    expect(result.referralIds).toEqual(['ref-001', 'ref-002'])
    expect(mockQueue.add).toHaveBeenCalledTimes(2)
  })

  it('uses referral ID as Bull job ID for deduplication', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: [REFERRAL], error: null } }],
    })
    await runScanJob(supa, mockQueue, silentLogger)

    const opts = mockQueue.add.mock.calls[0][2]
    expect(opts.jobId).toBe(`pay-${REFERRAL.id}`)
  })

  it('configures 3 retry attempts with exponential backoff', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: [REFERRAL], error: null } }],
    })
    await runScanJob(supa, mockQueue, silentLogger)

    const opts = mockQueue.add.mock.calls[0][2]
    expect(opts.attempts).toBe(3)
    expect(opts.backoff.type).toBe('exponential')
  })

  it('returns { enqueuedCount: 0 } when no referrals are eligible', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: [], error: null } }],
    })
    const result = await runScanJob(supa, mockQueue, silentLogger)
    expect(result.enqueuedCount).toBe(0)
    expect(mockQueue.add).not.toHaveBeenCalled()
  })

  it('propagates DB errors from findEligibleReferrals', async () => {
    const supa = makeSupabase({
      referrals: [{ order: { data: null, error: { message: 'timeout' } } }],
    })
    await expect(runScanJob(supa, mockQueue, silentLogger)).rejects.toThrow('timeout')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

describe('constants', () => {
  it('RETENTION_DAYS is 90', () => expect(RETENTION_DAYS).toBe(90))
  it('BONUS_PAID_STATUS is "BONUS_PAID"', () => expect(BONUS_PAID_STATUS).toBe('BONUS_PAID'))
})
