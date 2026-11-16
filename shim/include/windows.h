/* windows.h - minimal Win32 declarations for compiling fnv_decomp units on i686 Linux.
 * fnv-linux shim: grown only from compile errors. These are declarations; the platform
 * layer (Phase 5) implements the functions over POSIX/SDL. */
#ifndef FNV_SHIM_WINDOWS_H
#define FNV_SHIM_WINDOWS_H

#include <stddef.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Calling conventions and linkage */
#define WINAPI __stdcall
#define WINAPIV __cdecl
#define APIENTRY WINAPI
#define CALLBACK __stdcall
#define WINBASEAPI
#define WINUSERAPI
#define DECLSPEC_IMPORT
#define CONST const
#define VOID void
#ifndef FAR
#define FAR
#endif
#ifndef NEAR
#define NEAR
#endif

/* Basic types (ILP32: long is 32-bit on i686 Linux, as on Win32) */
typedef int BOOL;
typedef unsigned char BYTE;
typedef unsigned short WORD;
typedef unsigned long DWORD;
typedef long LONG;
typedef unsigned long ULONG;
typedef int INT;
typedef unsigned int UINT;
typedef short SHORT;
typedef unsigned short USHORT;
typedef char CHAR;
typedef unsigned char UCHAR;
typedef wchar_t WCHAR;
typedef float FLOAT;
typedef __int64 LONGLONG;
typedef unsigned __int64 ULONGLONG;
typedef unsigned __int64 DWORD64;
typedef int INT_PTR;
typedef unsigned int UINT_PTR;
typedef long LONG_PTR;
typedef unsigned long ULONG_PTR;
typedef ULONG_PTR DWORD_PTR;
typedef ULONG_PTR SIZE_T;
typedef LONG_PTR SSIZE_T;
typedef BYTE BOOLEAN;
typedef void *PVOID;
typedef void *LPVOID;
typedef const void *LPCVOID;
typedef CHAR *LPSTR, *PSTR;
typedef const CHAR *LPCSTR, *PCSTR;
typedef WCHAR *LPWSTR, *PWSTR;
typedef const WCHAR *LPCWSTR, *PCWSTR;
typedef BYTE *LPBYTE, *PBYTE;
typedef DWORD *LPDWORD, *PDWORD;
typedef WORD *LPWORD;
typedef LONG *LPLONG, *PLONG;
typedef BOOL *LPBOOL;
typedef void *HANDLE;
typedef HANDLE *PHANDLE, *LPHANDLE;
typedef LONG HRESULT;
typedef UINT_PTR WPARAM;
typedef LONG_PTR LPARAM;
typedef LONG_PTR LRESULT;
typedef WORD ATOM;
typedef DWORD COLORREF;

#define DECLARE_HANDLE(name) struct name##__ { int unused; }; typedef struct name##__ *name
DECLARE_HANDLE(HWND);
DECLARE_HANDLE(HINSTANCE);
DECLARE_HANDLE(HKEY);
DECLARE_HANDLE(HDC);
DECLARE_HANDLE(HICON);
DECLARE_HANDLE(HMENU);
DECLARE_HANDLE(HBRUSH);
DECLARE_HANDLE(HMONITOR);
typedef HINSTANCE HMODULE;
typedef HICON HCURSOR;

#define TRUE 1
#define FALSE 0
#ifndef NULL
#define NULL 0
#endif
#define MAX_PATH 260
#define INFINITE 0xFFFFFFFF
#define INVALID_HANDLE_VALUE ((HANDLE)(LONG_PTR)-1)

typedef union _LARGE_INTEGER {
    struct { DWORD LowPart; LONG HighPart; };
    struct { DWORD LowPart; LONG HighPart; } u;
    LONGLONG QuadPart;
} LARGE_INTEGER, *PLARGE_INTEGER;

typedef union _ULARGE_INTEGER {
    struct { DWORD LowPart; DWORD HighPart; };
    struct { DWORD LowPart; DWORD HighPart; } u;
    ULONGLONG QuadPart;
} ULARGE_INTEGER, *PULARGE_INTEGER;

typedef struct tagRECT { LONG left, top, right, bottom; } RECT, *PRECT, *LPRECT;
typedef const RECT *LPCRECT;
typedef struct tagPOINT { LONG x, y; } POINT, *PPOINT, *LPPOINT;
typedef struct tagSIZE { LONG cx, cy; } SIZE, *PSIZE, *LPSIZE;

