export type Subject =
  | 'chapter_count'
  | 'any_chapter'
  | 'every_chapter'
  | 'first_chapter'
  | 'last_chapter'
  | 'every_middle_chapter'
  | 'any_middle_chapter'
  | 'most_every_chapter';

export type CountOp = 'is' | 'is_not' | 'less_than' | 'not_less_than' | 'greater_than' | 'not_greater_than';

export type TextOp =
  | 'is'
  | 'is_not'
  | 'contains'
  | 'does_not_contain'
  | 'starts_with'
  | 'does_not_start_with'
  | 'ends_with'
  | 'does_not_end_with';

export type Part2 = 'text' | 'text_similar' | 'number' | 'book_title_exact' | 'book_title_similar' | 'regex';

export interface CountPredicate {
  kind: 'count';
  op: CountOp;
  value: number;
}

export interface TextPredicate {
  kind: 'text';
  op: TextOp;
  part2: Part2;
  value?: string | null;
  ignore_case: boolean;
}

export type Predicate = CountPredicate | TextPredicate;

export interface Rule {
  id: string;
  name: string;
  subject: Subject;
  predicates: Predicate[];
  enabled: boolean;
}

export interface RuleSet {
  id: string;
  name: string;
  match_any: boolean;
  enabled: boolean;
  items: Array<Rule | RuleSet>;
}

export type RuleOrSet = Rule | RuleSet;
