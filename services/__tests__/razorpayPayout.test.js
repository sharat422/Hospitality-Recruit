'use strict'

jest.mock('axios')

const axios = require('axios')
const { RazorpayPayoutService, createRazorpayPayoutService, PAYOUT_STATUS_MAP } = require('../razorpayPayout.service')

// ── Shared mock axios instance ────────────────────────────────────────────────

const mockPost = jest.fn()
const mockGet  = jest.fn()

axios.create.mockReturnValue({ post: mockPost, get: mockGet })

const VALID_OPTS = {
  keyId:         'rzp_test_key',
  keySecret:     'rzp_test_secret',
  accountNumber: '7894561230000012',
}

// ── Razorpay response fixtures ────────────────────────────────────────────────

const CONTACT_FIXTURE = {
  id: 'cont_abc123', entity: 'contact', name: 'Rahul Kumar', type: 'employee',
}
const FUND_ACCOUNT_FIXTURE = {
  id: 'fa_xyz456', entity: 'fund_account', contact_id: 'cont_abc123',
  account_type: 'vpa', vpa: { id: 'vpa_001', address: 'rahul@okaxis' },
}
const PAYOUT_PROCESSING_FIXTURE = {
  id: 'pout_999', entity: 'payout', fund_account_id: 'fa_xyz456',
  amount: 500000, currency: 'INR', status: 'processing', mode: 'UPI',
  reference_id: 'ref-001', notes: { referral_id: 'ref-001', upi_id: 'rahul@okaxis' },
}
const PAYOUT_PROCESSED_FIXTURE  = { ...PAYOUT_PROCESSING_FIXTURE, status: 'processed' }
const PAYOUT_FAILED_FIXTURE     = { ...PAYOUT_PROCESSING_FIXTURE, status: 'failed' }
const PAYOUT_REVERSED_FIXTURE   = { ...PAYOUT_PROCESSING_FIXTURE, status: 'reversed' }
const PAYOUT_QUEUED_FIXTURE     = { ...PAYOUT_PROCESSING_FIXTURE, status: 'queued' }

beforeEach(() => {
  mockPost.mockReset()
  mockGet.mockReset()
})

// ═══════════════════════════════════════════════════════════════════════════════
// Constructor
// ═══════════════════════════════════════════════════════════════════════════════

