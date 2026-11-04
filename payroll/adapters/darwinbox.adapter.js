'use strict'

/**
 * darwinbox.adapter.js
 *
 * Syncs referral bonuses to Darwinbox HRMS via the Darwinbox REST API.
 *
 * Required config:
 *   apiKey      — Darwinbox API key
 *   apiSecret   — Darwinbox API secret
 *   tenantUrl   — Full tenant base URL, e.g. "https://acme.darwinbox.io"
 *
 * Optional config:
 *   componentType       (default: 'REFERRAL_BONUS')
 *   retryBaseDelayMs
 *   maxAttempts
 *
 * API reference: https://developer.darwinbox.io/payroll
 * Auth: x-api-key + x-api-secret headers
 */

const axios = require('axios')
const { BasePayrollAdapter } = require('./base.adapter')

class DarwinboxAdapter extends BasePayrollAdapter {
  constructor (config = {}) {
    super(config)
    this.providerName = 'darwinbox'

    if (!config.apiKey)    throw new Error('DarwinboxAdapter: apiKey is required')
    if (!config.apiSecret) throw new Error('DarwinboxAdapter: apiSecret is required')
    if (!config.tenantUrl) throw new Error('DarwinboxAdapter: tenantUrl is required')

    this._componentType = config.componentType ?? 'REFERRAL_BONUS'

    this._client = axios.create({
      baseURL: config.tenantUrl.replace(/\/$/, ''),
      timeout: 15_000,
      headers: {
        'x-api-key':    config.apiKey,
        'x-api-secret': config.apiSecret,
        'Content-Type': 'application/json',
        Accept:         'application/json',
      },
    })
  }

  /**
   * POST /api/payroll/components/adhoc
   *
   * Payload:
   *   employee_id, component_type, amount, month, year, remarks
   *
   * Response:
   *   { success: true, data: { id, reference_id } }
   */
  async addReferralBonus (employee, amount, period, narration = 'Referral Bonus') {
    this._validate(employee, amount, period)

    const [year, month] = period.split('-').map(Number)

    return this._withRetry(async () => {
      this._log('info', 'Initiating addReferralBonus', {
        employeeId: employee.employeeId, amount, period,
      })

      const { data } = await this._client.post('/api/payroll/components/adhoc', {
        employee_id:    employee.employeeId,
        component_type: this._componentType,
        amount,
        month,
        year,
        remarks:        narration,
      })

      const inner       = data.data ?? data
      const referenceId = inner.reference_id ?? inner.id

      this._log('info', 'addReferralBonus succeeded', {
        employeeId: employee.employeeId, referenceId, period,
      })

      return this._buildResult(referenceId, employee, amount, period, data)
    })
  }
}

module.exports = { DarwinboxAdapter }
