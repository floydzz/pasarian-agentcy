import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { api, ApiError } from '@/api/client'
import type { ProductReference } from '@/api/types'
import { Plate } from '@/components/Plate'
import { cn } from '@/lib/utils'

/** Campaign-owned packshots, rendered as protected source material.
 *
 * The selected primary is never sent to a generative image model by the still
 * and marketing-video pipelines. It is placed after generation so its real
 * label, finish and shape stay reliable in every variation.
 */
export function ProductReferenceLibrary({
  campaignId,
  references,
  disabled = false,
  onChange,
}: {
  campaignId: number
  references: ProductReference[]
  disabled?: boolean
  onChange: (references: ProductReference[]) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const primary = references.find((reference) => reference.is_primary)

  const upload = (file: File | undefined) => {
    if (!file) return
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) {
      toast.error('Choose a PNG, JPEG, or WEBP product image.')
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      toast.error('Product images must be 20 MB or smaller.')
      return
    }
    const reader = new FileReader()
    reader.onerror = () => toast.error('Could not read that product image.')
    reader.onload = async () => {
      if (typeof reader.result !== 'string') {
        toast.error('Could not read that product image.')
        return
      }
      setUploading(true)
      try {
        const added = await api.uploadProductReference(campaignId, {
          label: file.name.replace(/\.[^.]+$/, '') || 'Product image',
          data_url: reader.result,
          is_primary: references.length === 0,
        })
        onChange([added, ...references.filter((reference) => reference.id !== added.id)])
        toast.success(
          added.is_primary
            ? 'Product lock is on for this campaign.'
            : 'Product image added to the campaign library.',
        )
      } catch (error) {
        toast.error((error as ApiError).message)
      } finally {
        setUploading(false)
      }
    }
    reader.readAsDataURL(file)
  }

  const makePrimary = async (reference: ProductReference) => {
    if (reference.is_primary) return
    try {
      const updated = await api.updateProductReference(campaignId, reference.id, {
        is_primary: true,
      })
      onChange(
        references.map((item) =>
          item.id === updated.id
            ? updated
            : { ...item, is_primary: false },
        ),
      )
      toast.success(`${updated.label} is now product-locked for new work.`)
    } catch (error) {
      toast.error((error as ApiError).message)
    }
  }

  const remove = async (reference: ProductReference) => {
    if (!window.confirm(`Remove “${reference.label}” from this campaign?`)) return
    try {
      await api.deleteProductReference(campaignId, reference.id)
      const remaining = references.filter((item) => item.id !== reference.id)
      if (reference.is_primary && remaining[0]) remaining[0] = { ...remaining[0], is_primary: true }
      onChange(remaining)
    } catch (error) {
      toast.error((error as ApiError).message)
    }
  }

  return (
    <section className="mb-5 rounded-xl border border-edge bg-[rgba(233,238,247,0.025)] p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="label">Product library</p>
          <p className="mt-1 text-[0.8125rem] leading-relaxed text-text-2">
            {primary
              ? `Product lock: “${primary.label}” stays intact in new stills and campaign videos.`
              : 'Upload a product photo to keep its packshot and label intact in new creative.'}
          </p>
        </div>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(event) => {
            upload(event.target.files?.[0])
            event.currentTarget.value = ''
          }}
        />
        <button
          type="button"
          disabled={disabled || uploading}
          onClick={() => input.current?.click()}
          className="display rounded-full border border-edge px-3.5 py-2 text-[0.6875rem] text-text-2 transition-colors hover:border-edge-strong hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        >
          {uploading ? 'Adding…' : references.length ? 'Add product image' : 'Upload product image'}
        </button>
      </div>

      {references.length > 0 && (
        <div className="mt-4 flex gap-3 overflow-x-auto pb-1">
          {references.map((reference) => (
            <article
              key={reference.id}
              className={cn(
                'relative w-28 shrink-0 overflow-hidden rounded-lg border bg-void',
                reference.is_primary ? 'border-go/70' : 'border-edge',
              )}
            >
              <Plate
                src={reference.media_url}
                alt={reference.label}
                frameClassName="w-full"
                className="aspect-square w-full object-contain bg-[rgba(233,238,247,0.04)] p-1.5"
              />
              <div className="border-t border-edge px-2 py-2">
                <p className="truncate text-[0.6875rem] text-text-2" title={reference.label}>{reference.label}</p>
                <div className="mt-2 flex items-center gap-2">
                  <button
                    type="button"
                    disabled={disabled || reference.is_primary}
                    onClick={() => void makePrimary(reference)}
                    className={cn(
                      'data text-[0.5625rem] transition-colors disabled:cursor-default',
                      reference.is_primary ? 'text-go' : 'text-text-3 hover:text-foreground',
                    )}
                  >
                    {reference.is_primary ? 'Locked' : 'Use this'}
                  </button>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => void remove(reference)}
                    className="data ml-auto text-[0.5625rem] text-text-3 transition-colors hover:text-flag disabled:opacity-40"
                  >
                    ×
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
