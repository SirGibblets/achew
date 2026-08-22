import type {
  CountOp,
  DurationOp,
  DurationPredicate,
  Predicate,
  Rule,
  RuleOrSet,
  RuleSet,
  Subject,
  TextOp,
  TextPredicate,
} from '../../types/rules';

export const SUBJECT_LABELS: Record<Subject, string> = {
  chapter_count: 'Chapter count',
  any_chapter: 'Any chapter',
  every_chapter: 'Every chapter',
  first_chapter: 'First chapter',
  last_chapter: 'Last chapter',
  every_middle_chapter: 'Every middle chapter',
  any_middle_chapter: 'Any middle chapter',
  most_every_chapter: 'Most every chapter',
};

export const MULTI_PREDICATE_SUBJECTS: Set<Subject> = new Set<Subject>([
  'chapter_count',
  'any_chapter',
  'every_chapter',
  'first_chapter',
  'last_chapter',
  'every_middle_chapter',
  'any_middle_chapter',
  'most_every_chapter',
]);

export const COUNT_OP_LABELS: Record<CountOp, string> = {
  is: 'is',
  is_not: 'is not',
  less_than: 'is less than',
  not_less_than: 'is not less than',
  greater_than: 'is greater than',
  not_greater_than: 'is not greater than',
};

export const DURATION_OP_LABELS: Record<DurationOp, string> = {
  shorter_than: 'is shorter than',
  longer_than: 'is longer than',
};

export const TEXT_OP_LABELS: Record<TextOp, [string, string]> = {
  is: ['matches', 'does not match'],
  is_not: ['matches', 'does not match'],
  contains: ['contains', 'does not contain'],
  does_not_contain: ['contains', 'does not contain'],
  starts_with: ['starts with', 'does not start with'],
  does_not_start_with: ['starts with', 'does not start with'],
  ends_with: ['ends with', 'does not end with'],
  does_not_end_with: ['ends with', 'does not end with'],
};

const NEGATED_OPS: Set<TextOp> = new Set<TextOp>([
  'is_not',
  'does_not_contain',
  'does_not_start_with',
  'does_not_end_with',
]);

export function getTextOpLabel(op: TextOp): string {
  const [pos, neg] = TEXT_OP_LABELS[op] ?? ['', ''];
  return NEGATED_OPS.has(op) ? neg : pos;
}

export function getPart2Label(pred: TextPredicate): string {
  const v = pred.value ?? '';
  switch (pred.part2) {
    case 'text':
      return `the text '${v}'`;
    case 'text_similar':
      return `text similar to '${v}'`;
    case 'number':
      return 'a number';
    case 'book_title_exact':
      return 'the book title (exact)';
    case 'book_title_similar':
      return 'the book title (similar)';
    case 'regex':
      return `the regex '${v}'`;
    default:
      return pred.part2;
  }
}

export function getDurationLabel(pred: DurationPredicate): string {
  const op = DURATION_OP_LABELS[pred.op] ?? pred.op;
  const unit = pred.value === 1 ? 'second' : 'seconds';
  return `${op} ${pred.value} ${unit}`;
}

function predicateLabel(pred: Predicate): string {
  switch (pred.kind) {
    case 'count':
      return `${COUNT_OP_LABELS[pred.op] ?? pred.op} ${pred.value}`;
    case 'duration':
      return getDurationLabel(pred);
    default:
      return `${getTextOpLabel(pred.op)} ${getPart2Label(pred)}`;
  }
}

export function autoRuleName(rule: Rule): string {
  if (rule.name) return rule.name;
  const subject = SUBJECT_LABELS[rule.subject] ?? rule.subject;
  if (!rule.predicates || rule.predicates.length === 0) return subject;
  return `${subject} ${rule.predicates.map(predicateLabel).join(' and ')}`;
}

export function autoRuleSetName(rs: RuleSet): string {
  return rs.name || 'Ruleset';
}

export function createBlankRule(subject: Subject = 'any_chapter'): Rule {
  return {
    id: crypto.randomUUID(),
    name: '',
    subject,
    predicates: [createBlankPredicate(subject)],
    enabled: true,
  };
}

export function createBlankPredicate(subject: Subject): Predicate {
  if (subject === 'chapter_count') {
    return { kind: 'count', op: 'is', value: 0 };
  }
  return createBlankTextPredicate('is');
}

export function createBlankTextPredicate(op: TextOp): TextPredicate {
  return { kind: 'text', op, part2: 'text', value: '', ignore_case: true };
}

/* Threshold a duration condition starts at, in seconds. */
const DEFAULT_DURATION_SECONDS = 60;

export function createBlankDurationPredicate(op: DurationOp): DurationPredicate {
  return { kind: 'duration', op, value: DEFAULT_DURATION_SECONDS };
}

export function createBlankRuleSet(): RuleSet {
  return {
    id: crypto.randomUUID(),
    name: '',
    match_any: true,
    enabled: true,
    items: [],
  };
}

export function cloneItem<T extends RuleOrSet>(item: T): T {
  return JSON.parse(JSON.stringify(item)) as T;
}

export function deepCloneWithNewIds<T extends RuleOrSet>(item: T): T {
  const clone = JSON.parse(JSON.stringify(item)) as T;
  return _reassignIds(clone);
}

function _reassignIds<T extends RuleOrSet>(item: T): T {
  item.id = crypto.randomUUID();
  if ('items' in item && Array.isArray(item.items)) {
    item.items = item.items.map((child) => _reassignIds(child));
  }
  return item;
}

export function hasEnabledRules(ruleset: RuleSet): boolean {
  if (!ruleset.enabled) return false;
  return (ruleset.items || []).some((item) => {
    if ('items' in item) return hasEnabledRules(item);
    return item.enabled;
  });
}
