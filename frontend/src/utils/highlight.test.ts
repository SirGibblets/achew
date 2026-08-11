import { describe, expect, it } from 'vitest';

import { buildContributorLine, splitHighlight, windowContributors } from './highlight';

/** Flatten a contributor line back to the text a user would read. */
const render = (clauses: { segments: { text: string }[] }[]) =>
  clauses.flatMap((c) => c.segments.map((s) => s.text)).join('');

/** All segments across every clause, for assertions that ignore clause boundaries. */
const allSegments = (clauses: { segments: { text: string; hit: boolean; more?: boolean }[] }[]) =>
  clauses.flatMap((c) => c.segments);

const plain = (text: string) => [{ text, hit: false }];

describe('splitHighlight', () => {
  it('returns the whole string unmatched when the query is empty', () => {
    expect(splitHighlight('Sample Book Title', '')).toEqual(plain('Sample Book Title'));
    expect(splitHighlight('Sample Book Title', '   ')).toEqual(plain('Sample Book Title'));
  });

  it('returns nothing for empty text', () => {
    expect(splitHighlight('', 'sample')).toEqual([]);
  });

  it('returns the whole string unmatched when the query is absent', () => {
    expect(splitHighlight('Sample Book Title', 'nomatch')).toEqual(plain('Sample Book Title'));
  });

  it('marks a match in the middle of the text', () => {
    expect(splitHighlight('Sample Book Title', 'Book')).toEqual([
      { text: 'Sample ', hit: false },
      { text: 'Book', hit: true },
      { text: ' Title', hit: false },
    ]);
  });

  it('matches case-insensitively while preserving the original casing', () => {
    expect(splitHighlight('Sample Book Title', 'TITLE')).toEqual([
      { text: 'Sample Book ', hit: false },
      { text: 'Title', hit: true },
    ]);
  });

  it('marks a match at the very start', () => {
    expect(splitHighlight('Title Of Something', 'title')).toEqual([
      { text: 'Title', hit: true },
      { text: ' Of Something', hit: false },
    ]);
  });

  it('marks every occurrence', () => {
    expect(splitHighlight('One Sample and Another Sample', 'sample')).toEqual([
      { text: 'One ', hit: false },
      { text: 'Sample', hit: true },
      { text: ' and Another ', hit: false },
      { text: 'Sample', hit: true },
    ]);
  });

  it('handles adjacent occurrences without emitting empty segments', () => {
    expect(splitHighlight('abab', 'ab')).toEqual([
      { text: 'ab', hit: true },
      { text: 'ab', hit: true },
    ]);
  });

  it('treats regex metacharacters in the query literally', () => {
    expect(splitHighlight('Sample Title (Unabridged)', '(unabridged)')).toEqual([
      { text: 'Sample Title ', hit: false },
      { text: '(Unabridged)', hit: true },
    ]);
    expect(splitHighlight('Sample Title', '.*')).toEqual(plain('Sample Title'));
  });

  it('ignores surrounding whitespace in the query', () => {
    expect(splitHighlight('Sample Subtitle', '  sample  ')).toEqual([
      { text: 'Sample', hit: true },
      { text: ' Subtitle', hit: false },
    ]);
  });
});

describe('windowContributors', () => {
  const cast = ['Ann', 'Bob', 'Cat', 'Dan', 'Eve', 'Fay'];

  it('returns an empty window for an empty list', () => {
    expect(windowContributors([], 'ann', 2)).toEqual({
      leadingEllipsis: false,
      names: [],
      trailingEllipsis: false,
      moreCount: 0,
    });
  });

  it('shows every name when the list fits the budget', () => {
    expect(windowContributors(['Ann', 'Bob'], '', 2)).toEqual({
      leadingEllipsis: false,
      names: ['Ann', 'Bob'],
      trailingEllipsis: false,
      moreCount: 0,
    });
  });

  it('shows every name when the list is shorter than the budget', () => {
    expect(windowContributors(['Ann'], 'ann', 2).names).toEqual(['Ann']);
  });

  it('counts the remainder when nothing matches', () => {
    expect(windowContributors(cast, '', 2)).toEqual({
      leadingEllipsis: false,
      names: ['Ann', 'Bob'],
      trailingEllipsis: false,
      moreCount: 4,
    });
  });

  it('counts the remainder when the query matches no name', () => {
    expect(windowContributors(cast, 'zeke', 2).moreCount).toBe(4);
  });

  it('windows around a match in the middle, eliding both sides', () => {
    // An even budget cannot centre the match, so it leads the window.
    expect(windowContributors(cast, 'dan', 2)).toEqual({
      leadingEllipsis: true,
      names: ['Dan', 'Eve'],
      trailingEllipsis: true,
      moreCount: 0,
    });
  });

  it('centres the match when the budget is odd', () => {
    expect(windowContributors(cast, 'dan', 3).names).toEqual(['Cat', 'Dan', 'Eve']);
  });

  it('does not elide before a match at the first index', () => {
    expect(windowContributors(cast, 'ann', 2)).toEqual({
      leadingEllipsis: false,
      names: ['Ann', 'Bob'],
      trailingEllipsis: true,
      moreCount: 0,
    });
  });

  it('does not elide after a match at the last index', () => {
    expect(windowContributors(cast, 'fay', 2)).toEqual({
      leadingEllipsis: true,
      names: ['Eve', 'Fay'],
      trailingEllipsis: false,
      moreCount: 0,
    });
  });

  it('fills the whole budget for a match near the end', () => {
    expect(windowContributors(cast, 'fay', 3).names).toEqual(['Dan', 'Eve', 'Fay']);
  });

  it('matches a partial name case-insensitively', () => {
    const narrators = ['Narrator One', 'Narrator Two', 'Narrator Three', 'Narrator Four', 'full cast'];
    expect(windowContributors(narrators, 'four', 1)).toEqual({
      leadingEllipsis: true,
      names: ['Narrator Four'],
      trailingEllipsis: true,
      moreCount: 0,
    });
  });

  it('returns an empty window for a non-positive budget', () => {
    expect(windowContributors(cast, 'ann', 0).names).toEqual([]);
  });
});

