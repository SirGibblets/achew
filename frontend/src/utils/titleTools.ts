// Pure text transforms behind the Edit Titles dialog and the Quick Tidy
// button. Everything here is deterministic string manipulation — callers
// preview the results and persist them via the apply-titles endpoint.

// ---------------------------------------------------------------------------
// Shared vocabulary
// ---------------------------------------------------------------------------

// Structural words that commonly precede a chapter number. A number token
// directly following one of these is safe to convert without user review.
const NUMBER_KEYWORD_LIST = [
  'chapter',
  'chap',
  'ch',
  'part',
  'pt',
  'book',
  'volume',
  'vol',
  'section',
  'episode',
  'ep',
  'letter',
  'act',
  'scene',
  'track',
  'disc',
  'number',
];

const NUMBER_KEYWORDS = new Set(NUMBER_KEYWORD_LIST);

// Words that stay lowercase in Title Case unless they begin or end the title:
// articles, coordinating conjunctions, and short prepositions.
const SMALL_WORDS = new Set([
  'a',
  'an',
  'and',
  'as',
  'at',
  'but',
  'by',
  'for',
  'if',
  'in',
  'nor',
  'of',
  'off',
  'on',
  'or',
  'per',
  'so',
  'the',
  'to',
  'up',
  'via',
  'yet',
]);

// ---------------------------------------------------------------------------
// Roman numerals
// ---------------------------------------------------------------------------

// Strict Roman numeral form (also matches the empty string, so callers must
// reject that separately).
const ROMAN_NUMERAL_RE = /^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$/;

// English words and acronyms that also happen to be valid Roman numerals.
// These are never treated as numbers unless they follow a structural keyword.
const ROMAN_FALSE_FRIENDS = new Set(['MIX', 'MM', 'CM', 'CD', 'MD', 'DC', 'DI', 'LI', 'MI']);

const ROMAN_DIGIT_VALUES: Record<string, number> = { I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000 };

const ROMAN_ENCODE_TABLE: [number, string][] = [
  [1000, 'M'],
  [900, 'CM'],
  [500, 'D'],
  [400, 'CD'],
  [100, 'C'],
  [90, 'XC'],
  [50, 'L'],
  [40, 'XL'],
  [10, 'X'],
  [9, 'IX'],
  [5, 'V'],
  [4, 'IV'],
  [1, 'I'],
];

export function toRoman(n: number): string | null {
  if (!Number.isInteger(n) || n < 1 || n > 3999) return null;
  let result = '';
  let rest = n;
  for (const [value, symbol] of ROMAN_ENCODE_TABLE) {
    while (rest >= value) {
      result += symbol;
      rest -= value;
    }
  }
  return result;
}

export function fromRoman(text: string): number | null {
  const upper = text.toUpperCase();
  if (!upper || !ROMAN_NUMERAL_RE.test(upper)) return null;
  let total = 0;
  for (let i = 0; i < upper.length; i++) {
    const value = ROMAN_DIGIT_VALUES[upper[i]];
    const next = ROMAN_DIGIT_VALUES[upper[i + 1]] ?? 0;
    total += value < next ? -value : value;
  }
  return total;
}

// ---------------------------------------------------------------------------
// Number words
// ---------------------------------------------------------------------------

// Indexes double as values (0–19).
const UNIT_WORDS = [
  'zero',
  'one',
  'two',
  'three',
  'four',
  'five',
  'six',
  'seven',
  'eight',
  'nine',
  'ten',
  'eleven',
  'twelve',
  'thirteen',
  'fourteen',
  'fifteen',
  'sixteen',
  'seventeen',
  'eighteen',
  'nineteen',
];

