/* d3d9.h - the subset of Direct3D 9 declarations fnv_decomp units use by name (fnv-linux shim,
 * grown from compile errors). Upstream mostly declares its own D3D stand-ins, so interfaces are
 * left incomplete here. Phase 5 replaces this with DXVK Native's d3d9.h. */
#ifndef FNV_SHIM_D3D9_H
#define FNV_SHIM_D3D9_H
#include <windows.h>

#ifndef MAKEFOURCC
#define MAKEFOURCC(a, b, c, d) \
    ((DWORD)(BYTE)(a) | ((DWORD)(BYTE)(b) << 8) | ((DWORD)(BYTE)(c) << 16) | ((DWORD)(BYTE)(d) << 24))
#endif

typedef DWORD D3DCOLOR;

typedef struct _D3DVECTOR { float x, y, z; } D3DVECTOR;

typedef struct _D3DMATRIX {
    union {
        struct {
            float _11, _12, _13, _14;
            float _21, _22, _23, _24;
            float _31, _32, _33, _34;
            float _41, _42, _43, _44;
        };
        float m[4][4];
    };
} D3DMATRIX;

typedef enum _D3DFORMAT {
    D3DFMT_UNKNOWN = 0,
    D3DFMT_R8G8B8 = 20, D3DFMT_A8R8G8B8 = 21, D3DFMT_X8R8G8B8 = 22, D3DFMT_R5G6B5 = 23,
    D3DFMT_X1R5G5B5 = 24, D3DFMT_A1R5G5B5 = 25, D3DFMT_A4R4G4B4 = 26, D3DFMT_R3G3B2 = 27,
    D3DFMT_A8 = 28, D3DFMT_A8R3G3B2 = 29, D3DFMT_X4R4G4B4 = 30, D3DFMT_A2B10G10R10 = 31,
    D3DFMT_A8B8G8R8 = 32, D3DFMT_X8B8G8R8 = 33, D3DFMT_G16R16 = 34, D3DFMT_A2R10G10B10 = 35,
    D3DFMT_A16B16G16R16 = 36, D3DFMT_A8P8 = 40, D3DFMT_P8 = 41, D3DFMT_L8 = 50, D3DFMT_A8L8 = 51,
    D3DFMT_A4L4 = 52, D3DFMT_V8U8 = 60, D3DFMT_L6V5U5 = 61, D3DFMT_X8L8V8U8 = 62, D3DFMT_Q8W8V8U8 = 63,
    D3DFMT_V16U16 = 64, D3DFMT_A2W10V10U10 = 67,
    D3DFMT_UYVY = MAKEFOURCC('U', 'Y', 'V', 'Y'), D3DFMT_R8G8_B8G8 = MAKEFOURCC('R', 'G', 'B', 'G'),
    D3DFMT_YUY2 = MAKEFOURCC('Y', 'U', 'Y', '2'), D3DFMT_G8R8_G8B8 = MAKEFOURCC('G', 'R', 'G', 'B'),
    D3DFMT_DXT1 = MAKEFOURCC('D', 'X', 'T', '1'), D3DFMT_DXT2 = MAKEFOURCC('D', 'X', 'T', '2'),
    D3DFMT_DXT3 = MAKEFOURCC('D', 'X', 'T', '3'), D3DFMT_DXT4 = MAKEFOURCC('D', 'X', 'T', '4'),
    D3DFMT_DXT5 = MAKEFOURCC('D', 'X', 'T', '5'),
    D3DFMT_D16_LOCKABLE = 70, D3DFMT_D32 = 71, D3DFMT_D15S1 = 73, D3DFMT_D24S8 = 75, D3DFMT_D24X8 = 77,
    D3DFMT_D24X4S4 = 79, D3DFMT_D16 = 80, D3DFMT_D32F_LOCKABLE = 82, D3DFMT_D24FS8 = 83,
    D3DFMT_D32_LOCKABLE = 84, D3DFMT_S8_LOCKABLE = 85, D3DFMT_L16 = 81,
    D3DFMT_VERTEXDATA = 100, D3DFMT_INDEX16 = 101, D3DFMT_INDEX32 = 102, D3DFMT_Q16W16V16U16 = 110,
    D3DFMT_MULTI2_ARGB8 = MAKEFOURCC('M', 'E', 'T', '1'),
    D3DFMT_R16F = 111, D3DFMT_G16R16F = 112, D3DFMT_A16B16G16R16F = 113, D3DFMT_R32F = 114,
    D3DFMT_G32R32F = 115, D3DFMT_A32B32G32R32F = 116, D3DFMT_CxV8U8 = 117,
    D3DFMT_A1 = 118, D3DFMT_A2B10G10R10_XR_BIAS = 119, D3DFMT_BINARYBUFFER = 199,
    D3DFMT_FORCE_DWORD = 0x7fffffff
} D3DFORMAT;

