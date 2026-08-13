#define _POSIX_C_SOURCE 200809L

#include "quickdraw_regions.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>


typedef enum {
    SHAPE_EMPTY, SHAPE_FULL, SHAPE_RECTANGLE, SHAPE_SPARSE_BANDS,
    SHAPE_DENSE_IRREGULAR, SHAPE_CHECKER, SHAPE_THIN, SHAPE_RANDOM
} Shape;

typedef union {
    QRG0 g0;
    QRG1 g1;
    QRG2 g2;
    QRG3 g3;
} RegionObject;

typedef struct {
    const char *name;
    int (*build)(const QRMask *, RegionObject *, QRStats *);
    int (*apply)(const RegionObject *, const QDBitmap *, QDRect,
                 QDBitmap *, QDRect, QRStats *);
    void (*destroy)(RegionObject *);
} Variant;

static uint64_t random_state = UINT64_C(0x243f6a8885a308d3);
static volatile uint64_t benchmark_sink;


static uint32_t random_u32(void) {
    uint64_t x = random_state;
    x ^= x << 13;
    x ^= x >> 7;
    x ^= x << 17;
    random_state = x;
    return (uint32_t) (x >> 16);
}


static int build_g0(const QRMask *mask, RegionObject *object, QRStats *stats) {
    return qr_g0_build(mask, &object->g0, stats);
}
static int build_g1(const QRMask *mask, RegionObject *object, QRStats *stats) {
    return qr_g1_build(mask, &object->g1, stats);
}
static int build_g2(const QRMask *mask, RegionObject *object, QRStats *stats) {
    return qr_g2_build(mask, &object->g2, stats);
}
static int build_g3(const QRMask *mask, RegionObject *object, QRStats *stats) {
    return qr_g3_build(mask, &object->g3, stats);
}
static int apply_g0(const RegionObject *object, const QDBitmap *src, QDRect sr,
                    QDBitmap *dst, QDRect dr, QRStats *stats) {
    return qr_g0_apply(&object->g0, src, sr, dst, dr, stats);
}
static int apply_g1(const RegionObject *object, const QDBitmap *src, QDRect sr,
                    QDBitmap *dst, QDRect dr, QRStats *stats) {
    return qr_g1_apply(&object->g1, src, sr, dst, dr, stats);
}
static int apply_g2(const RegionObject *object, const QDBitmap *src, QDRect sr,
                    QDBitmap *dst, QDRect dr, QRStats *stats) {
    return qr_g2_apply(&object->g2, src, sr, dst, dr, stats);
}
static int apply_g3(const RegionObject *object, const QDBitmap *src, QDRect sr,
                    QDBitmap *dst, QDRect dr, QRStats *stats) {
    return qr_g3_apply(&object->g3, src, sr, dst, dr, stats);
}
static void destroy_g0(RegionObject *object) { qr_g0_free(&object->g0); }
static void destroy_g1(RegionObject *object) { qr_g1_free(&object->g1); }
static void destroy_g2(RegionObject *object) { qr_g2_free(&object->g2); }
static void destroy_g3(RegionObject *object) { qr_g3_free(&object->g3); }

static Variant variants[] = {
    {"G0_bitmap", build_g0, apply_g0, destroy_g0},
    {"G1_runs", build_g1, apply_g1, destroy_g1},
    {"G2_quickdraw_transitions", build_g2, apply_g2, destroy_g2},
    {"G3_smaller_storage_hybrid", build_g3, apply_g3, destroy_g3},
};


static QRMask make_mask(int width, int height) {
    QRMask mask = {width, height, (width + 7) / 8, NULL};
    mask.bits = (uint8_t *) calloc((size_t) mask.stride * (size_t) height, 1);
    if (!mask.bits) exit(2);
    return mask;
}


static void free_mask(QRMask *mask) { free(mask->bits); *mask = (QRMask) {0}; }


static void fill_rect(QRMask *mask, int top, int left, int bottom, int right) {
    if (top < 0) top = 0;
    if (left < 0) left = 0;
    if (bottom > mask->height) bottom = mask->height;
    if (right > mask->width) right = mask->width;
    for (int y = top; y < bottom; ++y) {
        for (int x = left; x < right; ++x) qr_mask_set(mask, y, x, 1);
    }
}


