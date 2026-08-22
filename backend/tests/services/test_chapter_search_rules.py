"""Tests for Chapter Search rule evaluation (app/services/chapter_search/rules/).

Focused on the duration conditions, which read chapter start/end times out of the
SQLite cache rather than chapter titles. Chapters are built as plain cache records,
so no Audiobookshelf server or database is involved.
"""

from app.services.chapter_search.rules.evaluator import evaluate_ruleset
from app.services.chapter_search.rules.models import (
    CountOp,
    CountPredicate,
    DurationOp,
    DurationPredicate,
    Part2,
    Rule,
    RuleSet,
    Subject,
    TextOp,
    TextPredicate,
)


def chapters(*spans: tuple[str, float | None]) -> list[dict]:
    """Build cache records from (title, duration) pairs. A None duration leaves end_time unset."""
    records = []
    start = 0.0
    for title, duration in spans:
        records.append(
            {
                "title": title,
                "start_time": start,
                "end_time": None if duration is None else start + duration,
            }
        )
        start += duration or 0.0
    return records


def matches(rule: Rule, book_name: str, records: list[dict]) -> bool:
    matched, _ = evaluate_ruleset(RuleSet(name="root", match_any=True, items=[rule]), book_name, records)
    return matched


def duration_rule(subject: Subject, op: DurationOp, value: float) -> Rule:
    return Rule(subject=subject, predicates=[DurationPredicate(op=op, value=value)])


class TestDurationConditions:
    def test_first_chapter_longer_than(self):
        rule = duration_rule(Subject.FIRST_CHAPTER, DurationOp.LONGER_THAN, 60)
        assert matches(rule, "Book", chapters(("Intro", 90), ("One", 500)))
        assert not matches(rule, "Book", chapters(("Intro", 30), ("One", 500)))

    def test_last_chapter_shorter_than(self):
        rule = duration_rule(Subject.LAST_CHAPTER, DurationOp.SHORTER_THAN, 60)
        assert matches(rule, "Book", chapters(("One", 500), ("Credits", 20)))
        assert not matches(rule, "Book", chapters(("One", 500), ("Credits", 120)))

    def test_thresholds_are_exclusive(self):
        assert not matches(
            duration_rule(Subject.FIRST_CHAPTER, DurationOp.LONGER_THAN, 60), "Book", chapters(("A", 60))
        )
        assert not matches(
            duration_rule(Subject.FIRST_CHAPTER, DurationOp.SHORTER_THAN, 60), "Book", chapters(("A", 60))
        )

    def test_any_chapter_matches_a_single_short_chapter(self):
        rule = duration_rule(Subject.ANY_CHAPTER, DurationOp.SHORTER_THAN, 30)
        assert matches(rule, "Book", chapters(("One", 500), ("Two", 5), ("Three", 500)))
        assert not matches(rule, "Book", chapters(("One", 500), ("Two", 500)))

    def test_every_chapter_requires_all(self):
        rule = duration_rule(Subject.EVERY_CHAPTER, DurationOp.LONGER_THAN, 10)
        assert matches(rule, "Book", chapters(("One", 50), ("Two", 60)))
        assert not matches(rule, "Book", chapters(("One", 50), ("Two", 5)))

    def test_middle_chapters_exclude_first_and_last(self):
        rule = duration_rule(Subject.EVERY_MIDDLE_CHAPTER, DurationOp.LONGER_THAN, 60)
        # Short first and last chapters are ignored by the middle-chapter targets
        assert matches(rule, "Book", chapters(("Intro", 5), ("One", 500), ("Credits", 5)))


