package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestLiteralCode(t *testing.T) {
	tests := map[int64]string{
		0:    "`0`",
		42:   "`42`",
		-7:   "`7`N",
		1000: "`1000`",
	}
	for value, expected := range tests {
		actual, err := literalCode(value)
		if err != nil {
			t.Fatalf("literalCode(%d): %v", value, err)
		}
		if actual != expected {
			t.Fatalf("literalCode(%d) = %q, want %q", value, actual, expected)
		}
	}
}

func TestNestedRepeatRejected(t *testing.T) {
	program, err := parseSource(`
block nested
forever {
  A = 2
  repeat A {
    repeat A {
      nop
    }
  }
}
`)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := compileProgram(program); err == nil {
		t.Fatal("compileProgram accepted nested repeat")
	}
}

func TestBackpackRepeatAndQueryCompile(t *testing.T) {
	program, err := parseSource(`
block query_loop
input storage auto
output storage_out auto
forever {
  query storage
  repeat backpack {
    A = recv storage
    decrement backpack
    send storage_out
    A = recv storage
    send storage_out
  }
}
`)
	if err != nil {
		t.Fatal(err)
	}
	block, err := compileProgram(program)
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(block.Interior, "")
	for _, instruction := range "qmd" {
		if !strings.ContainsRune(joined, instruction) {
			t.Fatalf("compiled block does not contain %q", instruction)
		}
	}
}

func TestBroadcastAllCompilesWithMultipleOutputs(t *testing.T) {
	program, err := parseSource(`
block fanout
input request auto
output first top 0 2 64
output second bottom 0 2 64
forever {
  A = recv request
  broadcast all
}
`)
	if err != nil {
		t.Fatal(err)
	}
	block, err := compileProgram(program)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.Join(block.Interior, ""), "S") {
		t.Fatal("compiled block does not contain broadcast")
	}
}

func TestSignBranchCompiles(t *testing.T) {
	program, err := parseSource(`
block signs
input request auto
output response auto
forever {
  A = recv request
  if sign A {
    negative {
      A = -1
      send response
    }
    zero {
      A = 0
      send response
    }
    positive {
      A = 1
      send response
    }
  }
}
`)
	if err != nil {
		t.Fatal(err)
	}
	block, err := compileProgram(program)
	if err != nil {
		t.Fatal(err)
	}
	if block.Size == "" || len(block.Interior) == 0 {
		t.Fatal("compiler produced an empty block")
	}
}

func TestWhilePositiveCompiles(t *testing.T) {
	program, err := parseSource(`
block positive_stream
input values auto
output copied auto
forever {
  A = recv values
  while positive A {
    send copied
    A = recv values
  }
}
`)
	if err != nil {
		t.Fatal(err)
	}
	block, err := compileProgram(program)
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(block.Interior, "")
	if !strings.Contains(joined, "X") {
		t.Fatal("compiled while loop does not contain a sign branch")
	}
}

func TestRing34ExampleCompilesWithNamedPorts(t *testing.T) {
	program, err := parseFile(filepath.Join("examples", "ring34_exchange.bl"))
	if err != nil {
		t.Fatal(err)
	}
	block, err := compileProgram(program)
	if err != nil {
		t.Fatal(err)
	}
	if len(block.Ports) != 5 {
		t.Fatalf("compiled %d ports, want 5", len(block.Ports))
	}
	for name, port := range block.Ports {
		if port.Side == "auto" {
			t.Fatalf("port %q was not placed", name)
		}
	}
}

func TestWrongTestPortDirectionRejected(t *testing.T) {
	program, err := parseSource(`
block wrong_test_port
input request auto
output response auto
forever {
  A = recv request
  send response
}
test wrong {
  input response: 1
}
`)
	if err != nil {
		t.Fatal(err)
	}
	_, err = compileProgram(program)
	if err == nil || !strings.Contains(err.Error(), "not an input port") {
		t.Fatalf("compileProgram error = %v, want input-port error", err)
	}
}

func TestAnyReceiveAndBroadcastCompileWithMultiplePorts(t *testing.T) {
	program, err := parseSource(`
block merge_and_fork
input left auto
input right auto
output first auto
output second auto
forever {
  A = recv any
  broadcast
}
`)
	if err != nil {
		t.Fatal(err)
	}
	block, err := compileProgram(program)
	if err != nil {
		t.Fatal(err)
	}
	if len(block.Ports) != 4 {
		t.Fatalf("compiled %d ports, want 4", len(block.Ports))
	}
}
