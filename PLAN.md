# Roadmap

Status key: `done`, `in progress`, `not started`, `blocked`.

The port is built entirely on the player's machine: fetch fnv_decomp at the pinned commit,
apply automated transforms into a separate working tree, extract data from the player's own
exe, compile for i686 Linux with Clang, and link with a fixed-address linker layout. This repo
ships only tools, transforms and platform code. See `CLAUDE.md` for the hard rules and
`STATUS.md` for the latest numbers.

## Phase 0: Scaffold (status: done)

`PLAN.md`, `CLAUDE.md`, `STATUS.md`, `.gitignore`; `upstream.pin` + `scripts/fetch-upstream.sh`
(clones fnv_decomp at the pinned commit into `upstream/fnv_decomp`, refuses a dirty checkout);
Python 3.10+ standard library, pytest. libclang (system package) is used for AST work.

## Phase 1: Linkage and ABI analysis, `tools/analyze` (status: done)

`python3 -m tools.analyze` -> `out/analyze/`: alias map + GNU ld fragments, calling-convention
report with MSVC and i686-Linux ABI verdicts, vtable report (names + per-unit MSVC vftable
layouts from libclang), data report. Counts and reconciliation with the brief: `STATUS.md`.

## Phase 2: i686 compile baseline, `tools/compile_probe` (status: done)

`python3 -m tools.compile_probe [--mode obj]`, header shim in `shim/include`.
Baseline 60.0% of units pass `-fsyntax-only` and compile with `-c` (SSE2 floating point). Root-cause categories
and a greedy unlock order: `STATUS.md`.

## Phase 3: Transforms (status: not started) - proposal

Goal: every unit compiles with `-c` for i686 Linux, every function address has one ABI
across all units, and every class with a vtable has one agreed definition. Transforms read
`upstream/` and write `work/` (never in place), are keyed on `@fnv` addresses and units.json
(never on names), and are computed with libclang (cursor extents -> byte edits applied in
Python; a C++ LibTooling tool only if libclang cannot express an edit). Each transform has
synthetic-input tests and is measured by re-running the Phase 1/2 tools on `work/`.

### 3a. Infrastructure (small)
- `tools/transform`: edit model (file, offset, length, text, reason, address), conflict
  detection, idempotent application into `work/fnv_decomp`, a manifest of applied edits.
- `compile_probe --tree work/fnv_decomp` and `analyze --tree`, so every transform reports its
  delta against the baseline.

### 3b. MSVC leniencies (in greedy order; the % is the projected syntax pass rate)
1. Forward-declared enums used as complete types: give the forward declaration and the
   definition MSVC's underlying type (`: int`). First error in 585 units -> ~68%.
2. `__if_exists(T::member)` / `__if_not_exists` on an undefined class template: Clang
   instantiates, MSVC treats it as absent. Resolve these blocks statically as MSVC does
   (mostly two shared headers). -> ~75%.
3. Calling-convention redeclarations: put the definition's convention on every declaration
   of that function (240 units). -> ~79%.
4. Conflicting redeclarations: drop units' local `extern "C"` redeclarations of Win32/CRT
   functions the shim declares; give duplicate typedefs one definition. -> ~87% with 3d's
   view fixes.
5. Dialect: rvalue-to-reference casts, address of temporaries, narrowing (explicit casts),
   specialization order, exception specifications. -> ~91%.
