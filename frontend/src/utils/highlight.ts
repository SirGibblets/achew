// Helpers for showing a book search result's matched text. Audiobookshelf does
// not report which field or which name a query hit, so both the highlight spans
// and the contributor windowing are derived here from the raw query.
//
// Everything returns structured segments rather than markup: the query and the
// Audiobookshelf metadata are both untrusted, so callers render through
// {#each} + <mark> and never build an HTML string.

export interface HighlightSegment {
  text: string;
  hit: boolean;
}

export interface ContributorWindow {
  /** Names were hidden before the visible slice. */
  leadingEllipsis: boolean;
  names: string[];
  /** Names were hidden after the visible slice. */
  trailingEllipsis: boolean;
  /** Hidden name count. Non-zero only when nothing in the list matched. */
  moreCount: number;
}

// How many contributor names a card shows per list before eliding.
export const CONTRIBUTOR_BUDGET = 2;

/**
 * Split `text` into alternating plain and matched segments.
 *
 * Matching is case-insensitive and literal — the query is user input, so it is
 * compared as a plain substring rather than compiled into a regex.
 */
export function splitHighlight(text: string, query: string): HighlightSegment[] {
  const needle = query.trim().toLowerCase();
  if (!text || !needle) {
    return text ? [{ text, hit: false }] : [];
  }

  const haystack = text.toLowerCase();
  const segments: HighlightSegment[] = [];
  let cursor = 0;

  for (;;) {
    const found = haystack.indexOf(needle, cursor);
    if (found === -1) break;
    if (found > cursor) {
      segments.push({ text: text.slice(cursor, found), hit: false });
    }
    segments.push({ text: text.slice(found, found + needle.length), hit: true });
    cursor = found + needle.length;
  }

  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor), hit: false });
  }
  return segments.length > 0 ? segments : [{ text, hit: false }];
}

export interface ContributorSegment extends HighlightSegment {
  /** The trailing "+N more" count, which renders de-emphasised. */
  more?: boolean;
}

export interface ContributorClause {
  segments: ContributorSegment[];
  /**
   * Whether this clause holds the search match. The card never lets a clause
   * marked `priority` be clipped, so the matched name always stays readable.
   */
  priority: boolean;
}

/**
 * Assemble a card's contributor line as clauses, e.g.
 * `By Author One` + `, narrated by …Narrator Four, Narrator Five…`.
 *
 * Built here rather than in the template because the separators are
 * whitespace-exact and a Svelte `{#each}` cannot express them without the
 * surrounding markup's indentation leaking into the rendered text.
 *
 * Split into clauses rather than one flat run because the line is too long for
 * most cards. Windowing alone cannot save the match: it keeps the matched name
 * in the list, but the CSS that truncates the rendered line has no idea which
 * name mattered and will happily cut it off. Marking the clause lets the card
 * shrink the other one instead.
 */
export function buildContributorLine(
  authors: string[],
  narrators: string[],
  query: string,
  budget: number = CONTRIBUTOR_BUDGET,
): ContributorClause[] {
  const authorWindow = windowContributors(authors, query, budget);
  const narratorWindow = windowContributors(narrators, query, budget);

  const buildClause = (lead: string, win: ContributorWindow): ContributorClause => {
    const segments: ContributorSegment[] = [{ text: lead, hit: false }];
    if (win.leadingEllipsis) segments.push({ text: '…', hit: false });
    win.names.forEach((name, i) => {
      if (i > 0) segments.push({ text: ', ', hit: false });
      segments.push(...splitHighlight(name, query));
    });
    if (win.trailingEllipsis) segments.push({ text: '…', hit: false });
    if (win.moreCount > 0) segments.push({ text: ` +${win.moreCount} more`, hit: false, more: true });
    return { segments, priority: segments.some((s) => s.hit) };
  };

  const clauses: ContributorClause[] = [];
  if (authorWindow.names.length > 0) {
    clauses.push(buildClause('By ', authorWindow));
  }
  if (narratorWindow.names.length > 0) {
    const lead = authorWindow.names.length > 0 ? ', narrated by ' : 'Narrated by ';
    clauses.push(buildClause(lead, narratorWindow));
  }

  // With nothing matched there is no name to protect, so keep the authors —
  // the more identifying half — and let the narrators give up the space.
  if (clauses.length > 0 && !clauses.some((c) => c.priority)) {
    clauses[0].priority = true;
  }

  return clauses;
}

/** Index of the first name containing the query, or -1. */
function findMatchIndex(names: string[], query: string): number {
  const needle = query.trim().toLowerCase();
  if (!needle) return -1;
  return names.findIndex((name) => name.toLowerCase().includes(needle));
}

/**
 * Reduce a contributor list to the names worth showing on a card.
 *
 * A full-cast production can credit a dozen narrators, which no card can fit.
 * When one of them is why the book turned up in the results, the window slides
 * to keep that name visible and marks the elided sides with an ellipsis. When
 * nothing matched there is no name to anchor on, so the list is simply cut at
 * the budget and the remainder is reported as a count.
 */
export function windowContributors(
  names: string[],
  query: string,
  budget: number = CONTRIBUTOR_BUDGET,
): ContributorWindow {
  const empty: ContributorWindow = {
    leadingEllipsis: false,
    names: [],
    trailingEllipsis: false,
    moreCount: 0,
  };
  if (names.length === 0 || budget < 1) return empty;

  if (names.length <= budget) {
    return { ...empty, names: [...names] };
  }

  const matchIndex = findMatchIndex(names, query);
  if (matchIndex === -1) {
    return { ...empty, names: names.slice(0, budget), moreCount: names.length - budget };
  }

  // Centre the window on the match, then push it back inside the array so a
  // match near either end still fills the whole budget. An even budget cannot
  // centre, and biases towards showing the match first.
  let start = matchIndex - Math.floor((budget - 1) / 2);
  start = Math.max(0, Math.min(start, names.length - budget));
  const end = start + budget;

  return {
    leadingEllipsis: start > 0,
    names: names.slice(start, end),
    trailingEllipsis: end < names.length,
    moreCount: 0,
  };
}
