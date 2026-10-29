"""Freeze Python 3.11 Unicode 14 text semantics for the Rust port (development only).

Run in the reference image, never in the native runtime. No dataset is read.
"""
import argparse
import collections
import json
import re._casefix
import _sre
import unicodedata
from pathlib import Path


def ranges(numbers):
    result = []
    for n in numbers:
        if result and result[-1][1] + 1 == n:
            result[-1][1] = n
        else:
            result.append([n, n])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if unicodedata.unidata_version != "14.0.0":
        raise ValueError("Use the reference Python 3.11 Unicode 14 image")
    fold, decimal, groups = {}, {}, collections.defaultdict(list)
    word, space = [], []
    for n in range(0x110000):
        c = chr(n)
        if c.casefold() != c:
            fold[c] = c.casefold()
        if c.isalnum() or c == "_":
            word.append(n)
        if c.isspace():
            space.append(n)
        if c.isdecimal():
            decimal[c] = unicodedata.decimal(c)
        lo = _sre.unicode_tolower(n)
        group = min([lo, *re._casefix._EXTRA_CASES.get(lo, ())])
        groups[group].append(n)
    insensitive = {}
    for group in groups.values():
        if len(group) > 1:
            value = "".join(map(chr, group))
            for n in group:
                insensitive[chr(n)] = value
    result = dict(unicode_version=unicodedata.unidata_version,
                  casefold=fold, decimal=decimal, word=ranges(word),
                  space=ranges(space), insensitive=insensitive)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=True,
                                           separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
