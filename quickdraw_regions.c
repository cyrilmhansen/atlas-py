#include "quickdraw_regions.h"

#include <limits.h>
#include <stdlib.h>
#include <string.h>


enum { QR_SENTINEL = 32767 };
enum { QR_G3_RECTANGLE, QR_G3_BITMAP, QR_G3_RUNS };


int qr_mask_get(const QRMask *mask, int y, int x) {
    return (mask->bits[(size_t) y * (size_t) mask->stride + (size_t) x / 8]
            >> (7 - (x & 7))) & 1;
}


void qr_mask_set(QRMask *mask, int y, int x, int value) {
    uint8_t *byte = &mask->bits[(size_t) y * (size_t) mask->stride + (size_t) x / 8];
    uint8_t bit = (uint8_t) (0x80U >> (x & 7));
    *byte = value ? (uint8_t) (*byte | bit) : (uint8_t) (*byte & (uint8_t) ~bit);
}


static void mask_bbox(const QRMask *mask, int *top, int *left, int *bottom, int *right) {
    *top = mask->height;
    *left = mask->width;
    *bottom = 0;
    *right = 0;
    for (int y = 0; y < mask->height; ++y) {
        for (int x = 0; x < mask->width; ++x) {
            if (!qr_mask_get(mask, y, x)) {
                continue;
            }
            if (y < *top) *top = y;
            if (x < *left) *left = x;
            if (y + 1 > *bottom) *bottom = y + 1;
            if (x + 1 > *right) *right = x + 1;
        }
    }
    if (*top == mask->height) {
        *top = *left = *bottom = *right = 0;
    }
}


void qr_describe_mask(const QRMask *mask, QRStats *stats) {
    memset(stats, 0, sizeof *stats);
    int top, left, bottom, right;
    mask_bbox(mask, &top, &left, &bottom, &right);
    stats->bbox_pixels = (uint64_t) (right - left) * (uint64_t) (bottom - top);
    for (int y = 0; y < mask->height; ++y) {
        int inside = 0;
        int line_active = 0;
        for (int x = 0; x < mask->width; ++x) {
            int bit = qr_mask_get(mask, y, x);
            stats->covered_pixels += (uint64_t) bit;
            if (bit && !inside) {
                stats->runs++;
                line_active = 1;
            }
            inside = bit;
        }
        stats->active_lines += (uint64_t) line_active;
    }
    for (int y = 0; y <= mask->height; ++y) {
        int changed = 0;
        int previous_delta = 0;
        for (int x = 0; x < mask->width; ++x) {
            int current = y < mask->height ? qr_mask_get(mask, y, x) : 0;
            int previous = y > 0 ? qr_mask_get(mask, y - 1, x) : 0;
            int delta = current ^ previous;
            if (delta != previous_delta) {
                stats->transition_coordinates++;
                changed = 1;
            }
            previous_delta = delta;
        }
        if (previous_delta) {
            stats->transition_coordinates++;
            changed = 1;
        }
        stats->vertical_events += (uint64_t) changed;
    }
}


static int intersect_rect(QDRect a, QDRect b, QDRect *result) {
    result->top = a.top > b.top ? a.top : b.top;
    result->left = a.left > b.left ? a.left : b.left;
    result->bottom = a.bottom < b.bottom ? a.bottom : b.bottom;
    result->right = a.right < b.right ? a.right : b.right;
    return result->top < result->bottom && result->left < result->right;
}


static int copy_run(const QDBitmap *src, QDRect src_rect,
                    QDBitmap *dst, QDRect dst_rect,
                    int y, int left, int right, QRStats *stats) {
    if (left < dst_rect.left) left = dst_rect.left;
    if (right > dst_rect.right) right = dst_rect.right;
    if (y < dst_rect.top || y >= dst_rect.bottom || left >= right) {
        return 0;
    }
    QDRect destination = {y, left, y + 1, right};
    QDRect source = {
        src_rect.top + (y - dst_rect.top),
        src_rect.left + (left - dst_rect.left),
        src_rect.top + (y - dst_rect.top) + 1,
        src_rect.left + (right - dst_rect.left),
    };
    if (stats) stats->backend_calls++;
    return qd_bitblt_r3(src, source, dst, destination, NULL);
}


static uint8_t read_bitmap_bits(const QDBitmap *bitmap, int y, int x, int count) {
    int local_x = x - bitmap->bounds.left;
    size_t row = (size_t) (y - bitmap->bounds.top) * (size_t) bitmap->row_bytes;
    const uint8_t *source = bitmap->base + row + (size_t) local_x / 8;
    int offset = local_x & 7;
    uint16_t window = (uint16_t) source[0] << 8;
    if (offset + count > 8) window |= source[1];
    return (uint8_t) ((window >> (16 - offset - count)) & ((1U << count) - 1U));
}


