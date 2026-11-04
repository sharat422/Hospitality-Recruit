/**
 * Shadcn/ui Button component.
 */

import * as React from "react"

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'secondary' | 'destructive' | 'ghost'
  size?: 'default' | 'sm' | 'lg' | 'icon'
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', ...props }, ref) => (
    <button
      className={`inline-flex items-center justify-center rounded-md text-sm font-medium disabled:opacity-50 ${variant === 'outline' ? 'border border-slate-300 bg-white text-slate-900' : variant === 'destructive' ? 'bg-red-600 text-white' : variant === 'ghost' ? 'hover:bg-slate-100' : 'bg-primary text-primary-foreground hover:bg-primary/90'} ${size === 'sm' ? 'px-3 py-1' : size === 'icon' ? 'h-10 w-10' : size === 'lg' ? 'px-6 py-3' : 'px-4 py-2'} ${className || ''}`}
      ref={ref}
      {...props}
    />
  )
)
Button.displayName = "Button"

export { Button }
