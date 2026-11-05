# Staff Ops Translation Glossary

**Status:** proposed — the starter glossary referred to in the brief did not come
through, so this is my proposal. Replace it with yours if you have one.

## The rule

**Hotel words that staff already say in English stay as loanwords, written in
the local script.** A Chennai steward says "ஷிஃப்ட்", not a Tamil coinage for
"shift". Translating these makes screens *harder* to read, not easier.

Everything else — verbs, status words, plain nouns — is properly translated.

---

## Loanwords: transliterate, never translate

| English | हिंदी | తెలుగు | தமிழ் | ಕನ್ನಡ |
|---|---|---|---|---|
| Shift | शिफ्ट | షిఫ్ట్ | ஷிஃப்ட் | ಶಿಫ್ಟ್ |
| Roster | रोस्टर | రోస్టర్ | ரோஸ்டர் | ರೋಸ್ಟರ್ |
| Duty | ड्यूटी | డ్యూటీ | டியூட்டி | ಡ್ಯೂಟಿ |
| OT (overtime) | ओटी | ఓటీ | ஓடீ | ಓಟಿ |
| Punch in / out | पंच इन / आउट | పంచ్ ఇన్ / అవుట్ | பஞ்ச் இன் / அவுட் | ಪಂಚ್ ಇನ್ / ಔಟ್ |
| Comp Off | क्षतिपूर्ति अवकाश | కాంప్ ఆఫ్ | காம்ப் ஆஃப் | ಕಾಂಪ್ ಆಫ್ |
| Hotel | होटल | హోటల్ | ஹோட்டல் | ಹೋಟೆಲ್ |
| Casual (pool) | कैजुअल | కాజువల్ | கேஷுவல் | ಕ್ಯಾಶುಯಲ್ |
| Agency | एजेंसी | ఏజెన్సీ | ஏஜென்சி | ಏಜೆನ್ಸಿ |
| PF / ESI | पीएफ / ईएसआई | పీఎఫ్ / ఈఎస్ఐ | பிஎஃப் / ஈஎஸ்ஐ | ಪಿಎಫ್ / ಇಎಸ್‌ಐ |
| Profile | प्रोफ़ाइल | ప్రొఫైల్ | சுயவிவரம் | ಪ್ರೊಫೈಲ್ |
| Draft | ड्राफ्ट | డ్రాఫ్ట్ | வரைவு | ಕರಡು |

> Note the inconsistencies in the last two rows: Hindi and Telugu keep
> "profile" and "draft" as loanwords while Tamil and Kannada translate them.
> That reflects what people actually say in each language. **A reviewer should
> confirm these case by case** rather than forcing one pattern.

## Translate properly

| English | हिंदी | తెలుగు | தமிழ் | ಕನ್ನಡ |
|---|---|---|---|---|
| Present | उपस्थित | హాజరు | வந்தவர் | ಹಾಜರು |
| Absent | अनुपस्थित | గైర్హాజరు | வராதவர் | ಗೈರು |
| Weekly Off | साप्ताहिक अवकाश | వారపు సెలవు | வார விடுமுறை | ವಾರದ ರಜೆ |
| Leave | अवकाश | సెలవు | விடுப்பு | ರಜೆ |
| Approve | मंज़ूर करें | ఆమోదించండి | ஒப்புதல் | ಅನುಮೋದಿಸಿ |
| Reject | अस्वीकार करें | తిరస్కరించండి | நிராகரி | ತಿರಸ್ಕರಿಸಿ |
| Save | सेव करें | సేవ్ చేయండి | சேமி | ಉಳಿಸಿ |
| Department | विभाग | విభాగం | துறை | ವಿಭಾಗ |
| Employee | कर्मचारी | ఉద్యోగి | ஊழியர் | ನೌಕರ |
| Half Day | आधा दिन | సగం రోజు | அரை நாள் | ಅರ್ಧ ದಿನ |

---

## Tone

Staff screens address the person **politely but directly** — the imperative
form used with a colleague, not honorific officialese. Manager screens may be
slightly more formal.

- Hindi: use `करें` forms (सेव करें), not `कीजिए`.
- Telugu/Kannada: use the respectful imperative (`చేయండి`, `ಮಾಡಿ`).
- Tamil: the plain imperative (`சேமி`) is normal in app UI; `சேமியுங்கள்` reads
  as a form letter.

## Numbers, dates and money

Never translated, never localised into native-script digits:

- Digits are always 0–9. `1,00,000`, never `१,००,०००`.
- Dates are `DD-MM-YYYY`.
- Money is `₹` with Indian grouping.
- Times are 12-hour; AM/PM may use the local word (`पूर्वाह्न`, `முற்பகல்`).

Enforced in code by `frontend/src/lib/format.ts` — the `-u-nu-latn` locale
suffix forces Latin digits even in Hindi.

## Things to avoid

- **Do not translate a term differently in two screens.** "Shift" is the same
  word on the roster and on the attendance screen.
- **Do not use English word order** in Telugu/Kannada/Tamil. These are
  verb-final; a literal word-by-word rendering reads as machine output.
- **Do not abbreviate** in Indic scripts to make text fit. Fix the layout
  instead — the CSS in `staff-ops-fonts.css` lets buttons wrap.

## Review status

**Every non-English string currently in the repo is machine-made and flagged
`needs_review`.** Nothing is approved. Run:

```bash
node scripts/i18n/export-csv.mjs --needs-review
```

send the CSV to a native speaker, have them set `status` to `approved`, then:

```bash
node scripts/i18n/import-csv.mjs <file>.csv
```
