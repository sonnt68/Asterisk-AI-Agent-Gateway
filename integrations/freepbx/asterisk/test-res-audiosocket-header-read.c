/*
 * SPDX-License-Identifier: GPL-2.0-only
 * Receive functions Copyright (C) 2019, CyCore Systems, Inc.
 * Original author: Sean C McCord <scm@cycoresys.com>.
 * Distributed under GNU GPL version 2, like the pinned Asterisk source.
 *
 * Standalone regression harness for Asterisk 21.10.2 AudioSocket framing.
 *
 * The two receive functions below are the pinned 21.10.2 function body and
 * the reviewed header-read repair, extracted from res/res_audiosocket.c. The
 * harness supplies only the Asterisk frame, allocator, logger, and poll
 * seams, then drives the function through real nonblocking socketpairs.
 *
 * Compile with:
 *   cc -std=c11 -Wall -Wextra -Werror -pthread \
 *     test-res-audiosocket-header-read.c -o /tmp/test-audiosocket-header-read
 * Run with `baseline` to prove the known idle-EAGAIN failure, or `patched` to
 * run the complete repaired framing regression. The sibling runner executes
 * both modes and compares these bodies with the actual source passed via
 * `--source`.
 *
 * Pinned source: Asterisk 21.10.2, res_audiosocket.c SHA-256
 * a9ff97eca61dad09148ccb67de5584c0c6854d8cc748f916d6585d055f6c62da.
 */
#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define AST_FRAME_NULL 0
#define AST_FRAME_VOICE 2
#define AST_MALLOCD_DATA 1
#define AST_AUDIOSOCKET_KIND_HANGUP 0x00
#define AST_AUDIOSOCKET_KIND_AUDIO 0x10
#define LOG_WARNING 4
#define LOG_ERROR 3
#define AUDIO_SOCKET_HEADER_POLL_MSEC 5

struct ast_frame {
	int frametype;
	struct {
		void *format;
		int integer;
	} subclass;
	const char *src;
	int mallocd;
	struct {
		void *ptr;
	} data;
	int datalen;
	int samples;
};

static int ast_format_slin_storage;
static void *ast_format_slin = &ast_format_slin_storage;
extern struct ast_frame ast_null_frame;
struct ast_frame ast_null_frame = {.frametype = AST_FRAME_NULL};

static void ast_log(int level, const char *format, ...)
{
	(void)level;
	(void)format;
}

static void *ast_malloc(size_t size)
{
	return malloc(size);
}

static void ast_free(void *ptr)
{
	free(ptr);
}

static struct ast_frame *ast_frisolate(struct ast_frame *frame)
{
	struct ast_frame *copy = ast_malloc(sizeof(*copy));
	if (!copy) {
		return NULL;
	}
	*copy = *frame;
	return copy;
}

static int ast_wait_for_input(int fd, int timeout_msec)
{
	struct pollfd descriptor = {.fd = fd, .events = POLLIN};
	int result;

	do {
		result = poll(&descriptor, 1, timeout_msec);
	} while (result < 0 && errno == EINTR);
	return result;
}