static void generate_shape(QRMask *mask, Shape shape, uint64_t seed) {
    memset(mask->bits, 0, (size_t) mask->stride * (size_t) mask->height);
    uint64_t saved = random_state;
    random_state = seed;
    switch (shape) {
    case SHAPE_EMPTY:
        break;
    case SHAPE_FULL:
        fill_rect(mask, 0, 0, mask->height, mask->width);
        break;
    case SHAPE_RECTANGLE:
        fill_rect(mask, mask->height / 7, mask->width / 9,
                  mask->height - mask->height / 8,
                  mask->width - mask->width / 11);
        break;
    case SHAPE_SPARSE_BANDS:
        for (int band = 0; band < 12; ++band) {
            int top = 5 + band * (mask->height - 10) / 12;
            int left = 7 + (band * 83) % (mask->width > 180 ? mask->width - 170 : 1);
            fill_rect(mask, top, left, top + 3, left + 48 + (band % 5) * 17);
        }
        break;
    case SHAPE_DENSE_IRREGULAR:
        for (int y = 3; y < mask->height - 3; ++y) {
            int left = 4 + (y * 7 + (y / 11) * 13) % 37;
            int right = mask->width - 5 - (y * 5 + (y / 17) * 19) % 43;
            fill_rect(mask, y, left, y + 1, right);
            if ((y / 9) % 3 == 1) {
                int hole = mask->width / 2 + (y % 13) - 6;
                int hole_end = hole + 9;
                if (hole < 0) hole = 0;
                for (int x = hole; x < hole_end && x < mask->width; ++x)
                    qr_mask_set(mask, y, x, 0);
            }
        }
        break;
    case SHAPE_CHECKER:
        for (int y = 0; y < mask->height; ++y)
            for (int x = 0; x < mask->width; ++x)
                if (((x / 4) + (y / 4)) & 1) qr_mask_set(mask, y, x, 1);
        break;
    case SHAPE_THIN:
        for (int y = 0; y < mask->height; ++y) {
            int center = (int) ((int64_t) y * (mask->width - 1)
                                / (mask->height > 1 ? mask->height - 1 : 1));
            fill_rect(mask, y, center - 1, y + 1, center + 2);
        }
        break;
    case SHAPE_RANDOM:
        for (int box = 0; box < 20; ++box) {
            int left = (int) (random_u32() % (unsigned) mask->width);
            int top = (int) (random_u32() % (unsigned) mask->height);
            int right = left + 1 + (int) (random_u32() % 31U);
            int bottom = top + 1 + (int) (random_u32() % 17U);
            fill_rect(mask, top, left, bottom, right);
        }
        break;
    }
    random_state = saved;
}


static int bitmap_get(const QDBitmap *bitmap, int y, int x) {
    int local_x = x - bitmap->bounds.left;
    size_t offset = (size_t) (y - bitmap->bounds.top) * (size_t) bitmap->row_bytes
        + (size_t) local_x / 8;
    return (bitmap->base[offset] >> (7 - (local_x & 7))) & 1;
}


static void bitmap_set(QDBitmap *bitmap, int y, int x, int value) {
    int local_x = x - bitmap->bounds.left;
    size_t offset = (size_t) (y - bitmap->bounds.top) * (size_t) bitmap->row_bytes
        + (size_t) local_x / 8;
    uint8_t bit = (uint8_t) (0x80U >> (local_x & 7));
    bitmap->base[offset] = value ? (uint8_t) (bitmap->base[offset] | bit)
        : (uint8_t) (bitmap->base[offset] & (uint8_t) ~bit);
}


static void oracle_apply(const QRMask *clip, const QDBitmap *src, QDRect src_rect,
                         QDBitmap *dst, QDRect dst_rect) {
    for (int y = dst_rect.top; y < dst_rect.bottom; ++y) {
        for (int x = dst_rect.left; x < dst_rect.right; ++x) {
            if (y >= 0 && y < clip->height && x >= 0 && x < clip->width
                    && qr_mask_get(clip, y, x)) {
                bitmap_set(dst, y, x,
                           bitmap_get(src, src_rect.top + y - dst_rect.top,
                                      src_rect.left + x - dst_rect.left));
            }
        }
    }
}


static void fill_bytes(uint8_t *data, size_t size, uint64_t seed) {
    uint64_t saved = random_state;
    random_state = seed;
    for (size_t i = 0; i < size; ++i) data[i] = (uint8_t) random_u32();
    random_state = saved;
}


