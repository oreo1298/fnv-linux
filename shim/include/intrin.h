/* intrin.h - the MSVC compiler intrinsics fnv_decomp uses (fnv-linux shim; shadows Clang's
 * header, which on a non-Windows target would pull in its vector-typed SSE headers). */
#ifndef __INTRIN_H_ /* MSVC's own guard: upstream defines it to keep this header out */
#define __INTRIN_H_

#include <emmintrin.h>

#ifdef __cplusplus
extern "C" {
#endif
/* Recognised by Clang as builtins under -fms-extensions once declared. */
void __cdecl __debugbreak(void);
void _ReadWriteBarrier(void);
unsigned short __cdecl _byteswap_ushort(unsigned short value);
unsigned long __cdecl _byteswap_ulong(unsigned long value);
unsigned int __cdecl _rotl(unsigned int value, int shift);
/* fs:[offset] reads the Windows TEB. On i686 Linux FS is not set up: the platform layer
 * (Phase 5) must provide a TEB or these call sites must be transformed. */
unsigned long __readfsdword(unsigned long offset);
unsigned __int64 __rdtsc(void);
#ifdef __cplusplus
}
#endif

#endif /* __INTRIN_H_ */
