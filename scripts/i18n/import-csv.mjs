#!/usr/bin/env node
/**
 * Import a translator's reviewed CSV back into the locale files
 * (requirements 9 and 10).
 *
 *   node scripts/i18n/import-csv.mjs staff-ops-strings.csv
 *   node scripts/i18n/import-csv.mjs staff-ops-strings.csv --dry-run
 *
 * Rows marked `approved` are recorded in _status.json so they stop appearing
 * as needs_review. Rows whose translation is blank are skipped, never written
 * as empty strings — a blank cell means "not done yet", not "delete this".
 *
 * English is the source of truth: a row for a key that no longer exists in
 * English is reported and skipped rather than resurrecting a dead key.
 */

import { readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const LOCALES = resolve(HERE, '../../frontend/src/locales')
const SOURCE = 'en'

const argv = process.argv.slice(2)
const csvPath = argv.find((a) => !a.startsWith('--'))
const dryRun = argv.includes('--dry-run')

if (!csvPath) {
  console.error('Usage: node scripts/i18n/import-csv.mjs <file.csv> [--dry-run]')
  process.exit(2)
}

/** Minimal RFC 4180 parser: handles quotes, embedded commas and newlines. */
function parseCsv(text) {
  const rows = []
  let row = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 1 } else { quoted = false }
      } else field += ch
      continue
    }
    if (ch === '"') { quoted = true; continue }
    if (ch === ',') { row.push(field); field = ''; continue }
    if (ch === '\r') continue
    if (ch === '\n') { row.push(field); rows.push(row); row = []; field = ''; continue }
    field += ch
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row) }
  return rows.filter((r) => r.some((c) => c !== ''))
}

const raw = readFileSync(csvPath, 'utf8').replace(/^﻿/, '')
const rows = parseCsv(raw)
if (!rows.length) {
  console.error('CSV is empty')
  process.exit(2)
}

const header = rows[0].map((h) => h.trim().toLowerCase())
const need = ['namespace', 'key', 'language', 'translation']
for (const column of need) {
  if (!header.includes(column)) {
    console.error(`CSV is missing a "${column}" column. Found: ${header.join(', ')}`)
    process.exit(2)
  }
}
const col = Object.fromEntries(header.map((h, i) => [h, i]))

const readJson = (p) => JSON.parse(readFileSync(p, 'utf8'))
const knownLanguages = new Set(
  readdirSync(LOCALES, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name),
)

const changes = new Map()      // "lang/ns" -> { key: translation }
const approvals = new Map()    // lang -> Set(ids)
const problems = []
let skippedBlank = 0
let unchanged = 0

for (const row of rows.slice(1)) {
  const namespace = row[col.namespace]?.trim()
  const key = row[col.key]?.trim()
  const language = row[col.language]?.trim()
  const translation = row[col.translation] ?? ''
  const status = (row[col.status] ?? '').trim().toLowerCase()

  if (!namespace || !key || !language) continue
  if (!knownLanguages.has(language)) { problems.push(`unknown language "${language}" (${namespace}.${key})`); continue }
  if (language === SOURCE) { problems.push(`refusing to overwrite English: ${namespace}.${key}`); continue }

  const sourceFile = join(LOCALES, SOURCE, `${namespace}.json`)
  if (!existsSync(sourceFile)) { problems.push(`unknown namespace "${namespace}"`); continue }
  if (!(key in readJson(sourceFile))) { problems.push(`"${namespace}.${key}" no longer exists in English — skipped`); continue }

  if (!translation.trim()) { skippedBlank += 1; continue }

  const bucket = `${language}/${namespace}`
  if (!changes.has(bucket)) changes.set(bucket, {})
  changes.get(bucket)[key] = translation

  if (status === 'approved') {
    if (!approvals.has(language)) approvals.set(language, new Set())
    approvals.get(language).add(`${namespace}.${key}`)
  }
}

let written = 0
for (const [bucket, updates] of changes) {
  const [language, namespace] = bucket.split('/')
  const file = join(LOCALES, language, `${namespace}.json`)
  const current = existsSync(file) ? readJson(file) : {}
  let touched = 0
  for (const [key, value] of Object.entries(updates)) {
    if (current[key] === value) { unchanged += 1; continue }
    current[key] = value
    touched += 1
  }
  if (!touched) continue
  written += touched
  if (!dryRun) {
    const ordered = Object.fromEntries(Object.entries(current).sort(([a], [b]) => a.localeCompare(b)))
    writeFileSync(file, JSON.stringify(ordered, null, 2) + '\n', 'utf8')
  }
  console.log(`${dryRun ? '[dry-run] ' : ''}${bucket}: ${touched} updated`)
}

const statusPath = join(LOCALES, '_status.json')
const status = existsSync(statusPath)
  ? readJson(statusPath)
  : { sourceLanguage: SOURCE, note: '', reviewedKeys: {} }
let approved = 0
for (const [language, ids] of approvals) {
  const existing = new Set(status.reviewedKeys?.[language] ?? [])
  const before = existing.size
  for (const id of ids) existing.add(id)
  status.reviewedKeys[language] = [...existing].sort()
  approved += existing.size - before
}
if (!dryRun && approved) writeFileSync(statusPath, JSON.stringify(status, null, 2) + '\n', 'utf8')

console.log('')
console.log(`Translations written : ${written}`)
console.log(`Newly approved       : ${approved}`)
console.log(`Already correct      : ${unchanged}`)
console.log(`Blank, left alone    : ${skippedBlank}`)
if (problems.length) {
  console.log(`\nProblems (${problems.length}):`)
  for (const problem of problems.slice(0, 20)) console.log(`  - ${problem}`)
  if (problems.length > 20) console.log(`  … and ${problems.length - 20} more`)
}
if (dryRun) console.log('\nDry run — nothing was written.')