static int run_one_test(uint64_t case_id, int width, int height, Shape shape,
                        QDRect dst_rect, int src_shift, int src_padding,
                        int dst_padding) {
    QRMask mask = make_mask(width, height);
    generate_shape(&mask, shape, UINT64_C(0x9e3779b97f4a7c15) ^ case_id);
    int source_width = width + src_shift + 17;
    int src_stride = (source_width + 7) / 8 + src_padding;
    int dst_stride = (width + 7) / 8 + dst_padding;
    int rows = height + 7;
    size_t src_size = (size_t) src_stride * (size_t) rows;
    size_t dst_size = (size_t) dst_stride * (size_t) rows;
    uint8_t *src_data = (uint8_t *) malloc(src_size);
    uint8_t *initial_dst = (uint8_t *) malloc(dst_size);
    uint8_t *expected = (uint8_t *) malloc(dst_size);
    uint8_t *actual = (uint8_t *) malloc(dst_size);
    if (!src_data || !initial_dst || !expected || !actual) exit(2);
    fill_bytes(src_data, src_size, case_id ^ UINT64_C(0xa4093822299f31d0));
    fill_bytes(initial_dst, dst_size, case_id ^ UINT64_C(0x082efa98ec4e6c89));
    memcpy(expected, initial_dst, dst_size);
    QDBitmap src = {src_data, src_size, src_stride, {0, 0, rows, src_stride * 8}};
    QDBitmap expected_bitmap = {expected, dst_size, dst_stride, {0, 0, rows, dst_stride * 8}};
    QDRect src_rect = {2, src_shift, 2 + dst_rect.bottom - dst_rect.top,
                       src_shift + dst_rect.right - dst_rect.left};
    oracle_apply(&mask, &src, src_rect, &expected_bitmap, dst_rect);

    for (size_t v = 0; v < sizeof variants / sizeof variants[0]; ++v) {
        RegionObject object = {0};
        QRStats build_stats = {0};
        memcpy(actual, initial_dst, dst_size);
        QDBitmap actual_bitmap = {actual, dst_size, dst_stride, {0, 0, rows, dst_stride * 8}};
        if (variants[v].build(&mask, &object, &build_stats)
                || variants[v].apply(&object, &src, src_rect, &actual_bitmap,
                                     dst_rect, NULL)
                || memcmp(expected, actual, dst_size) != 0) {
            fprintf(stderr, "test mismatch case=%" PRIu64 " variant=%s shape=%d\n",
                    case_id, variants[v].name, shape);
            variants[v].destroy(&object);
            return 0;
        }
        variants[v].destroy(&object);
    }
    free(src_data); free(initial_dst); free(expected); free(actual); free_mask(&mask);
    return 1;
}


static int run_tests(void) {
    uint64_t case_id = 0;
    static const int widths[] = {1, 7, 8, 15, 16, 17, 31, 32, 33, 63, 64, 65,
                                 127, 255};
    for (size_t wi = 0; wi < sizeof widths / sizeof widths[0]; ++wi) {
        for (int shape = SHAPE_EMPTY; shape <= SHAPE_RANDOM; ++shape) {
            int width = widths[wi], height = 1 + (int) wi * 3;
            QDRect full = {0, 0, height, width};
            if (!run_one_test(++case_id, width, height, (Shape) shape, full,
                              (int) (wi % 9), (int) (wi % 5), (int) (wi % 7))) return 1;
            QDRect partial = {height / 4, width / 5,
                              height - height / 5, width - width / 6};
            if (!run_one_test(++case_id, width, height, (Shape) shape, partial,
                              3 + (int) (wi % 5), (int) (wi % 3), (int) (wi % 4))) return 1;
        }
    }
    if (!run_one_test(++case_id, 128, 64, SHAPE_RECTANGLE,
                      (QDRect) {0, 0, 4, 8}, 5, 3, 2)) return 1;
    if (!run_one_test(++case_id, 1024, 512, SHAPE_DENSE_IRREGULAR,
                      (QDRect) {0, 0, 512, 1024}, 7, 5, 3)) return 1;
    if (!run_one_test(++case_id, 513, 257, SHAPE_CHECKER,
                      (QDRect) {31, 29, 231, 487}, 11, 1, 7)) return 1;
    random_state = UINT64_C(0x452821e638d01377);
    for (int i = 0; i < 3000; ++i) {
        int width = 1 + (int) (random_u32() % 257U);
        int height = 1 + (int) (random_u32() % 129U);
        int left = (int) (random_u32() % (unsigned) width);
        int top = (int) (random_u32() % (unsigned) height);
        QDRect rect = {top, left,
                       top + 1 + (int) (random_u32() % (unsigned) (height - top)),
                       left + 1 + (int) (random_u32() % (unsigned) (width - left))};
        if (!run_one_test(++case_id, width, height,
                          (Shape) (random_u32() % (SHAPE_RANDOM + 1)), rect,
                          (int) (random_u32() % 17U), (int) (random_u32() % 8U),
                          (int) (random_u32() % 8U))) return 1;
    }
    printf("tests: %" PRIu64 " deterministic region cases, %zu variants, bit-identical\n",
           case_id, sizeof variants / sizeof variants[0]);
    return 0;
}


