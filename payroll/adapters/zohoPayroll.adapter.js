'use strict'

/**
 * zohoPayroll.adapter.js
 *
 * Syncs referral bonuses to Zoho Payroll (India) via the Zoho Payroll API.
 *
 * Required config:
 *   accessToken        — Zoho OAuth2 access token
 *   organizationId     — Zoho Payroll organisation ID
 *
 * Optional config:
 *   baseUrl            (default: https://payroll.zoho.in/api/v1)
 *   payComponentId     — Zoho pay component ID for referral bonus
 *   retryBaseDelayMs
 *   maxAttempts
 *
 * API reference: https://www.zoho.com/payroll/api/
 * Auth: Authorization: Zoho-oauthtoken {accessToken}
 *
 * Note on token refresh: Zoho access tokens expire in one hour. Pass a fresh
 * token on each instantiation or implement token refresh externally and
 * re-create the adapter.  A 401 from Zoho is NOT retried (non-retryable 4xx).
 */

const axios = require('axios')
const { BasePayrollAdapter } = require('./base.adapter')

const DEFAULT_BASE_URL = 'https://payroll.zoho.in/api/v1'

class ZohoPayrollAdapter extends BasePayrollAdapter {
  constructor (config = {}) {
    super(config)
    this.providerName = 'zoho'

    if (!config.accessToken)    throw new Error('ZohoPayrollAdapter: accessToken is required')
    if (!config.organizationId) throw new Error('ZohoPayrollAdapter: organizationId is required')

    this._payComponentId = config.payComponentId ?? 'REFERRAL_BONUS'

    this._client = axios.create({
      baseURL: config.baseUrl ?? DEFAULT_BASE_URL,
      timeout: 15_000,
      headers: {
        Authorization:    `Zoho-oauthtoken ${config.accessToken}`,
        'X-com-zoho-payroll-organizationid': config.organizationId,
        'Content-Type':   'application/json',
        Accept:           'application/json',
      },
    })
  }

  /**
   * POST /adhocpayments
   *
   * Payload:
   *   employee_id, pay_component_id, amount, pay_period (YYYY-MM-01), notes
   *
   * Response:
   *   { code: 0, message: 'success', data: { adhoc_payment_id } }
   *   Non-zero code indicates failure.
   */
  async addReferralBonus (employee, amount, period, narration = 'Referral Bonus') {
    this._validate(employee, amount, period)

    // Zoho expects the period as the first day of the month (YYYY-MM-01)
    const payPeriod = `${period}-01`

    return this._withRetry(async () => {
      this._log('info', 'Initiating addReferralBonus', {
        employeeId: employee.employeeId, amount, period,
      })

      const { data } = await this._client.post('/adhocpayments', {
        employee_id:      employee.employeeId,
        pay_component_id: this._payComponentId,
        amount,
        pay_period:       payPeriod,
        notes:            narration,
      })

      // Zoho signals errors with a non-zero `code` even on HTTP 200
      if (data.code !== 0) {
        const err = new Error(`Zoho Payroll error ${data.code}: ${data.message}`)
        err.zohoCode    = data.code
        err.zohoMessage = data.message
        err.skipRetry   = true      // business error — retrying the same payload won't help
        this._log('error', 'Zoho returned non-zero code', { code: data.code, message: data.message })
        throw err
      }

      const referenceId = data.data?.adhoc_payment_id ?? data.data?.id

      this._log('info', 'addReferralBonus succeeded', {
        employeeId: employee.employeeId, referenceId, period,
      })

      return this._buildResult(referenceId, employee, amount, period, data)
    })
  }
}

module.exports = { ZohoPayrollAdapter }