const TENS_WORDS = ['twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];

const UNIT_VALUES = new Map(UNIT_WORDS.map((word, i) => [word, i]));
const TENS_VALUES = new Map(TENS_WORDS.map((word, i) => [word, (i + 2) * 10]));

// Cardinal English words for 0–9999, lowercase, hyphenating 21–99 composites
// ("one hundred twenty-three"). Returns null outside that range.
export function numberToWords(n: number): string | null {
  if (!Number.isInteger(n) || n < 0 || n > 9999) return null;
  if (n < 20) return UNIT_WORDS[n];
  if (n < 100) {
    const tens = TENS_WORDS[Math.floor(n / 10) - 2];
    const unit = n % 10;
    return unit ? `${tens}-${UNIT_WORDS[unit]}` : tens;
  }
  if (n < 1000) {
    const hundreds = `${UNIT_WORDS[Math.floor(n / 100)]} hundred`;
    const rest = n % 100;
    return rest ? `${hundreds} ${numberToWords(rest)}` : hundreds;
  }
  const thousands = `${UNIT_WORDS[Math.floor(n / 1000)]} thousand`;
  const rest = n % 1000;
  return rest ? `${thousands} ${numberToWords(rest)}` : thousands;
}

export type NumberFormat =
  | 'digits'
  | 'digits-2'
  | 'digits-3'
  | 'roman-upper'
  | 'roman-lower'
  | 'words-title'
  | 'words-lower';

// Formats a number in the requested style, or null when the style cannot
// represent the value (Roman outside 1–3999, words outside 0–9999).
export function formatNumber(n: number, format: NumberFormat): string | null {
  switch (format) {
    case 'digits':
      return String(n);
    case 'digits-2':
    case 'digits-3': {
      if (n < 0) return String(n);
      return String(n).padStart(format === 'digits-2' ? 2 : 3, '0');
    }
    case 'roman-upper':
      return toRoman(n);
    case 'roman-lower':
      return toRoman(n)?.toLowerCase() ?? null;
    case 'words-title': {
      const words = numberToWords(n);
      return words ? words.replace(/\b[a-z]/g, (c) => c.toUpperCase()) : null;
    }
    case 'words-lower':
      return numberToWords(n);
  }
}

// ---------------------------------------------------------------------------
// Number scanning (shared by Convert Numbers and Tidy)
// ---------------------------------------------------------------------------

interface TextToken {
  text: string;
  start: number;
  end: number;
}

export interface NumberSpan {
  start: number;
  end: number;
  value: number;
}

function tokenize(title: string): TextToken[] {
  return [...title.matchAll(/[A-Za-z]+|\d+/g)].map((m) => ({
    text: m[0],
    start: m.index,
    end: m.index + m[0].length,
  }));
}

// True when the token at `index` directly follows a structural keyword,
// allowing "Chapter 5", "Ch. 5", "Chapter: 5", and "Chapter #5".
function isKeywordAnchored(title: string, tokens: TextToken[], index: number): boolean {
  const prev = tokens[index - 1];
  if (!prev || !NUMBER_KEYWORDS.has(prev.text.toLowerCase())) return false;
  const gap = title.slice(prev.end, tokens[index].start);
  return gap.length > 0 && /^[.:]?\s*#?\s*$/.test(gap);
}

// True when the span is the entire title apart from whitespace/punctuation,
// e.g. the title "XIV." or "Fourteen".
function isWholeTitle(title: string, start: number, end: number): boolean {
  const strip = (s: string) => s.replace(/[^A-Za-z0-9]+/g, '');
  return strip(title.slice(0, start)) === '' && strip(title.slice(end)) === '';
}

type NumberKind = 'digits' | 'words' | 'roman';

// A magnitude word directly after a spelled-out number means the parsed run
// was truncated by the parser's 0–9999 range and the phrase is a quantity,
// not a chapter number ("Twenty Thousand Leagues", "Five Million Reasons").
const MAGNITUDE_WORDS = new Set(['hundred', 'thousand', 'million', 'billion', 'trillion']);

// A number at the very start of the title acts as its own chapter marker —
// many transcriptions produce no keyword or punctuation at all ("one the
// beginning"). Leading digits always count. Spelled-out numbers count when
// they have a plausible chapter value (1–999, protecting "Twenty Thousand
// Leagues Under the Sea") and don't start a phrase ("One of Us Is Lying").
// Roman numerals only count when an explicit separator follows ("IV. The
// Reckoning"), since bare leading ones are usually words ("I Am Legend",
// "V for Vendetta") and transcriptions don't produce Roman numerals anyway.
function isLeadingNumber(title: string, span: NumberSpan, kind: NumberKind): boolean {
  if (title.slice(0, span.start).trim() !== '') return false;
  const after = title.slice(span.end);
  if (/^\s*[.:\-–—]\s/.test(after)) return true;
  if (!/^\s/.test(after)) return false;
  if (kind === 'digits') return true;
  if (kind === 'words') {
    if (span.value < 1 || span.value > 999 || startsContinuation(after)) return false;
    const next = after.match(/^\s+([A-Za-z]+)/);
    return !(next && MAGNITUDE_WORDS.has(next[1].toLowerCase()));
  }
  return false;
}

interface WordRunState {
  total: number;
  current: number;
  usedTens: boolean;
  usedUnit: boolean;
  usedHundred: boolean;
  usedThousand: boolean;
}

const INITIAL_RUN: WordRunState = {
  total: 0,
  current: 0,
  usedTens: false,
  usedUnit: false,
  usedHundred: false,
  usedThousand: false,
};

// Attempts to extend a spoken-number parse with one more word. Returns the
// next state, or null when the word cannot validly continue the number
// (which ends the run, so "One Two" parses as two separate numbers).
function stepWordRun(state: WordRunState, word: string): WordRunState | null {
  const unit = UNIT_VALUES.get(word);
  if (unit !== undefined) {
    if (state.usedUnit) return null;
    if (state.usedTens && unit >= 10) return null;
    if (unit === 0 && (state.total > 0 || state.current > 0 || state.usedTens)) return null;
    return { ...state, current: state.current + unit, usedUnit: true };
  }
  const tens = TENS_VALUES.get(word);
  if (tens !== undefined) {
    if (state.usedTens || state.usedUnit) return null;
    return { ...state, current: state.current + tens, usedTens: true };
  }
  if (word === 'hundred') {
    if (state.usedHundred || !state.usedUnit || state.usedTens || state.current < 1 || state.current > 9) return null;
    return { ...state, current: state.current * 100, usedTens: false, usedUnit: false, usedHundred: true };
  }
  if (word === 'thousand') {
    if (state.usedThousand || state.current < 1 || state.current > 9) return null;
    return {
      total: state.total + state.current * 1000,
      current: 0,
      usedTens: false,
      usedUnit: false,
      usedHundred: false,
      usedThousand: true,
    };
  }
  return null;
}

// Matches gaps allowed inside a spoken number: spaces or a hyphen.
const RUN_GAP_RE = /^\s+$|^\s*-\s*$/;

function matchWordRun(
  title: string,
  tokens: TextToken[],
  startIndex: number,
): { span: NumberSpan; nextIndex: number } | null {
  let state = INITIAL_RUN;
  let lastConsumed = -1;
  let j = startIndex;
  while (j < tokens.length && /[A-Za-z]/.test(tokens[j].text)) {
    if (j > startIndex) {
      const gap = title.slice(tokens[j - 1].end, tokens[j].start);
      if (!RUN_GAP_RE.test(gap)) break;
    }
    const word = tokens[j].text.toLowerCase();
    if (word === 'and') {
      // "and" joins only after hundred/thousand, and only when the next word
      // continues the number ("one hundred and five" but not "a hundred and then").
      if (!state.usedHundred && !state.usedThousand) break;
      const next = tokens[j + 1];
      if (!next || !/[A-Za-z]/.test(next.text)) break;
      if (!/^\s+$/.test(title.slice(tokens[j].end, next.start))) break;
      const stepped = stepWordRun(state, next.text.toLowerCase());
      if (!stepped) break;
      state = stepped;
      lastConsumed = j + 1;
      j += 2;
      continue;
    }
    const stepped = stepWordRun(state, word);
    if (!stepped) break;
    state = stepped;
    lastConsumed = j;
    j += 1;
  }
  if (lastConsumed < startIndex) return null;
  return {
    span: { start: tokens[startIndex].start, end: tokens[lastConsumed].end, value: state.total + state.current },
    nextIndex: lastConsumed + 1,
  };
}

// Finds number tokens in a title: digit runs, spoken numbers, and Roman
// numerals. With `keywordOnly`, only numbers following a structural keyword
// (or making up the whole title) are returned. Unanchored Roman numerals are
// only recognized when ALL-CAPS, at least two letters, and not a common
// English word ("Henry VIII" yes, "The Mix" no).
export function findNumberSpans(title: string, keywordOnly: boolean): NumberSpan[] {
  const tokens = tokenize(title);
  const spans: { span: NumberSpan; anchorIndex: number; kind: NumberKind }[] = [];
  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i];

    if (/^\d/.test(token.text)) {
      // Skip digits glued to letters ("14th", "MP3") and absurdly long runs.
      const prev = tokens[i - 1];
      const next = tokens[i + 1];
      const touchesLetters =
        (prev !== undefined && prev.end === token.start) || (next !== undefined && next.start === token.end);
      if (!touchesLetters && token.text.length <= 6) {
        spans.push({
          span: { start: token.start, end: token.end, value: parseInt(token.text, 10) },
          anchorIndex: i,
          kind: 'digits',
        });
      }
      i += 1;
      continue;
    }

    const run = matchWordRun(title, tokens, i);
    if (run) {
      spans.push({ span: run.span, anchorIndex: i, kind: 'words' });
      i = run.nextIndex;
      continue;
    }

    const value = fromRoman(token.text);
    if (value !== null) {
      const upper = token.text.toUpperCase();
      const span = { start: token.start, end: token.end, value };
      const anchored = isKeywordAnchored(title, tokens, i);
      const whole = isWholeTitle(title, token.start, token.end);
      const leading = isLeadingNumber(title, span, 'roman') && !ROMAN_FALSE_FRIENDS.has(upper);
      const allCaps = token.text === upper && token.text.length >= 2 && !ROMAN_FALSE_FRIENDS.has(upper);
      if (anchored || whole || leading || (!keywordOnly && allCaps)) {
        spans.push({ span, anchorIndex: i, kind: 'roman' });
      }
    }
    i += 1;
  }

  const accepted = keywordOnly
    ? spans.filter(
        (s) =>
          isKeywordAnchored(title, tokens, s.anchorIndex) ||
          isWholeTitle(title, s.span.start, s.span.end) ||
          isLeadingNumber(title, s.span, s.kind),
      )
    : spans;
  return accepted.map((s) => s.span);
}

