'use strict'

/**
 * payrollProviderFactory.js
 *
 * Central registry for all payroll adapters.
 *
 * Usage — instantiate an adapter:
 *   const adapter = PayrollProviderFactory.create('greythr', {
 *     apiKey: process.env.GREYTHR_API_KEY,
 *     tenantId: process.env.GREYTHR_TENANT_ID,
 *   })
 *   const result = await adapter.addReferralBonus(employee, 2000, '2026-05', 'Referral Bonus')
 *
 * Usage — fire-and-forget with Supabase sync:
 *   const result = await PayrollProviderFactory.syncReferralBonus({
 *     supabase,            // Supabase client (service-role)
 *     referralId,          // referrals.id UUID
 *     provider: 'keka',
 *     config:  { accessToken, tenantDomain },
 *     employee,            // { employeeId, name, email }
 *     amount,              // INR
 *     period,              // 'YYYY-MM'
 *     narration,
 *   })
 *   // → result.referenceId is now stored in referrals.payroll_reference
 */

require('dotenv').config()

const { GreytHRAdapter }     = require('./adapters/greytHR.adapter')
const { KekaAdapter }        = require('./adapters/keka.adapter')
const { DarwinboxAdapter }   = require('./adapters/darwinbox.adapter')
const { ZohoPayrollAdapter } = require('./adapters/zohoPayroll.adapter')

// Map of canonical provider name → adapter class
const REGISTRY = {
  greythr:     GreytHRAdapter,
  keka:        KekaAdapter,
  darwinbox:   DarwinboxAdapter,
  zoho:        ZohoPayrollAdapter,
  zohopayroll: ZohoPayrollAdapter,   // alias
}

class PayrollProviderFactory {
  /**
   * Instantiate the correct adapter for the given provider name.
   *
   * @param  {string} provider  Case-insensitive: 'greythr' | 'keka' | 'darwinbox' | 'zoho'
   * @param  {object} config    Provider-specific credentials and options
   * @returns {BasePayrollAdapter}
   * @throws  {Error} for unrecognised provider names
   */
  static create (provider, config = {}) {
    const key = String(provider).toLowerCase().replace(/[^a-z]/g, '')
    const AdapterClass = REGISTRY[key]

    if (!AdapterClass) {
      const known = Object.keys(REGISTRY).join(', ')
      throw new Error(
        `Unknown payroll provider: "${provider}". ` +
        `Registered providers: ${known}`
      )
    }

    return new AdapterClass(config)
  }

  /**
   * Add a referral bonus via the named provider AND persist the provider's
   * transaction reference back to the referrals row in Supabase.
   *
   * The Supabase update is best-effort: a failure to write the reference
   * does NOT roll back the already-submitted payroll entry.  The raw result
   * (including referenceId) is always returned so the caller can retry the
   * DB write if needed.
   *
   * @param {object} opts
   * @param {object}      opts.supabase      Supabase client (service-role key)
   * @param {string}      opts.referralId    UUID of the referral row
   * @param {string}      opts.provider      Payroll provider name
   * @param {object}      opts.config        Provider config / credentials
   * @param {object}      opts.employee      { employeeId, name, email }
   * @param {number}      opts.amount        INR
   * @param {string}      opts.period        'YYYY-MM'
   * @param {string}      [opts.narration]   Payslip description
   * @param {object}      [opts.logger]      Optional logger override
   * @returns {Promise<PayrollResult>}
   */
  static async syncReferralBonus ({
    supabase, referralId, provider, config,
    employee, amount, period, narration = 'Referral Bonus',
    logger = console,
  }) {
    const adapter = PayrollProviderFactory.create(provider, config)

    // Delegate to the adapter — retries happen inside addReferralBonus
    const result = await adapter.addReferralBonus(employee, amount, period, narration)

    // Persist payroll_reference to Supabase (best-effort)
    if (supabase && referralId) {
      try {
        const { error } = await supabase
          .from('referrals')
          .update({
            payroll_reference: result.referenceId,
            payroll_provider:  result.provider,
            payroll_synced_at: result.syncedAt,
          })
          .eq('id', referralId)

        if (error) {
          logger.warn(
            JSON.stringify({
              ts:        new Date().toISOString(),
              level:     'warn',
              message:   'Failed to store payroll_reference on referral',
              referralId,
              referenceId: result.referenceId,
              error:     error.message,
            })
          )
        }
      } catch (dbErr) {
        // Non-fatal — the bonus was already submitted
        logger.warn(
          JSON.stringify({
            ts:      new Date().toISOString(),
            level:   'warn',
            message: 'DB update threw while storing payroll_reference',
            referralId,
            error:   dbErr.message,
          })
        )
      }
    }

    return result
  }

  /** Return the list of registered provider names (excluding aliases). */
  static get supportedProviders () {
    return ['greythr', 'keka', 'darwinbox', 'zoho']
  }
}

module.exports = { PayrollProviderFactory, REGISTRY }