6. `operator new/delete` declared inside namespaces: hoist or drop duplicates. -> ~93%.
7. SSE: units that define `__m128` twice or redeclare intrinsics with their own union type
   (the shim already gives MSVC's model). -> ~95%.
8. SEH (`__try`, 3 units): rewrite to explicit checks or a platform-layer helper.

### 3c. ABI
1. Convention normalisation: annotate every non-static, non-variadic member function
   `__thiscall` (Clang honours it on i686 Linux: `this` in ECX, callee pops; verified).
   Then every declaration has its MSVC ABI on Linux, and the 2,029 thiscall-fastcall
   addresses (today on Linux: if-this-unused 1,422, no 560) behave exactly as in the original.
2. Remaining per-address mismatches (about 1,800 addresses that disagree even under MSVC
   rules): rewrite the declarations units actually call through to the definition's
   signature, by address. Verify with the convention report on `work/`.
3. Layout: a dual-ABI record-layout diff (Clang computes MSVC layouts with
   `--target=i686-pc-windows-msvc`) over every record in every unit; where Itanium layout
   differs (e.g. `__declspec(align)` bases under `#pragma pack`), add explicit alignment or
   padding. Upstream's size asserts then check the result.
4. Linkage by address: attach canonical labels (`asm("fnv.f.<addr>")`, `fnv.d.<addr>`) to every
   declaration bound to an address in units.json, so linking no longer depends on names
   (Phase 1's `data.ld`/`aliases.ld` then cover the rest).

### 3d. One class definition per vtable (the central hard problem)
- Canonical vftable per vtable address: the slot list from the richest consistent view, each
  slot tied to the function address defined for it. The Phase 1 AST pass already gives views
  for 2,448 of 2,491 addresses; 559 addresses have disagreeing views (99 among cleanly
  compiling units). Decided: on the player's machine the build reads the original vftable
  contents (slot -> function address) from the exe's `.rdata`, after the fingerprint check,
  and the transform uses them as ground truth: slot count, destructor slot, and which function
  address fills each slot. The data stays in `extracted/` (gitignored) and is never committed
  or printed. In cloud sessions this is developed and tested with synthetic PE fixtures; the
  views from the AST pass are the fallback when no exe is given.
- Rewrite every unit's view of a dynamic class to declare that canonical virtual-method list
  (and identical data layout, checked by the layout diff); per-unit non-virtual members can
  stay.
- Constructors and destructors that store an original vtable address: remove the store,
  rely on the compiler-generated Itanium vptr. Map MSVC scalar/vector deleting destructors
  (`??_G` 885 names, `??_E` 57; often defined as free `__fastcall` functions) to virtual
  destructors so Itanium D0/D1 are generated.
- Mismatched hierarchies between views (Phase 2 category 4, 206 units) are resolved by the
  same unification.

### Size estimate
- 3a: ~1 session. 3b: 2-3 sessions (8 transforms; reaching ~90-95% syntax pass).
  3c: 2-3 sessions (normalisation is small; the layout diff tool and per-address declaration
  rewrites are medium). 3d: 4-8 sessions (2,491 vtables, 959 referencing units, ~4,100
  vtable-name bindings, ~940 deleting-destructor names), the most uncertain part.
- Total: roughly 9-15 sessions of this length. Exit criterion: `-c` pass rate 100%, convention
  report shows no Linux `no`/`if-this-unused` verdicts at called references, every vtable
  address has one class definition used by all units.

## Phase 4: Data extractor, linker layout, code-pointer translation (status: not started)

Build order on the player's machine: fetch -> fingerprint check and extraction -> transforms
(3d consumes the original vftables) -> compile -> link. The extractor therefore runs before the
transforms; it exposes the vftable contents to them through `extracted/`.

- Extractor: reads only unencrypted `.data/.rdata/.bss` from the player's exe, after
  upstream's fingerprint check (`build/image_check.json`); fails cleanly otherwise.
  Synthetic PE fixtures here; real runs on the player's machine. The fingerprints hash
  `.text` bytes, and upstream says the Steam exe's code is encrypted on disk, so a Steam
  install fails the check by design. The DRM-free GOG release is the recommended source
  (untested whether it passes).
- Linker script: original sections at original VAs (non-PIE), new code at 0x10000000+.
  Data symbols at original addresses (`data.ld`).
- Code pointers in data: translate old function addresses to new ones (from units.json).
  Notes from Phase 1: 447 function addresses are also named as data (`DAT_` on a function);
  those names must resolve to the new function, not the old address. Vtable data in `.rdata`
  is not used once 3d is done (Itanium vtables), but RTTI/vtable pointers stored in static
  data still need translating.
- IAT slots (208, 0x00fdf000-0x00fdf4a0, 22 named without `__imp_`): fill with platform-layer
  functions or rewrite `__imp_` references to direct calls. `__tls_array` and 3 other
  absolute symbols. 4,202 compiler EH handler addresses and 374 out-of-scope functions are
  referenced from in-scope code: EH is regenerated by Clang; out-of-scope functions (CRT,
  helpers such as `__ftol2_sse`) must be provided by Phase 5.

## Phase 5: Platform layer (status: not started)

Win32 shim over POSIX (threads, critical sections, Interlocked*, TLS, VirtualAlloc/HeapAlloc,
FindFirstFile, registry, message pump), DXVK Native (32-bit d3d9; replaces the shim's d3d9.h
subset), SDL3 (window, input, gamepad, audio output), DirectSound shim, D3DX9 subset, Bink via
FFmpeg libavcodec, Steamworks stub, case-insensitive file system accepting backslash paths,
config and saves under XDG directories. Inputs from Phase 1: the 263 imported API names; the
out-of-scope functions above; MSVC CRT extensions declared in `shim/include/fnv_prelude.h`;
out-of-line definitions of the shim's SSE intrinsics (units that redeclare them call them as
external functions); a TEB for `__readfsdword` (38 occurrences); SEH.

Decided: SSE2 floating point (`-msse2 -mfpmath=sse`). The original computes with x87 (MSVC
2008, no `/arch`); the port computes scalar float/double math in SSE registers, so results can
differ in the last bits from the original (no 80-bit intermediates, no dependence on the x87
precision-control word that D3D9 sets). Code that reads or sets the x87 control word
(`_controlfp`, `fldcw` in inline asm) needs review in Phase 5/6; MXCSR (`_mm_setcsr`) is now
the live control register. Float/double return values still come back in ST0 (i386 SysV ABI),
as on MSVC.

## Phase 6: First link and boot (status: not started)

First full link; then boot to main menu; then in-game.

## Phase 7: Player-facing build (status: not started)

`build.sh "/path/to/Fallout New Vegas"` with dependency checks for CachyOS/Arch (`lib32-*`,
`clang`, `lld`, `mingw-w64-headers` if needed, libclang for the transforms).
