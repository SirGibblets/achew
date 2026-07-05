import { describe, expect, it } from 'vitest';

import {
  addRemoveText,
  applySequence,
  buildFindRegex,
  changeCase,
  convertNumbers,
  findNumberSpans,
  findReplace,
  formatNumber,
  fromRoman,
  numberToWords,
  sentenceCase,
  tidyTitle,
  titleCase,
  toRoman,
  DEFAULT_TIDY_OPTIONS,
  type FindReplaceOptions,
  type TidyOptions,
} from './titleTools';

describe('roman numerals', () => {
  it('round-trips 1–3999', () => {
    for (const n of [1, 4, 9, 14, 40, 49, 90, 444, 999, 1987, 2024, 3999]) {
      const roman = toRoman(n);
      expect(roman).not.toBeNull();
      expect(fromRoman(roman!)).toBe(n);
    }
  });

  it('rejects out-of-range and invalid input', () => {
    expect(toRoman(0)).toBeNull();
    expect(toRoman(4000)).toBeNull();
    expect(fromRoman('')).toBeNull();
    expect(fromRoman('IIII')).toBeNull();
    expect(fromRoman('VX')).toBeNull();
    expect(fromRoman('ABC')).toBeNull();
  });

  it('accepts lowercase input', () => {
    expect(fromRoman('xiv')).toBe(14);
  });
});

describe('numberToWords', () => {
  it('covers units, tens, hundreds, thousands', () => {
    expect(numberToWords(0)).toBe('zero');
    expect(numberToWords(13)).toBe('thirteen');
    expect(numberToWords(21)).toBe('twenty-one');
    expect(numberToWords(100)).toBe('one hundred');
    expect(numberToWords(123)).toBe('one hundred twenty-three');
    expect(numberToWords(1005)).toBe('one thousand five');
    expect(numberToWords(9999)).toBe('nine thousand nine hundred ninety-nine');
  });

  it('rejects out-of-range values', () => {
    expect(numberToWords(-1)).toBeNull();
    expect(numberToWords(10000)).toBeNull();
  });
});

describe('formatNumber', () => {
  it('formats each style', () => {
    expect(formatNumber(7, 'digits')).toBe('7');
    expect(formatNumber(7, 'digits-2')).toBe('07');
    expect(formatNumber(7, 'digits-3')).toBe('007');
    expect(formatNumber(14, 'roman-upper')).toBe('XIV');
    expect(formatNumber(14, 'roman-lower')).toBe('xiv');
    expect(formatNumber(21, 'words-title')).toBe('Twenty-One');
    expect(formatNumber(21, 'words-lower')).toBe('twenty-one');
  });

  it('returns null when the style cannot represent the value', () => {
    expect(formatNumber(0, 'roman-upper')).toBeNull();
    expect(formatNumber(10001, 'words-lower')).toBeNull();
  });
});

