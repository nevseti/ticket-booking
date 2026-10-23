/** «Артист. Название тура» → крупная строка и подпись; у хоккея крупно — команды. */
export function splitTitle(title: string): { headline: string; subtitle: string } {
  if (title.startsWith('Хоккей. ')) return { headline: title.slice(8), subtitle: 'Хоккей' }
  const dot = title.indexOf('. ')
  if (dot === -1) return { headline: title, subtitle: '' }
  return { headline: title.slice(0, dot), subtitle: title.slice(dot + 2) }
}
