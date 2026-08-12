#include "quickdraw_bitblt.h"

#include <stdlib.h>
#include <string.h>


static int rect_width(QDRect rect) { return rect.right - rect.left; }
static int rect_height(QDRect rect) { return rect.bottom - rect.top; }


static int valid_bitmap(const QDBitmap *bitmap) {
    if (!bitmap || !bitmap->base) {
        return 0;
    }
    int width = rect_width(bitmap->bounds);
    int height = rect_height(bitmap->bounds);
    if (bitmap->row_bytes <= 0 || width < 0 || height < 0) {
        return 0;
    }
    return width <= bitmap->row_bytes * 8
        && (size_t) bitmap->row_bytes * (size_t) height <= bitmap->size;
}


static int contains(QDRect outer, QDRect inner) {
    return inner.top >= outer.top && inner.left >= outer.left
        && inner.bottom <= outer.bottom && inner.right <= outer.right;
}


static int validate(const QDBitmap *src, QDRect src_rect,
                    const QDBitmap *dst, QDRect dst_rect) {
    if (!valid_bitmap(src) || !valid_bitmap(dst)) {
        return -1;
    }
    if (rect_width(src_rect) != rect_width(dst_rect)
            || rect_height(src_rect) != rect_height(dst_rect)) {
        return -1;
    }
    if (rect_width(dst_rect) <= 0 || rect_height(dst_rect) <= 0) {
        return 0;
    }
    return contains(src->bounds, src_rect) && contains(dst->bounds, dst_rect)
        ? 1 : -1;
}


static uint8_t get_bit(const QDBitmap *bitmap, int y, int x) {
    size_t row = (size_t) (y - bitmap->bounds.top) * (size_t) bitmap->row_bytes;
    int local_x = x - bitmap->bounds.left;
    return (uint8_t) ((bitmap->base[row + (size_t) local_x / 8]
                       >> (7 - (local_x & 7))) & 1U);
}


static void put_bit(QDBitmap *bitmap, int y, int x, uint8_t value) {
    size_t row = (size_t) (y - bitmap->bounds.top) * (size_t) bitmap->row_bytes;
    int local_x = x - bitmap->bounds.left;
    uint8_t *byte = &bitmap->base[row + (size_t) local_x / 8];
    uint8_t mask = (uint8_t) (0x80U >> (local_x & 7));
    *byte = value ? (uint8_t) (*byte | mask) : (uint8_t) (*byte & (uint8_t) ~mask);
}


/* Returns n bits in the low end of the result, first bitmap bit most significant. */
static uint64_t read_bits(const QDBitmap *bitmap, int y, int x, int n) {
    uint64_t value = 0;
    int consumed = 0;
    while (consumed < n) {
        int local_x = x + consumed - bitmap->bounds.left;
        size_t row = (size_t) (y - bitmap->bounds.top) * (size_t) bitmap->row_bytes;
        uint8_t byte = bitmap->base[row + (size_t) local_x / 8];
        int offset = local_x & 7;
        int take = 8 - offset;
        if (take > n - consumed) {
            take = n - consumed;
        }
        int shift = 8 - offset - take;
        uint8_t mask = (uint8_t) ((1U << take) - 1U);
        value = (value << take) | ((byte >> shift) & mask);
        consumed += take;
    }
    return value;
}


static void write_bits(QDBitmap *bitmap, int y, int x, int n, uint64_t value) {
    int consumed = 0;
    while (consumed < n) {
        int local_x = x + consumed - bitmap->bounds.left;
        size_t row = (size_t) (y - bitmap->bounds.top) * (size_t) bitmap->row_bytes;
        uint8_t *byte = &bitmap->base[row + (size_t) local_x / 8];
        int offset = local_x & 7;
        int take = 8 - offset;
        if (take > n - consumed) {
            take = n - consumed;
        }
        int source_shift = n - consumed - take;
        int destination_shift = 8 - offset - take;
        uint8_t field = (uint8_t) ((value >> source_shift) & ((1ULL << take) - 1ULL));
        uint8_t mask = (uint8_t) (((1U << take) - 1U) << destination_shift);
        *byte = (uint8_t) ((*byte & (uint8_t) ~mask) | (uint8_t) (field << destination_shift));
        consumed += take;
    }
}