describe('findNumberSpans', () => {
  const values = (title: string, keywordOnly: boolean) =>
    findNumberSpans(title, keywordOnly).map((s) => ({ value: s.value, text: title.slice(s.start, s.end) }));

  it('finds digits, spoken numbers, and anchored Roman numerals', () => {
    expect(values('Chapter 14', false)).toEqual([{ value: 14, text: '14' }]);
    expect(values('Chapter Twenty-One', false)).toEqual([{ value: 21, text: 'Twenty-One' }]);
    expect(values('Chapter One Hundred and Five', false)).toEqual([{ value: 105, text: 'One Hundred and Five' }]);
    expect(values('Chapter XIV', false)).toEqual([{ value: 14, text: 'XIV' }]);
    expect(values('chapter xiv', false)).toEqual([{ value: 14, text: 'xiv' }]);
  });

  it('keywordOnly keeps anchored and whole-title numbers, drops mid-title ones', () => {
    expect(values('Chapter 3 of 7', true)).toEqual([{ value: 3, text: '3' }]);
    expect(values('Fourteen', true)).toEqual([{ value: 14, text: 'Fourteen' }]);
    expect(values('Catch Twenty-Two', true)).toEqual([]);
  });

  it('convert-all mode finds unanchored numbers', () => {
    expect(values('Catch Twenty-Two', false)).toEqual([{ value: 22, text: 'Twenty-Two' }]);
    expect(values('The 39 Steps', false)).toEqual([{ value: 39, text: '39' }]);
  });

  it('splits invalid spoken sequences into separate numbers', () => {
    expect(values('One Two Three', false).map((v) => v.value)).toEqual([1, 2, 3]);
  });

  it('does not treat trailing "and" or non-number words as part of a run', () => {
    expect(values('One Hundred and Then Some', false)).toEqual([{ value: 100, text: 'One Hundred' }]);
    expect(values('Hundred Acre Wood', false)).toEqual([]);
  });

  it('treats leading numbers as chapter markers', () => {
    expect(values('1. The First Letter', true)).toEqual([{ value: 1, text: '1' }]);
    expect(values('Two: What', true)).toEqual([{ value: 2, text: 'Two' }]);
    expect(values('3 Hello', true)).toEqual([{ value: 3, text: '3' }]);
    expect(values('One the Beginning', true)).toEqual([{ value: 1, text: 'One' }]);
    expect(values('One Flew Over the Cuckoo’s Nest', true)).toEqual([{ value: 1, text: 'One' }]);
    expect(values('IV. The Reckoning', true)).toEqual([{ value: 4, text: 'IV' }]);
  });

  it('protects leading numbers that are likely title words', () => {
    expect(values('One of Us Is Lying', true)).toEqual([]);
    expect(values('Twenty Thousand Leagues Under the Sea', true)).toEqual([]);
    expect(values('I Am Legend', true)).toEqual([]);
    expect(values('V for Vendetta', true)).toEqual([]);
  });

  it('guards Roman false friends and glued digits', () => {
    expect(values('THE MIX TAPE', false)).toEqual([]);
    expect(values('Chapter MIX', false)).toEqual([{ value: 1009, text: 'MIX' }]);
    expect(values('I Am Legend', false)).toEqual([]);
    expect(values('The 14th Day', false)).toEqual([]);
    expect(values('MP3 Player', false)).toEqual([]);
  });
});

describe('convertNumbers', () => {
  it('converts to each target', () => {
    expect(convertNumbers('Chapter Fourteen', { target: 'digits', keywordOnly: true })).toBe('Chapter 14');
    expect(convertNumbers('Chapter 14', { target: 'roman-upper', keywordOnly: true })).toBe('Chapter XIV');
    expect(convertNumbers('Chapter XIV', { target: 'words-title', keywordOnly: true })).toBe('Chapter Fourteen');
    expect(convertNumbers('Chapter 21', { target: 'words-lower', keywordOnly: true })).toBe('Chapter twenty-one');
  });

  it('leaves numbers alone when the target cannot represent them', () => {
    expect(convertNumbers('Chapter 0', { target: 'roman-upper', keywordOnly: true })).toBe('Chapter 0');
  });

  it('converts multiple spans right-to-left', () => {
    expect(convertNumbers('Part Two Chapter Seven', { target: 'digits', keywordOnly: true })).toBe('Part 2 Chapter 7');
  });
});

describe('titleCase', () => {
  it('capitalizes words and lowercases small words', () => {
    expect(titleCase('the lord of the rings')).toBe('The Lord of the Rings');
    expect(titleCase('A TALE OF TWO CITIES')).toBe('A Tale of Two Cities');
  });

  it('always capitalizes the first and last word', () => {
    expect(titleCase('of mice and men of')).toBe('Of Mice and Men Of');
  });

  it('handles apostrophes and possessive names', () => {
    expect(titleCase("DON'T LOOK BACK")).toBe("Don't Look Back");
    expect(titleCase("o'brien's return")).toBe("O'Brien's Return");
  });

  it('capitalizes after sub-title breaks', () => {
    expect(titleCase('chapter 5: the sea')).toBe('Chapter 5: The Sea');
    expect(titleCase('home - the beginning')).toBe('Home - The Beginning');
  });

  it('keeps Roman numerals uppercase', () => {
    expect(titleCase('CHAPTER XIV: THE STORM')).toBe('Chapter XIV: The Storm');
    expect(titleCase('chapter xiv')).toBe('Chapter XIV');
    expect(titleCase('HENRY VIII AND THE COURT')).toBe('Henry VIII and the Court');
    expect(titleCase('THE MIX TAPE')).toBe('The Mix Tape');
    expect(titleCase('chapter xiv', false)).toBe('Chapter Xiv');
  });

  it('leaves ordinal suffixes alone', () => {
    expect(titleCase('the 3rd man')).toBe('The 3rd Man');
  });
});

