/* xmmintrin.h - MSVC-shaped SSE intrinsics for fnv-linux (shadows Clang's header).
 *
 * MSVC (cl 15.00) declares __m128 as a 16-byte-aligned union with named members
 * (m128_f32[4], m128_u32[4], ...) and declares the intrinsics as functions. fnv_decomp relies
 * on that: it accesses the members directly, forward-declares `union __m128`, and some units
 * declare their own __m128 and intrinsic prototypes, guarding the system header with
 * __if_not_exists(__m128). Clang's header uses a vector typedef and defines several intrinsics
 * as macros, which breaks all three. This header keeps MSVC's shapes:
 *   - __m128 is a union whose first member is m128_f32 (so brace initialisers match MSVC);
 *   - every intrinsic is a function with C linkage and no macro, so units may redeclare it;
 *   - semantics follow the instructions: comparisons and min/max use SSE's NaN rules,
 *     rsqrt/rcp use the hardware approximations, so results match the original game.
 * Only the intrinsics fnv_decomp uses are provided. */
#ifndef _INCLUDED_MM2 /* MSVC's own guard: upstream defines it to keep this header out */
#define _INCLUDED_MM2

#include <mmintrin.h>

typedef float __fnv_v4sf __attribute__((__vector_size__(16)));

typedef union __attribute__((__aligned__(16))) __m128 {
    float m128_f32[4];
    unsigned long long m128_u64[2];
    signed char m128_i8[16];
    short m128_i16[8];
    int m128_i32[4];
    long long m128_i64[2];
    unsigned char m128_u8[16];
    unsigned short m128_u16[8];
    unsigned int m128_u32[4];
    __fnv_v4sf __fnv_v; /* not in MSVC; used by this header only */
} __m128;

#define _MM_SHUFFLE(fp3, fp2, fp1, fp0) (((fp3) << 6) | ((fp2) << 4) | ((fp1) << 2) | (fp0))
#define _MM_TRANSPOSE4_PS(row0, row1, row2, row3) \
    do { \
        __m128 _t0 = _mm_shuffle_ps((row0), (row1), 0x44), _t2 = _mm_shuffle_ps((row0), (row1), 0xEE); \
        __m128 _t1 = _mm_shuffle_ps((row2), (row3), 0x44), _t3 = _mm_shuffle_ps((row2), (row3), 0xEE); \
        (row0) = _mm_shuffle_ps(_t0, _t1, 0x88); (row1) = _mm_shuffle_ps(_t0, _t1, 0xDD); \
        (row2) = _mm_shuffle_ps(_t2, _t3, 0x88); (row3) = _mm_shuffle_ps(_t2, _t3, 0xDD); \
    } while (0)
#define _MM_HINT_T0 1
#define _MM_HINT_T1 2
#define _MM_HINT_T2 3
#define _MM_HINT_NTA 0

#define __FNV_PS(expr0, expr1, expr2, expr3) \
    __m128 r; r.m128_f32[0] = (expr0); r.m128_f32[1] = (expr1); r.m128_f32[2] = (expr2); \
    r.m128_f32[3] = (expr3); return r
#define __FNV_PS_LANES(op) __FNV_PS(op(0), op(1), op(2), op(3))
#define __FNV_BITS(op) \
    __m128 r; for (int i = 0; i < 4; ++i) r.m128_u32[i] = (op); return r

/* set / load / store */
__FNV_INTRIN __m128 _mm_setzero_ps(void) { __FNV_PS(0.0f, 0.0f, 0.0f, 0.0f); }
__FNV_INTRIN __m128 _mm_set_ss(float a) { __FNV_PS(a, 0.0f, 0.0f, 0.0f); }
__FNV_INTRIN __m128 _mm_set_ps1(float a) { __FNV_PS(a, a, a, a); }
__FNV_INTRIN __m128 _mm_set1_ps(float a) { __FNV_PS(a, a, a, a); }
__FNV_INTRIN __m128 _mm_set_ps(float z, float y, float x, float w) { __FNV_PS(w, x, y, z); }
__FNV_INTRIN __m128 _mm_setr_ps(float w, float x, float y, float z) { __FNV_PS(w, x, y, z); }
__FNV_INTRIN __m128 _mm_load_ss(const float *p) { __FNV_PS(*p, 0.0f, 0.0f, 0.0f); }
__FNV_INTRIN __m128 _mm_load_ps1(const float *p) { float a = *p; __FNV_PS(a, a, a, a); }
__FNV_INTRIN __m128 _mm_load1_ps(const float *p) { float a = *p; __FNV_PS(a, a, a, a); }
__FNV_INTRIN __m128 _mm_load_ps(const float *p) { return *(const __m128 *)p; }
__FNV_INTRIN __m128 _mm_loadu_ps(const float *p) { __FNV_PS(p[0], p[1], p[2], p[3]); }
__FNV_INTRIN void _mm_store_ss(float *p, __m128 a) { *p = a.m128_f32[0]; }
__FNV_INTRIN void _mm_store_ps(float *p, __m128 a) { *(__m128 *)p = a; }
__FNV_INTRIN void _mm_stream_ps(float *p, __m128 a) { __builtin_nontemporal_store(a.__fnv_v, (__fnv_v4sf *)p); }
__FNV_INTRIN float _mm_cvtss_f32(__m128 a) { return a.m128_f32[0]; }

