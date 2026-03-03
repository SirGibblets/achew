/**
 * Utility functions for rule display (mirrors backend rules/models.py auto-name logic).
 */

export const SUBJECT_LABELS = {
    chapter_count: 'Chapter count',
    any_chapter: 'Any chapter',
    every_chapter: 'Every chapter',
    first_chapter: 'First chapter',
    last_chapter: 'Last chapter',
    every_middle_chapter: 'Every middle chapter',
    any_middle_chapter: 'Any middle chapter',
    most_every_chapter: 'Most every chapter',
};

export const MULTI_PREDICATE_SUBJECTS = new Set([
    'chapter_count',
    'any_chapter',
    'every_chapter',
    'first_chapter',
    'last_chapter',
    'every_middle_chapter',
    'any_middle_chapter',
    'most_every_chapter',
]);

export const COUNT_OP_LABELS = {
    is: 'is',
    is_not: 'is not',
    less_than: 'is less than',
    not_less_than: 'is not less than',
    greater_than: 'is greater than',
    not_greater_than: 'is not greater than',
};

export const TEXT_OP_LABELS = {
    is: ['matches', 'does not match'],
    is_not: ['matches', 'does not match'],
    contains: ['contains', 'does not contain'],
    does_not_contain: ['contains', 'does not contain'],
    starts_with: ['starts with', 'does not start with'],
    does_not_start_with: ['starts with', 'does not start with'],
    ends_with: ['ends with', 'does not end with'],
    does_not_end_with: ['ends with', 'does not end with'],
};

const NEGATED_OPS = new Set(['is_not', 'does_not_contain', 'does_not_start_with', 'does_not_end_with']);

export function getTextOpLabel(op) {
    const [pos, neg] = TEXT_OP_LABELS[op] || ['', ''];
    return NEGATED_OPS.has(op) ? neg : pos;
}

export function getPart2Label(pred) {
    const v = pred.value;
    switch (pred.part2) {
        case 'text': return `the text '${v}'`;
        case 'text_similar': return `text similar to '${v}'`;
        case 'number': return 'a number';
        case 'book_title_exact': return 'the book title (exact)';
        case 'book_title_similar': return 'the book title (similar)';
        case 'regex': return `the regex '${v}'`;
        default: return pred.part2;
    }
}

export function autoRuleName(rule) {
    if (rule.name) return rule.name;
    const subject = SUBJECT_LABELS[rule.subject] || rule.subject;
    if (!rule.predicates || rule.predicates.length === 0) return subject;

    const first = rule.predicates[0];
    if (first.kind === 'count') {
        const parts = rule.predicates
            .filter(p => p.kind === 'count')
            .map(p => `${COUNT_OP_LABELS[p.op] || p.op} ${p.value}`);
        return `${subject} ${parts.join(' and ')}`;
    }

    const parts = rule.predicates
        .filter(p => p.kind === 'text')
        .map(p => `${getTextOpLabel(p.op)} ${getPart2Label(p)}`);

    if (parts.length === 1) return `${subject} ${parts[0]}`;
    return `${subject} ${parts.join(' and ')}`;
}

export function autoRuleSetName(rs) {
    return rs.name || 'Rule Set';
}

/** Create a new blank rule with one empty text predicate */
export function createBlankRule(subject = 'any_chapter') {
    return {
        id: crypto.randomUUID(),
        name: '',
        subject,
        predicates: [createBlankPredicate(subject)],
        enabled: true,
    };
}

export function createBlankPredicate(subject) {
    if (subject === 'chapter_count') {
        return {kind: 'count', op: 'is', value: 0};
    }
    return {kind: 'text', op: 'is', part2: 'text', value: '', ignore_case: true};
}

/** Create a new rule set */
export function createBlankRuleSet() {
    return {
        id: crypto.randomUUID(),
        name: '',
        match_any: true,
        enabled: true,
        items: [],
    };
}

/** Deep-clone a rule or ruleset */
export function cloneItem(item) {
    return JSON.parse(JSON.stringify(item));
}

/** Deep-clone a rule or ruleset, assigning new UUIDs to all items */
export function deepCloneWithNewIds(item) {
    const clone = JSON.parse(JSON.stringify(item));
    return _reassignIds(clone);
}

function _reassignIds(item) {
    item.id = crypto.randomUUID();
    if (Array.isArray(item.items)) {
        item.items = item.items.map(_reassignIds);
    }
    return item;
}

/** Check whether any rule (recursively) in a ruleset is enabled */
export function hasEnabledRules(ruleset) {
    if (!ruleset.enabled) return false;
    return (ruleset.items || []).some(item => {
        if (item.items !== undefined) return hasEnabledRules(item); // it's a ruleset
        return item.enabled;
    });
}