export type NumberTarget = 'digits' | 'roman-upper' | 'roman-lower' | 'words-title' | 'words-lower';

export interface ConvertNumbersOptions {
  target: NumberTarget;
  keywordOnly: boolean;
}

export function convertNumbers(title: string, options: ConvertNumbersOptions): string {
  const spans = findNumberSpans(title, options.keywordOnly);
  let result = title;
  // Replace right-to-left so earlier span offsets stay valid.
  for (let i = spans.length - 1; i >= 0; i--) {
    const span = spans[i];
    const formatted = formatNumber(span.value, options.target);
    if (formatted === null) continue;
    result = result.slice(0, span.start) + formatted + result.slice(span.end);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Change case
// ---------------------------------------------------------------------------

export type CaseMode = 'title' | 'sentence' | 'upper' | 'lower';

// Word tokens for casing purposes: letters, digits, and apostrophes.
const CASE_TOKEN_RE = /[A-Za-z0-9'’]+/g;

// A Roman numeral stays uppercase when it follows a structural keyword
// ("chapter xiv" → "Chapter XIV") or was already ALL-CAPS and isn't a common
// English word ("HENRY VIII" → "Henry VIII", "THE MIX" → "The Mix").
function shouldKeepRoman(word: string, prevWord: string | undefined): boolean {
  if (fromRoman(word) === null) return false;
  if (prevWord !== undefined && NUMBER_KEYWORDS.has(prevWord.toLowerCase())) return true;
  const upper = word.toUpperCase();
  return word === upper && word.length >= 2 && !ROMAN_FALSE_FRIENDS.has(upper);
}

// Uppercases the first letter of a lowercase word, handling name prefixes
// ("o'brien" → "O'Brien" — but not contractions like "i'm") and leaving
// leading digits alone ("3rd").
function capitalizeWord(lower: string): string {
  let out = lower;
  if (/^[a-z]/.test(out)) out = out.charAt(0).toUpperCase() + out.slice(1);
  else if (/^['’][a-z]/.test(out)) out = out.slice(0, 1) + out.charAt(1).toUpperCase() + out.slice(2);
  if (/^[OoDdLl]['’][a-z]/.test(out)) out = out.slice(0, 2) + out.charAt(2).toUpperCase() + out.slice(3);
  return out;
}

// Sub-title boundaries (colon, sentence punctuation, dashes) reset
// capitalization just like the start of the title.
function isCaseBreak(gapBefore: string): boolean {
  return /[:.!?—]/.test(gapBefore) || /\s-\s/.test(gapBefore);
}

export function titleCase(title: string, keepRoman = true): string {
  const tokens = [...title.matchAll(CASE_TOKEN_RE)];
  if (tokens.length === 0) return title;
  let result = '';
  let cursor = 0;
  tokens.forEach((m, idx) => {
    const word = m[0];
    const gapBefore = title.slice(cursor, m.index);
    result += gapBefore;
    cursor = m.index + word.length;

    const prevWord = idx > 0 ? tokens[idx - 1][0] : undefined;
    if (keepRoman && shouldKeepRoman(word, prevWord)) {
      result += word.toUpperCase();
      return;
    }
    const lower = word.toLowerCase();
    const afterBreak = isCaseBreak(gapBefore);
    const isFirst = idx === 0;
    const isLast = idx === tokens.length - 1;
    if (!isFirst && !isLast && !afterBreak && SMALL_WORDS.has(lower)) {
      result += lower;
      return;
    }
    result += capitalizeWord(lower);
  });
  result += title.slice(cursor);
  return result;
}

export function sentenceCase(title: string, keepRoman = true): string {
  const tokens = [...title.matchAll(CASE_TOKEN_RE)];
  if (tokens.length === 0) return title;
  let result = '';
  let cursor = 0;
  tokens.forEach((m, idx) => {
    const word = m[0];
    const gapBefore = title.slice(cursor, m.index);
    result += gapBefore;
    cursor = m.index + word.length;

    const prevWord = idx > 0 ? tokens[idx - 1][0] : undefined;
    if (keepRoman && shouldKeepRoman(word, prevWord)) {
      result += word.toUpperCase();
      return;
    }
    const lower = word.toLowerCase();
    // The pronoun "I" and its contractions stay capitalized.
    if (lower === 'i' || /^i['’]/.test(lower)) {
      result += capitalizeWord(lower);
      return;
    }
    const sentenceStart = idx === 0 || isCaseBreak(gapBefore);
    result += sentenceStart ? capitalizeWord(lower) : lower;
  });
  result += title.slice(cursor);
  return result;
}

export function changeCase(title: string, mode: CaseMode, keepRoman = true): string {
  switch (mode) {
    case 'title':
      return titleCase(title, keepRoman);
    case 'sentence':
      return sentenceCase(title, keepRoman);
    case 'upper':
      return title.toUpperCase();
    case 'lower':
      return title.toLowerCase();
  }
}

// ---------------------------------------------------------------------------
// Find & replace
// ---------------------------------------------------------------------------

export interface FindReplaceOptions {
  find: string;
  replace: string;
  useRegex: boolean;
  matchCase: boolean;
  preserveCase: boolean;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Builds the search regex, or null when there is nothing to search for.
// Throws SyntaxError on an invalid user-supplied pattern.
export function buildFindRegex(options: FindReplaceOptions): RegExp | null {
  if (!options.find) return null;
  const source = options.useRegex ? options.find : escapeRegExp(options.find);
  return new RegExp(source, options.matchCase ? 'g' : 'gi');
}

// Re-shapes `replacement` to follow the letter-case pattern of the matched
// text: all-lowercase, ALL-CAPS, or Capitalized. Mixed-case matches leave the
// replacement as typed.
function matchCasePattern(matched: string, replacement: string): string {
  const letters = matched.replace(/[^a-zA-Z]/g, '');
  if (!letters) return replacement;
  if (letters === letters.toLowerCase()) return replacement.toLowerCase();
  if (letters.length > 1 && letters === letters.toUpperCase()) return replacement.toUpperCase();
  if (/^[A-Z]/.test(letters) && letters.slice(1) === letters.slice(1).toLowerCase()) {
    return replacement.charAt(0).toUpperCase() + replacement.slice(1).toLowerCase();
  }
  return replacement;
}

export function findReplace(title: string, options: FindReplaceOptions): string {
  let regex: RegExp | null;
  try {
    regex = buildFindRegex(options);
  } catch {
    return title;
  }
  if (!regex) return title;
  return title.replace(regex, (...args) => {
    const matched = args[0] as string;
    const namedGroups = typeof args[args.length - 1] === 'object' ? 1 : 0;
    const groups = args.slice(1, args.length - 2 - namedGroups) as (string | undefined)[];
    let replacement = options.replace;
    if (options.useRegex) {
      // Expand $$, $&, and $1–$99 ourselves, since the callback form of
      // String.replace does not.
      replacement = replacement.replace(/\$(\$|&|\d{1,2})/g, (token, ref: string) => {
        if (ref === '$') return '$';
        if (ref === '&') return matched;
        let num = parseInt(ref, 10);
        let suffix = '';
        if (num > groups.length && ref.length === 2) {
          num = parseInt(ref.charAt(0), 10);
          suffix = ref.charAt(1);
        }
        if (num >= 1 && num <= groups.length) return (groups[num - 1] ?? '') + suffix;
        return token;
      });
    }
    return options.preserveCase ? matchCasePattern(matched, replacement) : replacement;
  });
}

// ---------------------------------------------------------------------------
// Add or remove text
// ---------------------------------------------------------------------------

export interface AddRemoveOptions {
  op: 'add' | 'remove';
  where: 'start' | 'end';
  removeBy: 'text' | 'chars';
  text: string;
  count: number;
}

export function addRemoveText(title: string, options: AddRemoveOptions): string {
  const { op, where } = options;
  if (op === 'add') {
    if (!options.text) return title;
    return where === 'start' ? options.text + title : title + options.text;
  }
  if (options.removeBy === 'chars') {
    const count = Math.max(0, Math.floor(options.count));
    if (count === 0) return title;
    if (count >= title.length) return '';
    return where === 'start' ? title.slice(count) : title.slice(0, title.length - count);
  }
  if (!options.text) return title;
  if (where === 'start') return title.startsWith(options.text) ? title.slice(options.text.length) : title;
  return title.endsWith(options.text) ? title.slice(0, title.length - options.text.length) : title;
}

// ---------------------------------------------------------------------------
// Sequence
// ---------------------------------------------------------------------------

export type SequencePlacement = 'replace' | 'start' | 'end';

export interface SequenceOptions {
  template: string;
  start: number;
  format: NumberFormat;
  placement?: SequencePlacement;
}

// Fills the template for the chapter at `index` (0-based position among the
// chapters being renumbered). "{n}" becomes the sequence number, "{title}"
// the chapter's current title. Formats that cannot represent the value fall
// back to plain digits. The filled template replaces the title by default,
// or is prepended/appended to it when `placement` is 'start'/'end'.
export function applySequence(title: string, index: number, options: SequenceOptions): string {
  const n = options.start + index;
  const formatted = formatNumber(n, options.format) ?? String(n);
  const filled = options.template.replaceAll('{n}', formatted).replaceAll('{title}', title);
  switch (options.placement ?? 'replace') {
    case 'start':
      return filled + title;
    case 'end':
      return title + filled;
    case 'replace':
      return filled;
  }
}

// ---------------------------------------------------------------------------
// Tidy
// ---------------------------------------------------------------------------

export interface TidyOptions {
  whitespace: boolean;
  trailingPunctuation: boolean;
  normalizeNumbers: boolean;
  numberFormat: NumberTarget;
  chapterSeparator: boolean;
  separator: string;
  applyCase: boolean;
  caseMode: CaseMode;
}

export const DEFAULT_TIDY_OPTIONS: TidyOptions = {
  whitespace: true,
  trailingPunctuation: true,
  normalizeNumbers: true,
  numberFormat: 'digits',
  chapterSeparator: true,
  separator: ': ',
  applyCase: true,
  caseMode: 'title',
};

// Merges a persisted partial Tidy configuration (from editor settings) over
// the defaults.
export function resolveTidyOptions(saved?: Partial<TidyOptions> | null): TidyOptions {
  return { ...DEFAULT_TIDY_OPTIONS, ...(saved ?? {}) };
}

// Strips trailing separator punctuation. "?", "!", and ellipses are kept
// because they usually end a title intentionally.
function stripTrailingPunctuation(title: string): string {
  if (/(\.{3}|…)\s*$/.test(title)) return title.replace(/\s+$/, '');
  return title.replace(/[\s.,;:\-–—]+$/, '');
}

// Matches a title that is nothing but "Keyword " up to a given position,
// e.g. "Chapter " or "Ch. " — used to check that a number span directly
// follows a leading structural keyword.
const LEADING_KEYWORD_RE = new RegExp(`^\\s*(?:${NUMBER_KEYWORD_LIST.join('|')})\\.?\\s+$`, 'i');

// The text right after the chapter number: an optional ASR artifact period,
// whitespace, then title text that isn't already separated by punctuation.
const AFTER_NUMBER_RE = /^(\.)?\s+(["'‘“([A-Za-z0-9].*)$/;

// An existing explicit separator (colon or dash) right after the chapter
// number, to be normalized to the chosen separator. The whitespace after the
// separator is required so a glued dash ("Chapter 2-3") doesn't count.
const EXPLICIT_SEPARATOR_RE = /^\s*[:\-–—]\s+(["'‘“([A-Za-z0-9].*)$/;

// Words that signal the text after a chapter number continues the phrase
// ("Chapter 2 of Frankenstein by Mary Shelley") rather than starting a
// sub-title, so no separator belongs there. Articles are deliberately absent:
// "Chapter 14 The Hunt" does start a sub-title.
const SEPARATOR_STOP_WORDS = new Set(['of', 'in', 'on', 'at', 'by', 'for', 'from', 'with', 'to', 'and', 'or', 'nor']);

function startsContinuation(rest: string): boolean {
  const m = rest.match(/^["'‘“([\s]*([A-Za-z]+)/);
  return m !== null && SEPARATOR_STOP_WORDS.has(m[1].toLowerCase());
}

// Ensures the chosen separator sits between a leading chapter number and the
// title text: "Chapter 14 The Sea Voyage" → "Chapter 14: The Sea Voyage".
// The number may be digits, Roman, or spelled out ("Chapter One The
// Beginning"), and a number that starts the title counts as its own chapter
// marker ("3 Hello", "1. Intro", "Two: What" — see isLeadingNumber). An
// existing colon/dash separator is normalized to the chosen one, and a
// period right after the number ("Part 1. Operation Pajamas") is an ASR
// sentence-break artifact: it becomes the chosen separator, or is simply
// dropped when a continuation phrase follows.
function addChapterSeparator(title: string, separator: string): string {
  if (!separator) return title;

  // Locate the chapter number with the scanner so spelled-out numbers and
  // multi-word runs ("Twenty One") are recognized.
  const span = findNumberSpans(title, true)[0];
  if (!span) return title;
  const before = title.slice(0, span.start);
  const bareLead = before.trim() === '';
  if (!bareLead && !LEADING_KEYWORD_RE.test(before)) return title;

  const lead = title.slice(0, span.end);
  const after = title.slice(span.end);
  const explicit = after.match(EXPLICIT_SEPARATOR_RE);
  if (explicit) return `${lead}${separator}${explicit[1]}`;
  const m = after.match(AFTER_NUMBER_RE);
  if (m) {
    // A bare leading number followed by more digits ("14 05") is more likely
    // track numbering than a chapter title; leave it alone.
    if (bareLead && /^\d/.test(m[2])) return title;
    if (startsContinuation(m[2])) {
      return m[1] ? `${lead} ${m[2]}` : title;
    }
    // Without an artifact period to correct, don't insert a separator when
    // the title is already structured by a colon further along
    // ("Chapter 14 The Sea: Part 2").
    if (!m[1] && title.includes(':')) return title;
    return `${lead}${separator}${m[2]}`;
  }
  return title;
}

// One-pass cleanup used by the Quick Tidy button (with the user's saved
// options) and the Edit Titles dialog's Tidy mode (configurable). Order
// matters: the separator runs before number conversion (a leading digit
// number like "3 Hello" is recognized as a chapter marker, which wouldn't be
// safe after conversion to a bare Roman "III"), numbers are normalized
// before casing to sidestep Roman numeral casing pitfalls, and the separator
// precedes casing so the word after it is treated as a sub-title start.
export function tidyTitle(title: string, options: TidyOptions = DEFAULT_TIDY_OPTIONS): string {
  let result = title;
  if (options.whitespace) result = result.trim().replace(/\s+/g, ' ');
  if (options.trailingPunctuation) result = stripTrailingPunctuation(result);
  if (options.chapterSeparator) result = addChapterSeparator(result, options.separator);
  if (options.normalizeNumbers) result = convertNumbers(result, { target: options.numberFormat, keywordOnly: true });
  if (options.applyCase) result = changeCase(result, options.caseMode, true);
  return result;
}
