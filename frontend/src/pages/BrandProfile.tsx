import { useEffect, useMemo, useState } from 'react'
import { motion } from 'motion/react'
import { toast } from 'sonner'
import { Page } from '@/components/os/Shell'
import { PageHead } from '@/components/os/Sidebar'
import { ApiError, api } from '@/api/client'
import type { BrandProduct, BrandProfile as Profile, BrandProfileWrite } from '@/api/types'
import { MICRO } from '@/lib/motion'

type DraftProduct = Omit<BrandProduct, 'price' | 'benefits'> & {
  price: string
  benefits: string
}

type Draft = Omit<BrandProfileWrite, 'website' | 'approved_claims' | 'restrictions' | 'products'> & {
  website: string
  products: DraftProduct[]
  approved_claims: string
  restrictions: string
}

const inputClass =
  'mt-2 w-full rounded-lg border border-edge bg-[rgba(233,238,247,0.03)] px-3.5 py-2.5 text-[0.8125rem] leading-relaxed text-foreground transition-colors outline-none placeholder:text-text-3 focus:border-edge-strong focus:bg-[rgba(233,238,247,0.06)]'

function blankProduct(): DraftProduct {
  return { name: '', description: '', price: '', benefits: '' }
}

function emptyDraft(): Draft {
  return {
    company_name: '',
    industry: '',
    website: '',
    description: '',
    brand_voice: '',
    target_audience: '',
    products: [blankProduct()],
    approved_claims: '',
    restrictions: '',
  }
}

function toDraft(profile: Profile): Draft {
  if (!profile.configured) return emptyDraft()
  return {
    company_name: profile.company_name,
    industry: profile.industry,
    website: profile.website ?? '',
    description: profile.description,
    brand_voice: profile.brand_voice,
    target_audience: profile.target_audience,
    products: profile.products.map((product) => ({
      ...product,
      price: product.price ?? '',
      benefits: product.benefits ?? '',
    })),
    approved_claims: profile.approved_claims ?? '',
    restrictions: profile.restrictions ?? '',
  }
}

function toPayload(draft: Draft): BrandProfileWrite {
  return {
    ...draft,
    website: draft.website.trim() || null,
    approved_claims: draft.approved_claims.trim() || null,
    restrictions: draft.restrictions.trim() || null,
    products: draft.products.map((product) => ({
      ...product,
      price: product.price.trim() || null,
      benefits: product.benefits.trim() || null,
    })),
  }
}

/** The one workspace's source of truth.  Saved text becomes the company
 * corpus immediately, so a future campaign is grounded in what the person
 * wrote here rather than the bundled demonstration brand. */
