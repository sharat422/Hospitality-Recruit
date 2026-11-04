'use strict'

/**
 * razorpayPayout.service.js
 *
 * Server-side only. Credentials never leave this module.
 * Called from the FastAPI backend via a subprocess or through the
 * Python razorpay_payout_service.py wrapper.
 *
 * Razorpay Payouts flow:
 *   1. POST /v1/contacts           → contact_id    (once per employee)
 *   2. POST /v1/fund_accounts      → fund_account_id (once per UPI ID)
 *   3. POST /v1/payouts            → payout_id
 *   4. GET  /v1/payouts/:id        → poll status
 *
 * Payout statuses (Razorpay → internal):
 *   queued | pending | processing  → PROCESSING
 *   processed                      → PAID
 *   failed | reversed | cancelled  → FAILED
 */

const axios = require('axios')

const RAZORPAY_BASE_URL = 'https://api.razorpay.com/v1'

const PAYOUT_STATUS_MAP = Object.freeze({
  queued:     'PROCESSING',
  pending:    'PROCESSING',
  processing: 'PROCESSING',
  processed:  'PAID',
  failed:     'FAILED',
  reversed:   'FAILED',
  cancelled:  'FAILED',
})

// ─────────────────────────────────────────────────────────────────────────────

class RazorpayPayoutService {
  /**
   * @param {object} opts
   * @param {string} opts.keyId         RAZORPAY_KEY_ID
   * @param {string} opts.keySecret     RAZORPAY_KEY_SECRET
   * @param {string} opts.accountNumber RAZORPAY_FUND_ACCOUNT — source RazorpayX
   *                                    account number (16-digit)
   */
  constructor ({ keyId, keySecret, accountNumber }) {
    if (!keyId || !keySecret || !accountNumber) {
      throw new Error(
        'RazorpayPayoutService requires keyId, keySecret, and accountNumber. ' +
        'Set RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_FUND_ACCOUNT.'
      )
    }
    this.accountNumber = accountNumber
    // Credentials encoded once; never serialised into a response
    const encoded = Buffer.from(`${keyId}:${keySecret}`).toString('base64')
    this._client = axios.create({
      baseURL: RAZORPAY_BASE_URL,
      timeout: 10_000,
      headers: {
        Authorization: `Basic ${encoded}`,
        'Content-Type': 'application/json',
      },
    })
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

  /** Convert INR (float) to integer paise. 1 INR = 100 paise. */
  static inrToPaise (inr) {
    if (typeof inr !== 'number' || !isFinite(inr) || inr < 0) {
      throw new TypeError(`inrToPaise: invalid amount "${inr}"`)
    }
    return Math.round(inr * 100)
  }

  /**
   * Map a Razorpay payout status string to an internal status.
   * @param {string} razorpayStatus
   * @returns {'PROCESSING'|'PAID'|'FAILED'|'UNKNOWN'}
   */
  static mapStatus (razorpayStatus) {
    return PAYOUT_STATUS_MAP[razorpayStatus] ?? 'UNKNOWN'
  }

  // ── Razorpay API calls ───────────────────────────────────────────────────

  /**
   * Create a Contact representing the employee in Razorpay.
   * Contacts persist — reuse the returned id for all future fund accounts.
   *
   * @param {object} opts
   * @param {string} opts.name         Employee full name
   * @param {string} [opts.email]      Optional email
   * @param {string} [opts.phone]      Optional phone (+91XXXXXXXXXX)
   * @param {string} [opts.referenceId] Your internal employee/user ID
   * @returns {Promise<object>}  Razorpay contact entity { id, name, ... }
   */
  async createContact ({ name, email, phone, referenceId }) {
    const payload = {
      name: name || 'Employee',
      type: 'employee',
    }
    if (email)       payload.email        = email
    if (phone)       payload.contact      = phone
    if (referenceId) payload.reference_id = referenceId

    const { data } = await this._client.post('/contacts', payload)
    return data
  }

  /**
   * Create a Fund Account (UPI VPA) linked to a Razorpay Contact.
   * Once created, the fund_account id can be stored and reused.
   *
   * @param {object} opts
   * @param {string} opts.contactId  Razorpay contact id (cont_xxx)
   * @param {string} opts.upiId     UPI VPA string  e.g. "rahul@okaxis"
   * @returns {Promise<object>}  Razorpay fund_account entity { id, vpa, ... }
   */
  async createFundAccount ({ contactId, upiId }) {
    const { data } = await this._client.post('/fund_accounts', {
      contact_id:   contactId,
      account_type: 'vpa',
      vpa:          { address: upiId },
    })
    return data
  }

  /**
   * Create the actual payout to an employee fund account.
   *
   * Uses an idempotency key equal to referenceId so a retry with the same
   * referralId is safe and will not double-pay.
   *
   * @param {object} opts
   * @param {string} opts.fundAccountId  Razorpay fund account id (fa_xxx)
   * @param {number} opts.amountInr      Rupees (will be converted to paise)
   * @param {string} opts.referenceId    Your internal ref — used as idempotency key
   * @param {object} [opts.notes]        Metadata stored on the payout
   * @returns {Promise<object>}  Razorpay payout entity { id, status, amount, ... }
   */
  async createPayout ({ fundAccountId, amountInr, referenceId, notes = {} }) {
    const amountPaise = RazorpayPayoutService.inrToPaise(amountInr)
    const { data } = await this._client.post(
      '/payouts',
      {
        account_number:       this.accountNumber,
        fund_account_id:      fundAccountId,
        amount:               amountPaise,
        currency:             'INR',
        mode:                 'UPI',
        purpose:              'payout',
        queue_if_low_balance: true,
        reference_id:         referenceId,
        narration:            'HospRecruit referral bonus',
        notes,
      },
      {
        // Razorpay uses this header to deduplicate retries
        headers: { 'X-Payout-Idempotency': referenceId },
      }
    )
    return data
  }

  /**
   * Fetch a payout's current status from Razorpay.
   * Poll this after creation if the initial status is PROCESSING, or call
   * it from your webhook handler to refresh the DB record.
   *
   * @param {string} payoutId  e.g. "pout_xxx"
   * @returns {Promise<object>}
   */
  async fetchPayout (payoutId) {
    const { data } = await this._client.get(`/payouts/${payoutId}`)
    return data
  }

  // ── High-level orchestration ──────────────────────────────────────────────

  /**
   * End-to-end referral bonus payout.
   *
   * Pass existingFundAccountId to skip Contact + FundAccount creation
   * (you should store this after the first payout and reuse it).
   *
   * @param {object} opts
   * @param {string}  opts.referralId            Internal referral UUID (used as idempotency key)
   * @param {string}  opts.upiId                 Employee UPI VPA
   * @param {number}  opts.amountInr             Rupees to pay
   * @param {string}  [opts.employeeName]        Name on the Razorpay contact
   * @param {string}  [opts.employeeEmail]       Optional email
   * @param {string}  [opts.existingFundAccountId] Skip Contact+FundAccount creation if provided
   * @returns {Promise<{
   *   payoutId: string,
   *   status: string,
   *   internalStatus: 'PROCESSING'|'PAID'|'FAILED',
   *   amountPaise: number,
   *   fundAccountId: string,
   *   mock: false,
   *   raw: object
   * }>}
   */
  async processReferralPayout ({
    referralId, upiId, amountInr,
    employeeName = 'Employee', employeeEmail = null,
    existingFundAccountId = null,
  }) {
    let fundAccountId = existingFundAccountId

    if (!fundAccountId) {
      const contact = await this.createContact({
        name:        employeeName,
        email:       employeeEmail,
        referenceId: `emp-${referralId}`,
      })
      const fa = await this.createFundAccount({
        contactId: contact.id,
        upiId,
      })
      fundAccountId = fa.id
    }

    const payout = await this.createPayout({
      fundAccountId,
      amountInr,
      referenceId: referralId,
      notes: { referral_id: referralId, upi_id: upiId },
    })

    return {
      payoutId:       payout.id,
      status:         payout.status,
      internalStatus: RazorpayPayoutService.mapStatus(payout.status),
      amountPaise:    payout.amount,
      fundAccountId,
      mock:           false,
      raw:            payout,
    }
  }

  // ── Webhook helper ────────────────────────────────────────────────────────

  /**
   * Parse a Razorpay payout webhook payload.
   * Call this after you have verified the webhook signature with
   * Razorpay's SDK / HMAC check.
   *
   * @param {object} payload  Raw parsed JSON from Razorpay
   * @returns {{ payoutId, internalStatus, referralId, amountPaise, rawStatus }}
   * @throws if the payload is malformed
   */
  static parseWebhookPayload (payload) {
    const entity = payload?.payload?.payout?.entity
    if (!entity?.id) {
      throw new Error('Invalid Razorpay webhook payload: missing payout entity')
    }
    return {
      payoutId:       entity.id,
      internalStatus: RazorpayPayoutService.mapStatus(entity.status),
      referralId:     entity.notes?.referral_id ?? null,
      amountPaise:    entity.amount,
      rawStatus:      entity.status,
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Factory — reads credentials from environment (secrets stay server-side)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Build a service instance from env vars, or return null for mock mode.
 * Never call this from frontend code.
 *
 * @returns {RazorpayPayoutService|null}
 */
function createRazorpayPayoutService () {
  const keyId         = process.env.RAZORPAY_KEY_ID
  const keySecret     = process.env.RAZORPAY_KEY_SECRET
  const accountNumber = process.env.RAZORPAY_FUND_ACCOUNT

  if (!keyId || !keySecret || !accountNumber) {
    return null   // caller must handle null as mock mode
  }
  return new RazorpayPayoutService({ keyId, keySecret, accountNumber })
}

module.exports = {
  RazorpayPayoutService,
  createRazorpayPayoutService,
  PAYOUT_STATUS_MAP,
}
