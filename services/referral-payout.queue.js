'use strict'

/**
 * referral-payout.queue.js
 *
 * Creates and exports the singleton Bull queue used by both the scheduler
 * (which adds the daily cron job) and the worker (which processes jobs).
 *
 * Environment:
 *   REDIS_URL  — Redis connection string (default: redis://localhost:6379)
 */

require('dotenv').config()

const Bull = require('bull')

const QUEUE_NAME = 'referral-payout'

const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379'

const referralPayoutQueue = new Bull(QUEUE_NAME, redisUrl, {
  defaultJobOptions: {
    removeOnComplete: 100,   // keep last 100 completed jobs for inspection
    removeOnFail:     200,   // keep last 200 failed jobs for debugging
  },
})

module.exports = referralPayoutQueue
