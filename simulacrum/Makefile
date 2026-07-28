CC ?= cc
CFLAGS ?= -O3 -march=native -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic
CPPFLAGS ?=
FAST_MODE ?= 1
PROFILE_MODE ?= 0
TV_MODE ?= 0

ifeq ($(FAST_MODE),1)
CPPFLAGS += -DFAST_MODE
endif
ifeq ($(PROFILE_MODE),1)
CPPFLAGS += -DPROFILE_MODE
endif
ifeq ($(TV_MODE),1)
CPPFLAGS += -DTV_MODE
LDLIBS += -lSDL3
endif

.PHONY: all benchmark clean

MODE_STAMP := .fast-mode-$(FAST_MODE)
PROFILE_MODE_STAMP := .profile-mode-$(PROFILE_MODE)
TV_MODE_STAMP := .visual-mode-$(TV_MODE)

all: simulacrum

simulacrum: simulacrum.c $(MODE_STAMP) $(PROFILE_MODE_STAMP) $(TV_MODE_STAMP)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ $< $(LDLIBS)

.fast-mode-0:
	rm -f .fast-mode-1
	touch $@

.fast-mode-1:
	rm -f .fast-mode-0
	touch $@

.profile-mode-0:
	rm -f .profile-mode-1
	touch $@

.profile-mode-1:
	rm -f .profile-mode-0
	touch $@

.visual-mode-0:
	rm -f .visual-mode-1
	touch $@

.visual-mode-1:
	rm -f .visual-mode-0
	touch $@

benchmark: simulacrum
	./simulacrum ../../little_demo/processor/rotozoom_processor.man --frames 1

clean:
	rm -f simulacrum .fast-mode-0 .fast-mode-1 \
		.profile-mode-0 .profile-mode-1 \
		.visual-mode-0 .visual-mode-1