/* BEGIN_PINNED_BASELINE_FUNCTION */
struct ast_frame *baseline_receive_frame_with_hangup(const int svc,
	int *const hangup)
{
	int i = 0, n = 0, ret = 0;
	struct ast_frame f = {
		.frametype = AST_FRAME_VOICE,
		.subclass.format = ast_format_slin,
		.src = "AudioSocket",
		.mallocd = AST_MALLOCD_DATA,
	};
	uint8_t header[3];
	uint8_t *kind = &header[0];
	uint16_t *length = (uint16_t *) &header[1];
	uint8_t *data;

	if (hangup) {
		*hangup = 0;
	}

	n = read(svc, &header, 3);
	if (n == -1) {
		ast_log(LOG_WARNING, "Failed to read header from AudioSocket because: %s\n", strerror(errno));
		return NULL;
	}

	if (n == 0 || *kind == AST_AUDIOSOCKET_KIND_HANGUP) {
		/* Socket closure or requested hangup. */
		if (hangup) {
			*hangup = 1;
		}
		return NULL;
	}

	if (*kind != AST_AUDIOSOCKET_KIND_AUDIO) {
		ast_log(LOG_ERROR, "Received AudioSocket message other than hangup or audio, refer to protocol specification for valid message types\n");
		return NULL;
	}

	/* Swap endianess of length if needed. */
	*length = ntohs(*length);
	if (*length < 1) {
		ast_log(LOG_ERROR, "Invalid message length received from AudioSocket server. \n");
		return NULL;
	}

	data = ast_malloc(*length);
	if (!data) {
		ast_log(LOG_ERROR, "Failed to allocate for data from AudioSocket\n");
		return NULL;
	}

	ret = 0;
	n = 0;
	i = 0;
	while (i < *length) {
		n = read(svc, data + i, *length - i);
		if (n == -1) {
			if (errno == EAGAIN || errno == EWOULDBLOCK) {
				int poll_result = ast_wait_for_input(svc, 5);

				if (poll_result == 1) {
					continue;
				} else if (poll_result == 0) {
					ast_log(LOG_WARNING, "Poll timed out while waiting for data\n");
				} else {
					ast_log(LOG_WARNING, "Poll error: %s\n", strerror(errno));
				}
			}

			ast_log(LOG_ERROR, "Failed to read payload from AudioSocket: %s\n", strerror(errno));
			ret = -1;
			break;
		}
		if (n == 0) {
			ast_log(LOG_ERROR, "Insufficient payload read from AudioSocket\n");
			ret = -1;
			break;
		}
		i += n;
	}

	if (ret != 0) {
		ast_free(data);
		return NULL;
	}

	f.data.ptr = data;
	f.datalen = *length;
	f.samples = *length / 2;

	/* The frame steals data, so it doesn't need to be freed here */
	return ast_frisolate(&f);
}

/* END_PINNED_BASELINE_FUNCTION */

/* BEGIN_PATCHED_FUNCTION */
struct ast_frame *patched_receive_frame_with_hangup(const int svc,
	int *const hangup)
{
	int i = 0, n = 0, ret = 0;
	int header_bytes = 0;
	struct ast_frame f = {
		.frametype = AST_FRAME_VOICE,
		.subclass.format = ast_format_slin,
		.src = "AudioSocket",
		.mallocd = AST_MALLOCD_DATA,
	};
	uint8_t header[3];
	uint8_t *kind = &header[0];
	uint16_t *length = (uint16_t *) &header[1];
	uint8_t *data;

	if (hangup) {
		*hangup = 0;
	}

	/*
	 * The AudioSocket connection is nonblocking. A single read is not enough
	 * for a TCP frame header: it may return a partial header or EAGAIN after
	 * the channel wait reports readiness. Yield immediately when no header byte
	 * was consumed, but never discard a partial header: wait once using the
	 * payload reader's 5 ms bound and fail closed if it remains incomplete.
	 */
	while (header_bytes < (int)sizeof(header)) {
		n = read(svc, header + header_bytes, sizeof(header) - header_bytes);
		if (n > 0) {
			header_bytes += n;
			continue;
		}
		if (n == 0) {
			if (header_bytes == 0) {
				/* Socket closure before the next frame is a normal hangup. */
				if (hangup) {
					*hangup = 1;
				}
				return NULL;
			}
			ast_log(LOG_ERROR, "Insufficient header read from AudioSocket\n");
			return NULL;
		}
		if (errno == EINTR) {
			continue;
		}
		if (errno == EAGAIN || errno == EWOULDBLOCK) {
			if (header_bytes == 0) {
				/* No bytes were consumed, so retrying later cannot desync a frame. */
				return &ast_null_frame;
			}
			int poll_result = ast_wait_for_input(svc, AUDIO_SOCKET_HEADER_POLL_MSEC);
			if (poll_result == 1) {
				continue;
			}
			if (poll_result == 0) {
				ast_log(LOG_WARNING, "Poll timed out while waiting for header data\n");
			} else if (errno == EINTR) {
				continue;
			} else {
				ast_log(LOG_WARNING, "Poll error while reading AudioSocket header: %s\n",
					strerror(errno));
			}
			ast_log(LOG_ERROR, "Failed to read header from AudioSocket because: %s\n",
				strerror(errno));
			return NULL;
		}
		ast_log(LOG_WARNING, "Failed to read header from AudioSocket because: %s\n",
			strerror(errno));
		return NULL;
	}

	if (*kind == AST_AUDIOSOCKET_KIND_HANGUP) {
		/* Requested hangup. */
		if (hangup) {
			*hangup = 1;
		}
		return NULL;
	}

	if (*kind != AST_AUDIOSOCKET_KIND_AUDIO) {
		ast_log(LOG_ERROR, "Received AudioSocket message other than hangup or audio, refer to protocol specification for valid message types\n");
		return NULL;
	}

	/* Swap endianess of length if needed. */
	*length = ntohs(*length);
	if (*length < 1) {
		ast_log(LOG_ERROR, "Invalid message length received from AudioSocket server. \n");
		return NULL;
	}

	data = ast_malloc(*length);
	if (!data) {
		ast_log(LOG_ERROR, "Failed to allocate for data from AudioSocket\n");
		return NULL;
	}

	ret = 0;
	n = 0;
	i = 0;
	while (i < *length) {
		n = read(svc, data + i, *length - i);
		if (n == -1) {
			if (errno == EAGAIN || errno == EWOULDBLOCK) {
				int poll_result = ast_wait_for_input(svc, 5);

				if (poll_result == 1) {
					continue;
				} else if (poll_result == 0) {
					ast_log(LOG_WARNING, "Poll timed out while waiting for data\n");
				} else {
					ast_log(LOG_WARNING, "Poll error: %s\n", strerror(errno));
				}
			}

			ast_log(LOG_ERROR, "Failed to read payload from AudioSocket: %s\n", strerror(errno));
			ret = -1;
			break;
		}
		if (n == 0) {
			ast_log(LOG_ERROR, "Insufficient payload read from AudioSocket\n");
			ret = -1;
			break;
		}
		i += n;
	}

	if (ret != 0) {
		ast_free(data);
		return NULL;
	}

	f.data.ptr = data;
	f.datalen = *length;
	f.samples = *length / 2;

	/* The frame steals data, so it doesn't need to be freed here */
	return ast_frisolate(&f);
}

