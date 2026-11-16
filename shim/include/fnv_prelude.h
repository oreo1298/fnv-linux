/* fnv_prelude.h - forced include (-include) for compiling fnv_decomp units with Clang on
 * i686 Linux. Predefines what MSVC 2008 (cl 15.00) predefines for a 32-bit Windows build,
 * so upstream takes the same preprocessor paths as in its matching build.
 * Part of the fnv-linux header shim: only what compile errors showed to be needed. */
#ifndef FNV_PRELUDE_H
#define FNV_PRELUDE_H

#define _MSC_VER 1500
#define _MSC_FULL_VER 150030729
#define _MSC_EXTENSIONS 1
#define _WIN32 1
#define _M_IX86 600
#define _INTEGRAL_MAX_BITS 64
#ifdef __cplusplus
#define _NATIVE_WCHAR_T_DEFINED 1
#define _WCHAR_T_DEFINED 1
#endif

/* -fms-compatibility drops __GNUC__ (which we keep undefined, since upstream tests it), and
 * glibc's <string.h> C++ overloads then miss these two macros when __OPTIMIZE__ is set. */
#if !defined(__GNUC__) && !defined(__extern_always_inline)
#define __extern_inline extern __inline __attribute__((__gnu_inline__))
#define __extern_always_inline extern __inline __attribute__((__always_inline__, __gnu_inline__))
#endif

/* With _WIN32 defined, Clang's <mm_malloc.h> calls the MSVC CRT's aligned allocator. */
#ifdef __cplusplus
extern "C" {
#endif
void *__cdecl _aligned_malloc(__SIZE_TYPE__ size, __SIZE_TYPE__ alignment);
void __cdecl _aligned_free(void *block);
#ifdef __cplusplus
}
#endif

/* SAL annotations (sal.h) are empty for the compiler. */
#define _In_
#define _In_opt_
#define _Out_
#define _Out_opt_
#define _Inout_
#define _Inout_opt_
#define _In_z_
#define _Printf_format_string_

/* MSVC names the stdio FILE structure _iobuf; glibc names it _IO_FILE. */
#define _iobuf _IO_FILE

/* MSVC CRT extensions that MSVC declares in standard headers. Implemented by the platform
 * layer (Phase 5). */
#ifdef __cplusplus
extern "C" {
#endif
typedef int errno_t;
errno_t __cdecl strcpy_s(char *dst, __SIZE_TYPE__ size, const char *src);
errno_t __cdecl strncpy_s(char *dst, __SIZE_TYPE__ size, const char *src, __SIZE_TYPE__ count);
errno_t __cdecl strcat_s(char *dst, __SIZE_TYPE__ size, const char *src);
int __cdecl sprintf_s(char *dst, __SIZE_TYPE__ size, const char *format, ...);
int __cdecl vsprintf_s(char *dst, __SIZE_TYPE__ size, const char *format, __builtin_va_list args);
char *__cdecl _gcvt(double value, int digits, char *buffer);
char *__cdecl strtok_s(char *str, const char *delimiters, char **context);
errno_t __cdecl memmove_s(void *dst, __SIZE_TYPE__ size, const void *src, __SIZE_TYPE__ count);
int __cdecl _snprintf(char *dst, __SIZE_TYPE__ count, const char *format, ...);
__SIZE_TYPE__ __cdecl _msize(void *block);
errno_t __cdecl memcpy_s(void *dst, __SIZE_TYPE__ size, const void *src, __SIZE_TYPE__ count);
int __cdecl _finite(double x);
struct _IO_FILE;
errno_t __cdecl fopen_s(struct _IO_FILE **file, const char *name, const char *mode);
int __cdecl _fclose_nolock(struct _IO_FILE *file);
unsigned long __cdecl _byteswap_ulong(unsigned long value);
#ifdef __cplusplus
}
/* MSVC's secure-CRT template overloads for arrays. */
template <__SIZE_TYPE__ N> inline errno_t strcpy_s(char (&dst)[N], const char *src) { return strcpy_s(dst, N, src); }
template <__SIZE_TYPE__ N> inline errno_t strcat_s(char (&dst)[N], const char *src) { return strcat_s(dst, N, src); }
template <__SIZE_TYPE__ N> inline errno_t strncpy_s(char (&dst)[N], const char *src, __SIZE_TYPE__ n) { return strncpy_s(dst, N, src, n); }
template <__SIZE_TYPE__ N> inline int sprintf_s(char (&dst)[N], const char *format, ...)
{
    __builtin_va_list args;
    __builtin_va_start(args, format);
    int r = vsprintf_s(dst, N, format, args);
    __builtin_va_end(args);
    return r;
}
#endif

/* MSVC STL helper macros (<yvals.h>) that upstream code uses directly. */
#define _TRY_BEGIN try {
#define _CATCH(x) } catch (x) {
#define _CATCH_ALL } catch (...) {
#define _CATCH_END }
#define _RAISE(x) throw x
#define _RERAISE throw
#define _STDEXT_BEGIN namespace stdext {
#define _STDEXT_END }
#define _STDEXT ::stdext::
#define _STD_BEGIN namespace std {
#define _STD_END }
#define _STD ::std::

/* libstdc++ expects this GCC macro, which -fms-compatibility does not predefine. */
#ifndef __GCC_ATOMIC_TEST_AND_SET_TRUEVAL
#define __GCC_ATOMIC_TEST_AND_SET_TRUEVAL 1
#endif

#endif /* FNV_PRELUDE_H */
