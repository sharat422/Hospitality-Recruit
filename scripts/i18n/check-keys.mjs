#!/usr/bin/env node
/**
 * Report missing and untranslated Staff Ops keys per language (requirement 9).
 *
 *   node scripts/i18n/check-keys.mjs           # human-readable report
 *   node scripts/i18n/check-keys.mjs --json    # machine-readable
 *   node scripts/i18n/check-keys.mjs --ci      # exit 1 if anything is missing
 *
 * "Missing"      = the key exists in English but not in this language.
 * "Untranslated" = present but byte-identical to English. Sometimes correct
 *                  (a loanword like "OT"), so it is reported, not failed.
 * "Orphan"       = present in this language but gone from English.
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const LOCALES = resolve(HERE, '../../frontend/src/locales')
const SOURCE = 'en'

const args = new Set(process.argv.slice(2))
const asJson = args.has('--json')
const ci = args.has('--ci')

if (!existsSync(LOCALES)) {
  console.error(`No locales directory at ${LOCALES}`)
  process.exit(2)
}

const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'))

const languages = readdirSync(LOCALES, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort()

const namespaces = readdirSync(join(LOCALES, SOURCE))
  .filter((name) => name.endsWith('.json'))
  .map((name) => name.replace(/\.json$/, ''))
  .sort()

const statusPath = join(LOCALES, '_status.json')
const status = existsSync(statusPath) ? readJson(statusPath) : { reviewedKeys: {} }

const report = { source: SOURCE, namespaces, languages: {} }
let totalMissing = 0

for (const language of languages) {
  if (language === SOURCE) continue
  const entry = { missing: [], untranslated: [], orphan: [], needsReview: 0, total: 0 }
  const reviewed = new Set(status.reviewedKeys?.[language] ?? [])

  for (const namespace of namespaces) {
    const sourceFile = join(LOCALES, SOURCE, `${namespace}.json`)
    const targetFile = join(LOCALES, language, `${namespace}.json`)
    const source = readJson(sourceFile)
    const target = existsSync(targetFile) ? readJson(targetFile) : {}

    for (const [key, englishValue] of Object.entries(source)) {
      entry.total += 1
      const id = `${namespace}.${key}`
      if (!(key in target)) {
        entry.missing.push(id)
        continue
      }
      if (target[key] === englishValue) entry.untranslated.push(id)
      if (!reviewed.has(id)) entry.needsReview += 1
    }
    for (const key of Object.keys(target)) {
      if (!(key in source)) entry.orphan.push(`${namespace}.${key}`)
    }
  }

  entry.coveragePercent = entry.total
    ? Number((((entry.total - entry.missing.length) / entry.total) * 100).toFixed(1))
    : 100
  totalMissing += entry.missing.length
  report.languages[language] = entry
}

if (asJson) {
  console.log(JSON.stringify(report, null, 2))
} else {
  console.log(`\nStaff Ops translation status — source: ${SOURCE}`)
  console.log(`namespaces: ${namespaces.join(', ')}\n`)
  const pad = (s, n) => String(s).padEnd(n)
  console.log(pad('lang', 6) + pad('coverage', 10) + pad('missing', 9) + pad('same as en', 12) + pad('orphan', 8) + 'needs review')
  console.log('-'.repeat(62))
  for (const [language, entry] of Object.entries(report.languages)) {
    console.log(
      pad(language, 6) +
      pad(`${entry.coveragePercent}%`, 10) +
      pad(entry.missing.length, 9) +
      pad(entry.untranslated.length, 12) +
      pad(entry.orphan.length, 8) +
      `${entry.needsReview}/${entry.total}`,
    )
  }
  for (const [language, entry] of Object.entries(report.languages)) {
    if (entry.missing.length) {
      console.log(`\n  ${language} missing (${entry.missing.length}):`)
      for (const id of entry.missing.slice(0, 20)) console.log(`    - ${id}`)
      if (entry.missing.length > 20) console.log(`    … and ${entry.missing.length - 20} more`)
    }
    if (entry.orphan.length) {
      console.log(`\n  ${language} orphaned (${entry.orphan.length}) — removed from English:`)
      for (const id of entry.orphan.slice(0, 10)) console.log(`    - ${id}`)
    }
  }
  console.log('')
}

if (ci && totalMissing > 0) {
  console.error(`${totalMissing} key(s) missing. Run the CSV export to send them for translation.`)
  process.exit(1)
}