typedef struct _LIST_ENTRY { struct _LIST_ENTRY *Flink, *Blink; } LIST_ENTRY, *PLIST_ENTRY;

typedef struct _RTL_CRITICAL_SECTION_DEBUG *PRTL_CRITICAL_SECTION_DEBUG;
typedef struct _RTL_CRITICAL_SECTION {
    PRTL_CRITICAL_SECTION_DEBUG DebugInfo;
    LONG LockCount;
    LONG RecursionCount;
    HANDLE OwningThread;
    HANDLE LockSemaphore;
    ULONG_PTR SpinCount;
} RTL_CRITICAL_SECTION, *PRTL_CRITICAL_SECTION;
typedef RTL_CRITICAL_SECTION CRITICAL_SECTION, *PCRITICAL_SECTION, *LPCRITICAL_SECTION;

typedef struct _SYSTEMTIME {
    WORD wYear, wMonth, wDayOfWeek, wDay, wHour, wMinute, wSecond, wMilliseconds;
} SYSTEMTIME, *PSYSTEMTIME, *LPSYSTEMTIME;

typedef struct _FILETIME { DWORD dwLowDateTime; DWORD dwHighDateTime; } FILETIME, *PFILETIME, *LPFILETIME;

typedef struct _WIN32_FIND_DATAA {
    DWORD dwFileAttributes;
    FILETIME ftCreationTime;
    FILETIME ftLastAccessTime;
    FILETIME ftLastWriteTime;
    DWORD nFileSizeHigh;
    DWORD nFileSizeLow;
    DWORD dwReserved0;
    DWORD dwReserved1;
    CHAR cFileName[MAX_PATH];
    CHAR cAlternateFileName[14];
} WIN32_FIND_DATAA, *PWIN32_FIND_DATAA, *LPWIN32_FIND_DATAA;
typedef WIN32_FIND_DATAA WIN32_FIND_DATA, *LPWIN32_FIND_DATA;

typedef struct _SYSTEM_INFO {
    union {
        DWORD dwOemId;
        struct { WORD wProcessorArchitecture; WORD wReserved; };
    };
    DWORD dwPageSize;
    LPVOID lpMinimumApplicationAddress;
    LPVOID lpMaximumApplicationAddress;
    DWORD_PTR dwActiveProcessorMask;
    DWORD dwNumberOfProcessors;
    DWORD dwProcessorType;
    DWORD dwAllocationGranularity;
    WORD wProcessorLevel;
    WORD wProcessorRevision;
} SYSTEM_INFO, *LPSYSTEM_INFO;

typedef struct _SECURITY_ATTRIBUTES {
    DWORD nLength;
    LPVOID lpSecurityDescriptor;
    BOOL bInheritHandle;
} SECURITY_ATTRIBUTES, *PSECURITY_ATTRIBUTES, *LPSECURITY_ATTRIBUTES;

/* kernel32 */
WINBASEAPI BOOL WINAPI CloseHandle(HANDLE hObject);
WINBASEAPI DWORD WINAPI GetCurrentThreadId(void);
WINBASEAPI DWORD WINAPI GetTickCount(void);
WINBASEAPI void WINAPI GetSystemInfo(LPSYSTEM_INFO lpSystemInfo);
WINBASEAPI DWORD WINAPI TlsAlloc(void);
WINBASEAPI BOOL WINAPI TlsFree(DWORD dwTlsIndex);
WINBASEAPI LPVOID WINAPI TlsGetValue(DWORD dwTlsIndex);
WINBASEAPI BOOL WINAPI TlsSetValue(DWORD dwTlsIndex, LPVOID lpTlsValue);
WINBASEAPI void WINAPI InitializeCriticalSection(LPCRITICAL_SECTION lpCriticalSection);
WINBASEAPI void WINAPI DeleteCriticalSection(LPCRITICAL_SECTION lpCriticalSection);
WINBASEAPI void WINAPI EnterCriticalSection(LPCRITICAL_SECTION lpCriticalSection);
WINBASEAPI void WINAPI LeaveCriticalSection(LPCRITICAL_SECTION lpCriticalSection);
WINBASEAPI HANDLE WINAPI CreateSemaphoreA(LPSECURITY_ATTRIBUTES lpSemaphoreAttributes, LONG lInitialCount,
                                          LONG lMaximumCount, LPCSTR lpName);
