#include "io_helper.h"
#include "request.h"

//
// Some of this code stolen from Bryant/O'Halloran
// Hopefully this is not a problem ... :)
//

// ──────────────────────────────────────────────────────────────────────────────
// Internal helpers (unchanged from the original single-threaded server)
// ──────────────────────────────────────────────────────────────────────────────

void request_error(int fd, char *cause, char *errnum,
                   char *shortmsg, char *longmsg) {
    char buf[MAXBUF], body[MAXBUF];

    // Build the HTML body first so we know its length for the Content-Length header
    sprintf(body,
            "<!doctype html>\r\n"
            "<head>\r\n"
            "  <title>OSTEP WebServer Error</title>\r\n"
            "</head>\r\n"
            "<body>\r\n"
            "  <h2>%s: %s</h2>\r\n"
            "  <p>%s: %s</p>\r\n"
            "</body>\r\n"
            "</html>\r\n",
            errnum, shortmsg, longmsg, cause);

    sprintf(buf, "HTTP/1.0 %s %s\r\n", errnum, shortmsg);
    write_or_die(fd, buf, strlen(buf));

    sprintf(buf, "Content-Type: text/html\r\n");
    write_or_die(fd, buf, strlen(buf));

    sprintf(buf, "Content-Length: %lu\r\n\r\n", strlen(body));
    write_or_die(fd, buf, strlen(buf));

    write_or_die(fd, body, strlen(body));
}

//
// Reads and discards everything up to and including the blank line that
// separates HTTP request headers from the body.
//
void request_read_headers(int fd) {
    char buf[MAXBUF];
    readline_or_die(fd, buf, MAXBUF);
    while (strcmp(buf, "\r\n")) {
        readline_or_die(fd, buf, MAXBUF);
    }
}

//
// Resolves the URI into a filesystem path and (for CGI) query-string args.
// Returns 1 for static content, 0 for dynamic (CGI).
//
int request_parse_uri(char *uri, char *filename, char *cgiargs) {
    char *ptr;

    if (!strstr(uri, "cgi")) {
        // Static file
        strcpy(cgiargs, "");
        sprintf(filename, ".%s", uri);
        if (uri[strlen(uri) - 1] == '/')
            strcat(filename, "index.html");
        return 1;
    } else {
        // Dynamic CGI
        ptr = index(uri, '?');
        if (ptr) {
            strcpy(cgiargs, ptr + 1);
            *ptr = '\0';
        } else {
            strcpy(cgiargs, "");
        }
        sprintf(filename, ".%s", uri);
        return 0;
    }
}

//
// Maps a filename extension to its MIME type.
//
void request_get_filetype(char *filename, char *filetype) {
    if      (strstr(filename, ".html")) strcpy(filetype, "text/html");
    else if (strstr(filename, ".gif"))  strcpy(filetype, "image/gif");
    else if (strstr(filename, ".jpg"))  strcpy(filetype, "image/jpeg");
    else                                strcpy(filetype, "text/plain");
}

void request_serve_dynamic(int fd, char *filename, char *cgiargs) {
    char buf[MAXBUF], *argv[] = { NULL };

    // The server sends only the status line; the CGI script completes the headers.
    sprintf(buf,
            "HTTP/1.0 200 OK\r\n"
            "Server: OSTEP WebServer\r\n");
    write_or_die(fd, buf, strlen(buf));

    if (fork_or_die() == 0) {               // child
        setenv_or_die("QUERY_STRING", cgiargs, 1);
        dup2_or_die(fd, STDOUT_FILENO);     // redirect writes to the socket
        extern char **environ;
        execve_or_die(filename, argv, environ);
    } else {
        wait_or_die(NULL);
    }
}

void request_serve_static(int fd, char *filename, int filesize) {
    int   srcfd;
    char *srcp, filetype[MAXBUF], buf[MAXBUF];

    request_get_filetype(filename, filetype);
    srcfd = open_or_die(filename, O_RDONLY, 0);

    // Memory-map the file to avoid an extra copy into a user-space buffer
    srcp = mmap_or_die(0, filesize, PROT_READ, MAP_PRIVATE, srcfd, 0);
    close_or_die(srcfd);

    sprintf(buf,
            "HTTP/1.0 200 OK\r\n"
            "Server: OSTEP WebServer\r\n"
            "Content-Length: %d\r\n"
            "Content-Type: %s\r\n\r\n",
            filesize, filetype);
    write_or_die(fd, buf, strlen(buf));

    write_or_die(fd, srcp, filesize);
    munmap_or_die(srcp, filesize);
}

// ──────────────────────────────────────────────────────────────────────────────
// Original single-threaded entry point (kept for reference; not used by the
// concurrent server)
// ──────────────────────────────────────────────────────────────────────────────