static uint64_t now_ns(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC_RAW, &now);
    return (uint64_t) now.tv_sec * UINT64_C(1000000000) + (uint64_t) now.tv_nsec;
}


static uint64_t checksum(const uint8_t *data, size_t size) {
    uint64_t hash = UINT64_C(1469598103934665603);
    for (size_t i = 0; i < size; ++i) hash = (hash ^ data[i]) * UINT64_C(1099511628211);
    return hash;
}


static int compare_u64(const void *a, const void *b) {
    uint64_t x = *(const uint64_t *) a, y = *(const uint64_t *) b;
    return (x > y) - (x < y);
}


static void print_stats(const QRStats *stats) {
    printf("{\"covered_pixels\":%" PRIu64 ",\"bbox_pixels\":%" PRIu64
           ",\"active_lines\":%" PRIu64 ",\"runs\":%" PRIu64
           ",\"vertical_events\":%" PRIu64 ",\"transition_coordinates\":%" PRIu64
           ",\"scanned_mask_bits\":%" PRIu64 ",\"backend_calls\":%" PRIu64
           ",\"replayed_coordinates\":%" PRIu64 ",\"storage_bytes\":%zu"
           ",\"peak_temporary_bytes\":%zu,\"allocations\":%" PRIu64 "}",
           stats->covered_pixels, stats->bbox_pixels, stats->active_lines,
           stats->runs, stats->vertical_events, stats->transition_coordinates,
           stats->scanned_mask_bits, stats->backend_calls,
           stats->replayed_coordinates, stats->storage_bytes,
           stats->peak_temporary_bytes, stats->allocations);
}


typedef struct { const char *name; Shape shape; int width, height, reuse; } BenchCase;


