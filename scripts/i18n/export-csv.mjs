#!/usr/bin/env node
/**
 * Export every Staff Ops string to one CSV a translator can open in Excel
 * (requirements 9 and 10).
 *
 *   node scripts/i18n/export-csv.mjs                      -> staff-ops-strings.csv
 *   node scripts/i18n/export-csv.mjs --lang ta            -> Tamil only
 *   node scripts/i18n/export-csv.mjs --needs-review       -> only unapproved rows
 *   node scripts/i18n/export-csv.mjs --out /path/file.csv
 *
 * Columns: namespace, key, english, language, translation, status, notes
 *
 * `status` is `needs_review` for every machine-made string until a native
 * speaker marks it `approved`. Edit `translation` and/or `status` in Excel,
 * save as CSV, then run import-csv.mjs.
 *
 * The file is written UTF-8 with a BOM, because Excel on Windows otherwise
 * renders Devanagari, Telugu, Tamil and Kannada as mojibake.
 */

import { readFileSync, readdirSync, existsSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const LOCALES = resolve(HERE, '../../frontend/src/locales')
const SOURCE = 'en'

const argv = process.argv.slice(2)
const flag = (name) => {
  const i = argv.indexOf(name)
  return i === -1 ? null : argv[i + 1]
}
const onlyLanguage = flag('--lang')
const onlyNeedsReview = argv.includes('--needs-review')
const outPath = flag('--out') ?? resolve(process.cwd(), 'staff-ops-strings.csv')

const readJson = (p) => JSON.parse(readFileSync(p, 'utf8'))

const languages = readdirSync(LOCALES, { withFileTypes: true })
  .filter((e) => e.isDirectory() && e.name !== SOURCE)
  .map((e) => e.name)
  .filter((l) => !onlyLanguage || l === onlyLanguage)
  .sort()

const namespaces = readdirSync(join(LOCALES, SOURCE))
  .filter((n) => n.endsWith('.json'))
  .map((n) => n.replace(/\.json$/, ''))
  .sort()

const statusPath = join(LOCALES, '_status.json')
const status = existsSync(statusPath) ? readJson(statusPath) : { reviewedKeys: {} }

/** RFC 4180: quote everything, double any embedded quote. */
const cell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`

const rows = [['namespace', 'key', 'english', 'language', 'translation', 'status', 'notes']]
let needsReview = 0

for (const language of languages) {
  const reviewed = new Set(status.reviewedKeys?.[language] ?? [])
  for (const namespace of namespaces) {
    const source = readJson(join(LOCALES, SOURCE, `${namespace}.json`))
    const targetFile = join(LOCALES, language, `${namespace}.json`)
    const target = existsSync(targetFile) ? readJson(targetFile) : {}

    for (const [key, english] of Object.entries(source)) {
      const id = `${namespace}.${key}`
      const translation = target[key] ?? ''
      let rowStatus
      if (!translation) rowStatus = 'missing'
      else if (reviewed.has(id)) rowStatus = 'approved'
      else rowStatus = 'needs_review'

      if (onlyNeedsReview && rowStatus === 'approved') continue
      if (rowStatus !== 'approved') needsReview += 1

      const notes = translation && translation === english
        ? 'same as English — intended only for loanwords such as OT'
        : ''
      rows.push([namespace, key, english, language, translation, rowStatus, notes])
    }
  }
}

const csv = rows.map((r) => r.map(cell).join(',')).join('\r\n')
writeFileSync(outPath, '﻿' + csv, 'utf8')

console.log(`Wrote ${rows.length - 1} rows to ${outPath}`)
console.log(`Languages: ${languages.join(', ')}`)
console.log(`Needing review or missing: ${needsReview}`)
console.log('\nTranslator instructions:')
console.log('  1. Edit only the "translation" and "notes" columns.')
console.log('  2. Set "status" to approved once a native speaker is happy.')
console.log('  3. Keep hotel words (Shift, OT, Roster, Duty) as loanwords in your script.')
console.log('  4. Save as CSV UTF-8, then run: node scripts/i18n/import-csv.mjs <file>')
