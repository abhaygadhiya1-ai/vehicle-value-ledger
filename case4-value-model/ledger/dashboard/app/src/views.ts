// The four team views, then the Programme office (kept apart from the tool: not a tab, an entry of its own beside
// them). Each takes its business's colour from the Round 1 deck, on chrome only and always beside its name.
import type { Layer } from './ui'

export type ViewId = 'mgmt' | 'oem' | 'fin' | 'resale' | 'programme'

// layer: the data the view shows, named once in its band; a card carries a badge only for a layer its view does not
// name (the AI look, part 3: provenance said once)
export const VIEWS: { id: ViewId; name: string; acc: string; layer: Layer; part?: number }[] = [
  { id: 'mgmt', name: 'Management', acc: 'var(--acc-mgmt)', layer: 'proto' },
  { id: 'oem', name: 'New-car incentives', acc: 'var(--acc-oem)', layer: 'proto', part: 3 },
  { id: 'fin', name: 'Captive finance', acc: 'var(--acc-fin)', layer: 'proto', part: 4 },
  { id: 'resale', name: 'Used-car resale', acc: 'var(--acc-res)', layer: 'proto', part: 5 },
  { id: 'programme', name: 'Programme office', acc: 'var(--acc-prog)', layer: 'group', part: 6 },
]
