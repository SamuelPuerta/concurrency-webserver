#ifndef __REQUEST_H__
#define __REQUEST_H__

// Maximum buffer size used throughout the server
#define MAXBUF (8192)

//
// request_t — carries everything a worker thread needs to serve one HTTP request.
// The main (acceptor) thread fills this struct via request_parse() and places it
// in the shared buffer.  Worker threads dequeue it and call request_serve().
//
typedef struct {
    int  conn_fd;              // accepted socket descriptor
    char filename[MAXBUF];    // resolved file path (e.g. "./index.html")
    char cgiargs[MAXBUF];     // CGI query string (empty for static files)
    int  is_static;           // 1 = static file, 0 = CGI program
    int  filesize;            // st_size from stat(); used by SFF scheduler
} request_t;

//
// Original single-threaded handler — kept for reference / unit testing.
// Not used by the concurrent server.
//
void request_handle(int fd);

//
// request_parse()
//   Reads the HTTP request line and headers from fd, validates the method,
//   resolves the URI, and stats the file.  On success, *req_out is fully
//   populated and the function returns 0.
//
//   On any error (bad method, 404, 403) the appropriate HTTP error response
//   is sent to fd, fd is closed, and -1 is returned.  The caller must NOT
//   use fd or req_out after a -1 return.
//
int  request_parse(int fd, request_t *req_out);

//
// request_serve()
//   Dispatches a pre-parsed request to request_serve_static() or
//   request_serve_dynamic(), then closes req->conn_fd.
//   Called exclusively from worker threads.
//
void request_serve(request_t *req);

#endif // __REQUEST_H__