describe('sentenceCase', () => {
  it('capitalizes only sentence starts and the pronoun I', () => {
    expect(sentenceCase('THE THING I SAW. IT WAS BAD')).toBe('The thing I saw. It was bad');
    expect(sentenceCase("WHY I'M HERE")).toBe("Why I'm here");
  });

  it('restarts casing after sub-title breaks', () => {
    expect(sentenceCase('CHAPTER 1: THE BEGINNING')).toBe('Chapter 1: The beginning');
    expect(sentenceCase('HOME - THE BEGINNING')).toBe('Home - The beginning');
  });

  it('keeps anchored Roman numerals uppercase', () => {
    expect(sentenceCase('CHAPTER XIV THE STORM')).toBe('Chapter XIV the storm');
  });
});

describe('changeCase', () => {
  it('dispatches all four modes', () => {
    expect(changeCase('hello world', 'upper')).toBe('HELLO WORLD');
    expect(changeCase('HELLO WORLD', 'lower')).toBe('hello world');
    expect(changeCase('hello world', 'title')).toBe('Hello World');
    expect(changeCase('HELLO WORLD', 'sentence')).toBe('Hello world');
  });
});

describe('findReplace', () => {
  const base: FindReplaceOptions = { find: '', replace: '', useRegex: false, matchCase: false, preserveCase: false };

  it('replaces plain text case-insensitively by default', () => {
    expect(findReplace('Chapter One, chapter two', { ...base, find: 'chapter', replace: 'Part' })).toBe(
      'Part One, Part two',
    );
  });

  it('respects match case', () => {
    expect(findReplace('Chapter one chapter', { ...base, find: 'chapter', replace: 'Part', matchCase: true })).toBe(
      'Chapter one Part',
    );
  });

  it('treats replacement dollar signs literally in plain mode', () => {
    expect(findReplace('cost', { ...base, find: 'cost', replace: '$1.00' })).toBe('$1.00');
  });

  it('preserves case of the matched text', () => {
    const opts = { ...base, find: 'chapter', replace: 'part', preserveCase: true };
    expect(findReplace('CHAPTER Chapter chapter', opts)).toBe('PART Part part');
  });

  it('supports regex with capture groups', () => {
    const opts = { ...base, find: '(\\d+)-(\\d+)', replace: '$2-$1', useRegex: true };
    expect(findReplace('Track 3-14', opts)).toBe('Track 14-3');
  });

  it('supports $& and $$ in regex mode', () => {
    const opts = { ...base, find: '\\d+', replace: '[$&]$$', useRegex: true };
    expect(findReplace('page 7', opts)).toBe('page [7]$');
  });

  it('returns the title unchanged on empty or invalid patterns', () => {
    expect(findReplace('unchanged', { ...base, find: '' })).toBe('unchanged');
    expect(findReplace('unchanged', { ...base, find: '(', useRegex: true })).toBe('unchanged');
  });

  it('buildFindRegex throws on invalid patterns and returns null on empty', () => {
    expect(() => buildFindRegex({ ...base, find: '(', useRegex: true })).toThrow();
    expect(buildFindRegex({ ...base, find: '' })).toBeNull();
  });
});

describe('addRemoveText', () => {
  it('adds text at either end', () => {
    expect(addRemoveText('One', { op: 'add', where: 'start', removeBy: 'text', text: 'Chapter ', count: 0 })).toBe(
      'Chapter One',
    );
    expect(addRemoveText('One', { op: 'add', where: 'end', removeBy: 'text', text: '!', count: 0 })).toBe('One!');
  });

  it('removes matching text only when present', () => {
    const opts = { op: 'remove', where: 'start', removeBy: 'text', text: 'Chapter ', count: 0 } as const;
    expect(addRemoveText('Chapter One', opts)).toBe('One');
    expect(addRemoveText('Prologue', opts)).toBe('Prologue');
  });

  it('removes N characters and clamps to the title length', () => {
    expect(addRemoveText('Chapter', { op: 'remove', where: 'end', removeBy: 'chars', text: '', count: 3 })).toBe(
      'Chap',
    );
    expect(addRemoveText('abc', { op: 'remove', where: 'start', removeBy: 'chars', text: '', count: 10 })).toBe('');
  });
});