void request_handle(int fd) {
    int is_static;
    struct stat sbuf;
    char buf[MAXBUF], method[MAXBUF], uri[MAXBUF], version[MAXBUF];
    char filename[MAXBUF], cgiargs[MAXBUF];

    readline_or_die(fd, buf, MAXBUF);
    sscanf(buf, "%s %s %s", method, uri, version);
    printf("method:%s uri:%s version:%s\n", method, uri, version);

    if (strcasecmp(method, "GET")) {
        request_error(fd, method, "501", "Not Implemented",
                      "server does not implement this method");
        return;
    }
    request_read_headers(fd);

    is_static = request_parse_uri(uri, filename, cgiargs);
    if (stat(filename, &sbuf) < 0) {
        request_error(fd, filename, "404", "Not found",
                      "server could not find this file");
        return;
    }

    if (is_static) {
        if (!(S_ISREG(sbuf.st_mode)) || !(S_IRUSR & sbuf.st_mode)) {
            request_error(fd, filename, "403", "Forbidden",
                          "server could not read this file");
            return;
        }
        request_serve_static(fd, filename, sbuf.st_size);
    } else {
        if (!(S_ISREG(sbuf.st_mode)) || !(S_IXUSR & sbuf.st_mode)) {
            request_error(fd, filename, "403", "Forbidden",
                          "server could not run this CGI program");
            return;
        }
        request_serve_dynamic(fd, filename, cgiargs);
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// Concurrent-server interface
// ──────────────────────────────────────────────────────────────────────────────

//
// request_parse()
//
// Runs entirely in the ACCEPTOR (main) thread so that all metadata needed by
// the SFF scheduler (especially filesize) is available before the request is
// placed in the shared buffer.
//
// Flow:
//   1. Read request line → validate method is GET.
//   2. Drain HTTP headers (not needed for static serving).
//   3. Resolve URI → filename + cgiargs.
//   4. stat() the file to get its size and permission bits.
//   5. Populate *req_out and return 0.
//
// On any error the HTTP error response is written to fd, fd is closed, and -1
// is returned.  The caller must not touch fd or *req_out after a -1 return.
//
int request_parse(int fd, request_t *req_out) {
    struct stat sbuf;
    char buf[MAXBUF], method[MAXBUF], uri[MAXBUF], version[MAXBUF];
    char filename[MAXBUF], cgiargs[MAXBUF];
    int  is_static;

    // ── 1. Request line ──────────────────────────────────────────────────────
    readline_or_die(fd, buf, MAXBUF);
    sscanf(buf, "%s %s %s", method, uri, version);
    printf("[parse] method:%s uri:%s version:%s\n", method, uri, version);

    if (strcasecmp(method, "GET")) {
        request_error(fd, method, "501", "Not Implemented",
                      "server does not implement this method");
        close_or_die(fd);
        return -1;
    }

    // ── 2. Headers (discard) ─────────────────────────────────────────────────
    request_read_headers(fd);

    // ── 3. URI → path + args ─────────────────────────────────────────────────
    is_static = request_parse_uri(uri, filename, cgiargs);

    // ── 4. stat() ────────────────────────────────────────────────────────────
    if (stat(filename, &sbuf) < 0) {
        request_error(fd, filename, "404", "Not found",
                      "server could not find this file");
        close_or_die(fd);
        return -1;
    }

    if (is_static) {
        if (!(S_ISREG(sbuf.st_mode)) || !(S_IRUSR & sbuf.st_mode)) {
            request_error(fd, filename, "403", "Forbidden",
                          "server could not read this file");
            close_or_die(fd);
            return -1;
        }
    } else {
        if (!(S_ISREG(sbuf.st_mode)) || !(S_IXUSR & sbuf.st_mode)) {
            request_error(fd, filename, "403", "Forbidden",
                          "server could not run this CGI program");
            close_or_die(fd);
            return -1;
        }
    }

    // ── 5. Populate output struct ─────────────────────────────────────────────
    req_out->conn_fd   = fd;
    req_out->is_static = is_static;
    req_out->filesize  = (int) sbuf.st_size;
    strncpy(req_out->filename, filename, MAXBUF - 1);
    req_out->filename[MAXBUF - 1] = '\0';
    strncpy(req_out->cgiargs, cgiargs, MAXBUF - 1);
    req_out->cgiargs[MAXBUF - 1] = '\0';

    return 0;
}

//
// request_serve()
//
// Called from a WORKER thread.  Dispatches to the appropriate serving
// function and then closes the connection socket.
//
void request_serve(request_t *req) {
    if (req->is_static) {
        request_serve_static(req->conn_fd, req->filename, req->filesize);
    } else {
        request_serve_dynamic(req->conn_fd, req->filename, req->cgiargs);
    }
    close_or_die(req->conn_fd);
}
