# Status

Latest numbers. Upstream: fnv_decomp @ `91e1b6e8` (see `upstream.pin`). Measured 2026-11-16 in
the cloud container (Ubuntu 24.04, Clang 18.1.3, glibc/libstdc++ 13 multilib).

Reproduce:

    scripts/fetch-upstream.sh
    python3 -m tools.analyze --jobs 4               # Phase 1 -> out/analyze/
    python3 -m tools.compile_probe                  # Phase 2, -fsyntax-only -> out/compile_probe/syntax/
    python3 -m tools.compile_probe --mode obj       # Phase 2, -c -> out/compile_probe/obj/
    python3 -m tools.compile_probe.export           # -> status/compile_probe_*.{tsv,md}

| Phase | Status |
|---|---|
| 0 Scaffold | done |
| 1 Linkage and ABI analysis | done |
| 2 i686 compile baseline | done |
| 3-7 | not started (see `PLAN.md`) |

## Phase 1: linkage and ABI analysis

### Recipe, checked against the brief

| Brief | Measured | Note |
|---|---|---|
| ~3,000 units | 2,989 units, 2,979 sources | 10 sources are built twice as variants |
| ~3.9M lines | 3,961,681 lines (src, include, third_party) | |
| 70,611 in-scope functions | 68,657 functions + 1,954 EH tails = 70,611 | `totals` in units.json |
| 68,657 function addresses | 68,657 | |
| 262,366 bindings over 94,434 addresses | 262,366 over 94,434 | |
| 21,007 functions referenced only under other names | 21,006 | 21,007 if fold aliases are not counted as definition names: one address is referenced only through its fold alias |
| 53,289 data addresses | 53,289 non-function addresses | 4,618 of them lie inside the code range (EH handlers, out-of-scope code, 32 EH tails); 48,671 are real data |
| ~30,000 `extern DAT_` without definition | 32,217 `extern ... DAT_xxxxxxxx` declarations | naming 12,565 distinct addresses |
| 27 definitions of TESForm | 27 | |
| ~8,400 raw-offset accesses | 9,773 `(char*)p + N` patterns | depends on the pattern counted |
| 2,492 vtable addresses under 4,113 names | 2,491 addresses, 4,113 names | 7 `??_7` names are bound to two addresses each (same-named local classes); I find no 2,492nd address |

Name decoding: our demangler renders all 244,948 names `llvm-undname` accepts identically
(259,777 distinct names; the rest are C names, labels, constants, imports, EH helpers).
4 names in units.json are malformed (both demanglers reject them). 312 names are bound to more
than one address (706 name bindings left out of `aliases.ld`).

### Alias map (`out/analyze/aliases.{json,csv,ld}`, `data.ld`)

Every address with its definition and all names, plus GNU ld fragments. Canonical,
mangling-free symbols `fnv.f.<addr>` / `fnv.d.<addr>`; data is defined at its original
address; every decorated name is `PROVIDE`d onto its canonical. A test links a synthetic i686
object through both fragments with GNU ld.

### Calling conventions (`out/analyze/conventions.csv`, 132,862 rows with unit and source line)

Per function address, worst class over its (definition, other name) pairs. Verdicts come from
an argument-location model (registers, stack slots, callee cleanup, return location) under
MSVC rules and under Clang's default i686 Linux rules: `yes`, `yes-if-unused` (the definition
reads an argument the reference does not pass, e.g. the dummy EDX), `if-this-unused` (the
definition's `this`/self is not where it reads it), `unknown`, `no`.

| class | addresses | name pairs | i686 Linux verdicts (addresses) |
|---|---|---|---|
| cc-conflict (other convention differences) | 1,315 | 2,011 | no 484, if-this-unused 473, unknown 246, yes 102, yes-if-unused 10 |
| thiscall-fastcall | 2,029 | 9,118 | if-this-unused 1,422, no 560, unknown 47 (MSVC: yes 1,254, yes-if-unused 512) |
| member-free (same convention) | 26 | 58 | yes 16, no 4, unknown 4, if-this-unused 2 |
| function-as-data | 447 | 450 | (function addresses also named as data, e.g. `DAT_` on a function) |
| params-differ | 18,320 | 63,042 | yes 15,835, unknown 946, yes-if-unused 674, if-this-unused 443, no 422 |
| name-only | 8,601 | 35,283 | yes 8,201, unknown 400 |
| identical (only the definition name) | 37,919 | | |

27,512 function addresses are never referenced by relocation (reached only through vtables
and other data). Over all addresses with other names, i686 Linux verdicts: yes 24,597,
if-this-unused 2,343, unknown 1,643, no 1,471, yes-if-unused 684. Under MSVC rules the same
pairs give no 1,797 / if-this-unused 892: those mismatches exist in the original too, so they
are references that are never called through, or calls whose differences do not matter.

### Vtables (`out/analyze/vtables.csv`, `vtable_views.csv`)

2,491 vtable addresses, 4,113 names; 1,171 addresses have several names and 1,167 several
class names (up to 54 for one address); 756 are secondary-base (`{for ...}`) vftables;
959 units reference vtables.

AST pass, all 959 units, full run (26 s; libclang, function bodies skipped): MSVC vftable
layouts computed from each unit's own view (rules checked against Clang's
`-fdump-vtable-layouts` for an MSVC target in `tests/test_vtable_ast.py`).

| | |
|---|---|
| views computed / class not found / unsupported (virtual or incomplete base) / no vftable / subobject not found | 3,996 / 334 / 12 / 18 / 1 |
| addresses with a layout | 2,448 |
| addresses with two or more views | 1,018 |
| **addresses whose views disagree** | **559** (slot count 425, destructor slot 383) |
| of these, among views from units that compile cleanly | 99 |

