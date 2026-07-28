# Compressor

History Lesson compression experiments and artifact generators.

Run from this directory:

```sh
go run . \
  -input ../public_tests/history_lesson.txt \
  -output ./history_arithmetic.man \
  -encoding arithmetic

go run . \
  -input ../public_tests/history_lesson.txt \
  -output ./history_packed.man \
  -encoding packed \
  -decoder-block ../sim/blocks/packed_ascii_decoder_v3.block
```

Run the codec tests:

```sh
go test ./...
```
