/* emmintrin.h - MSVC-shaped SSE2 intrinsics for fnv-linux (shadows Clang's header).
 * See xmmintrin.h for why. Only the intrinsics fnv_decomp uses are provided. */
#ifndef _INCLUDED_EMM /* MSVC's own guard: upstream defines it to keep this header out */
#define _INCLUDED_EMM

#include <xmmintrin.h>

typedef union __attribute__((__aligned__(16))) __m128i {
    signed char m128i_i8[16];
    short m128i_i16[8];
    int m128i_i32[4];
    long long m128i_i64[2];
    unsigned char m128i_u8[16];
    unsigned short m128i_u16[8];
    unsigned int m128i_u32[4];
    unsigned long long m128i_u64[2];
} __m128i;

typedef struct __attribute__((__aligned__(16))) __m128d {
    double m128d_f64[2];
} __m128d;

__FNV_INTRIN __m128i _mm_setzero_si128(void) { __m128i r; r.m128i_u64[0] = r.m128i_u64[1] = 0; return r; }
__FNV_INTRIN __m128i _mm_set1_epi16(short w) { __m128i r; for (int i = 0; i < 8; ++i) r.m128i_i16[i] = w; return r; }
__FNV_INTRIN __m128i _mm_cvtsi32_si128(int a) { __m128i r = _mm_setzero_si128(); r.m128i_i32[0] = a; return r; }
__FNV_INTRIN __m128i _mm_load_si128(const __m128i *p) { return *p; }
__FNV_INTRIN __m128i _mm_loadu_si128(const __m128i *p) { __m128i r; __builtin_memcpy(&r, p, sizeof r); return r; }
__FNV_INTRIN __m128 _mm_castsi128_ps(__m128i a) { __m128 r; __builtin_memcpy(&r, &a, sizeof r); return r; }
__FNV_INTRIN __m128 _mm_cvtepi32_ps(__m128i a)
{
    __m128 r;
    for (int i = 0; i < 4; ++i) r.m128_f32[i] = (float)a.m128i_i32[i];
    return r;
}
__FNV_INTRIN __m128i _mm_srli_epi32(__m128i a, int count)
{
    for (int i = 0; i < 4; ++i) a.m128i_u32[i] = (unsigned)count > 31 ? 0 : a.m128i_u32[i] >> count;
    return a;
}
__FNV_INTRIN __m128i _mm_slli_epi32(__m128i a, int count)
{
    for (int i = 0; i < 4; ++i) a.m128i_u32[i] = (unsigned)count > 31 ? 0 : a.m128i_u32[i] << count;
    return a;
}
__FNV_INTRIN __m128i _mm_unpacklo_epi16(__m128i a, __m128i b)
{
    __m128i r;
    for (int i = 0; i < 4; ++i) { r.m128i_i16[2 * i] = a.m128i_i16[i]; r.m128i_i16[2 * i + 1] = b.m128i_i16[i]; }
    return r;
}
__FNV_INTRIN __m128i _mm_unpackhi_epi16(__m128i a, __m128i b)
{
    __m128i r;
    for (int i = 0; i < 4; ++i) { r.m128i_i16[2 * i] = a.m128i_i16[4 + i]; r.m128i_i16[2 * i + 1] = b.m128i_i16[4 + i]; }
    return r;
}
__FNV_INTRIN __m128i _mm_adds_epu16(__m128i a, __m128i b)
{
    for (int i = 0; i < 8; ++i) {
        unsigned s = (unsigned)a.m128i_u16[i] + b.m128i_u16[i];
        a.m128i_u16[i] = (unsigned short)(s > 0xFFFF ? 0xFFFF : s);
    }
    return a;
}

#endif /* _INCLUDED_EMM */
