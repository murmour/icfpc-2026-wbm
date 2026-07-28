package main

import (
	"strings"
	"testing"
)

func TestParseMultipleBlocks(t *testing.T) {
	program, err := parseSource(`
program pipeline

block main {
  forever {
    A = recv input
    send worker
  }
}

block worker {
  forever {
    A = recv main
    B = A
    A += B
    send output
  }
}
`)
	if err != nil {
		t.Fatalf("parseSource returned an error: %v", err)
	}
	if program.Name != "pipeline" || len(program.Blocks) != 2 {
		t.Fatalf("parsed %#v", program)
	}
}

func TestParseNamedPipe(t *testing.T) {
	program, err := parseSource(`
pipe storage 17..42
block main {
  forever {
    A = recv input
    send storage
    A = recv storage
    send output
  }
}
`)
	if err != nil {
		t.Fatalf("parseSource returned an error: %v", err)
	}
	if len(program.Pipes) != 1 ||
		program.Pipes[0].Name != "storage" ||
		program.Pipes[0].MinSize != 17 ||
		program.Pipes[0].MaxSize != 42 {
		t.Fatalf("parsed pipes %#v", program.Pipes)
	}
}

func TestParseOpenAndOmittedPipeRanges(t *testing.T) {
	for _, declaration := range []string{
		"pipe queue",
		"pipe queue ..",
		"pipe queue ..99",
		"pipe queue 17..",
	} {
		program, err := parseSource(declaration + `
block main {
  forever {
    send queue
    A = recv queue
  }
}
`)
		if err != nil {
			t.Errorf("%q: %v", declaration, err)
			continue
		}
		if program.Pipes[0].MinSize < 2 ||
			program.Pipes[0].MaxSize < program.Pipes[0].MinSize {
			t.Errorf("%q: parsed %#v", declaration, program.Pipes[0])
		}
	}
}

func TestParseRejectsPipeBlockNameConflict(t *testing.T) {
	_, err := parseSource(`
pipe main 2..
block main {
  forever {
    A = recv input
  }
}
`)
	if err == nil || !strings.Contains(err.Error(), "conflicts with a block") {
		t.Fatalf("got error %v", err)
	}
}

func TestParseRejectsInvalidPipeSize(t *testing.T) {
	_, err := parseSource(`
pipe storage 0..
block main {
  forever {
    A = recv input
  }
}
`)
	if err == nil || !strings.Contains(err.Error(), "invalid pipe size range") {
		t.Fatalf("got error %v", err)
	}
}

func TestParseRejectsUnknownPeer(t *testing.T) {
	_, err := parseSource(`
block main {
  forever {
    A = 1
    send missing
  }
}
`)
	if err == nil || !strings.Contains(err.Error(), `unknown endpoint "missing"`) {
		t.Fatalf("got error %v", err)
	}
}

func TestParseRestrictsExternalInputToOneBlock(t *testing.T) {
	_, err := parseSource(`
block main {
  forever {
    A = recv input
  }
}
block worker {
  forever {
    A = recv input
  }
}
`)
	if err == nil || !strings.Contains(err.Error(), "both receive from input") {
		t.Fatalf("got error %v", err)
	}
}