/* arithmetic */
#define __FNV_A(i) (a.m128_f32[i])
__FNV_INTRIN __m128 _mm_add_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0] + b.m128_f32[0], a.m128_f32[1] + b.m128_f32[1], a.m128_f32[2] + b.m128_f32[2], a.m128_f32[3] + b.m128_f32[3]); }
__FNV_INTRIN __m128 _mm_sub_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0] - b.m128_f32[0], a.m128_f32[1] - b.m128_f32[1], a.m128_f32[2] - b.m128_f32[2], a.m128_f32[3] - b.m128_f32[3]); }
__FNV_INTRIN __m128 _mm_mul_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0] * b.m128_f32[0], a.m128_f32[1] * b.m128_f32[1], a.m128_f32[2] * b.m128_f32[2], a.m128_f32[3] * b.m128_f32[3]); }
__FNV_INTRIN __m128 _mm_div_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0] / b.m128_f32[0], a.m128_f32[1] / b.m128_f32[1], a.m128_f32[2] / b.m128_f32[2], a.m128_f32[3] / b.m128_f32[3]); }
__FNV_INTRIN __m128 _mm_add_ss(__m128 a, __m128 b) { a.m128_f32[0] += b.m128_f32[0]; return a; }
__FNV_INTRIN __m128 _mm_sub_ss(__m128 a, __m128 b) { a.m128_f32[0] -= b.m128_f32[0]; return a; }
__FNV_INTRIN __m128 _mm_mul_ss(__m128 a, __m128 b) { a.m128_f32[0] *= b.m128_f32[0]; return a; }
__FNV_INTRIN __m128 _mm_div_ss(__m128 a, __m128 b) { a.m128_f32[0] /= b.m128_f32[0]; return a; }
__FNV_INTRIN __m128 _mm_sqrt_ps(__m128 a) { __FNV_PS(__builtin_sqrtf(a.m128_f32[0]), __builtin_sqrtf(a.m128_f32[1]), __builtin_sqrtf(a.m128_f32[2]), __builtin_sqrtf(a.m128_f32[3])); }
__FNV_INTRIN __m128 _mm_sqrt_ss(__m128 a) { a.m128_f32[0] = __builtin_sqrtf(a.m128_f32[0]); return a; }
/* Hardware approximations (12-bit), as the original game computes them. These need the SSE
 * instructions; they carry target("sse") and are not force-inlined, so the rest of a unit can
 * stay on the default i686 (x87) code generation. */
#ifdef __cplusplus
#define __FNV_INTRIN_SSE extern "C" inline __attribute__((__target__("sse"), __nodebug__))
#else
#define __FNV_INTRIN_SSE static __inline__ __attribute__((__target__("sse"), __nodebug__))
#endif
__FNV_INTRIN_SSE __m128 _mm_rsqrt_ps(__m128 a) { __m128 r; r.__fnv_v = __builtin_ia32_rsqrtps(a.__fnv_v); return r; }
__FNV_INTRIN_SSE __m128 _mm_rsqrt_ss(__m128 a) { __m128 r; r.__fnv_v = __builtin_ia32_rsqrtss(a.__fnv_v); return r; }
__FNV_INTRIN_SSE __m128 _mm_rcp_ps(__m128 a) { __m128 r; r.__fnv_v = __builtin_ia32_rcpps(a.__fnv_v); return r; }
/* MINPS/MAXPS: the second operand is returned when either is NaN or both are zero. */
__FNV_INTRIN __m128 _mm_min_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0] < b.m128_f32[0] ? a.m128_f32[0] : b.m128_f32[0], a.m128_f32[1] < b.m128_f32[1] ? a.m128_f32[1] : b.m128_f32[1], a.m128_f32[2] < b.m128_f32[2] ? a.m128_f32[2] : b.m128_f32[2], a.m128_f32[3] < b.m128_f32[3] ? a.m128_f32[3] : b.m128_f32[3]); }
__FNV_INTRIN __m128 _mm_max_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0] > b.m128_f32[0] ? a.m128_f32[0] : b.m128_f32[0], a.m128_f32[1] > b.m128_f32[1] ? a.m128_f32[1] : b.m128_f32[1], a.m128_f32[2] > b.m128_f32[2] ? a.m128_f32[2] : b.m128_f32[2], a.m128_f32[3] > b.m128_f32[3] ? a.m128_f32[3] : b.m128_f32[3]); }
#undef __FNV_A

