#ifndef QUICKDRAW_REGIONS_H
#define QUICKDRAW_REGIONS_H

#include "quickdraw_bitblt.h"

#include <stddef.h>
#include <stdint.h>

typedef struct {
    int width;
    int height;
    int stride;
    uint8_t *bits;
} QRMask;

typedef struct {
    int left;
    int right;
} QRRun;

typedef struct {
    uint64_t covered_pixels;
    uint64_t bbox_pixels;
    uint64_t active_lines;
    uint64_t runs;
    uint64_t vertical_events;
    uint64_t transition_coordinates;
    uint64_t scanned_mask_bits;
    uint64_t backend_calls;
    uint64_t replayed_coordinates;
    size_t storage_bytes;
    size_t peak_temporary_bytes;
    uint64_t allocations;
} QRStats;

typedef struct {
    int top, left, bottom, right;
    int width, height, stride;
    uint8_t *mask;
} QRG0;

typedef struct {
    int top, left, bottom, right;
    int height;
    size_t *line_offsets;
    QRRun *runs;
    size_t run_count;
} QRG1;

typedef struct {
    int top, left, bottom, right;
    int rectangular;
    int16_t *data;
    size_t word_count;
} QRG2;

typedef struct {
    int kind;
    int top, left, bottom, right;
    union {
        QRG0 bitmap;
        QRG1 runs;
    } representation;
} QRG3;

int qr_mask_get(const QRMask *mask, int y, int x);
void qr_mask_set(QRMask *mask, int y, int x, int value);
void qr_describe_mask(const QRMask *mask, QRStats *stats);

int qr_g0_build(const QRMask *mask, QRG0 *region, QRStats *stats);
int qr_g1_build(const QRMask *mask, QRG1 *region, QRStats *stats);
int qr_g2_build(const QRMask *mask, QRG2 *region, QRStats *stats);
int qr_g3_build(const QRMask *mask, QRG3 *region, QRStats *stats);
void qr_g0_free(QRG0 *region);
void qr_g1_free(QRG1 *region);
void qr_g2_free(QRG2 *region);
void qr_g3_free(QRG3 *region);

int qr_g0_apply(const QRG0 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats);
int qr_g1_apply(const QRG1 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats);
int qr_g2_apply(const QRG2 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats);
int qr_g3_apply(const QRG3 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats);

#endif
