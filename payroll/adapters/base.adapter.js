'use strict'

/**
 * base.adapter.js
 *
 * Abstract base class for all payroll provider adapters.
 *
 * Provides:
 *   • Input validation          (_validate)
 *   • Structured JSON logging   (_log)
 *   • Retry with exponential    (_withRetry)
 *     backoff and HTTP-status-
 *     aware retry decisions
 *   • Normalised result shape   (buildResult)
 *
 * Concrete adapters extend this class and implement addReferralBonus().
 */

const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/   // YYYY-MM

class BasePayrollAdapter {
  /**
   * @param {object} config
   * @param {number} [config.retryBaseDelayMs=1000]  Base delay for exponential backoff
   * @param {number} [config.maxAttempts=3]           Max retry attempts per call
   */
  constructor (config = {}) {
    this.config         = config
    this.providerName   = 'base'
    this._retryBase     = config.retryBaseDelayMs ?? 1_000
    this._maxAttempts   = config.maxAttempts      ?? 3
  }

  // ── Public interface ───────────────────────────────────────────────────────

  /**
   * Add a referral bonus to an employee's payroll for the given period.
   *
   * @param  {object} employee
   * @param  {string} employee.employeeId  Payroll system's employee code
   * @param  {string} employee.name
   * @param  {string} [employee.email]
   * @param  {number} amount               INR (must be > 0)
   * @param  {string} period               'YYYY-MM'
   * @param  {string} narration            Description shown on payslip
   * @returns {Promise<PayrollResult>}
   * @abstract
   */
  async addReferralBonus (_employee, _amount, _period, _narration) {
    throw new Error(`${this.providerName}.addReferralBonus() must be implemented`)
  }

  // ── Helpers (available to sub-classes) ────────────────────────────────────

  /**
   * Validate the common arguments before any API call.
   * Throws a descriptive Error on first validation failure.
   */
  _validate (employee, amount, period) {
    if (!employee || !employee.employeeId) {
      throw new Error('employee.employeeId is required')
    }
    if (typeof amount !== 'number' || amount <= 0 || !isFinite(amount)) {
      throw new Error(`amount must be a positive finite number, got: ${amount}`)
    }
    if (!PERIOD_RE.test(period)) {
      throw new Error(`period must be in YYYY-MM format (e.g. "2026-05"), got: "${period}"`)
    }
  }

  /**
   * Emit a structured log entry.
   *
   * @param {'info'|'warn'|'error'} level
   * @param {string}  message
   * @param {object}  [meta]
   */
  _log (level, message, meta = {}) {
    const entry = {
      ts:       new Date().toISOString(),
      level,
      provider: this.providerName,
      message,
      ...meta,
    }
    const line = JSON.stringify(entry)
    if (level === 'error') console.error(line)
    else if (level === 'warn')  console.warn(line)
    else                        console.log(line)
  }

  /**
   * True when the error warrants a retry attempt.
   *
   *   Network error (no response)       → retry
   *   HTTP 429 Too Many Requests        → retry (longer delay)
   *   HTTP 5xx Server Error             → retry
   *   HTTP 4xx Client Error (not 429)   → do NOT retry (bad request)
   */
  _isRetryable (err) {
    if (err.skipRetry)  return false           // caller explicitly opted out of retry
    if (!err.response)  return true            // network / DNS / timeout
    const s = err.response.status
    return s === 429 || s >= 500
  }

  /**
   * Call `fn` up to `maxAttempts` times with exponential backoff.
   * Stops immediately on non-retryable errors (4xx ≠ 429).
   *
   * @param  {function} fn
   * @param  {number}   [maxAttempts]
   * @returns {Promise<any>}
   */
  async _withRetry (fn, maxAttempts = this._maxAttempts) {
    let lastErr
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        return await fn()
      } catch (err) {
        lastErr = err
        const retryable = this._isRetryable(err)

        if (!retryable || attempt === maxAttempts) {
          this._log('error', 'Request failed — not retrying', {
            attempt, maxAttempts, status: err.response?.status, error: err.message,
          })
          throw err
        }

        const isRateLimit = err.response?.status === 429
        const delayMs     = isRateLimit
          ? 60_000
          : this._retryBase * (2 ** (attempt - 1))

        this._log('warn', `Attempt ${attempt}/${maxAttempts} failed — retrying in ${delayMs}ms`, {
          status: err.response?.status, error: err.message, delayMs,
        })

        await this._sleep(delayMs)
      }
    }
    throw lastErr
  }

  /** Overrideable in tests to avoid real waiting. */
  _sleep (ms) {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  /**
   * Build the normalised response object returned by every adapter.
   *
   * @param {string} referenceId   Provider's transaction / reference ID
   * @param {object} employee
   * @param {number} amount
   * @param {string} period
   * @param {object} raw           Raw API response
   * @returns {PayrollResult}
   */
  _buildResult (referenceId, employee, amount, period, raw) {
    return {
      success:     true,
      referenceId,
      provider:    this.providerName,
      employeeId:  employee.employeeId,
      amount,
      period,
      syncedAt:    new Date().toISOString(),
      raw,
    }
  }
}

/**
 * @typedef {object} PayrollResult
 * @property {true}   success
 * @property {string} referenceId   Provider's transaction / reference ID
 * @property {string} provider      'greythr' | 'keka' | 'darwinbox' | 'zoho'
 * @property {string} employeeId    Provider's employee code
 * @property {number} amount        INR
 * @property {string} period        'YYYY-MM'
 * @property {string} syncedAt      ISO timestamp
 * @property {object} raw           Raw API response
 */

module.exports = { BasePayrollAdapter, PERIOD_RE }