WINBASEAPI BOOL WINAPI CreateDirectoryA(LPCSTR lpPathName, LPSECURITY_ATTRIBUTES lpSecurityAttributes);
WINBASEAPI BOOL WINAPI DeleteFileA(LPCSTR lpFileName);
WINBASEAPI HANDLE WINAPI FindFirstFileA(LPCSTR lpFileName, LPWIN32_FIND_DATAA lpFindFileData);
WINBASEAPI BOOL WINAPI FindNextFileA(HANDLE hFindFile, LPWIN32_FIND_DATAA lpFindFileData);
WINBASEAPI BOOL WINAPI FindClose(HANDLE hFindFile);

#define WAIT_OBJECT_0 0x00000000L
#define WAIT_TIMEOUT 0x00000102L
#define WAIT_FAILED 0xFFFFFFFF
WINBASEAPI DWORD WINAPI GetLastError(void);
WINBASEAPI DWORD WINAPI WaitForSingleObject(HANDLE hHandle, DWORD dwMilliseconds);
WINBASEAPI HANDLE WINAPI CreateEventA(LPSECURITY_ATTRIBUTES lpEventAttributes, BOOL bManualReset,
                                      BOOL bInitialState, LPCSTR lpName);
WINBASEAPI BOOL WINAPI TryEnterCriticalSection(LPCRITICAL_SECTION lpCriticalSection);
WINBASEAPI void WINAPI DebugBreak(void);
WINBASEAPI BOOL WINAPI QueryPerformanceCounter(LARGE_INTEGER *lpPerformanceCount);
WINBASEAPI BOOL WINAPI QueryPerformanceFrequency(LARGE_INTEGER *lpFrequency);
WINBASEAPI BOOL WINAPI FileTimeToSystemTime(const FILETIME *lpFileTime, LPSYSTEMTIME lpSystemTime);

typedef struct _TIME_ZONE_INFORMATION {
    LONG Bias;
    WCHAR StandardName[32];
    SYSTEMTIME StandardDate;
    LONG StandardBias;
    WCHAR DaylightName[32];
    SYSTEMTIME DaylightDate;
    LONG DaylightBias;
} TIME_ZONE_INFORMATION, *PTIME_ZONE_INFORMATION, *LPTIME_ZONE_INFORMATION;
WINBASEAPI BOOL WINAPI SystemTimeToTzSpecificLocalTime(LPTIME_ZONE_INFORMATION lpTimeZoneInformation,
                                                       LPSYSTEMTIME lpUniversalTime, LPSYSTEMTIME lpLocalTime);

/* Interlocked operations: kernel32 exports in the 6.0A SDK (the game imports them). */
WINBASEAPI LONG WINAPI InterlockedIncrement(LONG volatile *lpAddend);
WINBASEAPI LONG WINAPI InterlockedDecrement(LONG volatile *lpAddend);
WINBASEAPI LONG WINAPI InterlockedExchange(LONG volatile *Target, LONG Value);
WINBASEAPI LONG WINAPI InterlockedExchangeAdd(LONG volatile *Addend, LONG Value);
WINBASEAPI LONG WINAPI InterlockedCompareExchange(LONG volatile *Destination, LONG Exchange, LONG Comperand);

#define SUCCEEDED(hr) (((HRESULT)(hr)) >= 0)
#define FAILED(hr) (((HRESULT)(hr)) < 0)
#define S_OK ((HRESULT)0L)
#define S_FALSE ((HRESULT)1L)
#define E_FAIL ((HRESULT)0x80004005L)

#define INVALID_FILE_ATTRIBUTES ((DWORD)-1)
#define FILE_ATTRIBUTE_READONLY 0x00000001
#define FILE_ATTRIBUTE_HIDDEN 0x00000002
#define FILE_ATTRIBUTE_DIRECTORY 0x00000010
#define FILE_ATTRIBUTE_NORMAL 0x00000080
WINBASEAPI DWORD WINAPI GetFileAttributesA(LPCSTR lpFileName);
WINBASEAPI BOOL WINAPI InitializeCriticalSectionAndSpinCount(LPCRITICAL_SECTION lpCriticalSection, DWORD dwSpinCount);

