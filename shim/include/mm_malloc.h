/* mm_malloc.h - replaces Clang's version. MSVC's <xmmintrin.h> takes _mm_malloc from <malloc.h>
 * as _aligned_malloc and does not pull in <stdlib.h>. Clang's version includes <stdlib.h>, which
 * breaks units that include <xmmintrin.h> inside __if_not_exists(__m128) { ... }: the
 * preprocessor expands the include, the parser skips the block, and glibc's include guards are
 * left set with nothing declared. (fnv-linux shim) */
#ifndef __MM_MALLOC_H
#define __MM_MALLOC_H
#define _mm_malloc(size, align) _aligned_malloc((size), (align))
#define _mm_free(p) _aligned_free(p)
#endif
