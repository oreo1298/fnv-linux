/* crtdefs.h - MSVC CRT base definitions (fnv-linux shim, grown from compile errors). */
#ifndef FNV_SHIM_CRTDEFS_H
#define FNV_SHIM_CRTDEFS_H
#include <stddef.h>
#include <stdint.h>

#ifndef _CRTIMP
#define _CRTIMP
#endif
#ifndef _CRTNOALIAS
#define _CRTNOALIAS
#endif
#ifndef _CRTRESTRICT
#define _CRTRESTRICT
#endif
typedef int errno_t;
typedef size_t rsize_t;
#endif
