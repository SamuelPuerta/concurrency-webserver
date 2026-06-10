# Makefile for the concurrent OSTEP web server
# Target: wserver
#
# Flags:
#   -pthread   links the POSIX thread library and enables thread-safe errno.
#   -Wextra    catches a few more common mistakes on top of -Wall.
#
# Usage:
#   make       → build wserver
#   make clean → remove all generated files

CC     = gcc
CFLAGS = -Wall -Wextra -pthread

# Object files needed for wserver
OBJS = wserver.o request.o io_helper.o buffer.o

# ──────────────────────────────────────────────────────────────────────────────
# Default target
# ──────────────────────────────────────────────────────────────────────────────
all: wserver

# ──────────────────────────────────────────────────────────────────────────────
# Server
# ──────────────────────────────────────────────────────────────────────────────
wserver: wserver.o request.o io_helper.o buffer.o
	$(CC) $(CFLAGS) -o $@ $^

# ──────────────────────────────────────────────────────────────────────────────
# Generic rule: compile each .c to a .o
# ──────────────────────────────────────────────────────────────────────────────
%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

# ──────────────────────────────────────────────────────────────────────────────
# Clean
# ──────────────────────────────────────────────────────────────────────────────
clean:
	-rm -f $(OBJS) wserver
