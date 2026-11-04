'use strict'

/**
 * keka.adapter.js
 *
 * Syncs referral bonuses to Keka HR Payroll via the Keka REST API.
 *
 * Required config:
 *   accessToken         — Keka OAuth2 bearer token
 *   tenantDomain        — e.g. "acme" (for acme.keka.com)
 *
 * Optional config:
 *   baseUrl             (default: https://{tenantDomain}.keka.com/api)
 *   earningComponentId  — Keka pay component ID for referral bonus
 *   retryBaseDelayMs
 *   maxAttempts
 *
 * API reference: https://developers.keka.com/reference/addearnings
 * Auth: Authorization: Bearer {accessToken}
 */

const axios = require('axios')
const { BasePayrollAdapter } = require('./base.adapter')

class KekaAdapter extends BasePayrollAdapter {
  constructor (config = {}) {
    super(config)
    this.providerName = 'keka'

    if (!config.accessToken)   throw new Error('KekaAdapter: accessToken is required')
    if (!config.tenantDomain)  throw new Error('KekaAdapter: tenantDomain is required')

    const baseUrl = config.baseUrl ?? `https://${config.tenantDomain}.keka.com/api`
    this._earningComponentId = config.earningComponentId ?? 'REFERRAL_BONUS'

    this._client = axios.create({
      baseURL: baseUrl,
      timeout: 15_000,
      headers: {
        Authorization:  `Bearer ${config.accessToken}`,
        'Content-Type': 'application/json',
        Accept:         'application/json',
      },
    })
  }

  /**
   * POST /v2/payroll/employees/:employeeId/additionalearnings
   *
   * Payload:
   *   earningComponentId, amount, remarks, month, year
   *
   * Response:
   *   { succeeded: true, data: { id, referenceNumber } }
   */
  async addReferralBonus (employee, amount, period, narration = 'Referral Bonus') {
    this._validate(employee, amount, period)

    const [year, month] = period.split('-').map(Number)

    return this._withRetry(async () => {
      this._log('info', 'Initiating addReferralBonus', {
        employeeId: employee.employeeId, amount, period,
      })

      const { data } = await this._client.post(
        `/v2/payroll/employees/${encodeURIComponent(employee.employeeId)}/additionalearnings`,
        {
          earningComponentId: this._earningComponentId,
          amount,
          remarks: narration,
          month,
          year,
        }
      )

      // Keka wraps results in a `data` envelope
      const inner       = data.data ?? data
      const referenceId = inner.referenceNumber ?? inner.id

      this._log('info', 'addReferralBonus succeeded', {
        employeeId: employee.employeeId, referenceId, period,
      })

      return this._buildResult(referenceId, employee, amount, period, data)
    })
  }
}

module.exports = { KekaAdapter }