/* R0: independent oracle; snapshot first, then copy one bit at a time. */
int qd_bitblt_r0(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats) {
    int status = validate(src, src_rect, dst, dst_rect);
    if (status <= 0) {
        return status < 0 ? -1 : 0;
    }
    int width = rect_width(dst_rect);
    int height = rect_height(dst_rect);
    size_t packed_row = ((size_t) width + 7U) / 8U;
    size_t temporary_size = packed_row * (size_t) height;
    uint8_t *snapshot = (uint8_t *) calloc(temporary_size, 1);
    if (!snapshot) {
        return -1;
    }
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            uint8_t bit = get_bit(src, src_rect.top + y, src_rect.left + x);
            if (bit) {
                snapshot[(size_t) y * packed_row + (size_t) x / 8]
                    |= (uint8_t) (0x80U >> (x & 7));
            }
        }
    }
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            uint8_t bit = (uint8_t) ((snapshot[(size_t) y * packed_row + (size_t) x / 8]
                                     >> (7 - (x & 7))) & 1U);
            put_bit(dst, dst_rect.top + y, dst_rect.left + x, bit);
        }
    }
    if (stats) {
        stats->useful_bits += (uint64_t) width * (uint64_t) height;
        stats->bit_reads += (uint64_t) width * (uint64_t) height;
        stats->bit_writes += (uint64_t) width * (uint64_t) height;
        if (temporary_size > stats->peak_temporary_bytes) {
            stats->peak_temporary_bytes = temporary_size;
        }
    }
    free(snapshot);
    return 0;
}


static void copy_32(const QDBitmap *src, int src_y, int src_x,
                    QDBitmap *dst, int dst_y, int dst_x, int width,
                    QDStats *stats) {
    int position = 0;
    while (position < width) {
        int destination_local = dst_x + position - dst->bounds.left;
        int count = 32 - (destination_local & 31);
        if (count > width - position) {
            count = width - position;
        }
        uint64_t value = read_bits(src, src_y, src_x + position, count);
        write_bits(dst, dst_y, dst_x + position, count, value);
        if (stats) {
            stats->word_iterations++;
            if (count != 32) {
                stats->edge_masks++;
            }
            if (((src_x + position - src->bounds.left)
                 - destination_local) & 31) {
                stats->reconstructed_words++;
            } else if (count == 32) {
                stats->aligned_words++;
            }
        }
        position += count;
    }
}


/* R1: generic 32-bit destination blocks; snapshot only when storage aliases. */
int qd_bitblt_r1(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats) {
    int status = validate(src, src_rect, dst, dst_rect);
    if (status <= 0) {
        return status < 0 ? -1 : 0;
    }
    int width = rect_width(dst_rect);
    int height = rect_height(dst_rect);
    const QDBitmap *effective_src = src;
    QDRect effective_rect = src_rect;
    QDBitmap snapshot_bitmap = {0};
    uint8_t *snapshot = NULL;

    if (src->base == dst->base) {
        size_t packed_row = ((size_t) width + 7U) / 8U;
        size_t temporary_size = packed_row * (size_t) height;
        snapshot = (uint8_t *) calloc(temporary_size, 1);
        if (!snapshot) {
            return -1;
        }
        snapshot_bitmap = (QDBitmap) {
            snapshot, temporary_size, (int) packed_row,
            {0, 0, height, (int) (packed_row * 8U)},
        };
        for (int y = 0; y < height; ++y) {
            copy_32(src, src_rect.top + y, src_rect.left,
                    &snapshot_bitmap, y, 0, width, stats);
        }
        effective_src = &snapshot_bitmap;
        effective_rect = (QDRect) {0, 0, height, width};
        if (stats && temporary_size > stats->peak_temporary_bytes) {
            stats->peak_temporary_bytes = temporary_size;
        }
    }

    for (int y = 0; y < height; ++y) {
        copy_32(effective_src, effective_rect.top + y, effective_rect.left,
                dst, dst_rect.top + y, dst_rect.left, width, stats);
    }
    if (stats) {
        stats->useful_bits += (uint64_t) width * (uint64_t) height;
    }
    free(snapshot);
    return 0;
}


