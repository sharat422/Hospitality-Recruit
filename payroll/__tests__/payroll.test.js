'use strict'

jest.mock('axios')
const axios = require('axios')

// ── Shared axios mock ─────────────────────────────────────────────────────────
// Each adapter calls axios.create() and uses the returned instance's .post()
// All adapters share the same mock so we reset per describe block.

const mockPost = jest.fn()
const mockGet  = jest.fn()
axios.create.mockReturnValue({ post: mockPost, get: mockGet })

const { BasePayrollAdapter, PERIOD_RE }  = require('../adapters/base.adapter')
const { GreytHRAdapter }                 = require('../adapters/greytHR.adapter')
const { KekaAdapter }                    = require('../adapters/keka.adapter')
const { DarwinboxAdapter }               = require('../adapters/darwinbox.adapter')
const { ZohoPayrollAdapter }             = require('../adapters/zohoPayroll.adapter')
const { PayrollProviderFactory, REGISTRY } = require('../payrollProviderFactory')

// ── Shared fixtures ───────────────────────────────────────────────────────────

const EMPLOYEE = { employeeId: 'EMP001', name: 'Rahul Kumar', email: 'rahul@hotel.in' }
const AMOUNT   = 2000
const PERIOD   = '2026-05'
const NARRATION = 'Referral Bonus – hired Priya Sharma'

const GREYTHR_CFG   = { apiKey: 'ghk', tenantId: 'acme', retryBaseDelayMs: 0, maxAttempts: 3 }
const KEKA_CFG      = { accessToken: 'kk_tok', tenantDomain: 'acme', retryBaseDelayMs: 0, maxAttempts: 3 }
const DARWINBOX_CFG = { apiKey: 'dbk', apiSecret: 'dbs', tenantUrl: 'https://acme.darwinbox.io', retryBaseDelayMs: 0 }
const ZOHO_CFG      = { accessToken: 'zoho_tok', organizationId: 'ORG001', retryBaseDelayMs: 0 }

// helpers
const http4xx  = (status = 400) => Object.assign(new Error(`HTTP ${status}`), { response: { status } })
const http5xx  = (status = 500) => Object.assign(new Error(`HTTP ${status}`), { response: { status } })
const netError = () => new Error('ECONNRESET')  // no .response

beforeEach(() => { mockPost.mockReset(); mockGet.mockReset() })

// ─────────────────────────────────────────────────────────────────────────────
// BasePayrollAdapter
// ─────────────────────────────────────────────────────────────────────────────