describe('constructor', () => {
  it('throws when keyId is missing', () => {
    expect(() => new RazorpayPayoutService({ keySecret: 's', accountNumber: 'n' }))
      .toThrow('keyId')
  })
  it('throws when keySecret is missing', () => {
    expect(() => new RazorpayPayoutService({ keyId: 'k', accountNumber: 'n' }))
      .toThrow('keySecret')
  })
  it('throws when accountNumber is missing', () => {
    expect(() => new RazorpayPayoutService({ keyId: 'k', keySecret: 's' }))
      .toThrow('accountNumber')
  })
  it('creates instance with valid opts', () => {
    expect(() => new RazorpayPayoutService(VALID_OPTS)).not.toThrow()
  })
  it('does not expose key credentials on the instance', () => {
    const svc = new RazorpayPayoutService(VALID_OPTS)
    const json = JSON.stringify(svc)
    expect(json).not.toContain('rzp_test_key')
    expect(json).not.toContain('rzp_test_secret')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// inrToPaise
// ═══════════════════════════════════════════════════════════════════════════════

describe('inrToPaise', () => {
  it.each([
    [1,        100],
    [5000,     500000],
    [0.5,      50],
    [2500,     250000],
    [99.99,    9999],
    [0,        0],
    [100000,   10000000],
  ])('converts ₹%d → %d paise', (inr, paise) => {
    expect(RazorpayPayoutService.inrToPaise(inr)).toBe(paise)
  })

  it('rounds half-paise to nearest', () => {
    // ₹0.005 = 0.5 paise → rounds to 1 paise
    expect(RazorpayPayoutService.inrToPaise(0.005)).toBe(1)
  })

  it('throws for negative amounts', () => {
    expect(() => RazorpayPayoutService.inrToPaise(-1)).toThrow(TypeError)
  })

  it('throws for non-finite values', () => {
    expect(() => RazorpayPayoutService.inrToPaise(Infinity)).toThrow(TypeError)
    expect(() => RazorpayPayoutService.inrToPaise(NaN)).toThrow(TypeError)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// mapStatus
// ═══════════════════════════════════════════════════════════════════════════════

describe('mapStatus', () => {
  const cases = Object.entries(PAYOUT_STATUS_MAP)
  it.each(cases)('"%s" → "%s"', (rzp, internal) => {
    expect(RazorpayPayoutService.mapStatus(rzp)).toBe(internal)
  })

  it('returns UNKNOWN for unrecognised status', () => {
    expect(RazorpayPayoutService.mapStatus('some_future_status')).toBe('UNKNOWN')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// createContact
// ═══════════════════════════════════════════════════════════════════════════════

describe('createContact', () => {
  let svc

  beforeEach(() => { svc = new RazorpayPayoutService(VALID_OPTS) })

  it('POSTs to /contacts and returns the entity', async () => {
    mockPost.mockResolvedValueOnce({ data: CONTACT_FIXTURE })

    const result = await svc.createContact({
      name: 'Rahul Kumar', email: 'rahul@hotel.in', referenceId: 'emp-uuid',
    })

    expect(mockPost).toHaveBeenCalledWith('/contacts', expect.objectContaining({
      name:         'Rahul Kumar',
      type:         'employee',
      email:        'rahul@hotel.in',
      reference_id: 'emp-uuid',
    }))
    expect(result.id).toBe('cont_abc123')
  })

  it('omits email/phone from payload when not provided', async () => {
    mockPost.mockResolvedValueOnce({ data: CONTACT_FIXTURE })
    await svc.createContact({ name: 'No Email' })

    const [, payload] = mockPost.mock.calls[0]
    expect(payload).not.toHaveProperty('email')
    expect(payload).not.toHaveProperty('contact')
  })

  it('falls back to "Employee" when name is empty', async () => {
    mockPost.mockResolvedValueOnce({ data: CONTACT_FIXTURE })
    await svc.createContact({})

    const [, payload] = mockPost.mock.calls[0]
    expect(payload.name).toBe('Employee')
  })

  it('propagates network errors', async () => {
    mockPost.mockRejectedValueOnce(new Error('Network error'))
    await expect(svc.createContact({ name: 'X' })).rejects.toThrow('Network error')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// createFundAccount
// ═══════════════════════════════════════════════════════════════════════════════

describe('createFundAccount', () => {
  let svc

  beforeEach(() => { svc = new RazorpayPayoutService(VALID_OPTS) })

  it('POSTs to /fund_accounts with vpa account_type', async () => {
    mockPost.mockResolvedValueOnce({ data: FUND_ACCOUNT_FIXTURE })

    const result = await svc.createFundAccount({
      contactId: 'cont_abc123', upiId: 'rahul@okaxis',
    })

    expect(mockPost).toHaveBeenCalledWith('/fund_accounts', {
      contact_id:   'cont_abc123',
      account_type: 'vpa',
      vpa:          { address: 'rahul@okaxis' },
    })
    expect(result.id).toBe('fa_xyz456')
    expect(result.vpa.address).toBe('rahul@okaxis')
  })

  it('propagates Razorpay API errors', async () => {
    mockPost.mockRejectedValueOnce(new Error('Invalid VPA'))
    await expect(svc.createFundAccount({ contactId: 'c', upiId: 'bad' })).rejects.toThrow()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// createPayout
// ═══════════════════════════════════════════════════════════════════════════════

describe('createPayout', () => {
  let svc

  beforeEach(() => { svc = new RazorpayPayoutService(VALID_OPTS) })

  it('converts INR to paise in the payload', async () => {
    mockPost.mockResolvedValueOnce({ data: PAYOUT_PROCESSING_FIXTURE })

    await svc.createPayout({
      fundAccountId: 'fa_xyz456',
      amountInr:     5000,
      referenceId:   'ref-001',
    })

    const [, payload] = mockPost.mock.calls[0]
    expect(payload.amount).toBe(500000)  // ₹5000 × 100
    expect(payload.currency).toBe('INR')
    expect(payload.mode).toBe('UPI')
  })

  it('sets X-Payout-Idempotency header to referenceId', async () => {
    mockPost.mockResolvedValueOnce({ data: PAYOUT_PROCESSING_FIXTURE })

    await svc.createPayout({
      fundAccountId: 'fa_xyz456', amountInr: 100, referenceId: 'unique-ref',
    })

    const [, , config] = mockPost.mock.calls[0]
    expect(config.headers['X-Payout-Idempotency']).toBe('unique-ref')
  })

  it('includes source accountNumber in payload', async () => {
    mockPost.mockResolvedValueOnce({ data: PAYOUT_PROCESSING_FIXTURE })

    await svc.createPayout({
      fundAccountId: 'fa_xyz456', amountInr: 100, referenceId: 'ref',
    })

    const [, payload] = mockPost.mock.calls[0]
    expect(payload.account_number).toBe('7894561230000012')
  })

  it('queues payout on low balance (queue_if_low_balance: true)', async () => {
    mockPost.mockResolvedValueOnce({ data: PAYOUT_QUEUED_FIXTURE })

    const result = await svc.createPayout({
      fundAccountId: 'fa_xyz456', amountInr: 100, referenceId: 'ref',
    })

    const [, payload] = mockPost.mock.calls[0]
    expect(payload.queue_if_low_balance).toBe(true)
    expect(result.status).toBe('queued')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// fetchPayout
// ═══════════════════════════════════════════════════════════════════════════════

describe('fetchPayout', () => {
  let svc

  beforeEach(() => { svc = new RazorpayPayoutService(VALID_OPTS) })

  it('GETs /payouts/:id', async () => {
    mockGet.mockResolvedValueOnce({ data: PAYOUT_PROCESSED_FIXTURE })

    const result = await svc.fetchPayout('pout_999')

    expect(mockGet).toHaveBeenCalledWith('/payouts/pout_999')
    expect(result.status).toBe('processed')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// processReferralPayout — full flow
// ═══════════════════════════════════════════════════════════════════════════════

describe('processReferralPayout', () => {
  let svc

  beforeEach(() => { svc = new RazorpayPayoutService(VALID_OPTS) })

  it('creates contact + fund account + payout when no existingFundAccountId', async () => {
    mockPost
      .mockResolvedValueOnce({ data: CONTACT_FIXTURE })        // createContact
      .mockResolvedValueOnce({ data: FUND_ACCOUNT_FIXTURE })   // createFundAccount
      .mockResolvedValueOnce({ data: PAYOUT_PROCESSING_FIXTURE }) // createPayout

    const result = await svc.processReferralPayout({
      referralId:    'ref-001',
      upiId:         'rahul@okaxis',
      amountInr:     5000,
      employeeName:  'Rahul Kumar',
      employeeEmail: 'rahul@hotel.in',
    })

    expect(mockPost).toHaveBeenCalledTimes(3)
    expect(result.payoutId).toBe('pout_999')
    expect(result.internalStatus).toBe('PROCESSING')
    expect(result.amountPaise).toBe(500000)
    expect(result.fundAccountId).toBe('fa_xyz456')
    expect(result.mock).toBe(false)
  })

  it('skips contact + fund account creation when existingFundAccountId provided', async () => {
    mockPost.mockResolvedValueOnce({ data: PAYOUT_PROCESSED_FIXTURE })

    const result = await svc.processReferralPayout({
      referralId:            'ref-002',
      upiId:                 'rahul@okaxis',
      amountInr:             2500,
      existingFundAccountId: 'fa_existing',
    })

    expect(mockPost).toHaveBeenCalledTimes(1)  // only createPayout
    expect(result.fundAccountId).toBe('fa_existing')
    expect(result.internalStatus).toBe('PAID')
  })

  it('maps "processed" status to PAID', async () => {
    mockPost
      .mockResolvedValueOnce({ data: CONTACT_FIXTURE })
      .mockResolvedValueOnce({ data: FUND_ACCOUNT_FIXTURE })
      .mockResolvedValueOnce({ data: PAYOUT_PROCESSED_FIXTURE })

    const result = await svc.processReferralPayout({
      referralId: 'ref-paid', upiId: 'x@upi', amountInr: 1000,
    })

    expect(result.internalStatus).toBe('PAID')
  })

  it('maps "failed" status to FAILED', async () => {
    mockPost
      .mockResolvedValueOnce({ data: CONTACT_FIXTURE })
      .mockResolvedValueOnce({ data: FUND_ACCOUNT_FIXTURE })
      .mockResolvedValueOnce({ data: PAYOUT_FAILED_FIXTURE })

    const result = await svc.processReferralPayout({
      referralId: 'ref-fail', upiId: 'x@upi', amountInr: 1000,
    })

    expect(result.internalStatus).toBe('FAILED')
  })

  it('maps "reversed" status to FAILED', async () => {
    mockPost
      .mockResolvedValueOnce({ data: CONTACT_FIXTURE })
      .mockResolvedValueOnce({ data: FUND_ACCOUNT_FIXTURE })
      .mockResolvedValueOnce({ data: PAYOUT_REVERSED_FIXTURE })

    const result = await svc.processReferralPayout({
      referralId: 'ref-rev', upiId: 'x@upi', amountInr: 1000,
    })

    expect(result.internalStatus).toBe('FAILED')
  })

  it('propagates errors from any step', async () => {
    mockPost
      .mockResolvedValueOnce({ data: CONTACT_FIXTURE })
      .mockRejectedValueOnce(new Error('Invalid VPA'))  // createFundAccount fails

    await expect(
      svc.processReferralPayout({ referralId: 'ref-err', upiId: 'bad@', amountInr: 500 })
    ).rejects.toThrow('Invalid VPA')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// parseWebhookPayload
// ═══════════════════════════════════════════════════════════════════════════════

describe('parseWebhookPayload', () => {
  const makePayload = (status, referralId = 'ref-wh-001') => ({
    event: 'payout.processed',
    payload: {
      payout: {
        entity: {
          id: 'pout_wh123',
          status,
          amount: 500000,
          notes: { referral_id: referralId },
        },
      },
    },
  })

  it.each([
    ['processed', 'PAID'],
    ['failed',    'FAILED'],
    ['reversed',  'FAILED'],
    ['queued',    'PROCESSING'],
    ['pending',   'PROCESSING'],
    ['processing','PROCESSING'],
  ])('maps webhook status "%s" → internalStatus "%s"', (status, internal) => {
    const result = RazorpayPayoutService.parseWebhookPayload(makePayload(status))
    expect(result.internalStatus).toBe(internal)
  })

  it('extracts payoutId, referralId, amountPaise', () => {
    const result = RazorpayPayoutService.parseWebhookPayload(makePayload('processed', 'my-ref'))
    expect(result.payoutId).toBe('pout_wh123')
    expect(result.referralId).toBe('my-ref')
    expect(result.amountPaise).toBe(500000)
    expect(result.rawStatus).toBe('processed')
  })

  it('returns null referralId when notes are absent', () => {
    const payload = makePayload('processed')
    delete payload.payload.payout.entity.notes
    const result = RazorpayPayoutService.parseWebhookPayload(payload)
    expect(result.referralId).toBeNull()
  })

  it('throws on malformed payload (missing entity)', () => {
    expect(() => RazorpayPayoutService.parseWebhookPayload({})).toThrow()
    expect(() => RazorpayPayoutService.parseWebhookPayload({ payload: {} })).toThrow()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// createRazorpayPayoutService factory
// ═══════════════════════════════════════════════════════════════════════════════

describe('createRazorpayPayoutService', () => {
  const { createRazorpayPayoutService: factory } = require('../razorpayPayout.service')

  beforeEach(() => {
    delete process.env.RAZORPAY_KEY_ID
    delete process.env.RAZORPAY_KEY_SECRET
    delete process.env.RAZORPAY_FUND_ACCOUNT
  })

  it('returns null when env vars are missing', () => {
    expect(factory()).toBeNull()
  })

  it('returns null when only some env vars are set', () => {
    process.env.RAZORPAY_KEY_ID = 'k'
    expect(factory()).toBeNull()
  })

  it('returns a service instance when all three vars are set', () => {
    process.env.RAZORPAY_KEY_ID     = 'rzp_test_id'
    process.env.RAZORPAY_KEY_SECRET = 'rzp_test_sec'
    process.env.RAZORPAY_FUND_ACCOUNT = '1234567890000001'
    expect(factory()).toBeInstanceOf(RazorpayPayoutService)
  })
})
