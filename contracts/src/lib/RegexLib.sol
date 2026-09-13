// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title RegexLib
/// @notice A self-contained regular-expression engine written in Solidity.
///
/// The onchain regex engine powering headline matching: a real, working matcher over
/// the DKIM-verified email Subject. Implemented as an NFA position-set simulation so
/// matching always terminates (no exponential backtracking), written assuming no gas
/// constraints. Matching runs publicly over authenticated subject bytes; no proof
/// circuit is required.
///
/// Supported syntax (a practical subset of JavaScript regex semantics):
///   - literal characters, `.` (any char except \n and \r)
///   - character classes `[abc]`, ranges `[a-z0-9]`, negation `[^...]`
///   - escapes: `\d \D \w \W \s \S`, `\n \t \r`, and escaped metacharacters (`\.` `\|` ...)
///   - groups `( ... )` and non-capturing `(?: ... )` (equivalent here)
///   - alternation `a|b`
///   - quantifiers `*` `+` `?` `{m}` `{m,}` `{m,n}`
///   - anchors `^` (input start) and `$` (input end)
///   - a global case-insensitive flag via the `(?i)` prefix
///
/// Not supported: lookaround, backreferences, lazy quantifiers (irrelevant for
/// boolean `test` semantics), unicode classes. `test` uses *search* semantics like
/// JavaScript's `RegExp.test`: the pattern may match anywhere in the input unless
/// anchored.
library RegexLib {
    uint16 internal constant INF = type(uint16).max;
    uint16 internal constant MAX_GROUP_DEPTH = 16;

    enum Kind {
        Char, // single literal character
        Any, // '.'
        Class, // character class
        Group, // parenthesised sub-expression
        Start, // '^' zero-width assertion
        End // '$' zero-width assertion
    }

    struct Atom {
        Kind kind;
        bytes1 ch; // Kind.Char: the literal
        uint16 cls; // Kind.Class: index into classes
        uint16 grp; // Kind.Group: index into alts
        uint16 minRep;
        uint16 maxRep; // INF = unbounded
    }

    struct CharClass {
        bool negated;
        uint16 start; // range slice start in `ranges`
        uint16 count;
    }

    struct Range {
        bytes1 lo;
        bytes1 hi;
    }

    // A sequence is a run of atoms matched one after another. Its atom indices live
    // in the flat `seqAtoms` pool at [start, start+count).
    struct Seq {
        uint16 start;
        uint16 count;
    }

    // An alternation is a set of sequences (branches). Its seq indices live in the
    // flat `altSeqs` pool at [start, start+count).
    struct Alt {
        uint16 start;
        uint16 count;
    }

    struct Prog {
        bytes pat;
        uint256 pos;
        bool ci; // case-insensitive
        Atom[] atoms;
        uint16 nAtoms;
        CharClass[] classes;
        uint16 nClasses;
        Range[] ranges;
        uint16 nRanges;
        Seq[] seqs;
        uint16 nSeqs;
        Alt[] alts;
        uint16 nAlts;
        uint16[] seqAtoms;
        uint16 nSeqAtoms;
        uint16[] altSeqs;
        uint16 nAltSeqs;
        uint16 depth; // current group-nesting depth (bounded so the matcher can't overflow the EVM stack)
        uint16 root;
    }

    // ---------------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------------

    /// @notice JavaScript-style `RegExp.test`: true if `pattern` matches anywhere in `input`.
    /// @dev `public` on purpose: RegexLib deploys once as an external library and is
    /// delegatecalled, keeping the regex engine out of every market's bytecode (E1).
    /// (Named `matches` rather than `test` so tooling never mistakes the deployed
    /// library for a test contract.)
    function matches(string memory pattern, string memory input) public pure returns (bool) {
        Prog memory p = parse(pattern);
        return run(p, bytes(input));
    }

    /// @notice Reverts with a descriptive message if `pattern` is not valid under the
    /// supported subset. Call at market creation so invalid patterns are rejected early.
    function validate(string memory pattern) public pure {
        parse(pattern);
    }

    // ---------------------------------------------------------------------
    // Parser (recursive descent -> node pools)
    // ---------------------------------------------------------------------

    function parse(string memory pattern) internal pure returns (Prog memory p) {
        bytes memory pat = bytes(pattern);
        require(pat.length <= 10_000, "Regex: pattern too long");
        p.pat = pat;
        p.pos = 0;
        if (pat.length >= 4 && pat[0] == "(" && pat[1] == "?" && pat[2] == "i" && pat[3] == ")") {
            p.ci = true;
            p.pos = 4;
        }
        uint256 cap = pat.length + 2;
        p.atoms = new Atom[](cap);
        p.classes = new CharClass[](cap);
        p.ranges = new Range[](3 * pat.length + 8);
        p.seqs = new Seq[](cap);
        p.alts = new Alt[](cap);
        p.seqAtoms = new uint16[](cap);
        p.altSeqs = new uint16[](cap);
        p.root = parseAlt(p);
        require(p.pos == pat.length, "Regex: unbalanced ')'");
    }

    function parseAlt(Prog memory p) private pure returns (uint16) {
        uint256 remaining = p.pat.length - p.pos + 1;
        uint16[] memory branches = new uint16[](remaining);
        uint256 nBranches = 0;
        while (true) {
            branches[nBranches++] = parseSeq(p);
            if (p.pos < p.pat.length && p.pat[p.pos] == "|") {
                p.pos++;
            } else {
                break;
            }
        }
        // Commit branch list contiguously into the flat pool.
        uint16 startIdx = p.nAltSeqs;
        for (uint256 i = 0; i < nBranches; i++) {
            p.altSeqs[p.nAltSeqs++] = branches[i];
        }
        p.alts[p.nAlts] = Alt({start: startIdx, count: uint16(nBranches)});
        return p.nAlts++;
    }

    function parseSeq(Prog memory p) private pure returns (uint16) {
        uint256 remaining = p.pat.length - p.pos + 1;
        uint16[] memory atomIdxs = new uint16[](remaining);
        uint256 nSeqAtoms = 0;
        while (p.pos < p.pat.length && p.pat[p.pos] != "|" && p.pat[p.pos] != ")") {
            atomIdxs[nSeqAtoms++] = parseAtom(p);
        }
        uint16 startIdx = p.nSeqAtoms;
        for (uint256 i = 0; i < nSeqAtoms; i++) {
            p.seqAtoms[p.nSeqAtoms++] = atomIdxs[i];
        }
        p.seqs[p.nSeqs] = Seq({start: startIdx, count: uint16(nSeqAtoms)});
        return p.nSeqs++;
    }

    function parseAtom(Prog memory p) private pure returns (uint16) {
        bytes1 c = p.pat[p.pos];
        Atom memory a;
        a.minRep = 1;
        a.maxRep = 1;

        if (c == "(") {
            p.pos++;
            // Non-capturing group marker `(?:` — capturing and non-capturing are
            // identical for boolean matching, so just skip the marker.
            if (p.pos + 1 < p.pat.length && p.pat[p.pos] == "?" && p.pat[p.pos + 1] == ":") {
                p.pos += 2;
            } else {
                require(p.pos >= p.pat.length || p.pat[p.pos] != "?", "Regex: unsupported group modifier");
            }
            a.kind = Kind.Group;
            // Cap nesting: the matcher recurses ~4 EVM frames per level, so a pattern
            // the parser accepts but the matcher can't run (EVM stack overflow) would
            // brick settlement. 16 is far below the ~45-level matcher limit and ample
            // for any realistic headline pattern.
            p.depth++;
            require(p.depth <= MAX_GROUP_DEPTH, "Regex: groups nested too deep");
            a.grp = parseAlt(p);
            p.depth--;
            require(p.pos < p.pat.length && p.pat[p.pos] == ")", "Regex: missing ')'");
            p.pos++;
        } else if (c == ".") {
            a.kind = Kind.Any;
            p.pos++;
        } else if (c == "[") {
            a.kind = Kind.Class;
            a.cls = parseClass(p);
        } else if (c == "^") {
            a.kind = Kind.Start;
            p.pos++;
        } else if (c == "$") {
            a.kind = Kind.End;
            p.pos++;
        } else if (c == "\\") {
            p.pos++;
            require(p.pos < p.pat.length, "Regex: trailing backslash");
            bytes1 e = p.pat[p.pos];
            p.pos++;
            if (e == "d" || e == "D" || e == "w" || e == "W" || e == "s" || e == "S") {
                a.kind = Kind.Class;
                a.cls = builtinClass(p, e);
            } else {
                // Reject escapes we don't implement (\b, \x41, \u..., backreferences \1)
                // rather than silently treating them as literals — JS gives them
                // different meaning, so accepting them would let a market's pattern
                // mean one thing in the wizard's JS preview and another onchain.
                require(isAllowedLiteralEscape(e), "Regex: unsupported escape");
                a.kind = Kind.Char;
                a.ch = unescapeControl(e);
            }
        } else if (c == "*" || c == "+" || c == "?") {
            revert("Regex: quantifier without target");
        } else {
            a.kind = Kind.Char;
            a.ch = c;
            p.pos++;
        }

        parseQuantifier(p, a);
        p.atoms[p.nAtoms] = a;
        return p.nAtoms++;
    }

    function parseQuantifier(Prog memory p, Atom memory a) private pure {
        if (p.pos >= p.pat.length) return;
        bytes1 q = p.pat[p.pos];
        if (q == "*") {
            requireQuantifiable(a);
            a.minRep = 0;
            a.maxRep = INF;
            p.pos++;
        } else if (q == "+") {
            requireQuantifiable(a);
            a.minRep = 1;
            a.maxRep = INF;
            p.pos++;
        } else if (q == "?") {
            requireQuantifiable(a);
            a.minRep = 0;
            a.maxRep = 1;
            p.pos++;
        } else if (q == "{") {
            // Lookahead: only treat `{` as a quantifier if it forms a valid `{m}`,
            // `{m,}` or `{m,n}` — otherwise it is a literal brace (JS behaviour).
            (bool ok, uint16 lo, uint16 hi, uint256 endPos) = tryParseBraces(p);
            if (ok) {
                requireQuantifiable(a);
                require(lo <= hi, "Regex: bad {m,n} bounds");
                a.minRep = lo;
                a.maxRep = hi;
                p.pos = endPos;
            }
        }
    }

    function tryParseBraces(Prog memory p) private pure returns (bool ok, uint16 lo, uint16 hi, uint256 endPos) {
        uint256 i = p.pos + 1; // skip '{'
        uint256 v = 0;
        bool sawDigit = false;
        while (i < p.pat.length && isDigit(p.pat[i])) {
            v = v * 10 + uint8(p.pat[i]) - 48;
            require(v < INF, "Regex: repetition too large");
            sawDigit = true;
            i++;
        }
        if (!sawDigit || i >= p.pat.length) return (false, 0, 0, 0);
        lo = uint16(v);
        if (p.pat[i] == "}") return (true, lo, lo, i + 1);
        if (p.pat[i] != ",") return (false, 0, 0, 0);
        i++; // skip ','
        if (i < p.pat.length && p.pat[i] == "}") return (true, lo, INF, i + 1);
        v = 0;
        sawDigit = false;
        while (i < p.pat.length && isDigit(p.pat[i])) {
            v = v * 10 + uint8(p.pat[i]) - 48;
            require(v < INF, "Regex: repetition too large");
            sawDigit = true;
            i++;
        }
        if (!sawDigit || i >= p.pat.length || p.pat[i] != "}") return (false, 0, 0, 0);
        return (true, lo, uint16(v), i + 1);
    }

    function parseClass(Prog memory p) private pure returns (uint16) {
        p.pos++; // consume '['
        bool negated = false;
        if (p.pos < p.pat.length && p.pat[p.pos] == "^") {
            negated = true;
            p.pos++;
        }
        uint16 startIdx = p.nRanges;
        bool first = true;
        while (true) {
            require(p.pos < p.pat.length, "Regex: unterminated class");
            bytes1 c = p.pat[p.pos];
            if (c == "]" && !first) {
                p.pos++;
                break;
            }
            first = false;
            if (c == "\\") {
                p.pos++;
                require(p.pos < p.pat.length, "Regex: trailing backslash");
                bytes1 e = p.pat[p.pos];
                p.pos++;
                if (e == "d" || e == "D" || e == "w" || e == "W" || e == "s" || e == "S") {
                    appendBuiltinRanges(p, e);
                    continue;
                }
                require(isAllowedLiteralEscape(e), "Regex: unsupported escape");
                c = unescapeControl(e);
            } else {
                p.pos++;
            }
            // Possible range `c-hi` (a trailing `-` before `]` is a literal dash). A `-`
            // followed by a class escape like `\d` is NOT a range endpoint — `[a-\d]`
            // means {a, '-', digits}, matching JS Annex B — so leave the `-` as a literal.
            if (
                p.pos + 1 < p.pat.length && p.pat[p.pos] == "-" && p.pat[p.pos + 1] != "]"
                    && !(p.pat[p.pos + 1] == "\\" && p.pos + 2 < p.pat.length && isClassEscape(p.pat[p.pos + 2]))
            ) {
                p.pos++; // consume '-'
                bytes1 hi = p.pat[p.pos];
                if (hi == "\\") {
                    p.pos++;
                    require(p.pos < p.pat.length, "Regex: trailing backslash");
                    bytes1 he = p.pat[p.pos];
                    require(isAllowedLiteralEscape(he), "Regex: unsupported escape");
                    hi = unescapeControl(he);
                }
                p.pos++;
                require(uint8(c) <= uint8(hi), "Regex: bad class range");
                p.ranges[p.nRanges++] = Range({lo: c, hi: hi});
            } else {
                p.ranges[p.nRanges++] = Range({lo: c, hi: c});
            }
        }
        p.classes[p.nClasses] = CharClass({negated: negated, start: startIdx, count: p.nRanges - startIdx});
        return p.nClasses++;
    }

    /// @dev Creates a standalone class node for `\d \D \w \W \s \S`.
    function builtinClass(Prog memory p, bytes1 e) private pure returns (uint16) {
        uint16 startIdx = p.nRanges;
        appendBuiltinRanges(p, e);
        p.classes[p.nClasses] = CharClass({negated: false, start: startIdx, count: p.nRanges - startIdx});
        return p.nClasses++;
    }

    /// @dev Appends the explicit (already-complemented where needed) range list of a builtin class.
    function appendBuiltinRanges(Prog memory p, bytes1 e) private pure {
        if (e == "d") {
            p.ranges[p.nRanges++] = Range(0x30, 0x39);
        } else if (e == "D") {
            p.ranges[p.nRanges++] = Range(0x00, 0x2F);
            p.ranges[p.nRanges++] = Range(0x3A, 0xFF);
        } else if (e == "w") {
            p.ranges[p.nRanges++] = Range(0x30, 0x39); // 0-9
            p.ranges[p.nRanges++] = Range(0x41, 0x5A); // A-Z
            p.ranges[p.nRanges++] = Range(0x5F, 0x5F); // _
            p.ranges[p.nRanges++] = Range(0x61, 0x7A); // a-z
        } else if (e == "W") {
            p.ranges[p.nRanges++] = Range(0x00, 0x2F);
            p.ranges[p.nRanges++] = Range(0x3A, 0x40);
            p.ranges[p.nRanges++] = Range(0x5B, 0x5E);
            p.ranges[p.nRanges++] = Range(0x60, 0x60);
            p.ranges[p.nRanges++] = Range(0x7B, 0xFF);
        } else if (e == "s") {
            p.ranges[p.nRanges++] = Range(0x09, 0x0D); // \t \n \v \f \r
            p.ranges[p.nRanges++] = Range(0x20, 0x20); // space
        } else if (e == "S") {
            p.ranges[p.nRanges++] = Range(0x00, 0x08);
            p.ranges[p.nRanges++] = Range(0x0E, 0x1F);
            p.ranges[p.nRanges++] = Range(0x21, 0xFF);
        }
    }

    function unescapeControl(bytes1 e) private pure returns (bytes1) {
        if (e == "n") return 0x0A;
        if (e == "t") return 0x09;
        if (e == "r") return 0x0D;
        if (e == "0") return 0x00;
        return e; // escaped metacharacter or ordinary escaped literal
    }

    /// @dev An escaped char that is a valid literal in our subset: the control escapes
    /// `\n \t \r \0`, or any escaped non-alphanumeric (a metacharacter/punctuation). Any
    /// other escaped ASCII letter/digit (`\b \x \u \c`, backreferences) is unsupported.
    function isAllowedLiteralEscape(bytes1 e) private pure returns (bool) {
        if (e == "n" || e == "t" || e == "r" || e == "0") return true;
        bool alnum = (e >= "0" && e <= "9") || (e >= "A" && e <= "Z") || (e >= "a" && e <= "z");
        return !alnum;
    }

    function isClassEscape(bytes1 e) private pure returns (bool) {
        return e == "d" || e == "D" || e == "w" || e == "W" || e == "s" || e == "S";
    }

    function requireQuantifiable(Atom memory a) private pure {
        require(a.kind != Kind.Start && a.kind != Kind.End, "Regex: nothing to repeat");
    }

    function isDigit(bytes1 c) private pure returns (bool) {
        return c >= "0" && c <= "9";
    }

    // ---------------------------------------------------------------------
    // Matcher (NFA position-set simulation)
    // ---------------------------------------------------------------------
    //
    // A "position set" is a bool[input.length + 1] where set[i] means "the pattern
    // consumed input up to (but excluding) index i". Search semantics fall out of
    // seeding the set with every start position; `^` filters it back to {0}.

    function run(Prog memory p, bytes memory s) private pure returns (bool) {
        bool[] memory starts = new bool[](s.length + 1);
        for (uint256 i = 0; i <= s.length; i++) {
            starts[i] = true;
        }
        bool[] memory ends = matchAlt(p, p.root, s, starts);
        return anySet(ends);
    }

    function matchAlt(Prog memory p, uint16 altIdx, bytes memory s, bool[] memory fromSet)
        private
        pure
        returns (bool[] memory out)
    {
        Alt memory alt = p.alts[altIdx];
        out = new bool[](s.length + 1);
        for (uint256 b = 0; b < alt.count; b++) {
            bool[] memory branchEnds = matchSeq(p, p.altSeqs[alt.start + b], s, fromSet);
            unionInto(out, branchEnds);
        }
    }

    function matchSeq(Prog memory p, uint16 seqIdx, bytes memory s, bool[] memory fromSet)
        private
        pure
        returns (bool[] memory cur)
    {
        Seq memory seq = p.seqs[seqIdx];
        cur = copySet(fromSet);
        for (uint256 i = 0; i < seq.count; i++) {
            cur = matchQuantified(p, p.atoms[p.seqAtoms[seq.start + i]], s, cur);
            if (!anySet(cur)) break;
        }
    }

    /// @dev Applies an atom with its {min,max} quantifier to a position set.
    function matchQuantified(Prog memory p, Atom memory a, bytes memory s, bool[] memory fromSet)
        private
        pure
        returns (bool[] memory result)
    {
        bool[] memory cur = copySet(fromSet);
        result = new bool[](s.length + 1);
        // Positions reachable with exactly `rep` repetitions live in `cur`; fold
        // every rep count within [minRep, maxRep] into `result`. Iteration stops at
        // a fixpoint (no new positions) or when the set empties, so `maxRep = INF`
        // terminates in at most input-length steps.
        if (a.minRep == 0) unionInto(result, cur);
        uint256 rep = 1;
        while (rep <= a.maxRep) {
            cur = matchOnce(p, a, s, cur);
            if (!anySet(cur)) break;
            if (rep >= a.minRep) {
                bool grew = unionInto(result, cur);
                if (!grew && rep > a.minRep) break; // fixpoint
            }
            rep++;
        }
    }

    /// @dev Matches a single occurrence of an atom against every position in the set.
    function matchOnce(Prog memory p, Atom memory a, bytes memory s, bool[] memory fromSet)
        private
        pure
        returns (bool[] memory out)
    {
        if (a.kind == Kind.Group) {
            return matchAlt(p, a.grp, s, fromSet);
        }
        out = new bool[](s.length + 1);
        for (uint256 i = 0; i <= s.length; i++) {
            if (!fromSet[i]) continue;
            if (a.kind == Kind.Start) {
                if (i == 0) out[i] = true;
            } else if (a.kind == Kind.End) {
                if (i == s.length) out[i] = true;
            } else if (i < s.length) {
                bytes1 c = s[i];
                if (a.kind == Kind.Char) {
                    if (charEq(c, a.ch, p.ci)) out[i + 1] = true;
                } else if (a.kind == Kind.Any) {
                    if (c != 0x0A && c != 0x0D) out[i + 1] = true;
                } else {
                    if (inClass(p, a.cls, c)) out[i + 1] = true;
                }
            }
        }
    }

    function inClass(Prog memory p, uint16 clsIdx, bytes1 c) private pure returns (bool) {
        CharClass memory cls = p.classes[clsIdx];
        bool hit = classRangesHit(p, cls, c);
        if (!hit && p.ci) {
            bytes1 swapped = swapCase(c);
            if (swapped != c) hit = classRangesHit(p, cls, swapped);
        }
        return cls.negated ? !hit : hit;
    }

    function classRangesHit(Prog memory p, CharClass memory cls, bytes1 c) private pure returns (bool) {
        for (uint256 r = 0; r < cls.count; r++) {
            Range memory rg = p.ranges[cls.start + r];
            if (c >= rg.lo && c <= rg.hi) return true;
        }
        return false;
    }

    function charEq(bytes1 a, bytes1 b, bool ci) private pure returns (bool) {
        if (a == b) return true;
        if (!ci) return false;
        return swapCase(a) == b;
    }

    function swapCase(bytes1 c) private pure returns (bytes1) {
        if (c >= "A" && c <= "Z") return bytes1(uint8(c) + 32);
        if (c >= "a" && c <= "z") return bytes1(uint8(c) - 32);
        return c;
    }

    // -- position-set helpers ---------------------------------------------

    function copySet(bool[] memory a) private pure returns (bool[] memory out) {
        out = new bool[](a.length);
        for (uint256 i = 0; i < a.length; i++) {
            out[i] = a[i];
        }
    }

    /// @dev Unions `src` into `dst`; returns true if `dst` gained a new position.
    function unionInto(bool[] memory dst, bool[] memory src) private pure returns (bool grew) {
        for (uint256 i = 0; i < dst.length; i++) {
            if (src[i] && !dst[i]) {
                dst[i] = true;
                grew = true;
            }
        }
    }

    function anySet(bool[] memory a) private pure returns (bool) {
        for (uint256 i = 0; i < a.length; i++) {
            if (a[i]) return true;
        }
        return false;
    }
}
