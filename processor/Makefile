RUSTC ?= rustc
RUSTFLAGS ?= -O

.PHONY: all clean

all: assembler

assembler: assembler.rs
	$(RUSTC) --edition=2021 $(RUSTFLAGS) assembler.rs -o $@

clean:
	rm -f assembler