static int run_benchmarks(void) {
    static const BenchCase cases[] = {
        {"rectangle", SHAPE_RECTANGLE, 1024, 512, 100},
        {"sparse_complex", SHAPE_SPARSE_BANDS, 1024, 512, 100},
        {"dense_complex", SHAPE_DENSE_IRREGULAR, 1024, 512, 100},
        {"checker_fragmented", SHAPE_CHECKER, 1024, 512, 20},
        {"thin", SHAPE_THIN, 1024, 512, 100},
        {"tiny_ui", SHAPE_RANDOM, 192, 96, 300},
    };
    enum { SAMPLES = 9, BUILD_SAMPLES = 31 };
    printf("{\"timer\":\"CLOCK_MONOTONIC_RAW\",\"samples\":%d,\"cases\":[", SAMPLES);
    for (size_t ci = 0; ci < sizeof cases / sizeof cases[0]; ++ci) {
        const BenchCase *bench = &cases[ci];
        QRMask mask = make_mask(bench->width, bench->height);
        generate_shape(&mask, bench->shape, UINT64_C(0xbe5466cf34e90c6c) + ci);
        QRStats description;
        qr_describe_mask(&mask, &description);
        int stride = (bench->width + 63) / 8 + 17;
        size_t bitmap_bytes = (size_t) stride * (size_t) bench->height;
        uint8_t *source_data = (uint8_t *) malloc(bitmap_bytes);
        uint8_t *initial_dst = (uint8_t *) malloc(bitmap_bytes);
        uint8_t *work_dst = (uint8_t *) malloc(bitmap_bytes);
        if (!source_data || !initial_dst || !work_dst) exit(2);
        fill_bytes(source_data, bitmap_bytes, UINT64_C(0xc0ac29b7c97c50dd) + ci);
        fill_bytes(initial_dst, bitmap_bytes, UINT64_C(0x3f84d5b5b5470917) + ci);
        QDBitmap src = {source_data, bitmap_bytes, stride,
                        {0, 0, bench->height, stride * 8}};
        QDBitmap dst = {work_dst, bitmap_bytes, stride,
                        {0, 0, bench->height, stride * 8}};
        QDRect rect = {0, 0, bench->height, bench->width};
        if (ci) putchar(',');
        printf("{\"name\":\"%s\",\"width\":%d,\"height\":%d,\"reuse\":%d,"
               "\"description\":", bench->name, bench->width, bench->height, bench->reuse);
        print_stats(&description);
        printf(",\"variants\":[");
        uint64_t expected_hash = 0;
        for (size_t vi = 0; vi < sizeof variants / sizeof variants[0]; ++vi) {
            uint64_t build_times[BUILD_SAMPLES];
            QRStats build_stats = {0}, apply_stats = {0};
            for (int sample = 0; sample < BUILD_SAMPLES; ++sample) {
                RegionObject temporary = {0};
                uint64_t start = now_ns();
                if (variants[vi].build(&mask, &temporary, &build_stats)) return 1;
                build_times[sample] = now_ns() - start;
                variants[vi].destroy(&temporary);
            }
            RegionObject object = {0};
            memset(&build_stats, 0, sizeof build_stats);
            if (variants[vi].build(&mask, &object, &build_stats)) return 1;
            uint64_t apply_times[SAMPLES];
            uint64_t hash = 0;
            variants[vi].apply(&object, &src, rect, &dst, rect, &apply_stats);
            for (int sample = 0; sample < SAMPLES; ++sample) {
                memcpy(work_dst, initial_dst, bitmap_bytes);
                uint64_t start = now_ns();
                for (int repeat = 0; repeat < bench->reuse; ++repeat) {
                    if (variants[vi].apply(&object, &src, rect, &dst, rect, NULL)) return 1;
                }
                apply_times[sample] = now_ns() - start;
                hash = checksum(work_dst, bitmap_bytes);
                benchmark_sink ^= hash;
            }
            if (vi == 0) expected_hash = hash;
            else if (hash != expected_hash) {
                fprintf(stderr, "benchmark mismatch %s %s\n", bench->name, variants[vi].name);
                return 1;
            }
            qsort(build_times, BUILD_SAMPLES, sizeof build_times[0], compare_u64);
            qsort(apply_times, SAMPLES, sizeof apply_times[0], compare_u64);
            uint64_t build_median = build_times[BUILD_SAMPLES / 2];
            uint64_t apply_median = apply_times[SAMPLES / 2];
            if (vi) putchar(',');
            printf("{\"name\":\"%s\",\"build_median_ns\":%" PRIu64
                   ",\"apply_batch_median_ns\":%" PRIu64
                   ",\"apply_batch_p95_ns\":%" PRIu64
                   ",\"apply_ns_per_operation\":%.3f"
                   ",\"useful_mib_per_second\":%.3f"
                   ",\"single_use_estimated_ns\":%.3f"
                   ",\"reuse100_estimated_ns\":%.3f,\"checksum\":\"%016" PRIx64
                   "\",\"build_stats\":",
                   variants[vi].name, build_median, apply_median,
                   apply_times[SAMPLES - 1], (double) apply_median / bench->reuse,
                   description.covered_pixels * 1000000000.0
                       / (8.0 * 1048576.0 * ((double) apply_median / bench->reuse)),
                   build_median + (double) apply_median / bench->reuse,
                   build_median + 100.0 * (double) apply_median / bench->reuse, hash);
            print_stats(&build_stats);
            printf(",\"apply_stats\":");
            print_stats(&apply_stats);
            putchar('}');
            variants[vi].destroy(&object);
        }
        printf("]}");
        free(source_data); free(initial_dst); free(work_dst); free_mask(&mask);
    }
    printf("],\"sink\":\"%016" PRIx64 "\"}\n", benchmark_sink);
    return 0;
}


int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--test") == 0) return run_tests();
    if (argc == 2 && strcmp(argv[1], "--benchmark") == 0) return run_benchmarks();
    fprintf(stderr, "usage: %s --test | --benchmark\n", argv[0]);
    return 2;
}