### Data (`out/analyze/data.csv`)

| kind | addresses |
|---|---|
| plain globals | 37,577 (named 18,741, placeholder `DAT_`-style only 18,015, C-named 821) |
| string literals | 7,389 |
| code inside the code range (not in scope) | 4,577 (EH handler stubs 4,202, out-of-scope functions 374) |
| vtables / vbtables | 2,491 / 5 |
| float constants | 695 |
| RTTI type descriptors | 295 |
| import (IAT) slots | 208 (22 named without `__imp_`), 263 imported API names |
| EH tails, local static guards, absolute (`__tls_array`) | 32, 16, 4 |

2,277 addresses are referenced under names of more than one kind (e.g. a vtable also named
as a `DAT_` global). The IAT is 0x00fdf000-0x00fdf4a0; two `__imp_` names are ordinary
globals elsewhere.

## Phase 2: i686 compile baseline

Flags: `--target=i686-linux-gnu -fms-extensions -fms-compatibility -fasm-blocks
-malign-double` plus, from the errors: `-fms-compatibility-version=19.00` (Clang otherwise
drops char16_t, which libstdc++ needs; `_MSC_VER` stays 1500 via the prelude),
`-mlong-double-64` (MSVC's long double is 64-bit; with `-malign-double` an 80-bit one is
12 bytes aligned to 8, which libstdc++ rejects), `-fdelayed-template-parsing` (MSVC 2008 has
no two-phase lookup), `-msse2 -mfpmath=sse` (decided: SSE2 floating point; also provides the
builtins `_mm_prefetch`/`_mm_setcsr` need), and
`-std=gnu++14` (gnu++17 rejects `register`/dynamic exception specs and crashed Clang on 5
units; gnu++98 passes fewer: 56.9%). 32-bit headers: Ubuntu `gcc-multilib g++-multilib`.
Header shim: `shim/include` (see `CLAUDE.md`).

| mode | pass | |
|---|---|---|
| `-fsyntax-only` | **1,792 / 2,989 (60.0%)** | 1,197 with errors, no crashes |
| `-c` | **1,792 / 2,989 (60.0%)** | the same units as `-fsyntax-only` |

Per unit: `status/compile_probe_units.tsv`. Per area: `status/compile_probe_areas.md`
(Havok 85%, Gamebryo 84%, zlib 100%; game code: fallout_shared 31%, fallout 29%,
staging 13%).

Root-cause categories (units with at least one such error; "first" = units whose first error
is in the category; "unblocks" = units that compile once this and the categories above it
are fixed, greedy order, optimistic since fixes can expose hidden errors):

| # | category | units | first | unblocks | cumulative pass |
|---|---|---|---|---|---|
| 1 | forward-declared enum used as a complete type | 604 | 585 | +254 | 68.5% |
| 2 | `__if_exists`/`__if_not_exists` on an undefined template | 360 | 260 | +206 | 75.3% |
| 3 | calling-convention redeclaration | 240 | 101 | +121 | 79.4% |
| 4 | per-unit class views disagree (hierarchy, members) | 206 | 6 | +120 | 83.4% |
| 5 | conflicting redeclarations (types, linkage, return type) | 201 | 101 | +112 | 87.2% |
| 6 | C++ dialect strictness (rvalue refs, temporaries, narrowing, ...) | 150 | 48 | +111 | 90.9% |
| 7 | operator new/delete declared inside a namespace | 72 | 17 | +56 | 92.7% |
| 8 | MSVC SSE model (own `__m128`, intrinsic redeclarations) | 67 | 30 | +57 | 94.6% |
| 9 | incomplete class type in this unit's view | 52 | 16 | +42 | 96.1% |
| 10 | layout static assert fails or is not constant | 49 | 1 | +37 | 97.3% |
| | undeclared identifier / other / SEH (3 units) / ... | | | +81 | 100% |

Top Clang messages (`out/compile_probe/syntax/histogram.csv` has all):

| # | message (identifiers as 'X') | units | first |
|---|---|---|---|
| 1 | field has incomplete type 'X' | 592 | 577 |
| 2 | implicit instantiation of undefined template 'X' | 360 | 260 |
| 3 | function declared 'X' here was previously declared without calling convention | 237 | 100 |
| 4 | cannot initialize object parameter of type 'X' with an expression of type 'X' | 150 | 0 |
| 5 | functions that differ only in their return type cannot be overloaded | 103 | 44 |
| 6 | 'X' is an incomplete type | 103 | 4 |
| 7 | conflicting types for 'X' | 79 | 18 |
| 8 | 'X' cannot be declared inside a namespace | 72 | 17 |
| 9 | no matching member function for call to 'X' | 64 | 0 |
| 10 | taking the address of a temporary object of type 'X' | 63 | 10 |

Other findings:

- MS inline asm: 89 units contain `__asm`; Clang rejected none (46 of them compile; the others
  fail earlier). Whether the asm is correct on Linux (frame assumptions, TEB access) is
  untested.
- A real layout difference: under `#pragma pack(1)`, Itanium layout lets the pack cap the
  alignment of a `__declspec(align(16))` base; MSVC does not. `hkpNullCollisionFilter` is
  0x24 bytes on Clang/Linux vs 0x30 on MSVC (Clang's own MSVC-target layout agrees with
  upstream's assert). An explicit alignment on the class fixes it; one on a field does not.
- SEH (`__try`) is unsupported by Clang on Linux (3 units).
- `__readfsdword` (TEB access, 38 occurrences) compiles but needs a TEB at runtime.
