# fnv-linux: working notes for Claude sessions

A native Linux port of Fallout: New Vegas built from the byte-matching decompilation
[fnv_decomp](https://github.com/momusdigital/fnv_decomp), pinned in `upstream.pin`.
This repo holds only the port's tools, source transforms and platform code.
Read `PLAN.md` for the roadmap and `STATUS.md` for the latest numbers before starting work.

## Hard rules

- Never commit or print game executables, bytes from them, extracted data, object files built
  from the exe, game assets, or upstream source files. `upstream/`, `work/`, `out/`, `build/`
  and `extracted/` are gitignored; keep generated reports there unless they contain only
  addresses, names, counts and our own text (report summaries in `STATUS.md` are fine;
  verbatim upstream source lines are not).
- Never add anything that decrypts, unpacks or bypasses the Steam DRM wrapper. The data
  extractor reads only unencrypted data sections and fails cleanly with a clear message if the
  exe does not pass upstream's fingerprint check (`build/image_check.json`). The DRM-free GOG
  release is the recommended source; whether its exe passes the fingerprints is untested.
- Never modify the upstream checkout in place. Transforms write to a separate working tree
  (`work/`). `scripts/fetch-upstream.sh` refuses to proceed if the checkout is dirty.
- Cloud sessions have no copy of the game. Anything that needs the exe takes it as a path
  argument and is tested with small synthetic PE fixtures.
- Don't open PRs or issues on fnv_decomp.
- Python 3.10+, standard library unless a dependency clearly earns its place; pytest for tests.
- Small commits with clear messages; keep `STATUS.md` current.

## Upstream facts (pinned commit 91e1b6e8)

- Byte-matching decompilation of the Steam PC exe v1.4.0.525: 2,989 translation units under
  `src/` (plus `third_party/zlib-1.2.1`), ~3.9M lines, 70,611 in-scope functions match. Includes
  statically linked Gamebryo, Havok, SpeedTree, FaceGen, zlib and some MSVC CRT functions.
  Building it yields object files to compare, not a game. Upstream compiles each unit with
  MSVC 2008 (SP1/RTM) or 2005 and the Windows SDK 6.0A headers, plus `/I include`.
- `build/units.json`: `units[]` with `source`, `compiler` (`sp1`/`rtm`/`vc8`), `flags` (MSVC),
  `functions[]` (`address`, decorated `symbol`, `size`, optional `fold_aliases`), `symbols`
  (decorated name -> original address), `eh_tails`, `literal_symbols`. Function definitions in
  source carry `// @fnv 0xADDR` tags.
- Linking is by original address, not by name: the same address is referenced under many
  names; ~30,000 `extern DAT_xxxxxxxx` globals are never defined (initial data is deliberately
  not in the repo). Imports appear as `__imp__Name@N` bound to IAT slot addresses.
- Types are per-unit views: many separate definitions of the same class (e.g. 27 of
  `TESForm`), placeholder virtuals (`v000()`, `vf41`), raw-offset field access, the same vtable
  address referenced under different `??_7...@@6B@` names.
- The code leans on 32-bit MSVC ABI coincidences (e.g. a function called as a `__thiscall`
  member but defined as a `__fastcall` free function; both take arg 1 in ECX under MSVC).
  Clang on i686 Linux passes `this` on the stack and uses the Itanium vtable layout, so these
  break silently.
- Upstream relies on MSVC-only behaviour the port must reproduce or transform: forward-declared
  enums as complete types, `__if_exists`, no two-phase lookup, `#define _INCLUDED_MM2` to keep
  MSVC's `xmmintrin.h` out, its own `__m128` unions, `__declspec(align)` under `#pragma pack`.
- Upstream's fingerprint check hashes a few `.text` functions. The Steam exe as installed has
  encrypted code, so it fails the check by design; only a plain (DRM-free) exe can pass.

## Architecture (decided)

- Distribution: nothing from upstream or the game is shipped. On the player's machine:
  fetch fnv_decomp at the pinned commit -> check and extract data from the player's exe ->
  apply automated transforms (the vtable unification uses the extracted vftables) -> compile ->
  link.
- Target: 32-bit x86 Linux (i686), Clang with
  `--target=i686-linux-gnu -fms-extensions -fms-compatibility -fasm-blocks -malign-double`
  (upstream's size `static_assert`s catch layout differences). 64-bit is out of scope.
- Source changes are transforms, not diffs: keyed on `@fnv` address tags and `units.json`, never
  on names (upstream renames constantly). Use Clang tooling (libclang / AST JSON) where semantics
  matter; avoid fragile regex.
- Data: original `.data/.rdata/.bss` loaded at their original virtual addresses (fixed non-PIE
  layout via linker script; new code well above, e.g. 0x10000000+). Each data symbol defined at
  its original address. Data->code pointers translated with the old->new function address table
  from units.json; data->data pointers stay valid.
- Vtables: use compiler-generated Itanium vtables, so constructors storing an original vtable
  address are rewritten. Needs one agreed class definition per vtable: the central hard problem.
  The local build may read the original vftable contents (slot -> function address) from the
  player's exe `.rdata` (after the fingerprint check) as ground truth for the unification;
  extraction therefore runs before the transforms. Never commit or print that data.
- Floating point: SSE2 (`-msse2 -mfpmath=sse`), not x87. Results may differ from the original
  in the last bits; accepted.
- Platform: DXVK Native (32-bit) for d3d9, SDL3 for window/input/gamepad/audio output,
  DirectSound shim, FFmpeg libavcodec for Bink, a D3DX9 subset implemented here, Steamworks
  stub, Win32 shim over POSIX; case-insensitive file access accepting backslash paths.
- Player's test machine: CachyOS (Arch), x86-64, NVIDIA; 32-bit deps from `lib32-*` packages.

## Repo layout and tools

- `upstream.pin`, `scripts/fetch-upstream.sh`: pinned upstream fetch into `upstream/fnv_decomp`.
- `tools/common/`: `msvc_demangle.py` (structured MSVC demangler; renders exactly like
  llvm-undname), `units.py` (units.json model), `source_index.py` (@fnv tags, line lookup),
  `undname.py` (llvm-undname batch wrapper).
- `tools/analyze/` (Phase 1, `python3 -m tools.analyze --jobs 4 [steps]`): `addresses.py`
  (address kinds, alias map, ld fragments), `abi.py` (argument-location model, MSVC vs i686
  Linux), `conventions.py`, `data.py`, `vtables.py` + `vtable_ast.py` (libclang views, MSVC
  vftable layout). Output: `out/analyze/`.
- `tools/compile_probe/` (Phase 2, `python3 -m tools.compile_probe [--mode obj] [--recategorize]`):
  flags in `BASE_FLAGS`/`DEFAULT_STD`, `categories.py` (root causes), `export.py` (writes
  `status/`). Output: `out/compile_probe/`.
- `shim/include/`: Windows/MSVC header shim for Clang on Linux, grown only from errors:
  `fnv_prelude.h` (forced include: MSVC macros, SAL, CRT extensions, yvals macros),
  `windows.h`, `d3d9.h` (subset; DXVK Native replaces it in Phase 5), MSVC-shaped
  `mmintrin.h`/`xmmintrin.h`/`emmintrin.h`/`intrin.h` (union `__m128`, intrinsics as
  functions, MSVC include guards), `mm_malloc.h`, `crtdefs.h`, `commctrl.h`.
- `status/`: committed per-unit compile results (paths, counts, categories only).
- `tests/`: pytest; synthetic fixtures only. `pytest -q` from the repo root.

## Compile flags (Phase 2)

`--target=i686-linux-gnu -fms-extensions -fms-compatibility -fasm-blocks -malign-double
-fms-compatibility-version=19.00 -mlong-double-64 -fdelayed-template-parsing -msse2
-mfpmath=sse -std=gnu++14 -include shim/include/fnv_prelude.h -isystem shim/include
-I upstream/include`. Why each extra flag is there: `STATUS.md`. The shim's `xmmintrin.h`
requires SSE2.

## Environment notes

- Cloud container: Ubuntu 24.04, clang 18. `apt-get install gcc-multilib g++-multilib
  python3-clang-18` gives i686 headers and the libclang bindings (in
  `/usr/lib/python3/dist-packages`; `tools/analyze/vtable_ast.py` finds them). `llvm-undname`
  is on PATH. `/usr/bin/time` is absent.
- Never pipe a long-running tool into `head`: SIGPIPE kills it mid-run. Redirect to a log.
- Full runs: analyze ~1 min (`--no-locations` faster), compile probe ~45 s (syntax) / ~1 min
  (obj) with 4 jobs.