/* END_PATCHED_FUNCTION */

typedef struct ast_frame *(*receive_fn)(int svc, int *hangup);

static const uint8_t audio_frame[] = {0x10, 0x00, 0x04, 1, 2, 3, 4};

static void fail_test(const char *name, const char *detail)
{
	fprintf(stderr, "%s: %s\n", name, detail);
	exit(EXIT_FAILURE);
}

static void require_test(int condition, const char *name, const char *detail)
{
	if (!condition) {
		fail_test(name, detail);
	}
}

static void close_pair(int sockets[2])
{
	close(sockets[0]);
	close(sockets[1]);
}

static void open_pair(int sockets[2])
{
	int flags;

	if (socketpair(AF_UNIX, SOCK_STREAM, 0, sockets) < 0) {
		fail_test("socketpair", strerror(errno));
	}
	flags = fcntl(sockets[0], F_GETFL, 0);
	if (flags < 0 || fcntl(sockets[0], F_SETFL, flags | O_NONBLOCK) < 0) {
		close_pair(sockets);
		fail_test("fcntl", strerror(errno));
	}
}

static void write_all(int fd, const uint8_t *data, size_t length, const char *name)
{
	while (length) {
		ssize_t written = write(fd, data, length);
		if (written > 0) {
			data += written;
			length -= (size_t)written;
		} else if (written < 0 && errno == EINTR) {
			continue;
		} else {
			fail_test(name, strerror(errno));
		}
	}
}

static double monotonic_millis(void)
{
	struct timespec now;
	if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
		fail_test("clock_gettime", strerror(errno));
	}
	return (double)now.tv_sec * 1000.0 + (double)now.tv_nsec / 1000000.0;
}

static void release_frame(struct ast_frame *frame)
{
	if (frame && frame != &ast_null_frame) {
		ast_free(frame->data.ptr);
		ast_free(frame);
	}
}

