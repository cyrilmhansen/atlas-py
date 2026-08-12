CC ?= cc
CFLAGS ?= -O3 -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic

.PHONY: all test benchmark measurements clean

all: quickdraw_bitblt_experiment

quickdraw_bitblt_experiment: quickdraw_bitblt.c quickdraw_bitblt_experiment.c quickdraw_bitblt.h
	$(CC) $(CFLAGS) quickdraw_bitblt.c quickdraw_bitblt_experiment.c -o $@

test: quickdraw_bitblt_experiment
	./quickdraw_bitblt_experiment --test

benchmark: quickdraw_bitblt_experiment
	./quickdraw_bitblt_experiment --benchmark > quickdraw_bitblt_benchmark.json

measurements:
	python3 -B run_quickdraw_bitblt.py

clean:
	$(RM) quickdraw_bitblt_experiment
