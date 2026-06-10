#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "buffer.h"
#include "io_helper.h"
#include "request.h"

// ──────────────────────────────────────────────────────────────────────────────
// Default configuration
// ──────────────────────────────────────────────────────────────────────────────
#define DEFAULT_PORT       10000
#define DEFAULT_THREADS    4
#define DEFAULT_BUF_SIZE   16
#define DEFAULT_POLICY     POLICY_FIFO

static char default_root[] = ".";

// ──────────────────────────────────────────────────────────────────────────────
// Worker thread
//
// Each worker loops forever: it blocks on buffer_get() waiting for the next
// request, then calls request_serve() which dispatches and closes the socket.
// ──────────────────────────────────────────────────────────────────────────────
static void *worker_fn(void *arg) {
    long id = (long) arg;
    (void) id;  // suppress unused-variable warning when printf is removed

    while (1) {
        request_t req = buffer_get();
        printf("[worker %ld] serving fd=%d file=%s size=%d\n",
               id, req.conn_fd, req.filename, req.filesize);
        request_serve(&req);
    }
    return NULL;  // unreachable
}

// ──────────────────────────────────────────────────────────────────────────────
// main()
//
// Usage:
//   ./wserver [-d basedir] [-p port] [-t threads] [-b bufsize] [-s fifo|sff]
//
//   -d  Base directory to serve files from          (default: ".")
//   -p  TCP port to listen on                       (default: 10000)
//   -t  Number of worker threads in the pool        (default: 4)
//   -b  Capacity of the shared request buffer       (default: 16)
//   -s  Scheduling policy: "fifo" or "sff"          (default: fifo)
// ──────────────────────────────────────────────────────────────────────────────
int main(int argc, char *argv[]) {
    // ── Parse command-line arguments ─────────────────────────────────────────
    char          *root_dir    = default_root;
    int            port        = DEFAULT_PORT;
    int            num_threads = DEFAULT_THREADS;
    int            buf_size    = DEFAULT_BUF_SIZE;
    sched_policy_t policy      = DEFAULT_POLICY;

    int c;
    while ((c = getopt(argc, argv, "d:p:t:b:s:")) != -1) {
        switch (c) {
        case 'd':
            root_dir = optarg;
            break;
        case 'p':
            port = atoi(optarg);
            break;
        case 't':
            num_threads = atoi(optarg);
            if (num_threads < 1) {
                fprintf(stderr, "wserver: -t must be >= 1\n");
                exit(1);
            }
            break;
        case 'b':
            buf_size = atoi(optarg);
            if (buf_size < 1) {
                fprintf(stderr, "wserver: -b must be >= 1\n");
                exit(1);
            }
            break;
        case 's':
            if (strcasecmp(optarg, "sff") == 0) {
                policy = POLICY_SFF;
            } else if (strcasecmp(optarg, "fifo") == 0) {
                policy = POLICY_FIFO;
            } else {
                fprintf(stderr, "wserver: -s must be 'fifo' or 'sff'\n");
                exit(1);
            }
            break;
        default:
            fprintf(stderr,
                    "usage: wserver [-d basedir] [-p port] "
                    "[-t threads] [-b bufsize] [-s fifo|sff]\n");
            exit(1);
        }
    }

    printf("[wserver] Starting — policy=%s threads=%d bufsize=%d port=%d dir=%s\n",
           policy == POLICY_FIFO ? "FIFO" : "SFF",
           num_threads, buf_size, port, root_dir);

    // ── Serve from the requested directory ───────────────────────────────────
    chdir_or_die(root_dir);

    // ── Initialize the shared buffer ─────────────────────────────────────────
    buffer_init(buf_size, policy);

    // ── Spawn the worker thread pool ─────────────────────────────────────────
    pthread_t *workers = malloc(sizeof(pthread_t) * (size_t) num_threads);
    assert(workers != NULL);

    for (long i = 0; i < num_threads; i++) {
        int rc = pthread_create(&workers[i], NULL, worker_fn, (void *) i);
        if (rc != 0) {
            fprintf(stderr, "wserver: pthread_create failed (rc=%d)\n", rc);
            exit(1);
        }
    }
    printf("[wserver] %d worker thread(s) ready\n", num_threads);

    // ── Acceptor loop ─────────────────────────────────────────────────────────
    //
    // The main thread accepts incoming connections, calls request_parse() to
    // read the HTTP request line, drain headers, resolve the URI, and stat()
    // the file — populating a request_t with all metadata the scheduler needs.
    //
    // If parsing succeeds the request is placed in the shared buffer; worker
    // threads pick it up according to the active scheduling policy.
    //
    // If parsing fails (bad method, 404, 403) request_parse() already sent the
    // error response and closed the fd, so we simply move on to the next
    // connection.
    //
    int listen_fd = open_listen_fd_or_die(port);
    printf("[wserver] Listening on port %d\n", port);

    while (1) {
        struct sockaddr_in client_addr;
        int client_len = sizeof(client_addr);

        int conn_fd = accept_or_die(listen_fd,
                                    (sockaddr_t *)  &client_addr,
                                    (socklen_t *)   &client_len);

        request_t req;
        if (request_parse(conn_fd, &req) == 0) {
            // Valid request: hand it off to the buffer for a worker to serve
            buffer_put(&req);
        }
        // If request_parse returned -1, the error was already handled and
        // conn_fd was closed inside request_parse — nothing more to do here.
    }

    // Unreachable in normal operation; included for completeness.
    free(workers);
    buffer_destroy();
    return 0;
}
