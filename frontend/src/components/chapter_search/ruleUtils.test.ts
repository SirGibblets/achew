import { describe, expect, it } from 'vitest';

import { autoRuleName, createBlankDurationPredicate, createBlankTextPredicate } from './ruleUtils';
import type { Predicate, Rule, Subject } from '../../types/rules';

/**
 * Auto-generated rule names are produced independently by the backend
 * (`rules/models.py::_auto_name`). The expectations here mirror
 * `backend/tests/services/test_chapter_search_rules.py::TestAutoNames` so the two
 * implementations cannot drift apart.
 */

function rule(subject: Subject, predicates: Predicate[], name = ''): Rule {
  return { id: 'r1', name, subject, predicates, enabled: true };
}

describe('autoRuleName', () => {
  it('names a duration condition', () => {
    const r = rule('first_chapter', [{ kind: 'duration', op: 'longer_than', value: 60 }]);
    expect(autoRuleName(r)).toBe('First chapter is longer than 60 seconds');
  });

  it('uses the singular unit for a one-second threshold', () => {
    const r = rule('any_chapter', [{ kind: 'duration', op: 'shorter_than', value: 1 }]);
    expect(autoRuleName(r)).toBe('Any chapter is shorter than 1 second');
  });

  it('keeps a fractional threshold', () => {
    const r = rule('last_chapter', [{ kind: 'duration', op: 'shorter_than', value: 90.5 }]);
    expect(autoRuleName(r)).toBe('Last chapter is shorter than 90.5 seconds');
  });

  it('joins mixed text and duration conditions with "and"', () => {
    const r = rule('any_chapter', [
      { kind: 'text', op: 'contains', part2: 'text', value: 'credits', ignore_case: true },
      { kind: 'duration', op: 'shorter_than', value: 45 },
    ]);
    expect(autoRuleName(r)).toBe("Any chapter contains the text 'credits' and is shorter than 45 seconds");
  });

  it('leaves count rules unchanged', () => {
    const r = rule('chapter_count', [{ kind: 'count', op: 'less_than', value: 4 }]);
    expect(autoRuleName(r)).toBe('Chapter count is less than 4');
  });

  it('prefers a custom name', () => {
    const r = rule('first_chapter', [{ kind: 'duration', op: 'longer_than', value: 60 }], 'Long intro');
    expect(autoRuleName(r)).toBe('Long intro');
  });
});

describe('blank predicates', () => {
  it('starts a duration condition at 60 seconds', () => {
    expect(createBlankDurationPredicate('longer_than')).toEqual({
      kind: 'duration',
      op: 'longer_than',
      value: 60,
    });
  });

  it('starts a text condition with an empty, case-insensitive value', () => {
    expect(createBlankTextPredicate('contains')).toEqual({
      kind: 'text',
      op: 'contains',
      part2: 'text',
      value: '',
      ignore_case: true,
    });
  });
});