static int same_word_alignment(const QDBitmap *src, int src_x,
                               const QDBitmap *dst, int dst_x) {
    return ((src_x - src->bounds.left) & 15) == ((dst_x - dst->bounds.left) & 15);
}


static void copy_16_row(const QDBitmap *src, int src_y, int src_x,
                        QDBitmap *dst, int dst_y, int dst_x, int width,
                        int reverse, QDStats *stats) {
    int aligned = same_word_alignment(src, src_x, dst, dst_x);
    int position = reverse ? width : 0;
    while ((!reverse && position < width) || (reverse && position > 0)) {
        int count;
        int start;
        if (!reverse) {
            int destination_local = dst_x + position - dst->bounds.left;
            count = 16 - (destination_local & 15);
            if (count > width - position) {
                count = width - position;
            }
            start = position;
            position += count;
        } else {
            int end_local = dst_x + position - dst->bounds.left;
            count = end_local & 15;
            if (count == 0) {
                count = 16;
            }
            if (count > position) {
                count = position;
            }
            position -= count;
            start = position;
        }

        if (aligned && count == 16) {
            size_t src_offset = (size_t) (src_y - src->bounds.top) * (size_t) src->row_bytes
                + (size_t) (src_x + start - src->bounds.left) / 8U;
            size_t dst_offset = (size_t) (dst_y - dst->bounds.top) * (size_t) dst->row_bytes
                + (size_t) (dst_x + start - dst->bounds.left) / 8U;
            uint16_t value;
            memcpy(&value, src->base + src_offset, sizeof value);
            memcpy(dst->base + dst_offset, &value, sizeof value);
            if (stats) {
                stats->aligned_words++;
            }
        } else {
            uint64_t value = read_bits(src, src_y, src_x + start, count);
            write_bits(dst, dst_y, dst_x + start, count, value);
            if (stats) {
                if (count != 16) {
                    stats->edge_masks++;
                }
                if (!aligned) {
                    stats->reconstructed_words++;
                }
            }
        }
        if (stats) {
            stats->word_iterations++;
            stats->reverse_words += (uint64_t) reverse;
        }
    }
}


/*
 * R2: independently written from the historical mechanisms: 16-bit edges,
 * overlap-safe direction, reconstructed unaligned words, aligned fast path.
 */
int qd_bitblt_r2(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats) {
    int status = validate(src, src_rect, dst, dst_rect);
    if (status <= 0) {
        return status < 0 ? -1 : 0;
    }
    int width = rect_width(dst_rect);
    int height = rect_height(dst_rect);
    int same_storage = src->base == dst->base;
    int reverse_rows = same_storage
        && (src_rect.top - src->bounds.top) < (dst_rect.top - dst->bounds.top);
    int reverse_words = same_storage && !reverse_rows
        && (src_rect.top - src->bounds.top) == (dst_rect.top - dst->bounds.top)
        && (src_rect.left - src->bounds.left) < (dst_rect.left - dst->bounds.left);

    for (int row = 0; row < height; ++row) {
        int logical_row = reverse_rows ? height - 1 - row : row;
        copy_16_row(src, src_rect.top + logical_row, src_rect.left,
                    dst, dst_rect.top + logical_row, dst_rect.left,
                    width, reverse_words, stats);
    }
    if (stats) {
        stats->useful_bits += (uint64_t) width * (uint64_t) height;
        stats->reverse_rows += reverse_rows ? (uint64_t) height : 0;
    }
    return 0;
}


static int same_64_alignment(const QDBitmap *src, int src_x,
                             const QDBitmap *dst, int dst_x) {
    return ((src_x - src->bounds.left) & 63) == ((dst_x - dst->bounds.left) & 63);
}


