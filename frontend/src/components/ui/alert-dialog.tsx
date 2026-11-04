import * as Dialog from '@radix-ui/react-alert-dialog'
import { ComponentProps } from 'react'

export const AlertDialog = Dialog.Root
export const AlertDialogTrigger = Dialog.Trigger
export const AlertDialogTitle = Dialog.Title
export const AlertDialogDescription = Dialog.Description
export const AlertDialogAction = Dialog.Action
export const AlertDialogCancel = Dialog.Cancel
export function AlertDialogContent({ children, ...props }: ComponentProps<typeof Dialog.Content>) {
  return <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" /><Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(90vw,32rem)] -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl" {...props}>{children}</Dialog.Content></Dialog.Portal>
}