/* bitwise */
__FNV_INTRIN __m128 _mm_and_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_u32[i] & b.m128_u32[i]); }
__FNV_INTRIN __m128 _mm_andnot_ps(__m128 a, __m128 b) { __FNV_BITS(~a.m128_u32[i] & b.m128_u32[i]); }
__FNV_INTRIN __m128 _mm_or_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_u32[i] | b.m128_u32[i]); }
__FNV_INTRIN __m128 _mm_xor_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_u32[i] ^ b.m128_u32[i]); }

/* comparisons: all-ones where true; ordered predicates are false for NaN, as in SSE */
__FNV_INTRIN __m128 _mm_cmpeq_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_f32[i] == b.m128_f32[i] ? 0xFFFFFFFFu : 0u); }
__FNV_INTRIN __m128 _mm_cmplt_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_f32[i] < b.m128_f32[i] ? 0xFFFFFFFFu : 0u); }
__FNV_INTRIN __m128 _mm_cmple_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_f32[i] <= b.m128_f32[i] ? 0xFFFFFFFFu : 0u); }
__FNV_INTRIN __m128 _mm_cmpgt_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_f32[i] > b.m128_f32[i] ? 0xFFFFFFFFu : 0u); }
__FNV_INTRIN __m128 _mm_cmpge_ps(__m128 a, __m128 b) { __FNV_BITS(a.m128_f32[i] >= b.m128_f32[i] ? 0xFFFFFFFFu : 0u); }
__FNV_INTRIN __m128 _mm_cmpeq_ss(__m128 a, __m128 b) { a.m128_u32[0] = a.m128_f32[0] == b.m128_f32[0] ? 0xFFFFFFFFu : 0u; return a; }
__FNV_INTRIN int _mm_movemask_ps(__m128 a)
{
    return (int)((a.m128_u32[0] >> 31) | ((a.m128_u32[1] >> 31) << 1) | ((a.m128_u32[2] >> 31) << 2) |
                 ((a.m128_u32[3] >> 31) << 3));
}

/* shuffles and moves (the immediate need not be a constant) */
__FNV_INTRIN __m128 _mm_shuffle_ps(__m128 a, __m128 b, unsigned int imm)
{
    __FNV_PS(a.m128_f32[imm & 3], a.m128_f32[(imm >> 2) & 3], b.m128_f32[(imm >> 4) & 3], b.m128_f32[(imm >> 6) & 3]);
}
__FNV_INTRIN __m128 _mm_unpacklo_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0], b.m128_f32[0], a.m128_f32[1], b.m128_f32[1]); }
__FNV_INTRIN __m128 _mm_unpackhi_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[2], b.m128_f32[2], a.m128_f32[3], b.m128_f32[3]); }
__FNV_INTRIN __m128 _mm_movelh_ps(__m128 a, __m128 b) { __FNV_PS(a.m128_f32[0], a.m128_f32[1], b.m128_f32[0], b.m128_f32[1]); }
__FNV_INTRIN __m128 _mm_movehl_ps(__m128 a, __m128 b) { __FNV_PS(b.m128_f32[2], b.m128_f32[3], a.m128_f32[2], a.m128_f32[3]); }
__FNV_INTRIN __m128 _mm_move_ss(__m128 a, __m128 b) { a.m128_f32[0] = b.m128_f32[0]; return a; }

/* Clang implements these as library builtins once declared. */
#ifdef __cplusplus
extern "C" {
#endif
void _mm_prefetch(const char *p, int hint);
unsigned int _mm_getcsr(void);
void _mm_setcsr(unsigned int value);
#ifdef __cplusplus
}
#endif

#undef __FNV_PS
#undef __FNV_PS_LANES
#undef __FNV_BITS

#endif /* _INCLUDED_MM2 */
