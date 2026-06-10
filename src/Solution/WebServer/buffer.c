#include <assert.h>
#include <pthread.h>
#include <stdlib.h>
#include <stdio.h>

#include "buffer.h"

// ──────────────────────────────────────────────────────────────────────────────
// Internal state
// ──────────────────────────────────────────────────────────────────────────────

static request_t     *slots;      // heap-allocated array of request slots
static int            cap;        // maximum number of slots
static int            count;      // current number of occupied slots
static int            head;       // index of the oldest entry (FIFO front)
static int            tail;       // index of next free slot (one past the last)
static sched_policy_t sched;      // active scheduling policy

// Synchronization primitives
static pthread_mutex_t mtx       = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t  not_empty = PTHREAD_COND_INITIALIZER;
static pthread_cond_t  not_full  = PTHREAD_COND_INITIALIZER;

// ──────────────────────────────────────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────────────────────────────────────

void buffer_init(int capacity, sched_policy_t policy) {
    assert(capacity > 0);
    cap   = capacity;
    sched = policy;
    count = 0;
    head  = 0;
    tail  = 0;

    slots = malloc(sizeof(request_t) * (size_t) capacity);
    assert(slots != NULL);

    printf("[buffer] initialized: capacity=%d policy=%s\n",
           capacity, policy == POLICY_FIFO ? "FIFO" : "SFF");
}

// ─── Producer ─────────────────────────────────────────────────────────────────

void buffer_put(request_t *req) {
    pthread_mutex_lock(&mtx);

    // Wait while the buffer is full
    while (count == cap)
        pthread_cond_wait(&not_full, &mtx);

    slots[tail] = *req;             // copy the whole struct by value
    tail = (tail + 1) % cap;
    count++;

    pthread_cond_signal(&not_empty);  // wake one waiting worker
    pthread_mutex_unlock(&mtx);
}

// ─── Consumer ─────────────────────────────────────────────────────────────────

request_t buffer_get(void) {
    pthread_mutex_lock(&mtx);

    // Wait while the buffer is empty
    while (count == 0)
        pthread_cond_wait(&not_empty, &mtx);

    request_t req;

    if (sched == POLICY_FIFO) {
        // ── FIFO: O(1) — take the oldest entry at head ──────────────────────
        req  = slots[head];
        head = (head + 1) % cap;

    } else {
        // ── SFF: O(n) — find the entry with the smallest filesize ────────────
        //
        // The buffer is a circular array whose live entries span positions
        //   head, (head+1)%cap, …, (head+count-1)%cap
        // We scan them all to locate the minimum.
        //
        int min_logical = 0;                        // logical index (0 = oldest)
        int min_size    = slots[head].filesize;

        for (int i = 1; i < count; i++) {
            int idx = (head + i) % cap;
            if (slots[idx].filesize < min_size) {
                min_size    = slots[idx].filesize;
                min_logical = i;
            }
        }

        int min_phys = (head + min_logical) % cap;  // physical slot index
        req = slots[min_phys];

        //
        // Compact: shift every entry from (min_phys+1) … (tail-1) one slot
        // toward head to fill the gap left by the removed entry, then retract
        // tail by one.
        //
        // Example (cap=6, head=1, tail=5, count=4, min_phys=3):
        //   Before: _ A B [C] D _   ([ ] = removed, head=1, tail=5)
        //   After:  _ A B  D  _ _   (head=1, tail=4)
        //
        int cur  = min_phys;
        int next = (cur + 1) % cap;
        while (next != tail) {
            slots[cur] = slots[next];
            cur  = next;
            next = (next + 1) % cap;
        }
        tail = (tail - 1 + cap) % cap;
    }

    count--;
    pthread_cond_signal(&not_full);   // wake the acceptor if it was blocked
    pthread_mutex_unlock(&mtx);
    return req;
}

// ─── Cleanup ──────────────────────────────────────────────────────────────────

void buffer_destroy(void) {
    free(slots);
    slots = NULL;
}
