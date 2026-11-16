# Roadmap

Status key: `done`, `in progress`, `not started`, `blocked`.

The port is built entirely on the player's machine: fetch fnv_decomp at the pinned commit,
apply automated transforms into a separate working tree, extract data from the player's own
exe, compile for i686 Linux with Clang, and link with a fixed-address linker layout. This repo
ships only tools, transforms and platform code. See `CLAUDE.md` for the hard rules.

## Phase 0: Scaffold (status: in progress)

- `PLAN.md`, `CLAUDE.md`, `STATUS.md`, `.gitignore`.
- `upstream.pin` + `scripts/fetch-upstream.sh`: clone fnv_decomp at the pinned commit into
  `upstream/fnv_decomp` (gitignored); refuse to continue if the checkout is dirty.
- Python 3.10+ standard library; pytest.

## Phase 1: Linkage and ABI analysis, `tools/analyze` (status: not started)

No game needed. Inputs: `build/units.json` and the source tree.

1. Alias map: per original address, the defining symbol and every other name that references
   it. Emits a GNU ld script fragment / `--defsym` list for later link phases.
2. Calling-convention mismatch report, decoded from MSVC decorated names. Classes: name-only
   alias, thiscall<->fastcall, member<->free, other convention conflicts, parameter-list
   differences. Counts plus a full CSV with unit and source line of each reference.
3. Vtable report: every name and unit referencing each vtable address; per-unit virtual method
   lists (Clang AST) with slot-count and virtual-destructor-position disagreements.
4. Data report: every referenced non-function address, classified as vtable, RTTI, string
   literal, import slot, or plain global.

## Phase 2: i686 compile baseline, `tools/compile_probe` (status: not started)

- 32-bit system headers (gcc-multilib/g++-multilib).
- Minimal Windows/MSVC header shim in `shim/include`, grown only as errors demand.
- Every unit with `-fsyntax-only`, then `-c`, in parallel. Per-unit results and an error
  histogram in `STATUS.md`. No upstream fixes in this phase.

## Phase 3: Transforms (status: not started)

Source-to-source transforms from `upstream/` into `work/`, keyed on `@fnv` addresses and
units.json, implemented with Clang tooling:

- Fix calling-convention mismatches (thiscall<->fastcall, member<->free) at definitions or at
  references so every address has one ABI on Linux.
- MSVC-only constructs: forward-declared enums without an underlying type, convention
  redeclarations, MS inline asm Clang rejects, other leniencies the Phase 2 histogram shows.
- Unify class definitions for every class with a vtable: one agreed definition per vtable
  address, with per-unit views reduced to that definition.

## Phase 4: Data extractor, linker layout, code-pointer translation (status: not started)

- Extractor: reads only unencrypted `.data/.rdata/.bss` from the player's exe, after
  upstream's fingerprint check; fails cleanly otherwise. Synthetic PE fixtures here; real runs
  on the player's machine. Note: the fingerprints hash `.text` bytes, and upstream says the
  Steam exe's code is encrypted on disk, so a Steam install fails the check by design. The
  DRM-free GOG release is the recommended source (untested whether it passes).
- Linker script: original sections at original VAs (non-PIE), new code at 0x10000000+.
- Data symbol definitions at original addresses; data->code pointer translation table from
  units.json (old address -> new symbol); data->data pointers unchanged.

## Phase 5: Platform layer (status: not started)

Win32 shim over POSIX (threads, critical sections, Interlocked*, TLS, VirtualAlloc/HeapAlloc,
FindFirstFile, registry, message pump), DXVK Native (32-bit d3d9), SDL3 (window, input,
gamepad, audio output), DirectSound shim, D3DX9 subset, Bink via FFmpeg libavcodec, Steamworks
stub, case-insensitive file system accepting backslash paths, config and saves under XDG
directories.

## Phase 6: First link and boot (status: not started)

First full link; then boot to main menu; then in-game.

## Phase 7: Player-facing build (status: not started)

`build.sh "/path/to/Fallout New Vegas"` with dependency checks for CachyOS/Arch (`lib32-*`).
