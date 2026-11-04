import { Clock3,FileText,Search,X } from 'lucide-react'
import { useEffect,useMemo,useRef,useState } from 'react'
import { useNavigate } from 'react-router-dom'
import apiClient from '../lib/api'

const CATEGORIES = [
  ['candidates', 'Candidates'], ['employees', 'Employees'], ['jobs', 'Jobs'],
  ['applications', 'Applications'], ['referrals', 'Referrals'], ['documents', 'Documents'],
  ['properties', 'Properties'], ['departments', 'Departments'], ['complaints', 'Complaints'],
] as const

interface SearchResult {
  category: string
  id: string
  title: string
  subtitle: string
  status?: string | null
  url: string
  matchType: string
}

interface RecentSearch {
  id: string
  query: string
  categories: string[]
  result_count: number
  searched_at: string
}

export function GlobalSearch() {
  const navigate = useNavigate()
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<SearchResult[]>([])
  const [recent, setRecent] = useState<RecentSearch[]>([])
  const [category, setCategory] = useState('all')
  const [error, setError] = useState('')

  const categoryParam = category === 'all' ? undefined : category
  const grouped = useMemo(() => results.reduce<Record<string, SearchResult[]>>((acc, item) => {
    const group = acc[item.category] ??= []
    group.push(item)
    return acc
  }, {}), [results])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault(); setOpen(true); inputRef.current?.focus()
      }
      if (event.key === 'Escape') setOpen(false)
    }
    const onClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onClick)
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('mousedown', onClick) }
  }, [])

  useEffect(() => {
    if (!open || query.trim().length >= 2) return
    apiClient.get<{ recent: RecentSearch[] }>('/search/recent')
      .then(({ data }) => setRecent(data.recent)).catch(() => setRecent([]))
  }, [open, query])

  useEffect(() => {
    const value = query.trim()
    if (value.length < 2) { setResults([]); setLoading(false); return }
    setLoading(true); setError('')
    const timer = window.setTimeout(() => {
      apiClient.get<{ results: SearchResult[] }>('/search/autocomplete', {
        params: { q: value, limit: 10, categories: categoryParam },
      }).then(({ data }) => setResults(data.results))
        .catch((err) => setError(err.response?.data?.detail ?? 'Search is unavailable.'))
        .finally(() => setLoading(false))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [query, categoryParam])

  const submit = async (value = query) => {
    const clean = value.trim()
    if (clean.length < 2) return
    setQuery(clean); setLoading(true); setError(''); setOpen(true)
    try {
      const { data } = await apiClient.get<{ results: SearchResult[] }>('/search', {
        params: { q: clean, limit: 30, categories: categoryParam },
      })
      setResults(data.results)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Search is unavailable.')
    } finally { setLoading(false) }
  }

  const choose = (item: SearchResult) => {
    setOpen(false); setQuery(''); navigate(item.url)
  }

  const clearRecent = async () => {
    await apiClient.delete('/search/recent'); setRecent([])
  }

  return (
    <div ref={rootRef} className="relative w-full max-w-2xl">
      <form onSubmit={(event) => { event.preventDefault(); void submit() }} className="flex h-11 w-full items-center rounded-md border border-gray-300 bg-white focus-within:border-purple-500 focus-within:ring-2 focus-within:ring-purple-100">
        <Search className="ml-3 h-4 w-4 shrink-0 text-gray-400" />
        <input ref={inputRef} value={query} onChange={event => { setQuery(event.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)} aria-label="Search across HospRecruit" aria-expanded={open}
          placeholder="Search people, jobs, referrals…" className="min-w-0 flex-1 border-0 bg-transparent px-2 text-sm outline-none" />
        {query && <button type="button" onClick={() => setQuery('')} className="p-2 text-gray-400 hover:text-gray-700" aria-label="Clear search"><X className="h-4 w-4" /></button>}
        <select value={category} onChange={event => setCategory(event.target.value)} aria-label="Search category"
          className="mr-1 hidden h-9 max-w-36 border-0 border-l border-gray-200 bg-white px-2 text-xs text-gray-600 outline-none sm:block">
          <option value="all">All categories</option>
          {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <kbd className="mr-2 hidden rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[10px] text-gray-400 lg:block">Ctrl K</kbd>
      </form>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-2 max-h-[70vh] overflow-y-auto rounded-md border border-gray-200 bg-white shadow-xl">
          <div className="border-b border-gray-100 p-2 sm:hidden">
            <select value={category} onChange={event => setCategory(event.target.value)} className="h-10 w-full rounded border border-gray-200 px-2 text-sm">
              <option value="all">All categories</option>
              {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
          {loading && <p className="px-4 py-6 text-center text-sm text-gray-500">Searching…</p>}
          {error && <p className="px-4 py-4 text-sm text-red-700">{error}</p>}
          {!loading && !error && query.trim().length >= 2 && results.length === 0 && <p className="px-4 py-6 text-center text-sm text-gray-500">No authorized results found.</p>}
          {!loading && query.trim().length >= 2 && Object.entries(grouped).map(([group, items]) => (
            <section key={group} aria-label={group}>
              <p className="sticky top-0 border-y border-gray-100 bg-gray-50 px-4 py-1.5 text-xs font-semibold uppercase text-gray-500">{group}</p>
              {items.map(item => <button key={`${item.category}:${item.id}`} type="button" onClick={() => choose(item)} className="flex min-h-14 w-full items-center gap-3 px-4 py-2 text-left hover:bg-purple-50 focus:bg-purple-50 focus:outline-none">
                <FileText className="h-4 w-4 shrink-0 text-purple-500" />
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-gray-900">{item.title}</span><span className="block truncate text-xs text-gray-500">{item.subtitle}</span></span>
                {item.status && <span className="max-w-24 truncate rounded bg-gray-100 px-2 py-1 text-[10px] font-medium text-gray-600">{item.status}</span>}
              </button>)}
            </section>
          ))}
          {!loading && query.trim().length < 2 && (
            <section>
              <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2"><span className="text-xs font-semibold uppercase text-gray-500">Recent searches</span>{recent.length > 0 && <button onClick={() => void clearRecent()} className="text-xs text-purple-700">Clear</button>}</div>
              {recent.length === 0 ? <p className="px-4 py-6 text-center text-sm text-gray-500">Type at least 2 characters to search.</p> : recent.map(item => <button key={item.id} onClick={() => void submit(item.query)} className="flex min-h-12 w-full items-center gap-3 px-4 py-2 text-left hover:bg-gray-50"><Clock3 className="h-4 w-4 text-gray-400" /><span className="flex-1 truncate text-sm text-gray-700">{item.query}</span><span className="text-xs text-gray-400">{item.result_count} results</span></button>)}
            </section>
          )}
        </div>
      )}
    </div>
  )
}