static uint8_t read_scan_bits(const uint8_t *scan, int x, int count) {
    const uint8_t *source = scan + (size_t) x / 8;
    int offset = x & 7;
    uint16_t window = (uint16_t) source[0] << 8;
    if (offset + count > 8) window |= source[1];
    return (uint8_t) ((window >> (16 - offset - count)) & ((1U << count) - 1U));
}


static void apply_mask_row(const uint8_t *scan, const QDBitmap *src,
                           QDRect src_rect, QDBitmap *dst, QDRect dst_rect,
                           int y, int left, int right, QRStats *stats) {
    int x = left;
    while (x < right) {
        int destination_local = x - dst->bounds.left;
        int count = 8 - (destination_local & 7);
        if (count > right - x) count = right - x;
        uint8_t active = read_scan_bits(scan, x, count);
        if (active) {
            int source_y = src_rect.top + y - dst_rect.top;
            int source_x = src_rect.left + x - dst_rect.left;
            uint8_t source_value = read_bitmap_bits(src, source_y, source_x, count);
            size_t destination_offset = (size_t) (y - dst->bounds.top)
                * (size_t) dst->row_bytes + (size_t) destination_local / 8;
            int shift = 8 - (destination_local & 7) - count;
            uint8_t field_mask = (uint8_t) (active << shift);
            uint8_t field_value = (uint8_t) (source_value << shift);
            dst->base[destination_offset] = (uint8_t) (
                (dst->base[destination_offset] & (uint8_t) ~field_mask)
                | (field_value & field_mask));
        }
        x += count;
    }
    if (stats) stats->scanned_mask_bits += (uint64_t) (right - left);
}


int qr_g0_build(const QRMask *mask, QRG0 *region, QRStats *stats) {
    memset(region, 0, sizeof *region);
    region->width = mask->width;
    region->height = mask->height;
    region->stride = mask->stride;
    size_t bytes = (size_t) mask->stride * (size_t) mask->height;
    region->mask = (uint8_t *) malloc(bytes);
    if (!region->mask) return -1;
    memcpy(region->mask, mask->bits, bytes);
    mask_bbox(mask, &region->top, &region->left, &region->bottom, &region->right);
    if (stats) {
        stats->storage_bytes = sizeof *region + bytes;
        stats->allocations = 1;
    }
    return 0;
}


int qr_g1_build(const QRMask *mask, QRG1 *region, QRStats *stats) {
    memset(region, 0, sizeof *region);
    region->height = mask->height;
    mask_bbox(mask, &region->top, &region->left, &region->bottom, &region->right);
    size_t run_count = 0;
    for (int y = 0; y < mask->height; ++y) {
        int previous = 0;
        for (int x = 0; x < mask->width; ++x) {
            int bit = qr_mask_get(mask, y, x);
            if (bit && !previous) ++run_count;
            previous = bit;
        }
    }
    region->line_offsets = (size_t *) calloc((size_t) mask->height + 1,
                                              sizeof *region->line_offsets);
    region->runs = run_count ? (QRRun *) malloc(run_count * sizeof *region->runs) : NULL;
    if (!region->line_offsets || (run_count && !region->runs)) {
        qr_g1_free(region);
        return -1;
    }
    size_t index = 0;
    for (int y = 0; y < mask->height; ++y) {
        region->line_offsets[y] = index;
        int x = 0;
        while (x < mask->width) {
            while (x < mask->width && !qr_mask_get(mask, y, x)) ++x;
            int left = x;
            while (x < mask->width && qr_mask_get(mask, y, x)) ++x;
            if (left < x) region->runs[index++] = (QRRun) {left, x};
        }
    }
    region->line_offsets[mask->height] = index;
    region->run_count = index;
    if (stats) {
        stats->storage_bytes = sizeof *region
            + ((size_t) mask->height + 1) * sizeof *region->line_offsets
            + run_count * sizeof *region->runs;
        stats->allocations = run_count ? 2 : 1;
    }
    return 0;
}


static int mask_is_bbox_rectangle(const QRMask *mask, int top, int left,
                                  int bottom, int right) {
    if (top == bottom || left == right) return 1;
    for (int y = 0; y < mask->height; ++y) {
        for (int x = 0; x < mask->width; ++x) {
            int expected = y >= top && y < bottom && x >= left && x < right;
            if (qr_mask_get(mask, y, x) != expected) return 0;
        }
    }
    return 1;
}


