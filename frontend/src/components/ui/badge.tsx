import { HTMLAttributes } from 'react'

export function Badge({ variant = 'default', className = '', ...props }: HTMLAttributes<HTMLSpanElement> & { variant?: 'default' | 'secondary' | 'destructive' | 'outline' }) {
  const styles = { default: 'bg-blue-100 text-blue-900', secondary: 'bg-slate-100 text-slate-800', destructive: 'bg-red-100 text-red-900', outline: 'border border-slate-300' }
  return <span className={`inline-flex rounded-full px-2 py-1 text-xs ${styles[variant]} ${className}`} {...props} />
}
