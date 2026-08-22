"""Rule evaluation logic for Chapter Search."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, Sequence

from rapidfuzz.distance import JaroWinkler

from .models import (
    CountOp,
    CountPredicate,
    DurationOp,
    DurationPredicate,
    Part2,
    Predicate,
    Rule,
    RuleSet,
    Subject,
    TextOp,
    TextPredicate,
)

JARO_WINKLER_THRESHOLD = 0.9


@dataclass(frozen=True)
class _Chapter:
    """A cached chapter reduced to the fields rules can inspect."""

    title: str
    duration: Optional[float]


def _to_chapters(records: list[dict]) -> list[_Chapter]:
    return [_Chapter(title=r.get("title") or "", duration=_chapter_duration(r)) for r in records]


def _chapter_duration(record: dict) -> Optional[float]:
    """Chapter length in seconds, or None when the cache holds no usable end time."""
    start = record.get("start_time")
    end = record.get("end_time")
    if start is None or end is None:
        return None
    duration = end - start
    return duration if duration > 0 else None


def evaluate_ruleset(
    ruleset: RuleSet,
    book_name: str,
    chapters: list[dict],
) -> tuple[bool, list[str]]:
    """
    Evaluate a RuleSet against a book's chapters.

    Args:
        chapters: cached chapter records, each with "title", "start_time" and "end_time"

    Returns:
        (matched, list_of_matched_rule_ids)
    """
    matched_ids: list[str] = []
    match, ids = _eval_ruleset(ruleset, book_name, _to_chapters(chapters))
    matched_ids.extend(ids)
    return match, matched_ids


def _eval_ruleset(
    ruleset: RuleSet,
    book_name: str,
    chapters: list[_Chapter],
) -> tuple[bool, list[str]]:
    if not ruleset.enabled:
        return False, []

    matched_ids: list[str] = []
    results: list[bool] = []

    for item in ruleset.items:
        if isinstance(item, RuleSet):
            item_matched, item_ids = _eval_ruleset(item, book_name, chapters)
        else:
            item_matched, item_ids = _eval_rule(item, book_name, chapters)

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
    chapters: list[_Chapter],
) -> tuple[bool, list[str]]:
    if not rule.enabled or not rule.predicates:
        return False, []

    matched = _eval_rule_logic(rule, book_name, chapters)
    return matched, [rule.id] if matched else []


def _eval_rule_logic(rule: Rule, book_name: str, chapters: list[_Chapter]) -> bool:
    subject = rule.subject
    predicates = rule.predicates

    if subject == Subject.CHAPTER_COUNT:
        count = len(chapters)
        return all(_eval_count(p, count) for p in predicates if isinstance(p, CountPredicate))

    subject_chapters = _resolve_subjects(subject, chapters)
    if not subject_chapters and subject != Subject.CHAPTER_COUNT:
        # e.g. no middle chapters in a 2-chapter book
        return False

    chapter_preds = [p for p in predicates if not isinstance(p, CountPredicate)]

    if subject == Subject.EVERY_CHAPTER:
        return all(_chapter_matches_all_preds(c, chapter_preds, book_name) for c in subject_chapters)

    if subject == Subject.FIRST_CHAPTER:
        return _chapter_matches_all_preds(subject_chapters[0], chapter_preds, book_name)

    if subject == Subject.LAST_CHAPTER:
        return _chapter_matches_all_preds(subject_chapters[-1], chapter_preds, book_name)

    if subject == Subject.EVERY_MIDDLE_CHAPTER:
        return all(_chapter_matches_all_preds(c, chapter_preds, book_name) for c in subject_chapters)

    if subject == Subject.ANY_CHAPTER:
        return any(_chapter_matches_all_preds(c, chapter_preds, book_name) for c in subject_chapters)

    if subject == Subject.ANY_MIDDLE_CHAPTER:
        return any(_chapter_matches_all_preds(c, chapter_preds, book_name) for c in subject_chapters)

    if subject == Subject.MOST_EVERY_CHAPTER:
        required = math.ceil(0.66 * len(subject_chapters))
        count = sum(1 for c in subject_chapters if _chapter_matches_all_preds(c, chapter_preds, book_name))
        return count >= required

    return False


def _resolve_subjects(subject: Subject, chapters: list[_Chapter]) -> list[_Chapter]:
    """Return the list of chapters that are the 'subject' for this rule."""
    if not chapters:
        return []
    if subject in {Subject.ANY_CHAPTER, Subject.EVERY_CHAPTER, Subject.MOST_EVERY_CHAPTER}:
        return chapters
    if subject == Subject.FIRST_CHAPTER:
        return [chapters[0]]
    if subject == Subject.LAST_CHAPTER:
        return [chapters[-1]]
    if subject in {Subject.EVERY_MIDDLE_CHAPTER, Subject.ANY_MIDDLE_CHAPTER}:
        return chapters[1:-1]  # excludes first and last
    return []


def _chapter_matches_all_preds(
    chapter: _Chapter,
    predicates: Sequence[Predicate],
    book_name: str,
) -> bool:
    return all(_eval_chapter_pred(pred, chapter, book_name) for pred in predicates)


def _eval_chapter_pred(pred: Predicate, chapter: _Chapter, book_name: str) -> bool:
    if isinstance(pred, DurationPredicate):
        return _eval_duration(pred, chapter.duration)
    if isinstance(pred, TextPredicate):
        return _eval_text_pred(pred, chapter.title, book_name)
    return False


def _eval_duration(pred: DurationPredicate, duration: Optional[float]) -> bool:
    """Compare a chapter's length against the threshold. Unknown durations never match."""
    if duration is None:
        return False
    if pred.op == DurationOp.SHORTER_THAN:
        return duration < pred.value
    return duration > pred.value


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
