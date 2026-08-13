#ifndef QUICKDRAW_REGION_OPS_H
#define QUICKDRAW_REGION_OPS_H

#include "quickdraw_bitblt.h"
#include <stddef.h>
#include <stdint.h>

typedef enum { QRO_INTERSECT, QRO_UNION, QRO_DIFF, QRO_XOR } QROp;

typedef struct {
    int width, height, stride;
    uint8_t *bits;
} QROMask;

typedef struct { int left, right; } QRORun;

typedef struct {
    int y, count;
    int16_t *x;
} QROEvent;

typedef struct {
    uint64_t area, bbox_area, active_lines, runs, vertical_events, transitions;
    size_t storage_bytes, temporary_bytes;
    uint64_t allocations;
} QROStats;

typedef struct { int width, height, stride; uint8_t *bits; } QROB0;
typedef struct {
    int width, height, top, left, bottom, right;
    size_t *offsets; QRORun *runs; size_t run_count;
} QROB1;
typedef struct {
    int width, height, top, left, bottom, right;
    QROEvent *events; size_t event_count;
} QROB2;

int qro_get(const QROMask *, int y, int x);
void qro_set(QROMask *, int y, int x, int value);
void qro_stats_mask(const QROMask *, QROStats *);

int qro_b0_build(const QROMask *, QROB0 *, QROStats *);
int qro_b1_build(const QROMask *, QROB1 *, QROStats *);
int qro_b2_build(const QROMask *, QROB2 *, QROStats *);
void qro_b0_free(QROB0 *); void qro_b1_free(QROB1 *); void qro_b2_free(QROB2 *);

int qro_b0_op(const QROB0 *, const QROB0 *, QROp, QROB0 *, QROStats *);
int qro_b1_op(const QROB1 *, const QROB1 *, QROp, QROB1 *, QROStats *);
int qro_b2_op(const QROB2 *, const QROB2 *, QROp, QROB2 *, QROStats *);

int qro_b0_apply(const QROB0 *, const QDBitmap *, QDRect, QDBitmap *, QDRect);
int qro_b1_apply(const QROB1 *, const QDBitmap *, QDRect, QDBitmap *, QDRect);
int qro_b2_apply(const QROB2 *, const QDBitmap *, QDRect, QDBitmap *, QDRect);

#endif