export function BrandProfile() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saved, setSaved] = useState<Draft | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .getBrandProfile()
      .then((received) => {
        const next = toDraft(received)
        setProfile(received)
        setDraft(next)
        setSaved(next)
      })
      .catch((error: ApiError) => toast.error(error.message))
  }, [])

  const dirty = useMemo(
    () => draft !== null && saved !== null && JSON.stringify(draft) !== JSON.stringify(saved),
    [draft, saved],
  )

  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (!draft || saving) return
    setSaving(true)
    try {
      const received = await api.saveBrandProfile(toPayload(draft))
      const next = toDraft(received)
      setProfile(received)
      setDraft(next)
      setSaved(next)
      toast.success('Brand profile saved — future plans will use it as ground truth')
    } catch (error) {
      toast.error((error as ApiError).message)
    } finally {
      setSaving(false)
    }
  }

  if (!draft || !profile) {
    return (
      <Page>
        <p className="mt-14 text-sm text-text-3">Loading your workspace…</p>
      </Page>
    )
  }

  return (
    <Page>
      <PageHead
        title="Brand profile"
        action={
          <p className="data shrink-0 text-text-3">
            {profile.configured
              ? `${profile.knowledge_chunks} grounded ${profile.knowledge_chunks === 1 ? 'chunk' : 'chunks'}`
              : 'not configured'}
          </p>
        }
      >
        This is the company truth the crew may cite. Save your profile before planning a
        campaign; it replaces the bundled demo brand for this workspace.
      </PageHead>

      <form onSubmit={save} className="mt-10 max-w-4xl space-y-5 pb-12">
        <Section title="Company">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Company name" htmlFor="company-name" required>
              <input
                id="company-name"
                value={draft.company_name}
                onChange={(event) => setDraft({ ...draft, company_name: event.target.value })}
                placeholder="Kawan Kopi"
                className={inputClass}
              />
            </Field>
            <Field label="Industry" htmlFor="industry" required>
              <input
                id="industry"
                value={draft.industry}
                onChange={(event) => setDraft({ ...draft, industry: event.target.value })}
                placeholder="Specialty coffee"
                className={inputClass}
              />
            </Field>
          </div>
          <Field label="Website" htmlFor="website" hint="Optional">
            <input
              id="website"
              value={draft.website}
              onChange={(event) => setDraft({ ...draft, website: event.target.value })}
              placeholder="https://yourcompany.com"
              className={inputClass}
            />
          </Field>
          <Field label="What the company does" htmlFor="description" required>
            <textarea
              id="description"
              rows={4}
              value={draft.description}
              onChange={(event) => setDraft({ ...draft, description: event.target.value })}
              placeholder="What you sell, what makes the company distinctive, and where you operate."
              className={`${inputClass} resize-y`}
            />
          </Field>
        </Section>

        <Section title="Audience and voice">
          <Field label="Target audience" htmlFor="audience" required>
            <textarea
              id="audience"
              rows={3}
              value={draft.target_audience}
              onChange={(event) => setDraft({ ...draft, target_audience: event.target.value })}
              placeholder="Who they are, where they are, and what they care about."
              className={`${inputClass} resize-y`}
            />
          </Field>
          <Field label="Brand voice" htmlFor="voice" required>
            <textarea
              id="voice"
              rows={3}
              value={draft.brand_voice}
              onChange={(event) => setDraft({ ...draft, brand_voice: event.target.value })}
              placeholder="e.g. Warm, concise, bilingual when natural. Never patronising."
              className={`${inputClass} resize-y`}
            />
          </Field>
        </Section>

        <Section title="Products and services" detail="Give the crew facts it can use, not a sales pitch.">
          <div className="space-y-4">
            {draft.products.map((product, index) => (
              <ProductCard
                key={index}
                product={product}
                index={index}
                removable={draft.products.length > 1}
                onChange={(field, value) =>
                  setDraft({
                    ...draft,
                    products: draft.products.map((current, productIndex) =>
                      productIndex === index ? { ...current, [field]: value } : current,
                    ),
                  })
                }
                onRemove={() =>
                  setDraft({
                    ...draft,
                    products: draft.products.filter((_, productIndex) => productIndex !== index),
                  })
                }
              />
            ))}
          </div>
          <button
            type="button"
            onClick={() => setDraft({ ...draft, products: [...draft.products, blankProduct()] })}
            className="mt-4 text-[0.8125rem] text-text-2 transition-colors hover:text-foreground"
          >
            + Add another product
          </button>
        </Section>

        <Section title="Claims and guardrails" detail="These boundaries apply to every agent before a concept reaches review.">
          <Field label="Approved claims" htmlFor="claims" hint="Optional">
            <textarea
              id="claims"
              rows={3}
              value={draft.approved_claims}
              onChange={(event) => setDraft({ ...draft, approved_claims: event.target.value })}
              placeholder="Facts and promises the company can substantiate."
              className={`${inputClass} resize-y`}
            />
          </Field>
          <Field label="Restrictions or claims to avoid" htmlFor="restrictions" hint="Optional">
            <textarea
              id="restrictions"
              rows={3}
              value={draft.restrictions}
              onChange={(event) => setDraft({ ...draft, restrictions: event.target.value })}
              placeholder="e.g. Do not make medical claims; do not mention competitors."
              className={`${inputClass} resize-y`}
            />
          </Field>
        </Section>

        <div className="flex items-center gap-4 pt-2">
          <motion.button
            type="submit"
            disabled={!dirty || saving}
            whileHover={!dirty || saving ? undefined : { y: -1 }}
            whileTap={!dirty || saving ? undefined : { scale: 0.985 }}
            transition={MICRO}
            className="display rounded-full bg-foreground px-5 py-2.5 text-[0.8125rem] text-void transition-opacity disabled:cursor-not-allowed disabled:opacity-35"
          >
            {saving ? 'Saving profile…' : 'Save brand profile'}
          </motion.button>
          {dirty && <span className="data text-text-3">unsaved changes</span>}
        </div>
      </form>
    </Page>
  )
}

function Section({ title, detail, children }: { title: string; detail?: string; children: React.ReactNode }) {
  return (
    <section className="glass rounded-xl px-5 py-5 sm:px-7 sm:py-6">
      <h2 className="display text-[0.9375rem]">{title}</h2>
      {detail && <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-text-3">{detail}</p>}
      <div className="mt-5 space-y-5">{children}</div>
    </section>
  )
}

function Field({ label, htmlFor, hint, required, children }: {
  label: string
  htmlFor: string
  hint?: string
  required?: boolean
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <label htmlFor={htmlFor} className="label">{label}</label>
        {required && <span className="data text-text-3">required</span>}
        {hint && <span className="data text-text-3">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function ProductCard({ product, index, removable, onChange, onRemove }: {
  product: DraftProduct
  index: number
  removable: boolean
  onChange: (field: keyof DraftProduct, value: string) => void
  onRemove: () => void
}) {
  const prefix = `product-${index}`
  return (
    <div className="rounded-lg border border-edge bg-[rgba(233,238,247,0.035)] p-4 sm:p-5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="data text-text-3">product {index + 1}</p>
        {removable && (
          <button type="button" onClick={onRemove} className="text-[0.75rem] text-text-3 transition-colors hover:text-foreground">
            Remove
          </button>
        )}
      </div>
      <div className="mt-4 grid gap-5 sm:grid-cols-2">
        <Field label="Product name" htmlFor={`${prefix}-name`} required>
          <input id={`${prefix}-name`} value={product.name} onChange={(event) => onChange('name', event.target.value)} placeholder="Rumah Blend" className={inputClass} />
        </Field>
        <Field label="Price or offer" htmlFor={`${prefix}-price`} hint="Optional">
          <input id={`${prefix}-price`} value={product.price} onChange={(event) => onChange('price', event.target.value)} placeholder="RM42 / 250g" className={inputClass} />
        </Field>
      </div>
      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <Field label="What it is" htmlFor={`${prefix}-description`} required>
          <textarea id={`${prefix}-description`} rows={3} value={product.description} onChange={(event) => onChange('description', event.target.value)} placeholder="A concise, factual description." className={`${inputClass} resize-y`} />
        </Field>
        <Field label="Key benefits" htmlFor={`${prefix}-benefits`} hint="Optional">
          <textarea id={`${prefix}-benefits`} rows={3} value={product.benefits} onChange={(event) => onChange('benefits', event.target.value)} placeholder="Benefits that can be substantiated." className={`${inputClass} resize-y`} />
        </Field>
      </div>
    </div>
  )
}
