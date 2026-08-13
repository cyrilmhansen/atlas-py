The copy routine uses 64-bit words when both source and destination are 8-byte aligned.

For unaligned inputs it uses the generic byte path.

The two paths preserve the same byte sequence.