static void require_pcm(struct ast_frame *frame, const char *name)
{
	require_test(frame && frame != &ast_null_frame, name, "expected a PCM frame");
	require_test(frame->frametype == AST_FRAME_VOICE, name, "wrong frame type");
	require_test(frame->datalen == 4, name, "wrong PCM length");
	require_test(memcmp(frame->data.ptr, audio_frame + 3, 4) == 0, name,
		"PCM payload was changed");
	release_frame(frame);
}

struct delayed_write {
	int fd;
	const uint8_t *prefix;
	size_t prefix_length;
	const uint8_t *suffix;
	size_t suffix_length;
	long delay_nanoseconds;
	_Atomic int prefix_written;
};

static void *write_delayed_suffix(void *argument)
{
	struct delayed_write *writer = argument;
	struct timespec delay = {
		.tv_sec = writer->delay_nanoseconds / 1000000000L,
		.tv_nsec = writer->delay_nanoseconds % 1000000000L,
	};

	write_all(writer->fd, writer->prefix, writer->prefix_length, "fragment prefix");
	atomic_store(&writer->prefix_written, 1);
	nanosleep(&delay, NULL);
	write_all(writer->fd, writer->suffix, writer->suffix_length, "fragment suffix");
	return NULL;
}

static void wait_for_prefix(struct delayed_write *writer)
{
	while (!atomic_load(&writer->prefix_written)) {
		struct timespec pause = {.tv_nsec = 100000L};
		nanosleep(&pause, NULL);
	}
}

static void test_idle_and_next_pcm(receive_fn receive, int patched)
{
	int sockets[2];
	int hangup = 0;
	double elapsed;
	struct ast_frame *frame;

	open_pair(sockets);
	elapsed = monotonic_millis();
	frame = receive(sockets[0], &hangup);
	elapsed = monotonic_millis() - elapsed;
	if (patched) {
		require_test(frame == &ast_null_frame && hangup == 0, "patched idle EAGAIN",
			"expected ast_null_frame without consuming a header");
		require_test(elapsed < 20.0, "patched idle EAGAIN", "idle read was not bounded");
	} else {
		require_test(frame == NULL && hangup == 0, "baseline idle EAGAIN",
			"expected the known NULL/error result");
	}

	write_all(sockets[1], audio_frame, sizeof(audio_frame), "next PCM frame");
	require_pcm(receive(sockets[0], &hangup), patched ? "patched next PCM" : "baseline next PCM");
	close_pair(sockets);
}

static void test_fragmented_header(receive_fn receive)
{
	int sockets[2];
	struct delayed_write writer = {
		.prefix = audio_frame,
		.prefix_length = 1,
		.suffix = audio_frame + 1,
		.suffix_length = sizeof(audio_frame) - 1,
		.delay_nanoseconds = 1000000L,
	};
	pthread_t thread;

	open_pair(sockets);
	writer.fd = sockets[1];
	if (pthread_create(&thread, NULL, write_delayed_suffix, &writer) != 0) {
		close_pair(sockets);
		fail_test("fragmented header", "pthread_create failed");
	}
	wait_for_prefix(&writer);
	require_pcm(receive(sockets[0], NULL), "fragmented header");
	pthread_join(thread, NULL);
	close_pair(sockets);
}

static void test_stalled_partial_header(receive_fn receive)
{
	int sockets[2];
	int hangup = 0;
	double elapsed;
	struct ast_frame *frame;

	open_pair(sockets);
	write_all(sockets[1], audio_frame, 1, "stalled header");
	elapsed = monotonic_millis();
	frame = receive(sockets[0], &hangup);
	elapsed = monotonic_millis() - elapsed;
	require_test(frame == NULL && hangup == 0, "stalled partial header",
		"expected a bounded fatal result");
	require_test(elapsed >= 4.0 && elapsed < 100.0, "stalled partial header",
		"partial-header wait was not bounded by the 5 ms poll");
	close_pair(sockets);
}

