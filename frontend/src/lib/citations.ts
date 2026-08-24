/** The planner writes its citations into the rationale text as
 * `… [sources: brand.md#0-ab, brand.md#2-cd]`. Splitting them back out lets the
 * reviewer see the claim and the chunks it rests on as two different things. */
export function splitCitations(rationale: string): {
  text: string
  sources: string[]
} {
  const match = rationale.match(/^([\s\S]*?)\s*\[sources:\s*([^\]]*)\]\s*$/)
  if (!match) return { text: rationale.trim(), sources: [] }
  return {
    text: match[1].trim(),
    sources: match[2]
      .split(',')
      .map((source) => source.trim())
      .filter(Boolean),
  }
}
