/* commctrl.h - the tree-view declarations fnv_decomp uses (fnv-linux shim). */
#pragma once
#include <windows.h>

typedef struct _TREEITEM *HTREEITEM;
typedef struct tagNMHDR { HWND hwndFrom; UINT_PTR idFrom; UINT code; } NMHDR, *LPNMHDR;
typedef struct tagTVITEMA {
    UINT mask; HTREEITEM hItem; UINT state; UINT stateMask; LPSTR pszText; int cchTextMax;
    int iImage; int iSelectedImage; int cChildren; LPARAM lParam;
} TVITEMA, *LPTVITEMA;
typedef struct tagTVITEMEXA {
    UINT mask; HTREEITEM hItem; UINT state; UINT stateMask; LPSTR pszText; int cchTextMax;
    int iImage; int iSelectedImage; int cChildren; LPARAM lParam; int iIntegral;
} TVITEMEXA, *LPTVITEMEXA;
typedef struct tagNMTREEVIEWA { NMHDR hdr; UINT action; TVITEMA itemOld; TVITEMA itemNew; POINT ptDrag; } NMTREEVIEWA;
#pragma pack(push, 1)
typedef struct tagTVKEYDOWN { NMHDR hdr; WORD wVKey; UINT flags; } NMTVKEYDOWN;
#pragma pack(pop)