typedef enum _D3DPOOL {
    D3DPOOL_DEFAULT = 0, D3DPOOL_MANAGED = 1, D3DPOOL_SYSTEMMEM = 2, D3DPOOL_SCRATCH = 3,
    D3DPOOL_FORCE_DWORD = 0x7fffffff
} D3DPOOL;

typedef enum _D3DDEVTYPE {
    D3DDEVTYPE_HAL = 1, D3DDEVTYPE_REF = 2, D3DDEVTYPE_SW = 3, D3DDEVTYPE_NULLREF = 4,
    D3DDEVTYPE_FORCE_DWORD = 0x7fffffff
} D3DDEVTYPE;

typedef enum _D3DMULTISAMPLE_TYPE {
    D3DMULTISAMPLE_NONE = 0, D3DMULTISAMPLE_NONMASKABLE = 1, D3DMULTISAMPLE_2_SAMPLES = 2,
    D3DMULTISAMPLE_3_SAMPLES = 3, D3DMULTISAMPLE_4_SAMPLES = 4, D3DMULTISAMPLE_5_SAMPLES = 5,
    D3DMULTISAMPLE_6_SAMPLES = 6, D3DMULTISAMPLE_7_SAMPLES = 7, D3DMULTISAMPLE_8_SAMPLES = 8,
    D3DMULTISAMPLE_9_SAMPLES = 9, D3DMULTISAMPLE_10_SAMPLES = 10, D3DMULTISAMPLE_11_SAMPLES = 11,
    D3DMULTISAMPLE_12_SAMPLES = 12, D3DMULTISAMPLE_13_SAMPLES = 13, D3DMULTISAMPLE_14_SAMPLES = 14,
    D3DMULTISAMPLE_15_SAMPLES = 15, D3DMULTISAMPLE_16_SAMPLES = 16,
    D3DMULTISAMPLE_FORCE_DWORD = 0x7fffffff
} D3DMULTISAMPLE_TYPE;

typedef enum _D3DRESOURCETYPE {
    D3DRTYPE_SURFACE = 1, D3DRTYPE_VOLUME = 2, D3DRTYPE_TEXTURE = 3, D3DRTYPE_VOLUMETEXTURE = 4,
    D3DRTYPE_CUBETEXTURE = 5, D3DRTYPE_VERTEXBUFFER = 6, D3DRTYPE_INDEXBUFFER = 7,
    D3DRTYPE_FORCE_DWORD = 0x7fffffff
} D3DRESOURCETYPE;

#define D3DUSAGE_RENDERTARGET 0x00000001L
#define D3DUSAGE_DEPTHSTENCIL 0x00000002L
#define D3DUSAGE_WRITEONLY 0x00000008L
#define D3DUSAGE_DYNAMIC 0x00000200L
#define D3DLOCK_READONLY 0x00000010L
#define D3DLOCK_DISCARD 0x00002000L
#define D3DLOCK_NOOVERWRITE 0x00001000L
#define D3DLOCK_NOSYSLOCK 0x00000800L

typedef struct _D3DLOCKED_RECT { INT Pitch; void *pBits; } D3DLOCKED_RECT;