class TestUnknownDurations:
    """Chapters the cache has no usable end time for can never satisfy a duration condition."""

    def test_missing_end_time_never_matches(self):
        assert not matches(
            duration_rule(Subject.FIRST_CHAPTER, DurationOp.SHORTER_THAN, 60), "Book", chapters(("A", None))
        )
        assert not matches(
            duration_rule(Subject.FIRST_CHAPTER, DurationOp.LONGER_THAN, 60), "Book", chapters(("A", None))
        )

    def test_zero_length_chapter_is_treated_as_unknown(self):
        assert not matches(
            duration_rule(Subject.FIRST_CHAPTER, DurationOp.SHORTER_THAN, 60), "Book", chapters(("A", 0))
        )

    def test_unknown_duration_fails_every_chapter(self):
        rule = duration_rule(Subject.EVERY_CHAPTER, DurationOp.LONGER_THAN, 10)
        assert not matches(rule, "Book", chapters(("One", 50), ("Two", None)))


class TestMixedConditions:
    def test_text_and_duration_are_anded_per_chapter(self):
        rule = Rule(
            subject=Subject.ANY_CHAPTER,
            predicates=[
                TextPredicate(op=TextOp.CONTAINS, part2=Part2.TEXT, value="credits"),
                DurationPredicate(op=DurationOp.SHORTER_THAN, value=45),
            ],
        )
        assert matches(rule, "Book", chapters(("Opening Credits", 20), ("One", 500)))
        # Right title, too long
        assert not matches(rule, "Book", chapters(("Opening Credits", 90), ("One", 500)))
        # Short enough, wrong title
        assert not matches(rule, "Book", chapters(("Prologue", 20), ("One", 500)))

    def test_both_conditions_must_hold_on_the_same_chapter(self):
        rule = Rule(
            subject=Subject.ANY_CHAPTER,
            predicates=[
                TextPredicate(op=TextOp.CONTAINS, part2=Part2.TEXT, value="credits"),
                DurationPredicate(op=DurationOp.SHORTER_THAN, value=45),
            ],
        )
        assert not matches(rule, "Book", chapters(("Opening Credits", 90), ("Short Filler", 10)))


class TestAutoNames:
    def test_duration_rule_name(self):
        rule = duration_rule(Subject.FIRST_CHAPTER, DurationOp.LONGER_THAN, 60)
        assert rule.display_name() == "First chapter is longer than 60 seconds"

    def test_singular_second(self):
        rule = duration_rule(Subject.ANY_CHAPTER, DurationOp.SHORTER_THAN, 1)
        assert rule.display_name() == "Any chapter is shorter than 1 second"

    def test_fractional_threshold_keeps_its_decimal(self):
        rule = duration_rule(Subject.LAST_CHAPTER, DurationOp.SHORTER_THAN, 90.5)
        assert rule.display_name() == "Last chapter is shorter than 90.5 seconds"

    def test_mixed_predicates_are_joined_with_and(self):
        rule = Rule(
            subject=Subject.ANY_CHAPTER,
            predicates=[
                TextPredicate(op=TextOp.CONTAINS, part2=Part2.TEXT, value="credits"),
                DurationPredicate(op=DurationOp.SHORTER_THAN, value=45),
            ],
        )
        assert rule.display_name() == "Any chapter contains the text 'credits' and is shorter than 45 seconds"

    def test_count_rule_name_is_unchanged(self):
        rule = Rule(subject=Subject.CHAPTER_COUNT, predicates=[CountPredicate(op=CountOp.LESS_THAN, value=4)])
        assert rule.display_name() == "Chapter count is less than 4"

    def test_custom_name_wins(self):
        rule = duration_rule(Subject.FIRST_CHAPTER, DurationOp.LONGER_THAN, 60)
        rule.name = "Long intro"
        assert rule.display_name() == "Long intro"


class TestPersistenceRoundTrip:
    def test_duration_predicate_survives_json(self):
        ruleset = RuleSet(
            name="root",
            match_any=True,
            items=[duration_rule(Subject.FIRST_CHAPTER, DurationOp.LONGER_THAN, 60)],
        )
        restored = RuleSet.model_validate(ruleset.model_dump(mode="json"))
        rule = restored.items[0]
        assert isinstance(rule, Rule)
        assert rule.display_name() == "First chapter is longer than 60 seconds"
        assert matches(rule, "Book", chapters(("Intro", 90)))