static size_t g2_words_needed(const QRMask *mask) {
    size_t words = 1;
    for (int y = 0; y <= mask->height; ++y) {
        int previous_delta = 0;
        int changes = 0;
        for (int x = 0; x < mask->width; ++x) {
            int current = y < mask->height ? qr_mask_get(mask, y, x) : 0;
            int previous = y > 0 ? qr_mask_get(mask, y - 1, x) : 0;
            int delta = current ^ previous;
            if (delta != previous_delta) ++changes;
            previous_delta = delta;
        }
        if (previous_delta) ++changes;
        if (changes) words += (size_t) changes + 2;
    }
    return words;
}


int qr_g2_build(const QRMask *mask, QRG2 *region, QRStats *stats) {
    memset(region, 0, sizeof *region);
    if (mask->width >= QR_SENTINEL || mask->height >= QR_SENTINEL) return -1;
    mask_bbox(mask, &region->top, &region->left, &region->bottom, &region->right);
    region->rectangular = mask_is_bbox_rectangle(mask, region->top, region->left,
                                                 region->bottom, region->right);
    if (region->rectangular) {
        if (stats) stats->storage_bytes = sizeof *region;
        return 0;
    }
    size_t words = g2_words_needed(mask);
    region->data = (int16_t *) malloc(words * sizeof *region->data);
    if (!region->data) return -1;
    size_t index = 0;
    for (int y = 0; y <= mask->height; ++y) {
        int previous_delta = 0;
        size_t event_start = index;
        region->data[index++] = (int16_t) y;
        for (int x = 0; x < mask->width; ++x) {
            int current = y < mask->height ? qr_mask_get(mask, y, x) : 0;
            int previous = y > 0 ? qr_mask_get(mask, y - 1, x) : 0;
            int delta = current ^ previous;
            if (delta != previous_delta) region->data[index++] = (int16_t) x;
            previous_delta = delta;
        }
        if (previous_delta) region->data[index++] = (int16_t) mask->width;
        if (index == event_start + 1) {
            index = event_start;
        } else {
            region->data[index++] = QR_SENTINEL;
        }
    }
    region->data[index++] = QR_SENTINEL;
    region->word_count = index;
    if (index != words) return -1;
    if (stats) {
        stats->storage_bytes = sizeof *region + words * sizeof *region->data;
        stats->allocations = 1;
    }
    return 0;
}


void qr_g0_free(QRG0 *region) { free(region->mask); memset(region, 0, sizeof *region); }
void qr_g1_free(QRG1 *region) {
    free(region->line_offsets); free(region->runs); memset(region, 0, sizeof *region);
}
void qr_g2_free(QRG2 *region) { free(region->data); memset(region, 0, sizeof *region); }


int qr_g3_build(const QRMask *mask, QRG3 *region, QRStats *stats) {
    memset(region, 0, sizeof *region);
    mask_bbox(mask, &region->top, &region->left, &region->bottom, &region->right);
    if (mask_is_bbox_rectangle(mask, region->top, region->left,
                               region->bottom, region->right)) {
        region->kind = QR_G3_RECTANGLE;
        if (stats) stats->storage_bytes = sizeof *region;
        return 0;
    }

    size_t run_count = 0;
    for (int y = 0; y < mask->height; ++y) {
        int previous = 0;
        for (int x = 0; x < mask->width; ++x) {
            int bit = qr_mask_get(mask, y, x);
            if (bit && !previous) ++run_count;
            previous = bit;
        }
    }
    size_t bitmap_bytes = (size_t) mask->stride * (size_t) mask->height;
    size_t runs_bytes = ((size_t) mask->height + 1) * sizeof(size_t)
        + run_count * sizeof(QRRun);
    QRStats selected = {0};
    int result;
    if (runs_bytes <= bitmap_bytes) {
        region->kind = QR_G3_RUNS;
        result = qr_g1_build(mask, &region->representation.runs, &selected);
        if (!result && stats) {
            *stats = selected;
            stats->storage_bytes = sizeof *region + runs_bytes;
        }
    } else {
        region->kind = QR_G3_BITMAP;
        result = qr_g0_build(mask, &region->representation.bitmap, &selected);
        if (!result && stats) {
            *stats = selected;
            stats->storage_bytes = sizeof *region + bitmap_bytes;
        }
    }
    return result;
}