static void test_fragmented_payload(receive_fn receive)
{
	int sockets[2];
	struct delayed_write writer = {
		.prefix = audio_frame,
		.prefix_length = 5,
		.suffix = audio_frame + 5,
		.suffix_length = 2,
		.delay_nanoseconds = 1000000L,
	};
	pthread_t thread;

	open_pair(sockets);
	writer.fd = sockets[1];
	if (pthread_create(&thread, NULL, write_delayed_suffix, &writer) != 0) {
		close_pair(sockets);
		fail_test("fragmented payload", "pthread_create failed");
	}
	wait_for_prefix(&writer);
	require_pcm(receive(sockets[0], NULL), "fragmented payload");
	pthread_join(thread, NULL);
	close_pair(sockets);
}

static void test_eof_and_explicit_hangup(receive_fn receive)
{
	int sockets[2];
	int hangup;
	struct ast_frame *frame;
	const uint8_t hangup_frame[] = {AST_AUDIOSOCKET_KIND_HANGUP, 0x00, 0x00};

	open_pair(sockets);
	close(sockets[1]);
	hangup = 0;
	frame = receive(sockets[0], &hangup);
	require_test(frame == NULL && hangup == 1, "clean EOF", "EOF was not reported as hangup");
	close(sockets[0]);

	open_pair(sockets);
	write_all(sockets[1], hangup_frame, sizeof(hangup_frame), "explicit hangup");
	hangup = 0;
	frame = receive(sockets[0], &hangup);
	require_test(frame == NULL && hangup == 1, "explicit hangup",
		"hangup frame was not reported");
	close_pair(sockets);

	open_pair(sockets);
	write_all(sockets[1], audio_frame, 1, "partial EOF");
	close(sockets[1]);
	hangup = 0;
	frame = receive(sockets[0], &hangup);
	require_test(frame == NULL && hangup == 0, "partial-header EOF",
		"partial header was reported as a clean hangup");
	close(sockets[0]);
}

static void test_invalid_headers_and_payload(receive_fn receive)
{
	int sockets[2];
	int hangup;
	struct ast_frame *frame;
	const uint8_t invalid_kind[] = {0x03, 0x00, 0x01};
	const uint8_t invalid_length[] = {AST_AUDIOSOCKET_KIND_AUDIO, 0x00, 0x00};

	open_pair(sockets);
	write_all(sockets[1], invalid_kind, sizeof(invalid_kind), "invalid kind");
	hangup = 0;
	frame = receive(sockets[0], &hangup);
	require_test(frame == NULL && hangup == 0, "invalid kind", "invalid kind was accepted");
	close_pair(sockets);

	open_pair(sockets);
	write_all(sockets[1], invalid_length, sizeof(invalid_length), "invalid length");
	hangup = 0;
	frame = receive(sockets[0], &hangup);
	require_test(frame == NULL && hangup == 0, "invalid length", "zero length was accepted");
	close_pair(sockets);

	open_pair(sockets);
	write_all(sockets[1], audio_frame, 5, "partial payload");
	close(sockets[1]);
	hangup = 0;
	frame = receive(sockets[0], &hangup);
	require_test(frame == NULL && hangup == 0, "partial payload EOF",
		"incomplete PCM payload was accepted");
	close(sockets[0]);
}

static int run_mode(const char *mode)
{
	const int patched = strcmp(mode, "patched") == 0;
	receive_fn receive;

	if (!patched && strcmp(mode, "baseline") != 0) {
		fprintf(stderr, "usage: %s baseline|patched\n", "test-res-audiosocket-header-read");
		return EXIT_FAILURE;
	}
	receive = patched ? patched_receive_frame_with_hangup : baseline_receive_frame_with_hangup;
	test_idle_and_next_pcm(receive, patched);
	if (!patched) {
		puts("baseline: idle EAGAIN returned the known NULL/error result");
		return EXIT_SUCCESS;
	}
	test_fragmented_header(receive);
	test_stalled_partial_header(receive);
	test_fragmented_payload(receive);
	test_eof_and_explicit_hangup(receive);
	test_invalid_headers_and_payload(receive);
	puts("patched: AudioSocket header and payload regression tests passed");
	return EXIT_SUCCESS;
}

int main(int argc, char **argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: %s baseline|patched\n", argv[0]);
		return EXIT_FAILURE;
	}
	return run_mode(argv[1]);
}
