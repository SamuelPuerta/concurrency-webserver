#ifndef __BUFFER_H__
#define __BUFFER_H__

#include "request.h"

// ──────────────────────────────────────────────────────────────────────────────
// Scheduling policy
// ──────────────────────────────────────────────────────────────────────────────
typedef enum {
    POLICY_FIFO = 0,   // First In, First Out  — classic FIFO queue
    POLICY_SFF  = 1    // Smallest File First  — approximates SJF using file size
} sched_policy_t;

// ──────────────────────────────────────────────────────────────────────────────
// Shared buffer API
//
// Thread safety: all public functions are internally synchronized via a mutex
// and two condition variables (not_empty / not_full).  Callers need no external
// locking.
// ──────────────────────────────────────────────────────────────────────────────

//
// buffer_init()  — call once before spawning worker threads.
//   capacity : maximum number of pending requests the buffer can hold.
//   policy   : POLICY_FIFO or POLICY_SFF.
//
void buffer_init(int capacity, sched_policy_t policy);

//
// buffer_put()  — producer side (acceptor / main thread).
//   Copies *req into the buffer.  Blocks if the buffer is full until a worker
//   frees a slot.
//
void buffer_put(request_t *req);

//
// buffer_get()  — consumer side (worker threads).
//   Removes and returns the next request according to the active policy.
//   Blocks if the buffer is empty until the acceptor adds a request.
//
//   FIFO : returns the oldest request (O(1)).
//   SFF  : scans all pending requests and returns the one with the smallest
//          filesize (O(n) where n ≤ capacity), then compacts the internal
//          array so the buffer stays consistent.
//
request_t buffer_get(void);

//
// buffer_destroy()  — call after all worker threads have exited.
//   Frees internal storage.
//
void buffer_destroy(void);

#endif // __BUFFER_H__
