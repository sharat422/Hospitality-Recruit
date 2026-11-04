import { useEffect,useState } from 'react';

type Toast = { title: string; description?: string; variant?: 'default' | 'destructive'; duration?: number }
const eventName = 'hosprecruit:toast'
function toast(message: Toast) { window.dispatchEvent(new CustomEvent(eventName, { detail: message })) }
export function useToast() { return { toast } }
export function Toaster() {
  const [message, setMessage] = useState<Toast | null>(null)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    const receive = (event: Event) => {
      const next = (event as CustomEvent<Toast>).detail
      clearTimeout(timer)
      setMessage(next)
      timer = setTimeout(() => setMessage(null), next.duration ?? 5000)
    }
    window.addEventListener(eventName, receive)
    return () => { clearTimeout(timer); window.removeEventListener(eventName, receive) }
  }, [])
  return <div role="status" aria-live="polite" className="fixed bottom-4 right-4 z-[100]">{message && <div className={`max-w-sm rounded-lg border bg-white p-4 shadow-lg ${message.variant === 'destructive' ? 'text-red-700' : 'text-slate-900'}`}><strong>{message.title}</strong><p>{message.description}</p><button onClick={() => setMessage(null)} aria-label="Dismiss notification">Dismiss</button></div>}</div>
}
