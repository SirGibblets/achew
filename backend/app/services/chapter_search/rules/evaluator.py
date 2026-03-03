"""Rule evaluation logic for Chapter Search."""

from __future__ import annotations

import math
import re
from typing import Union

from rapidfuzz.distance import JaroWinkler

from .models import (
    CountOp,
    CountPredicate,
    Part2,
    Rule,
    RuleSet,
    Subject,
    TextOp,
    TextPredicate,
)

JARO_WINKLER_THRESHOLD = 0.9


def evaluate_ruleset(
    ruleset: RuleSet,
    book_name: str,
    chapter_titles: list[str],
) -> tuple[bool, list[str]]:
    """
    Evaluate a RuleSet against a book's chapters.

    Returns:
        (matched, list_of_matched_rule_ids)
    """
    matched_ids: list[str] = []
    match, ids = _eval_ruleset(ruleset, book_name, chapter_titles)
    matched_ids.extend(ids)
    return match, matched_ids


def _eval_ruleset(
    ruleset: RuleSet,
    book_name: str,
    chapter_titles: list[str],
) -> tuple[bool, list[str]]:
    if not ruleset.enabled:
        return False, []

    matched_ids: list[str] = []
    results: list[bool] = []

    for item in ruleset.items:
        if isinstance(item, RuleSet):
            item_matched, item_ids = _eval_ruleset(item, book_name, chapter_titles)
        else:
            item_matched, item_ids = _eval_rule(item, book_name, chapter_titles)

        results.append(item_matched)
        matched_ids.extend(item_ids)

    if not results:
        return False, []

    if ruleset.match_any:
        overall = any(results)
    else:
        overall = all(results)

    return overall, matched_ids if overall else []


def _eval_rule(
    rule: Rule,
    book_name: str,
    chapter_titles: list[str],
) -> tuple[bool, list[str]]:
    if not rule.enabled or not rule.predicates:
        return False, []

    matched = _eval_rule_logic(rule, book_name, chapter_titles)
    return matched, [rule.id] if matched else []


def _eval_rule_logic(rule: Rule, book_name: str, chapter_titles: list[str]) -> bool:
    subject = rule.subject
    predicates = rule.predicates

    if subject == Subject.CHAPTER_COUNT:
        count = len(chapter_titles)
        return all(_eval_count(p, count) for p in predicates if isinstance(p, CountPredicate))

    subjects_titles = _resolve_subjects(subject, chapter_titles)
    if not subjects_titles and subject != Subject.CHAPTER_COUNT:
        # e.g. no middle chapters in a 2-chapter book
        return False

    text_preds = [p for p in predicates if isinstance(p, TextPredicate)]

    if subject == Subject.EVERY_CHAPTER:
        return all(_chapter_matches_all_preds(t, text_preds, book_name) for t in subjects_titles)

    if subject == Subject.FIRST_CHAPTER:
        return _chapter_matches_all_preds(subjects_titles[0], text_preds, book_name)

    if subject == Subject.LAST_CHAPTER:
        return _chapter_matches_all_preds(subjects_titles[-1], text_preds, book_name)

    if subject == Subject.EVERY_MIDDLE_CHAPTER:
        return all(_chapter_matches_all_preds(t, text_preds, book_name) for t in subjects_titles)

    if subject == Subject.ANY_CHAPTER:
        return any(_chapter_matches_all_preds(t, text_preds, book_name) for t in subjects_titles)

    if subject == Subject.ANY_MIDDLE_CHAPTER:
        return any(_chapter_matches_all_preds(t, text_preds, book_name) for t in subjects_titles)

    if subject == Subject.MOST_EVERY_CHAPTER:
        required = math.ceil(0.66 * len(subjects_titles))
        count = sum(1 for t in subjects_titles if _chapter_matches_all_preds(t, text_preds, book_name))
        return count >= required

    return False


def _resolve_subjects(subject: Subject, titles: list[str]) -> list[str]:
    """Return the list of chapter titles that are the 'subject' for this rule."""
    if not titles:
        return []
    if subject in {Subject.ANY_CHAPTER, Subject.EVERY_CHAPTER, Subject.MOST_EVERY_CHAPTER}:
        return titles
    if subject == Subject.FIRST_CHAPTER:
        return [titles[0]]
    if subject == Subject.LAST_CHAPTER:
        return [titles[-1]]
    if subject in {Subject.EVERY_MIDDLE_CHAPTER, Subject.ANY_MIDDLE_CHAPTER}:
        return titles[1:-1]  # excludes first and last
    return []


def _chapter_matches_all_preds(
    title: str,
    predicates: list[TextPredicate],
    book_name: str,
) -> bool:
    return all(_eval_text_pred(pred, title, book_name) for pred in predicates)


