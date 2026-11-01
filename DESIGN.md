# PriceWatch EG design

**Subject:** a personal price tracker for Egyptian online stores.
**Reader:** the owner and a friend, on a laptop or phone, often for ten seconds at a time.
**Job of every screen:** answer "is this a good price, and where?"

**Concept: the shelf-edge label.** A shop tells you a price with a bright tag on the
shelf edge. Here, the yellow tag means one thing only: the current best price. Everything
around it stays quiet, so the eye lands on tags first when scanning the list.

Light mode only. There is no dark theme, by the owner's preference.

## Palette

| Token | Hex | Use |
|---|---|---|
| `--sheet` | `#FFFFFF` | Page background |
| `--mist` | `#EEF4F1` | Side rail, decision band, open panels |
| `--ink` | `#12322B` | Text, headings, active states (Nile green) |
| `--ink-2` | `#4F6A63` | Secondary text; 5.9:1 on white, 5.3:1 on mist |
| `--line` | `#D3DED9` | Row dividers |
| `--line-strong` | `#7E978F` | Input and button outlines; 3:1 on white |
| `--tag` | `#FFD23F` | The price tag and the active nav marker, nothing else |
| `--action` | `#0B6B55` | Primary buttons |

Status colours are for state only, and always come with a word or a sign:
good `#0B7A4B` on `#E1F3EA`, watch `#7D5200` on `#FFF1CC`,
wait `#A83A1C` on `#FBE9E3`, critical `#B3261E`.

Chart series keep the validated categorical order in `app.css`. Text never wears a series colour.

## Type

- **Barlow Condensed** 600/700: prices, verdicts, page headings. It has the narrow, loud
  numerals of retail signage, and long prices fit in tight columns.
- **IBM Plex Sans** with **IBM Plex Sans Arabic**, 400/500/600: everything else. Vendor
  titles are often Arabic, so both scripts must look like one family.
- `ui-monospace` only for things you paste as code: selectors, topics, test output.

Sentence case for labels, no all-caps.
Prices use tabular numerals.

## Spacing

Tailwind's spacing utilities, as used by the original screens.

## Shape

Corners follow the job, never one radius everywhere: buttons 4px, inputs 3px, badges 2px,
dialog 6px, cards 4px. The tag has its own notched shape and a punched hole.
No shadows and no gradients.

## Layout

Keep the original simple screens: rate tiles and alerts on top, then the items table.
Forms open in modals from a button that is always visible (track item, edit item, pin URL, edit vendor),
so pages stay short. Keep scrolling low: vendors with no price and no pin collapse behind one button.
A theme change touches colours and fonts only. The owner found a restructured layout too complex.

## Tone

Plain verbs and specific nouns. Buttons say what happens. Empty states say what to do next.
No marketing words. Existing labels and icons stay as they are unless the owner asks.

## Motion

None that isn't a reply to an action. The only state changes are immediate.

## References

- [ikea.com](https://www.ikea.com/): price as the loudest element, with a yellow tag.
- [camelcamelcamel.com](https://camelcamelcamel.com/): the job of a price-history page.
- [gov.uk](https://www.gov.uk/): plain words, strong focus states, no decoration.
