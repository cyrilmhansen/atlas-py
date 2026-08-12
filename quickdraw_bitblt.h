#ifndef QUICKDRAW_BITBLT_H
#define QUICKDRAW_BITBLT_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int top;
    int left;
    int bottom;
    int right;
} QDRect;

typedef struct {
    uint8_t *base;
    size_t size;
    int row_bytes;
    QDRect bounds;
} QDBitmap;

typedef struct {
    uint64_t useful_bits;
    uint64_t bit_reads;
    uint64_t bit_writes;
    uint64_t word_iterations;
    uint64_t edge_masks;
    uint64_t reconstructed_words;
    uint64_t aligned_words;
    uint64_t reverse_rows;
    uint64_t reverse_words;
    uint64_t memmove_bytes;
    size_t peak_temporary_bytes;
} QDStats;

typedef int (*QDBitBlt)(const QDBitmap *, QDRect, QDBitmap *, QDRect,
                        QDStats *);

int qd_bitblt_r0(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats);
int qd_bitblt_r1(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats);
int qd_bitblt_r2(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats);
int qd_bitblt_r3(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats);

#endif
