import { useEffect, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { Concept } from '@/api/types'

/** The gate's edit action, as a handoff rather than an editor.
 *
 * You say what should change; the planner reworks the concept against the
 * knowledge base and has to cite it again. That is deliberate — typing directly
 * into the concept would let an edit introduce a claim the brand cannot make. */
export function EditDialog({
  concept,
  open,
  onOpenChange,
  onSubmit,
}: {
  concept: Concept
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (note: string) => Promise<void>
}) {
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    if (open) setNote('')
  }, [open])

  async function send() {
    if (!note.trim() || sending) return
    setSending(true)
    try {
      await onSubmit(note.trim())
      onOpenChange(false)
    } finally {
      setSending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="tracking-tight">Send this concept back</DialogTitle>
          <DialogDescription>
            The planner reworks “{concept.theme}” around your note and re-cites the
            knowledge base. It keeps whatever you don’t ask it to change.
          </DialogDescription>
        </DialogHeader>

        <Textarea
          autoFocus
          rows={4}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Drop the LRT setting — our customers shop from home."
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) send()
          }}
        />

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!note.trim() || sending} onClick={send}>
            {sending ? 'Reworking…' : 'Rework concept'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
