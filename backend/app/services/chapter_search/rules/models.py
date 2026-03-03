"""Rule and RuleSet Pydantic models for Chapter Search."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class Subject(str, Enum):
    CHAPTER_COUNT = "chapter_count"
    ANY_CHAPTER = "any_chapter"
    EVERY_CHAPTER = "every_chapter"
    FIRST_CHAPTER = "first_chapter"
    LAST_CHAPTER = "last_chapter"
    EVERY_MIDDLE_CHAPTER = "every_middle_chapter"
    ANY_MIDDLE_CHAPTER = "any_middle_chapter"
    MOST_EVERY_CHAPTER = "most_every_chapter"


# Subjects that support multiple predicates (AND logic)
MULTI_PREDICATE_SUBJECTS = {
    Subject.CHAPTER_COUNT,
    Subject.ANY_CHAPTER,
    Subject.EVERY_CHAPTER,
    Subject.FIRST_CHAPTER,
    Subject.LAST_CHAPTER,
    Subject.EVERY_MIDDLE_CHAPTER,
    Subject.ANY_MIDDLE_CHAPTER,
    Subject.MOST_EVERY_CHAPTER,
}

# Subjects that use chapter-count logic (numeric predicate only)
COUNT_SUBJECTS = {Subject.CHAPTER_COUNT}


class CountOp(str, Enum):
    IS = "is"
    IS_NOT = "is_not"
    LESS_THAN = "less_than"
    NOT_LESS_THAN = "not_less_than"
    GREATER_THAN = "greater_than"
    NOT_GREATER_THAN = "not_greater_than"


class TextOp(str, Enum):
    IS = "is"
    IS_NOT = "is_not"
    CONTAINS = "contains"
    DOES_NOT_CONTAIN = "does_not_contain"
    STARTS_WITH = "starts_with"
    DOES_NOT_START_WITH = "does_not_start_with"
    ENDS_WITH = "ends_with"
    DOES_NOT_END_WITH = "does_not_end_with"


class Part2(str, Enum):
    TEXT = "text"                         # [T] — exact/case-insensitive text
    TEXT_SIMILAR = "text_similar"         # [T] — fuzzy Jaro-Winkler
    NUMBER = "number"                     # is a number (numeric)
    BOOK_TITLE_EXACT = "book_title_exact"
    BOOK_TITLE_SIMILAR = "book_title_similar"  # fuzzy
    REGEX = "regex"                       # [R]


# Part2 values that use a text variable
TEXT_PART2 = {Part2.TEXT, Part2.TEXT_SIMILAR}
# Part2 values that use a regex variable
REGEX_PART2 = {Part2.REGEX}
# Part2 values that are always case-insensitive (fuzzy)
ALWAYS_CASE_INSENSITIVE = {Part2.TEXT_SIMILAR, Part2.BOOK_TITLE_SIMILAR}
# Part2 values that have an ignore_case option
HAS_IGNORE_CASE = {Part2.TEXT, Part2.REGEX}


class CountPredicate(BaseModel):
    """Predicate for chapter_count subject."""
    kind: Literal["count"] = "count"
    op: CountOp
    value: int


class TextPredicate(BaseModel):
    """Predicate for per-chapter subjects."""
    kind: Literal["text"] = "text"
    op: TextOp
    part2: Part2
    value: Optional[str] = None     # T or R; None for number/book_title predicates
    ignore_case: bool = True        # only meaningful for TEXT and REGEX part2


Predicate = Annotated[Union[CountPredicate, TextPredicate], Field(discriminator="kind")]


class Rule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = ""              # custom display name; empty = auto-generate
    subject: Subject
    predicates: list[Predicate]  # at least 1
    enabled: bool = True

    def display_name(self) -> str:
        """Return custom name if set, otherwise auto-generate from subject + predicates."""
        if self.name:
            return self.name
        return _auto_name(self)


class RuleSet(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = ""              # custom display name; empty = "Rule Set"
    match_any: bool = True      # True = ANY, False = ALL
    enabled: bool = True
    items: list[Union[Rule, RuleSet]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def display_name(self) -> str:
        return self.name or "Rule Set"


# ---------------------------------------------------------------------------
# Auto-name generation
# ---------------------------------------------------------------------------

def _subject_label(subject: Subject) -> str:
    return {
        Subject.CHAPTER_COUNT: "Chapter count",
        Subject.ANY_CHAPTER: "Any chapter",
        Subject.EVERY_CHAPTER: "Every chapter",
        Subject.FIRST_CHAPTER: "First chapter",
        Subject.LAST_CHAPTER: "Last chapter",
        Subject.EVERY_MIDDLE_CHAPTER: "Every middle chapter",
        Subject.ANY_MIDDLE_CHAPTER: "Any middle chapter",
        Subject.MOST_EVERY_CHAPTER: "Most every chapter",
    }[subject]


def _count_pred_label(pred: CountPredicate) -> str:
    op_labels = {
        CountOp.IS: f"is {pred.value}",
        CountOp.IS_NOT: f"is not {pred.value}",
        CountOp.LESS_THAN: f"is less than {pred.value}",
        CountOp.NOT_LESS_THAN: f"is not less than {pred.value}",
        CountOp.GREATER_THAN: f"is greater than {pred.value}",
        CountOp.NOT_GREATER_THAN: f"is not greater than {pred.value}",
    }
    return op_labels[pred.op]


def _text_pred_label(pred: TextPredicate) -> str:
    op_map = {
        TextOp.IS: ("matches", "does not match"),
        TextOp.IS_NOT: ("matches", "does not match"),
        TextOp.CONTAINS: ("contains", "does not contain"),
        TextOp.DOES_NOT_CONTAIN: ("contains", "does not contain"),
        TextOp.STARTS_WITH: ("starts with", "does not start with"),
        TextOp.DOES_NOT_START_WITH: ("starts with", "does not start with"),
        TextOp.ENDS_WITH: ("ends with", "does not end with"),
        TextOp.DOES_NOT_END_WITH: ("ends with", "does not end with"),
    }
    negated = pred.op in {
        TextOp.IS_NOT, TextOp.DOES_NOT_CONTAIN,
        TextOp.DOES_NOT_START_WITH, TextOp.DOES_NOT_END_WITH
    }
    _, neg_label = op_map[pred.op]
    pos_label, _ = op_map[pred.op]
    verb = neg_label if negated else pos_label

    part2_map = {
        Part2.TEXT: f"the text '{pred.value}'",
        Part2.TEXT_SIMILAR: f"text similar to '{pred.value}'",
        Part2.NUMBER: "a number",
        Part2.BOOK_TITLE_EXACT: "the book title (exact)",
        Part2.BOOK_TITLE_SIMILAR: "the book title (similar)",
        Part2.REGEX: f"the regex '{pred.value}'",
    }
    return f"{verb} {part2_map.get(pred.part2, '')}"


def _auto_name(rule: Rule) -> str:
    subject = _subject_label(rule.subject)
    if not rule.predicates:
        return subject

    first = rule.predicates[0]
    if isinstance(first, CountPredicate):
        parts = [_count_pred_label(p) for p in rule.predicates if isinstance(p, CountPredicate)]
        return f"{subject} {' and '.join(parts)}"

    parts = [_text_pred_label(p) for p in rule.predicates if isinstance(p, TextPredicate)]
    if len(parts) == 1:
        return f"{subject} {parts[0]}"
    return f"{subject} {' and '.join(parts)}"


# ---------------------------------------------------------------------------
# Default rule set
# ---------------------------------------------------------------------------

def create_default_ruleset() -> RuleSet:
    return RuleSet(
        name="Chapter Search Rules",
        match_any=True,
        items=[
            Rule(
                name="Book has a low chapter count",
                subject=Subject.CHAPTER_COUNT,
                predicates=[CountPredicate(op=CountOp.LESS_THAN, value=4)],
                enabled=True,
            ),
            Rule(
                name="Most chapters contain only numbers",
                subject=Subject.MOST_EVERY_CHAPTER,
                predicates=[TextPredicate(op=TextOp.IS, part2=Part2.NUMBER)],
                enabled=True,
            ),
            Rule(
                name="Most chapters contain the book title",
                subject=Subject.MOST_EVERY_CHAPTER,
                predicates=[TextPredicate(op=TextOp.CONTAINS, part2=Part2.BOOK_TITLE_SIMILAR)],
                enabled=True,
            ),
            RuleSet(
                name="First chapter is not an intro",
                match_any=True,
                enabled=False,
                items=[
                    Rule(
                        name="First chapter doesn't include 'intro' or 'credit'",
                        subject=Subject.FIRST_CHAPTER,
                        predicates=[
                            TextPredicate(op=TextOp.DOES_NOT_CONTAIN, part2=Part2.TEXT, value="intro", ignore_case=True),
                            TextPredicate(op=TextOp.DOES_NOT_CONTAIN, part2=Part2.TEXT, value="credit", ignore_case=True)
                            ],
                        enabled=True,
                    ),
                    Rule(
                        name="First chapter includes 'chapter'",
                        subject=Subject.FIRST_CHAPTER,
                        predicates=[TextPredicate(op=TextOp.CONTAINS, part2=Part2.TEXT, value="chapter", ignore_case=True)],
                        enabled=True,
                    ),
                ],
            ),
        ],
    )