static void copy_64_row(const QDBitmap *src, int src_y, int src_x,
                        QDBitmap *dst, int dst_y, int dst_x, int width,
                        int reverse, QDStats *stats) {
    int aligned = same_64_alignment(src, src_x, dst, dst_x);
    int position = reverse ? width : 0;
    while ((!reverse && position < width) || (reverse && position > 0)) {
        int count;
        int start;
        if (!reverse) {
            int destination_local = dst_x + position - dst->bounds.left;
            count = 64 - (destination_local & 63);
            if (count > width - position) {
                count = width - position;
            }
            start = position;
            position += count;
        } else {
            int end_local = dst_x + position - dst->bounds.left;
            count = end_local & 63;
            if (count == 0) {
                count = 64;
            }
            if (count > position) {
                count = position;
            }
            position -= count;
            start = position;
        }

        if (aligned && count == 64) {
            size_t src_offset = (size_t) (src_y - src->bounds.top) * (size_t) src->row_bytes
                + (size_t) (src_x + start - src->bounds.left) / 8U;
            size_t dst_offset = (size_t) (dst_y - dst->bounds.top) * (size_t) dst->row_bytes
                + (size_t) (dst_x + start - dst->bounds.left) / 8U;
            uint64_t value;
            memcpy(&value, src->base + src_offset, sizeof value);
            memcpy(dst->base + dst_offset, &value, sizeof value);
            if (stats) {
                stats->aligned_words++;
            }
        } else {
            uint64_t value = read_bits(src, src_y, src_x + start, count);
            write_bits(dst, dst_y, dst_x + start, count, value);
            if (stats) {
                if (count != 64) {
                    stats->edge_masks++;
                }
                if (!aligned) {
                    stats->reconstructed_words++;
                }
            }
        }
        if (stats) {
            stats->word_iterations++;
            stats->reverse_words += (uint64_t) reverse;
        }
    }
}


/* R3: byte-aligned memmove path; otherwise overlap-safe 64-bit blocks. */
int qd_bitblt_r3(const QDBitmap *src, QDRect src_rect,
                 QDBitmap *dst, QDRect dst_rect, QDStats *stats) {
    int status = validate(src, src_rect, dst, dst_rect);
    if (status <= 0) {
        return status < 0 ? -1 : 0;
    }
    int width = rect_width(dst_rect);
    int height = rect_height(dst_rect);
    int source_x = src_rect.left - src->bounds.left;
    int destination_x = dst_rect.left - dst->bounds.left;
    int byte_aligned = ((source_x | destination_x | width) & 7) == 0;
    int same_storage = src->base == dst->base;
    int reverse_rows = same_storage
        && (src_rect.top - src->bounds.top) < (dst_rect.top - dst->bounds.top);

    if (byte_aligned) {
        size_t bytes = (size_t) width / 8U;
        for (int row = 0; row < height; ++row) {
            int logical_row = reverse_rows ? height - 1 - row : row;
            size_t src_offset = (size_t) (src_rect.top + logical_row - src->bounds.top)
                * (size_t) src->row_bytes + (size_t) source_x / 8U;
            size_t dst_offset = (size_t) (dst_rect.top + logical_row - dst->bounds.top)
                * (size_t) dst->row_bytes + (size_t) destination_x / 8U;
            memmove(dst->base + dst_offset, src->base + src_offset, bytes);
        }
        if (stats) {
            stats->useful_bits += (uint64_t) width * (uint64_t) height;
            stats->memmove_bytes += bytes * (uint64_t) height;
            stats->reverse_rows += reverse_rows ? (uint64_t) height : 0;
        }
        return 0;
    }

    int reverse_words = same_storage && !reverse_rows
        && (src_rect.top - src->bounds.top) == (dst_rect.top - dst->bounds.top)
        && source_x < destination_x;
    for (int row = 0; row < height; ++row) {
        int logical_row = reverse_rows ? height - 1 - row : row;
        copy_64_row(src, src_rect.top + logical_row, src_rect.left,
                    dst, dst_rect.top + logical_row, dst_rect.left,
                    width, reverse_words, stats);
    }
    if (stats) {
        stats->useful_bits += (uint64_t) width * (uint64_t) height;
        stats->reverse_rows += reverse_rows ? (uint64_t) height : 0;
    }
    return 0;
}