describe('BasePayrollAdapter', () => {
  class ConcreteAdapter extends BasePayrollAdapter {
    constructor (cfg) { super(cfg); this.providerName = 'test' }
    async addReferralBonus (e, a, p, n) {
      this._validate(e, a, p)
      return this._buildResult('REF-001', e, a, p, {})
    }
  }

  describe('_validate', () => {
    it('throws when employee.employeeId is missing', () => {
      const a = new ConcreteAdapter({})
      expect(() => a._validate({}, 100, '2026-05')).toThrow('employeeId')
    })
    it('throws when amount is zero', () => {
      const a = new ConcreteAdapter({})
      expect(() => a._validate(EMPLOYEE, 0, '2026-05')).toThrow('positive')
    })
    it('throws when amount is negative', () => {
      const a = new ConcreteAdapter({})
      expect(() => a._validate(EMPLOYEE, -50, '2026-05')).toThrow('positive')
    })
    it('throws when period is wrong format', () => {
      const a = new ConcreteAdapter({})
      expect(() => a._validate(EMPLOYEE, 100, '05-2026')).toThrow('YYYY-MM')
    })
    it('throws when period month > 12', () => {
      const a = new ConcreteAdapter({})
      expect(() => a._validate(EMPLOYEE, 100, '2026-13')).toThrow('YYYY-MM')
    })
    it('passes with valid inputs', () => {
      const a = new ConcreteAdapter({})
      expect(() => a._validate(EMPLOYEE, 1, '2026-01')).not.toThrow()
    })
  })

  describe('_buildResult', () => {
    it('returns normalised shape', async () => {
      const a      = new ConcreteAdapter({})
      const result = await a.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
      expect(result).toMatchObject({
        success:    true,
        referenceId: 'REF-001',
        provider:   'test',
        employeeId: 'EMP001',
        amount:     2000,
        period:     '2026-05',
      })
      expect(result.syncedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    })
  })

  describe('_withRetry', () => {
    it('retries on 5xx errors and succeeds on third attempt', async () => {
      const a = new ConcreteAdapter({ retryBaseDelayMs: 0, maxAttempts: 3 })
      a._sleep = jest.fn().mockResolvedValue()
      const fn = jest.fn()
        .mockRejectedValueOnce(http5xx(500))
        .mockRejectedValueOnce(http5xx(503))
        .mockResolvedValueOnce('ok')
      const result = await a._withRetry(fn)
      expect(result).toBe('ok')
      expect(fn).toHaveBeenCalledTimes(3)
      expect(a._sleep).toHaveBeenCalledTimes(2)
    })

    it('does NOT retry on 4xx client errors', async () => {
      const a = new ConcreteAdapter({ retryBaseDelayMs: 0 })
      a._sleep = jest.fn()
      const fn = jest.fn().mockRejectedValue(http4xx(422))
      await expect(a._withRetry(fn)).rejects.toMatchObject({ response: { status: 422 } })
      expect(fn).toHaveBeenCalledTimes(1)
      expect(a._sleep).not.toHaveBeenCalled()
    })

    it('retries on network errors (no response)', async () => {
      const a = new ConcreteAdapter({ retryBaseDelayMs: 0, maxAttempts: 2 })
      a._sleep = jest.fn().mockResolvedValue()
      const fn = jest.fn()
        .mockRejectedValueOnce(netError())
        .mockResolvedValueOnce('recovered')
      const result = await a._withRetry(fn, 2)
      expect(result).toBe('recovered')
      expect(fn).toHaveBeenCalledTimes(2)
    })

    it('retries on 429 with 60s sleep', async () => {
      const a = new ConcreteAdapter({ retryBaseDelayMs: 0, maxAttempts: 2 })
      a._sleep = jest.fn().mockResolvedValue()
      const fn = jest.fn()
        .mockRejectedValueOnce(http4xx(429))
        .mockResolvedValueOnce('ok')
      await a._withRetry(fn, 2)
      expect(a._sleep).toHaveBeenCalledWith(60_000)
    })

    it('throws after exhausting all attempts', async () => {
      const a = new ConcreteAdapter({ retryBaseDelayMs: 0, maxAttempts: 3 })
      a._sleep = jest.fn().mockResolvedValue()
      const fn = jest.fn().mockRejectedValue(http5xx())
      await expect(a._withRetry(fn, 3)).rejects.toMatchObject({ response: { status: 500 } })
      expect(fn).toHaveBeenCalledTimes(3)
    })
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// GreytHRAdapter
// ─────────────────────────────────────────────────────────────────────────────

describe('GreytHRAdapter', () => {
  it('throws when apiKey is missing', () => {
    expect(() => new GreytHRAdapter({ tenantId: 't' })).toThrow('apiKey')
  })
  it('throws when tenantId is missing', () => {
    expect(() => new GreytHRAdapter({ apiKey: 'k' })).toThrow('tenantId')
  })

  it('POSTs to the correct endpoint with correct payload', async () => {
    mockPost.mockResolvedValueOnce({
      data: { status: 'SUCCESS', transactionRef: 'GHR-TXN-001', id: 'ghrid-1' },
    })
    const adapter = new GreytHRAdapter(GREYTHR_CFG)
    await adapter.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)

    expect(mockPost).toHaveBeenCalledWith(
      `/api/v2/payroll/employees/${EMPLOYEE.employeeId}/adhoc-earnings`,
      expect.objectContaining({
        empCode:       'EMP001',
        componentCode: 'REFERRAL_BONUS',
        amount:        2000,
        year:          2026,
        month:         5,
        narration:     NARRATION,
        type:          'EARNING',
      })
    )
  })

  it('maps transactionRef to referenceId', async () => {
    mockPost.mockResolvedValueOnce({ data: { transactionRef: 'GHR-TX-99' } })
    const result = await new GreytHRAdapter(GREYTHR_CFG)
      .addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('GHR-TX-99')
    expect(result.provider).toBe('greythr')
    expect(result.success).toBe(true)
  })

  it('falls back to .id when transactionRef is absent', async () => {
    mockPost.mockResolvedValueOnce({ data: { id: 'ghrid-fallback' } })
    const result = await new GreytHRAdapter(GREYTHR_CFG)
      .addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('ghrid-fallback')
  })

  it('retries on 5xx and succeeds', async () => {
    mockPost
      .mockRejectedValueOnce(http5xx(500))
      .mockResolvedValueOnce({ data: { transactionRef: 'GHR-RETRY' } })
    const adapter = new GreytHRAdapter(GREYTHR_CFG)
    adapter._sleep = jest.fn().mockResolvedValue()
    const result = await adapter.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('GHR-RETRY')
    expect(mockPost).toHaveBeenCalledTimes(2)
  })

  it('throws validation error before hitting the API', async () => {
    await expect(
      new GreytHRAdapter(GREYTHR_CFG).addReferralBonus({}, -1, 'bad', NARRATION)
    ).rejects.toThrow('employeeId')
    expect(mockPost).not.toHaveBeenCalled()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// KekaAdapter
// ─────────────────────────────────────────────────────────────────────────────

describe('KekaAdapter', () => {
  it('throws when accessToken is missing', () => {
    expect(() => new KekaAdapter({ tenantDomain: 'x' })).toThrow('accessToken')
  })
  it('throws when tenantDomain is missing', () => {
    expect(() => new KekaAdapter({ accessToken: 'x' })).toThrow('tenantDomain')
  })

  it('POSTs to the correct endpoint with correct payload', async () => {
    mockPost.mockResolvedValueOnce({
      data: { succeeded: true, data: { id: 'kk-001', referenceNumber: 'KEKA-REF-001' } },
    })
    const adapter = new KekaAdapter(KEKA_CFG)
    await adapter.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)

    expect(mockPost).toHaveBeenCalledWith(
      `/v2/payroll/employees/${EMPLOYEE.employeeId}/additionalearnings`,
      expect.objectContaining({
        earningComponentId: 'REFERRAL_BONUS',
        amount:  2000,
        remarks: NARRATION,
        year:    2026,
        month:   5,
      })
    )
  })

  it('maps referenceNumber to referenceId', async () => {
    mockPost.mockResolvedValueOnce({ data: { data: { referenceNumber: 'KK-REF-007' } } })
    const result = await new KekaAdapter(KEKA_CFG)
      .addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('KK-REF-007')
    expect(result.provider).toBe('keka')
  })

  it('retries on network error and succeeds', async () => {
    mockPost
      .mockRejectedValueOnce(netError())
      .mockResolvedValueOnce({ data: { data: { referenceNumber: 'KK-NET-OK' } } })
    const adapter = new KekaAdapter(KEKA_CFG)
    adapter._sleep = jest.fn().mockResolvedValue()
    const result = await adapter.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('KK-NET-OK')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// DarwinboxAdapter
// ─────────────────────────────────────────────────────────────────────────────

describe('DarwinboxAdapter', () => {
  it('throws when apiKey is missing', () => {
    expect(() => new DarwinboxAdapter({ apiSecret: 's', tenantUrl: 'https://u' })).toThrow('apiKey')
  })
  it('throws when apiSecret is missing', () => {
    expect(() => new DarwinboxAdapter({ apiKey: 'k', tenantUrl: 'https://u' })).toThrow('apiSecret')
  })
  it('throws when tenantUrl is missing', () => {
    expect(() => new DarwinboxAdapter({ apiKey: 'k', apiSecret: 's' })).toThrow('tenantUrl')
  })

  it('POSTs to the correct endpoint with correct payload', async () => {
    mockPost.mockResolvedValueOnce({ data: { success: true, data: { reference_id: 'DB-REF-01', id: '99' } } })
    const adapter = new DarwinboxAdapter(DARWINBOX_CFG)
    await adapter.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)

    expect(mockPost).toHaveBeenCalledWith(
      '/api/payroll/components/adhoc',
      expect.objectContaining({
        employee_id:    'EMP001',
        component_type: 'REFERRAL_BONUS',
        amount:         2000,
        month:          5,
        year:           2026,
        remarks:        NARRATION,
      })
    )
  })

  it('maps reference_id to referenceId', async () => {
    mockPost.mockResolvedValueOnce({ data: { data: { reference_id: 'DB-REF-77' } } })
    const result = await new DarwinboxAdapter(DARWINBOX_CFG)
      .addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('DB-REF-77')
    expect(result.provider).toBe('darwinbox')
  })

  it('does not retry on 4xx', async () => {
    mockPost.mockRejectedValue(http4xx(400))
    await expect(
      new DarwinboxAdapter(DARWINBOX_CFG).addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    ).rejects.toMatchObject({ response: { status: 400 } })
    expect(mockPost).toHaveBeenCalledTimes(1)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// ZohoPayrollAdapter
// ─────────────────────────────────────────────────────────────────────────────

describe('ZohoPayrollAdapter', () => {
  it('throws when accessToken is missing', () => {
    expect(() => new ZohoPayrollAdapter({ organizationId: 'x' })).toThrow('accessToken')
  })
  it('throws when organizationId is missing', () => {
    expect(() => new ZohoPayrollAdapter({ accessToken: 'x' })).toThrow('organizationId')
  })

  it('POSTs to /adhocpayments with period as YYYY-MM-01', async () => {
    mockPost.mockResolvedValueOnce({ data: { code: 0, data: { adhoc_payment_id: 'ZOHO-PMT-01' } } })
    const adapter = new ZohoPayrollAdapter(ZOHO_CFG)
    await adapter.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)

    expect(mockPost).toHaveBeenCalledWith(
      '/adhocpayments',
      expect.objectContaining({
        employee_id:      'EMP001',
        amount:           2000,
        pay_period:       '2026-05-01',   // YYYY-MM-01
        notes:            NARRATION,
      })
    )
  })

  it('maps adhoc_payment_id to referenceId', async () => {
    mockPost.mockResolvedValueOnce({ data: { code: 0, data: { adhoc_payment_id: 'ZOHO-7' } } })
    const result = await new ZohoPayrollAdapter(ZOHO_CFG)
      .addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('ZOHO-7')
    expect(result.provider).toBe('zoho')
  })

  it('throws when Zoho returns non-zero code (even on HTTP 200)', async () => {
    mockPost.mockResolvedValueOnce({ data: { code: 57, message: 'Insufficient balance' } })
    await expect(
      new ZohoPayrollAdapter(ZOHO_CFG).addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    ).rejects.toThrow('Zoho Payroll error 57')
  })

  it('retries on 5xx and eventually succeeds', async () => {
    mockPost
      .mockRejectedValueOnce(http5xx(502))
      .mockResolvedValueOnce({ data: { code: 0, data: { adhoc_payment_id: 'ZOHO-OK' } } })
    const adapter = new ZohoPayrollAdapter(ZOHO_CFG)
    adapter._sleep = jest.fn().mockResolvedValue()
    const result = await adapter.addReferralBonus(EMPLOYEE, AMOUNT, PERIOD, NARRATION)
    expect(result.referenceId).toBe('ZOHO-OK')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// PayrollProviderFactory
// ─────────────────────────────────────────────────────────────────────────────

describe('PayrollProviderFactory', () => {
  describe('create', () => {
    it('returns GreytHRAdapter for "greythr"', () => {
      expect(PayrollProviderFactory.create('greythr', GREYTHR_CFG)).toBeInstanceOf(GreytHRAdapter)
    })
    it('returns GreytHRAdapter for "GreytHR" (case-insensitive)', () => {
      expect(PayrollProviderFactory.create('GreytHR', GREYTHR_CFG)).toBeInstanceOf(GreytHRAdapter)
    })
    it('returns KekaAdapter for "keka"', () => {
      expect(PayrollProviderFactory.create('keka', KEKA_CFG)).toBeInstanceOf(KekaAdapter)
    })
    it('returns DarwinboxAdapter for "darwinbox"', () => {
      expect(PayrollProviderFactory.create('darwinbox', DARWINBOX_CFG)).toBeInstanceOf(DarwinboxAdapter)
    })
    it('returns ZohoPayrollAdapter for "zoho"', () => {
      expect(PayrollProviderFactory.create('zoho', ZOHO_CFG)).toBeInstanceOf(ZohoPayrollAdapter)
    })
    it('returns ZohoPayrollAdapter for "zohopayroll" alias', () => {
      expect(PayrollProviderFactory.create('zohopayroll', ZOHO_CFG)).toBeInstanceOf(ZohoPayrollAdapter)
    })
    it('throws for an unknown provider', () => {
      expect(() => PayrollProviderFactory.create('sap', {}))
        .toThrow(/Unknown payroll provider.*"sap"/)
    })
    it('lists supported providers', () => {
      expect(PayrollProviderFactory.supportedProviders).toEqual(
        expect.arrayContaining(['greythr', 'keka', 'darwinbox', 'zoho'])
      )
    })
  })

  describe('syncReferralBonus', () => {
    it('calls addReferralBonus and stores payroll_reference in Supabase', async () => {
      mockPost.mockResolvedValueOnce({ data: { transactionRef: 'GHR-SYNC-01' } })

      const mockUpdate = jest.fn().mockReturnThis()
      const mockEq     = jest.fn().mockResolvedValue({ error: null })
      const supabase   = { from: jest.fn().mockReturnValue({ update: mockUpdate, eq: mockEq }) }
      mockUpdate.mockReturnValue({ eq: mockEq })

      const result = await PayrollProviderFactory.syncReferralBonus({
        supabase,
        referralId: 'ref-uuid-001',
        provider:   'greythr',
        config:     GREYTHR_CFG,
        employee:   EMPLOYEE,
        amount:     AMOUNT,
        period:     PERIOD,
        narration:  NARRATION,
      })

      expect(result.referenceId).toBe('GHR-SYNC-01')
      expect(result.success).toBe(true)
      expect(supabase.from).toHaveBeenCalledWith('referrals')
      expect(mockUpdate).toHaveBeenCalledWith(
        expect.objectContaining({ payroll_reference: 'GHR-SYNC-01', payroll_provider: 'greythr' })
      )
      expect(mockEq).toHaveBeenCalledWith('id', 'ref-uuid-001')
    })

    it('still returns result when Supabase DB update fails (best-effort)', async () => {
      mockPost.mockResolvedValueOnce({ data: { transactionRef: 'GHR-DB-ERR' } })

      const mockUpdate = jest.fn().mockReturnThis()
      const mockEq     = jest.fn().mockResolvedValue({ error: { message: 'DB down' } })
      const supabase   = { from: jest.fn().mockReturnValue({ update: mockUpdate, eq: mockEq }) }
      mockUpdate.mockReturnValue({ eq: mockEq })

      const warnLogger = { warn: jest.fn() }
      const result = await PayrollProviderFactory.syncReferralBonus({
        supabase,
        referralId: 'ref-uuid-002',
        provider:   'greythr',
        config:     GREYTHR_CFG,
        employee:   EMPLOYEE,
        amount:     AMOUNT,
        period:     PERIOD,
        logger:     warnLogger,
      })

      // Bonus was submitted — result is intact
      expect(result.referenceId).toBe('GHR-DB-ERR')
      expect(result.success).toBe(true)
      // Warning was logged
      expect(warnLogger.warn).toHaveBeenCalledWith(
        expect.stringContaining('payroll_reference')
      )
    })

    it('works without supabase (no DB write attempted)', async () => {
      mockPost.mockResolvedValueOnce({ data: { transactionRef: 'GHR-NO-DB' } })
      const result = await PayrollProviderFactory.syncReferralBonus({
        supabase:   null,
        referralId: null,
        provider:   'greythr',
        config:     GREYTHR_CFG,
        employee:   EMPLOYEE,
        amount:     AMOUNT,
        period:     PERIOD,
      })
      expect(result.referenceId).toBe('GHR-NO-DB')
    })

    it('propagates adapter errors (does not swallow them)', async () => {
      mockPost.mockRejectedValue(http4xx(422))
      await expect(
        PayrollProviderFactory.syncReferralBonus({
          supabase: null, referralId: null,
          provider: 'greythr', config: GREYTHR_CFG,
          employee: EMPLOYEE, amount: AMOUNT, period: PERIOD,
        })
      ).rejects.toMatchObject({ response: { status: 422 } })
    })
  })
})