describe('buildContributorLine', () => {
  const fullCast = ['Narrator One', 'Narrator Two', 'Narrator Three', 'Narrator Four', 'Narrator Five'];

  it('joins authors and narrators into one prose line', () => {
    expect(render(buildContributorLine(['Author One'], ['Narrator One'], ''))).toBe(
      'By Author One, narrated by Narrator One',
    );
  });

  it('separates multiple names with a comma and a space', () => {
    expect(render(buildContributorLine(['Author One', 'Author Two'], [], ''))).toBe('By Author One, Author Two');
  });

  it('capitalises the narrator clause when there is no author', () => {
    expect(render(buildContributorLine([], ['Narrator One'], ''))).toBe('Narrated by Narrator One');
  });

  it('omits the narrator clause entirely when there are none', () => {
    expect(render(buildContributorLine(['Author One'], [], ''))).toBe('By Author One');
  });

  it('returns nothing when there are no contributors at all', () => {
    expect(buildContributorLine([], [], 'anything')).toEqual([]);
  });

  it('brackets a matched narrator with bare ellipses', () => {
    expect(render(buildContributorLine(['Author One'], fullCast, 'Narrator Four', 2))).toBe(
      'By Author One, narrated by …Narrator Four, Narrator Five',
    );
  });

  it('counts the overflow when no narrator matches', () => {
    expect(render(buildContributorLine(['Author One'], fullCast, 'nomatch', 2))).toBe(
      'By Author One, narrated by Narrator One, Narrator Two +3 more',
    );
  });

  it('marks the overflow segment so it can be styled apart', () => {
    const segments = allSegments(buildContributorLine([], fullCast, '', 2));
    expect(segments.filter((s) => s.more)).toEqual([{ text: ' +3 more', hit: false, more: true }]);
  });

  it('highlights only the matched portion of a name', () => {
    const clauses = buildContributorLine(['Author Ravenna'], ['Narrator One'], 'ravenna');
    expect(
      allSegments(clauses)
        .filter((s) => s.hit)
        .map((s) => s.text),
    ).toEqual(['Ravenna']);
    expect(render(clauses)).toBe('By Author Ravenna, narrated by Narrator One');
  });

  it('highlights matches in both clauses at once', () => {
    const clauses = buildContributorLine(['Contributor Nora'], ['Contributor Nora'], 'nora');
    expect(
      allSegments(clauses)
        .filter((s) => s.hit)
        .map((s) => s.text),
    ).toEqual(['Nora', 'Nora']);
  });

  it('protects the narrator clause when the narrator matched', () => {
    // A full-cast anthology: the long author list would otherwise push the matched
    // narrator past the end of the line and out of view.
    const clauses = buildContributorLine(
      ['Author One', 'Author Two', 'Author Three'],
      ['Narrator One', 'Narrator Two', 'Narrator Three', "Narrator O'Quinn"],
      "o'quinn",
    );
    expect(clauses.map((c) => c.priority)).toEqual([false, true]);
    expect(render([clauses[1]])).toBe(", narrated by …Narrator Three, Narrator O'Quinn");
  });

  it('protects the author clause when the author matched', () => {
    const clauses = buildContributorLine(
      ['Author Quinlan'],
      ['Narrator One', 'Narrator Two', 'Narrator Three'],
      'quinlan',
    );
    expect(clauses.map((c) => c.priority)).toEqual([true, false]);
  });

  it('falls back to protecting the authors when nothing matched', () => {
    const clauses = buildContributorLine(['Author One'], fullCast, 'nothing-here');
    expect(clauses.map((c) => c.priority)).toEqual([true, false]);
  });

  it('protects the only clause when there is just one', () => {
    expect(buildContributorLine([], ['Narrator One'], '').map((c) => c.priority)).toEqual([true]);
  });

  it('keeps the comma with the narrator clause so a clipped author clause still reads', () => {
    const clauses = buildContributorLine(['A'], ['B'], '');
    expect(clauses[1].segments[0].text).toBe(', narrated by ');
  });

  it('never emits a space before a comma', () => {
    const line = render(buildContributorLine(['A', 'B'], ['C', 'D'], ''));
    expect(line).not.toMatch(/\s,/);
    expect(line).toBe('By A, B, narrated by C, D');
  });
});