void qr_g3_free(QRG3 *region) {
    if (region->kind == QR_G3_BITMAP) qr_g0_free(&region->representation.bitmap);
    if (region->kind == QR_G3_RUNS) qr_g1_free(&region->representation.runs);
    memset(region, 0, sizeof *region);
}


int qr_g0_apply(const QRG0 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats) {
    QDRect bbox = {region->top, region->left, region->bottom, region->right};
    QDRect work;
    if (!intersect_rect(bbox, dst_rect, &work)) return 0;
    for (int y = work.top; y < work.bottom; ++y) {
        const uint8_t *scan = region->mask + (size_t) y * (size_t) region->stride;
        apply_mask_row(scan, src, src_rect, dst, dst_rect,
                       y, work.left, work.right, stats);
    }
    return 0;
}


int qr_g1_apply(const QRG1 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats) {
    QDRect bbox = {region->top, region->left, region->bottom, region->right};
    QDRect work;
    if (!intersect_rect(bbox, dst_rect, &work)) return 0;
    for (int y = work.top; y < work.bottom; ++y) {
        for (size_t i = region->line_offsets[y]; i < region->line_offsets[y + 1]; ++i) {
            if (copy_run(src, src_rect, dst, dst_rect, y,
                         region->runs[i].left, region->runs[i].right, stats)) return -1;
        }
    }
    return 0;
}


static void xor_scan_range(uint8_t *scan, int left, int right) {
    while (left < right && (left & 7)) {
        scan[(size_t) left / 8] ^= (uint8_t) (0x80U >> (left & 7));
        ++left;
    }
    while (left + 8 <= right) {
        scan[(size_t) left / 8] ^= 0xffU;
        left += 8;
    }
    while (left < right) {
        scan[(size_t) left / 8] ^= (uint8_t) (0x80U >> (left & 7));
        ++left;
    }
}


int qr_g2_apply(const QRG2 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats) {
    QDRect bbox = {region->top, region->left, region->bottom, region->right};
    QDRect work;
    if (!intersect_rect(bbox, dst_rect, &work)) return 0;
    if (region->rectangular) {
        if (stats) stats->backend_calls++;
        QDRect source = {
            src_rect.top + (work.top - dst_rect.top),
            src_rect.left + (work.left - dst_rect.left),
            src_rect.top + (work.bottom - dst_rect.top),
            src_rect.left + (work.right - dst_rect.left),
        };
        return qd_bitblt_r3(src, source, dst, work, NULL);
    }
    int scan_width = region->right;
    size_t scan_bytes = ((size_t) scan_width + 7U) / 8U;
    uint8_t *scan = (uint8_t *) calloc(scan_bytes, 1);
    if (!scan) return -1;
    if (stats) {
        stats->allocations++;
        if (scan_bytes > stats->peak_temporary_bytes) stats->peak_temporary_bytes = scan_bytes;
    }
    size_t index = 0;
    for (int y = region->top; y < work.bottom; ++y) {
        while (region->data[index] != QR_SENTINEL && region->data[index] == y) {
            ++index;
            int inside = 0;
            int left = 0;
            while (region->data[index] != QR_SENTINEL) {
                int coordinate = region->data[index++];
                if (!inside) left = coordinate;
                else xor_scan_range(scan, left, coordinate);
                inside = !inside;
                if (stats) stats->replayed_coordinates++;
            }
            ++index;
        }
        if (y < work.top) continue;
        apply_mask_row(scan, src, src_rect, dst, dst_rect,
                       y, work.left, work.right, stats);
    }
    free(scan);
    return 0;
}


int qr_g3_apply(const QRG3 *region, const QDBitmap *src, QDRect src_rect,
                QDBitmap *dst, QDRect dst_rect, QRStats *stats) {
    if (region->kind == QR_G3_BITMAP) {
        return qr_g0_apply(&region->representation.bitmap, src, src_rect,
                           dst, dst_rect, stats);
    }
    if (region->kind == QR_G3_RUNS) {
        return qr_g1_apply(&region->representation.runs, src, src_rect,
                           dst, dst_rect, stats);
    }
    QDRect rectangle = {region->top, region->left, region->bottom, region->right};
    QDRect work;
    if (!intersect_rect(rectangle, dst_rect, &work)) return 0;
    QDRect source = {
        src_rect.top + work.top - dst_rect.top,
        src_rect.left + work.left - dst_rect.left,
        src_rect.top + work.bottom - dst_rect.top,
        src_rect.left + work.right - dst_rect.left,
    };
    if (stats) stats->backend_calls++;
    return qd_bitblt_r3(src, source, dst, work, NULL);
}