#pragma pack(push, 2)
typedef struct tagBITMAPFILEHEADER {
    WORD bfType; DWORD bfSize; WORD bfReserved1; WORD bfReserved2; DWORD bfOffBits;
} BITMAPFILEHEADER;
#pragma pack(pop)
typedef struct tagBITMAPINFOHEADER {
    DWORD biSize; LONG biWidth; LONG biHeight; WORD biPlanes; WORD biBitCount; DWORD biCompression;
    DWORD biSizeImage; LONG biXPelsPerMeter; LONG biYPelsPerMeter; DWORD biClrUsed; DWORD biClrImportant;
} BITMAPINFOHEADER;

typedef HANDLE HLOCAL;
#define FORMAT_MESSAGE_ALLOCATE_BUFFER 0x00000100
#define FORMAT_MESSAGE_IGNORE_INSERTS 0x00000200
#define FORMAT_MESSAGE_FROM_SYSTEM 0x00001000
WINBASEAPI DWORD WINAPI FormatMessageA(DWORD dwFlags, LPCVOID lpSource, DWORD dwMessageId, DWORD dwLanguageId,
                                       LPSTR lpBuffer, DWORD nSize, void *Arguments);
WINBASEAPI HLOCAL WINAPI LocalFree(HLOCAL hMem);

/* guiddef.h */
#ifndef GUID_DEFINED
#define GUID_DEFINED
typedef struct _GUID { unsigned long Data1; unsigned short Data2; unsigned short Data3; unsigned char Data4[8]; } GUID;
#endif
typedef GUID IID;
typedef GUID CLSID;
#ifdef __cplusplus
#define REFIID const IID &
#define REFCLSID const IID &
#define REFGUID const GUID &
#else
#define REFIID const IID *
#define REFCLSID const IID *
#define REFGUID const GUID *
#endif

/* user32 */
#define INPUT_MOUSE 0
#define INPUT_KEYBOARD 1
#define INPUT_HARDWARE 2
#define MOUSEEVENTF_MOVE 0x0001
#define MOUSEEVENTF_LEFTDOWN 0x0002
#define MOUSEEVENTF_LEFTUP 0x0004
#define MOUSEEVENTF_ABSOLUTE 0x8000
typedef struct tagMOUSEINPUT {
    LONG dx; LONG dy; DWORD mouseData; DWORD dwFlags; DWORD time; ULONG_PTR dwExtraInfo;
} MOUSEINPUT;
typedef struct tagKEYBDINPUT { WORD wVk; WORD wScan; DWORD dwFlags; DWORD time; ULONG_PTR dwExtraInfo; } KEYBDINPUT;
typedef struct tagHARDWAREINPUT { DWORD uMsg; WORD wParamL; WORD wParamH; } HARDWAREINPUT;
typedef struct tagINPUT {
    DWORD type;
    union { MOUSEINPUT mi; KEYBDINPUT ki; HARDWAREINPUT hi; };
} INPUT, *PINPUT, *LPINPUT;
WINUSERAPI UINT WINAPI SendInput(UINT cInputs, LPINPUT pInputs, int cbSize);

typedef struct tagMSG {
    HWND hwnd;
    UINT message;
    WPARAM wParam;
    LPARAM lParam;
    DWORD time;
    POINT pt;
} MSG, *PMSG, *LPMSG;
typedef LRESULT (CALLBACK *WNDPROC)(HWND, UINT, WPARAM, LPARAM);
WINUSERAPI LRESULT WINAPI SendMessageA(HWND hWnd, UINT Msg, WPARAM wParam, LPARAM lParam);
WINUSERAPI LRESULT WINAPI DefWindowProcA(HWND hWnd, UINT Msg, WPARAM wParam, LPARAM lParam);
WINUSERAPI BOOL WINAPI PeekMessageA(LPMSG lpMsg, HWND hWnd, UINT wMsgFilterMin, UINT wMsgFilterMax,
                                    UINT wRemoveMsg);
WINUSERAPI BOOL WINAPI TranslateMessage(const MSG *lpMsg);
WINUSERAPI LRESULT WINAPI DispatchMessageA(const MSG *lpMsg);
WINUSERAPI int WINAPI ShowCursor(BOOL bShow);

/* shell32 (shellapi.h, included by windows.h) */
HINSTANCE WINAPI ShellExecuteA(HWND hwnd, LPCSTR lpOperation, LPCSTR lpFile, LPCSTR lpParameters,
                               LPCSTR lpDirectory, INT nShowCmd);

#ifdef __cplusplus
}
#endif

#endif /* FNV_SHIM_WINDOWS_H */