def _eval_count(pred: CountPredicate, count: int) -> bool:
    v = pred.value
    result = {
        CountOp.IS: count == v,
        CountOp.IS_NOT: count != v,
        CountOp.LESS_THAN: count < v,
        CountOp.NOT_LESS_THAN: count >= v,
        CountOp.GREATER_THAN: count > v,
        CountOp.NOT_GREATER_THAN: count <= v,
    }[pred.op]
    return result


def _eval_text_pred(pred: TextPredicate, title: str, book_name: str) -> bool:
    op = pred.op
    part2 = pred.part2

    # Determine what we're comparing against
    if part2 == Part2.NUMBER:
        target_is_number = _is_number(title)
        # "is a number" → positive when it IS a number
        # "is not a number" → positive when it's NOT a number
        positive = op in {TextOp.IS, TextOp.IS_NOT}
        if op == TextOp.IS:
            return target_is_number
        if op == TextOp.IS_NOT:
            return not target_is_number
        # contains/starts_with/ends_with with "a number" are unusual — treat as partial numeric check
        if op == TextOp.CONTAINS:
            return _contains_number(title)
        if op == TextOp.DOES_NOT_CONTAIN:
            return not _contains_number(title)
        # starts_with/ends_with a number
        if op == TextOp.STARTS_WITH:
            return bool(title) and title[0].isdigit()
        if op == TextOp.DOES_NOT_START_WITH:
            return not (bool(title) and title[0].isdigit())
        if op == TextOp.ENDS_WITH:
            return bool(title) and title[-1].isdigit()
        if op == TextOp.DOES_NOT_END_WITH:
            return not (bool(title) and title[-1].isdigit())
        return False

    if part2 in {Part2.BOOK_TITLE_EXACT, Part2.BOOK_TITLE_SIMILAR}:
        compare_value = book_name
    else:
        compare_value = pred.value or ""

    # Fuzzy matching (always case-insensitive)
    if part2 in {Part2.TEXT_SIMILAR, Part2.BOOK_TITLE_SIMILAR}:
        fuzzy_match = _fuzzy_match(title.lower(), compare_value.lower(), op)
        if op in {TextOp.IS, TextOp.CONTAINS, TextOp.STARTS_WITH, TextOp.ENDS_WITH}:
            return fuzzy_match
        return not fuzzy_match

    # Exact / regex
    compare_title = title.lower() if pred.ignore_case else title
    compare_val = compare_value.lower() if pred.ignore_case else compare_value

    if part2 == Part2.REGEX:
        flags = re.IGNORECASE if pred.ignore_case else 0
        try:
            match = bool(re.search(compare_value, title, flags))
        except re.error:
            match = False
        if op in {TextOp.IS, TextOp.CONTAINS, TextOp.STARTS_WITH, TextOp.ENDS_WITH}:
            return match
        return not match

    # Plain text (TEXT or BOOK_TITLE_EXACT)
    if op == TextOp.IS:
        return compare_title == compare_val
    if op == TextOp.IS_NOT:
        return compare_title != compare_val
    if op == TextOp.CONTAINS:
        return compare_val in compare_title
    if op == TextOp.DOES_NOT_CONTAIN:
        return compare_val not in compare_title
    if op == TextOp.STARTS_WITH:
        return compare_title.startswith(compare_val)
    if op == TextOp.DOES_NOT_START_WITH:
        return not compare_title.startswith(compare_val)
    if op == TextOp.ENDS_WITH:
        return compare_title.endswith(compare_val)
    if op == TextOp.DOES_NOT_END_WITH:
        return not compare_title.endswith(compare_val)

    return False


def _fuzzy_similar(a: str, b: str) -> bool:
    """Return True if Jaro-Winkler similarity meets the threshold."""
    return JaroWinkler.normalized_similarity(a, b) >= JARO_WINKLER_THRESHOLD


def _fuzzy_match(title: str, compare_value: str, op: TextOp) -> bool:
    """Fuzzy match with operator-aware substring logic. Inputs must be lowercased."""
    n = len(compare_value)

    if op in {TextOp.IS, TextOp.IS_NOT} or len(title) <= n:
        return _fuzzy_similar(title, compare_value)

    if op in {TextOp.STARTS_WITH, TextOp.DOES_NOT_START_WITH}:
        return _fuzzy_similar(title[:n], compare_value)

    if op in {TextOp.ENDS_WITH, TextOp.DOES_NOT_END_WITH}:
        return _fuzzy_similar(title[-n:], compare_value)

    # CONTAINS / DOES_NOT_CONTAIN — sliding window
    for i in range(len(title) - n + 1):
        if _fuzzy_similar(title[i : i + n], compare_value):
            return True
    return False


def _is_number(text: str) -> bool:
    """Return True if the text, stripped, is a valid number (int or float)."""
    stripped = text.strip()
    if not stripped:
        return False
    try:
        float(stripped)
        return True
    except ValueError:
        return False


def _contains_number(text: str) -> bool:
    return bool(re.search(r"\d", text))