describe('applySequence', () => {
  it('fills {n} and {title} using the checked-position index', () => {
    const opts = { template: 'Chapter {n}: {title}', start: 5, format: 'digits' } as const;
    expect(applySequence('Intro', 0, opts)).toBe('Chapter 5: Intro');
    expect(applySequence('Outro', 2, opts)).toBe('Chapter 7: Outro');
  });

  it('formats numbers and falls back to digits when out of range', () => {
    expect(applySequence('', 0, { template: '{n}', start: 4, format: 'roman-upper' })).toBe('IV');
    expect(applySequence('', 0, { template: '{n}', start: 1, format: 'digits-2' })).toBe('01');
    expect(applySequence('', 0, { template: '{n}', start: 0, format: 'roman-upper' })).toBe('0');
  });

  it('supports start/end placement', () => {
    const opts = { template: '{n}. ', start: 1, format: 'digits', placement: 'start' } as const;
    expect(applySequence('Intro', 0, opts)).toBe('1. Intro');
    expect(applySequence('Intro', 0, { template: ' ({n})', start: 1, format: 'digits', placement: 'end' })).toBe(
      'Intro (1)',
    );
  });
});

describe('tidyTitle', () => {
  it('applies the full default pipeline', () => {
    expect(tidyTitle('  CHAPTER   FOURTEEN THE SEA VOYAGE.  ')).toBe('Chapter 14: The Sea Voyage');
  });

  it('fixes whitespace and trailing punctuation', () => {
    expect(tidyTitle('Chapter 1.')).toBe('Chapter 1');
    expect(tidyTitle('Chapter  1 -')).toBe('Chapter 1');
  });

  it('keeps intentional terminal punctuation', () => {
    expect(tidyTitle('Where Am I?')).toBe('Where Am I?');
    expect(tidyTitle('And Then...')).toBe('And Then...');
    expect(tidyTitle('And Then…')).toBe('And Then…');
  });

  it('normalizes anchored numbers but not mid-title words', () => {
    expect(tidyTitle('CHAPTER TWENTY-ONE')).toBe('Chapter 21');
    expect(tidyTitle('CATCH TWENTY-TWO')).toBe('Catch Twenty-Two');
  });

  it('tidies keyword-less transcribed announcements', () => {
    expect(tidyTitle('one the beginning')).toBe('1: The Beginning');
    expect(tidyTitle('two meeting a new friend')).toBe('2: Meeting a New Friend');
    expect(tidyTitle('fifteen days left')).toBe('15: Days Left');
    expect(tidyTitle('One of Us Is Lying')).toBe('One of Us Is Lying');
    expect(tidyTitle('TWENTY THOUSAND LEAGUES UNDER THE SEA')).toBe('Twenty Thousand Leagues Under the Sea');
  });

  it('adds the separator after chapter numbers when text follows unseparated', () => {
    expect(tidyTitle('Chapter 14 The Hunt')).toBe('Chapter 14: The Hunt');
    expect(tidyTitle('14 The Hunt')).toBe('14: The Hunt');
    expect(tidyTitle('Chapter 14')).toBe('Chapter 14');
    expect(tidyTitle('Chapter 14: The Hunt')).toBe('Chapter 14: The Hunt');
  });

  it('normalizes an existing separator to the chosen one', () => {
    expect(tidyTitle('Chapter 14 - The Hunt')).toBe('Chapter 14: The Hunt');
    expect(tidyTitle('Chapter 14: The Hunt', { ...DEFAULT_TIDY_OPTIONS, separator: ' - ' })).toBe(
      'Chapter 14 - The Hunt',
    );
    expect(
      tidyTitle('chapter 2: the next step', { ...DEFAULT_TIDY_OPTIONS, numberFormat: 'words-title', separator: ' - ' }),
    ).toBe('Chapter Two - The Next Step');
    expect(tidyTitle('3: Undaunted by Defeat', { ...DEFAULT_TIDY_OPTIONS, separator: ' - ' })).toBe(
      '3 - Undaunted by Defeat',
    );
    expect(tidyTitle('Chapter 2-3 The Battle', { ...DEFAULT_TIDY_OPTIONS, applyCase: false })).toBe(
      'Chapter 2-3 The Battle',
    );
  });

  it('does not insert a colon before continuation phrases', () => {
    expect(tidyTitle('Chapter 2 of Frankenstein by Mary Shelley')).toBe('Chapter 2 of Frankenstein by Mary Shelley');
    expect(tidyTitle('Chapter Two of Frankenstein by Mary Shelley')).toBe('Chapter 2 of Frankenstein by Mary Shelley');
    expect(tidyTitle('14 of Hearts')).toBe('14 of Hearts');
  });

  it('inserts the separator after spelled-out chapter numbers', () => {
    expect(tidyTitle('chapter one the beginning')).toBe('Chapter 1: The Beginning');
    expect(tidyTitle('chapter one the beginning', { ...DEFAULT_TIDY_OPTIONS, normalizeNumbers: false })).toBe(
      'Chapter One: The Beginning',
    );
    expect(
      tidyTitle('CHAPTER TWENTY ONE THE GREAT ESCAPE', { ...DEFAULT_TIDY_OPTIONS, numberFormat: 'words-title' }),
    ).toBe('Chapter Twenty-One: The Great Escape');
    expect(tidyTitle('Chapter One. The Beginning', { ...DEFAULT_TIDY_OPTIONS, normalizeNumbers: false })).toBe(
      'Chapter One: The Beginning',
    );
    expect(tidyTitle('Chapter One of Frankenstein', { ...DEFAULT_TIDY_OPTIONS, normalizeNumbers: false })).toBe(
      'Chapter One of Frankenstein',
    );
  });

  it('treats a period after keyword+number as an ASR artifact', () => {
    expect(tidyTitle('Part 1. Operation Pajamas')).toBe('Part 1: Operation Pajamas');
    expect(tidyTitle('Chapter V. The Sea')).toBe('Chapter 5: The Sea');
    expect(tidyTitle('Chapter 2. of Frankenstein by Mary Shelley')).toBe('Chapter 2 of Frankenstein by Mary Shelley');
  });

  it('treats a leading number as a chapter marker', () => {
    expect(tidyTitle('3. Undaunted by Defeat')).toBe('3: Undaunted by Defeat');
    expect(tidyTitle('14 05')).toBe('14 05');
  });

  it('converts leading numbers per the configured format and separator', () => {
    const opts: TidyOptions = { ...DEFAULT_TIDY_OPTIONS, numberFormat: 'roman-upper', separator: ' - ' };
    expect(tidyTitle('1. the first Letter', opts)).toBe('I - The First Letter');
    expect(tidyTitle('two: what?', opts)).toBe('II - What?');
    expect(tidyTitle('3 hello', opts)).toBe('III - Hello');
    expect(tidyTitle('four - soup', opts)).toBe('IV - Soup');
  });

  it('treats Letter as a structural keyword', () => {
    expect(tidyTitle('Letter one of Frankenstein')).toBe('Letter 1 of Frankenstein');
  });

  it('respects disabled options', () => {
    expect(tidyTitle('CHAPTER ONE.', { ...DEFAULT_TIDY_OPTIONS, applyCase: false })).toBe('CHAPTER 1');
    expect(tidyTitle('chapter one', { ...DEFAULT_TIDY_OPTIONS, normalizeNumbers: false })).toBe('Chapter One');
  });

  it('supports configurable number formats', () => {
    expect(tidyTitle('Chapter Fourteen The Storm', { ...DEFAULT_TIDY_OPTIONS, numberFormat: 'roman-upper' })).toBe(
      'Chapter XIV: The Storm',
    );
    expect(tidyTitle('Chapter 2', { ...DEFAULT_TIDY_OPTIONS, numberFormat: 'words-title' })).toBe('Chapter Two');
  });

  it('supports configurable separators', () => {
    expect(tidyTitle('Chapter 14 The Hunt', { ...DEFAULT_TIDY_OPTIONS, separator: ' - ' })).toBe(
      'Chapter 14 - The Hunt',
    );
    expect(tidyTitle('Part 1. Operation Pajamas', { ...DEFAULT_TIDY_OPTIONS, separator: ' - ' })).toBe(
      'Part 1 - Operation Pajamas',
    );
    expect(tidyTitle('Chapter 14 Voyage', { ...DEFAULT_TIDY_OPTIONS, separator: '' })).toBe('Chapter 14 Voyage');
  });

  it('supports configurable case modes', () => {
    expect(tidyTitle('CHAPTER 14 THE STORM', { ...DEFAULT_TIDY_OPTIONS, caseMode: 'sentence' })).toBe(
      'Chapter 14: The storm',
    );
  });
});
