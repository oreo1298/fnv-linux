/* mmintrin.h - MSVC-shaped MMX intrinsics for fnv-linux (shadows Clang's header).
 *
 * MSVC declares __m64 as a union with named members and the intrinsics as functions;
 * fnv_decomp relies on both (member access such as m64_i16[i], and units that declare
 * intrinsics themselves). Clang's own header uses vector types and macros instead.
 * The intrinsics here are element-wise and touch no MMX registers, so _mm_empty is a no-op.
 * Only the intrinsics fnv_decomp uses are provided. */
#ifndef _MMINTRIN_H_INCLUDED /* MSVC's own guard: upstream defines it to keep this header out */
#define _MMINTRIN_H_INCLUDED

typedef union __attribute__((__aligned__(8))) __m64 {
    unsigned long long m64_u64;
    float m64_f32[2];
    signed char m64_i8[8];
    short m64_i16[4];
    int m64_i32[2];
    long long m64_i64;
    unsigned char m64_u8[8];
    unsigned short m64_u16[4];
    unsigned int m64_u32[2];
} __m64;

#ifdef __cplusplus
#define __FNV_INTRIN extern "C" inline __attribute__((__always_inline__, __nodebug__))
#else
#define __FNV_INTRIN static __inline__ __attribute__((__always_inline__, __nodebug__))
#endif

__FNV_INTRIN void _mm_empty(void) {}

__FNV_INTRIN __m64 _mm_setzero_si64(void) { __m64 r; r.m64_u64 = 0; return r; }

__FNV_INTRIN __m64 _mm_set_pi32(int i1, int i0) { __m64 r; r.m64_i32[0] = i0; r.m64_i32[1] = i1; return r; }

__FNV_INTRIN __m64 _mm_and_si64(__m64 a, __m64 b) { __m64 r; r.m64_u64 = a.m64_u64 & b.m64_u64; return r; }

__FNV_INTRIN __m64 _mm_add_pi16(__m64 a, __m64 b)
{
    __m64 r;
    for (int i = 0; i < 4; ++i) r.m64_u16[i] = (unsigned short)(a.m64_u16[i] + b.m64_u16[i]);
    return r;
}

__FNV_INTRIN __m64 _mm_sub_pi16(__m64 a, __m64 b)
{
    __m64 r;
    for (int i = 0; i < 4; ++i) r.m64_u16[i] = (unsigned short)(a.m64_u16[i] - b.m64_u16[i]);
    return r;
}

__FNV_INTRIN __m64 _mm_cmpgt_pi16(__m64 a, __m64 b)
{
    __m64 r;
    for (int i = 0; i < 4; ++i) r.m64_i16[i] = a.m64_i16[i] > b.m64_i16[i] ? -1 : 0;
    return r;
}

__FNV_INTRIN __m64 _mm_cmpeq_pi16(__m64 a, __m64 b)
{
    __m64 r;
    for (int i = 0; i < 4; ++i) r.m64_i16[i] = a.m64_i16[i] == b.m64_i16[i] ? -1 : 0;
    return r;
}

__FNV_INTRIN __m64 _mm_srli_si64(__m64 a, int count)
{
    __m64 r;
    r.m64_u64 = (unsigned)count > 63 ? 0 : a.m64_u64 >> count;
    return r;
}

__FNV_INTRIN __m64 _mm_srli_pi16(__m64 a, int count)
{
    __m64 r;
    for (int i = 0; i < 4; ++i) r.m64_u16[i] = (unsigned)count > 15 ? 0 : (unsigned short)(a.m64_u16[i] >> count);
    return r;
}

__FNV_INTRIN __m64 _mm_slli_pi16(__m64 a, int count)
{
    __m64 r;
    for (int i = 0; i < 4; ++i) r.m64_u16[i] = (unsigned)count > 15 ? 0 : (unsigned short)(a.m64_u16[i] << count);
    return r;
}

__FNV_INTRIN __m64 _mm_unpacklo_pi16(__m64 a, __m64 b)
{
    __m64 r;
    r.m64_i16[0] = a.m64_i16[0]; r.m64_i16[1] = b.m64_i16[0];
    r.m64_i16[2] = a.m64_i16[1]; r.m64_i16[3] = b.m64_i16[1];
    return r;
}

__FNV_INTRIN __m64 _mm_unpacklo_pi32(__m64 a, __m64 b)
{
    __m64 r;
    r.m64_i32[0] = a.m64_i32[0]; r.m64_i32[1] = b.m64_i32[0];
    return r;
}

#endif /* _MMINTRIN_H_INCLUDED */
