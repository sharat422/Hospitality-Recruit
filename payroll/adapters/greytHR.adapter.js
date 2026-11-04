'use strict'

/**
 * greytHR.adapter.js
 *
 * Syncs referral bonuses to greytHR Payroll via the greytHR REST API.
 *
 * Required config:
 *   apiKey    — greytHR API key (Settings → API Access)
 *   tenantId  — greytHR tenant / subdomain identifier
 *
 * Optional config:
 *   baseUrl             (default: https://api.greythr.com)
 *   componentCode       (default: 'REFERRAL_BONUS')
 *   retryBaseDelayMs    (default: 1000)
 *   maxAttempts         (default: 3)
 *
 * API reference: https://developer.greythr.com/payroll
 * Auth: X-GreytHR-ApiKey header
 */

const axios = require('axios')
const { BasePayrollAdapter } = require('./base.adapter')

const DEFAULT_BASE_URL = 'https://api.greythr.com'

class GreytHRAdapter extends BasePayrollAdapter {
  constructor (config = {}) {
    super(config)
    this.providerName = 'greythr'

    if (!config.apiKey)   throw new Error('GreytHRAdapter: apiKey is required')
    if (!config.tenantId) throw new Error('GreytHRAdapter: tenantId is required')

    this._componentCode = config.componentCode ?? 'REFERRAL_BONUS'
    this._client = axios.create({
      baseURL: config.baseUrl ?? DEFAULT_BASE_URL,
      timeout: 15_000,
      headers: {
        'X-GreytHR-ApiKey': config.apiKey,
        'X-Tenant-Id':      config.tenantId,
        'Content-Type':     'application/json',
        Accept:             'application/json',
      },
    })
  }

  /**
   * POST /api/v2/payroll/employees/:empCode/adhoc-earnings
   *
   * Payload:
   *   empCode, componentCode, year, month, amount, narration, type
   *
   * Response:
   *   { status: 'SUCCESS', transactionRef: '...', id: '...' }
   */
  async addReferralBonus (employee, amount, period, narration = 'Referral Bonus') {
    this._validate(employee, amount, period)

    const [year, month] = period.split('-').map(Number)

    return this._withRetry(async () => {
      this._log('info', 'Initiating addReferralBonus', {
        employeeId: employee.employeeId, amount, period,
      })

      const { data } = await this._client.post(
        `/api/v2/payroll/employees/${encodeURIComponent(employee.employeeId)}/adhoc-earnings`,
        {
          empCode:       employee.employeeId,
          componentCode: this._componentCode,
          year,
          month,
          amount,
          narration,
          type: 'EARNING',
        }
      )

      const referenceId = data.transactionRef ?? data.id ?? data.referenceNo
      this._log('info', 'addReferralBonus succeeded', {
        employeeId: employee.employeeId, referenceId, period,
      })

      return this._buildResult(referenceId, employee, amount, period, data)
    })
  }
}

module.exports = { GreytHRAdapter }