typedef struct _D3DSURFACE_DESC {
    D3DFORMAT Format;
    D3DRESOURCETYPE Type;
    DWORD Usage;
    D3DPOOL Pool;
    D3DMULTISAMPLE_TYPE MultiSampleType;
    DWORD MultiSampleQuality;
    UINT Width;
    UINT Height;
} D3DSURFACE_DESC;

typedef struct _D3DDISPLAYMODE { UINT Width; UINT Height; UINT RefreshRate; D3DFORMAT Format; } D3DDISPLAYMODE;

typedef struct _D3DVSHADERCAPS2_0 {
    DWORD Caps; INT DynamicFlowControlDepth; INT NumTemps; INT StaticFlowControlDepth;
} D3DVSHADERCAPS2_0;
typedef struct _D3DPSHADERCAPS2_0 {
    DWORD Caps; INT DynamicFlowControlDepth; INT NumTemps; INT StaticFlowControlDepth; INT NumInstructionSlots;
} D3DPSHADERCAPS2_0;

typedef struct _D3DCAPS9 {
    D3DDEVTYPE DeviceType;
    UINT AdapterOrdinal;
    DWORD Caps, Caps2, Caps3, PresentationIntervals, CursorCaps, DevCaps, PrimitiveMiscCaps, RasterCaps,
          ZCmpCaps, SrcBlendCaps, DestBlendCaps, AlphaCmpCaps, ShadeCaps, TextureCaps, TextureFilterCaps,
          CubeTextureFilterCaps, VolumeTextureFilterCaps, TextureAddressCaps, VolumeTextureAddressCaps,
          LineCaps, MaxTextureWidth, MaxTextureHeight, MaxVolumeExtent, MaxTextureRepeat,
          MaxTextureAspectRatio, MaxAnisotropy;
    float MaxVertexW, GuardBandLeft, GuardBandTop, GuardBandRight, GuardBandBottom, ExtentsAdjust;
    DWORD StencilCaps, FVFCaps, TextureOpCaps, MaxTextureBlendStages, MaxSimultaneousTextures,
          VertexProcessingCaps, MaxActiveLights, MaxUserClipPlanes, MaxVertexBlendMatrices,
          MaxVertexBlendMatrixIndex;
    float MaxPointSize;
    DWORD MaxPrimitiveCount, MaxVertexIndex, MaxStreams, MaxStreamStride, VertexShaderVersion,
          MaxVertexShaderConst, PixelShaderVersion;
    float PixelShader1xMaxValue;
    DWORD DevCaps2;
    float MaxNpatchTessellationLevel;
    DWORD Reserved5;
    UINT MasterAdapterOrdinal, AdapterOrdinalInGroup, NumberOfAdaptersInGroup;
    DWORD DeclTypes, NumSimultaneousRTs, StretchRectFilterCaps;
    D3DVSHADERCAPS2_0 VS20Caps;
    D3DPSHADERCAPS2_0 PS20Caps;
    DWORD VertexTextureFilterCaps, MaxVShaderInstructionsExecuted, MaxPShaderInstructionsExecuted,
          MaxVertexShader30InstructionSlots, MaxPixelShader30InstructionSlots;
} D3DCAPS9;
typedef char fnv_shim_d3dcaps9_size[sizeof(D3DCAPS9) == 304 ? 1 : -1];

/* Interfaces: opaque here (upstream calls through its own declarations). */
#ifdef __cplusplus
struct IDirect3D9; struct IDirect3DDevice9; struct IDirect3DSurface9; struct IDirect3DBaseTexture9;
struct IDirect3DTexture9; struct IDirect3DCubeTexture9; struct IDirect3DVolumeTexture9;
struct IDirect3DVertexBuffer9; struct IDirect3DIndexBuffer9; struct IDirect3DVertexDeclaration9;
struct IDirect3DVertexShader9; struct IDirect3DPixelShader9; struct IDirect3DQuery9;
#else
typedef struct IDirect3D9 IDirect3D9; typedef struct IDirect3DDevice9 IDirect3DDevice9;
typedef struct IDirect3DSurface9 IDirect3DSurface9; typedef struct IDirect3DTexture9 IDirect3DTexture9;
#endif

#endif /* FNV_SHIM_D3D9_H */
