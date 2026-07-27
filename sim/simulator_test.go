package main

import (
	"strings"
	"testing"
)

func testProgram(t *testing.T, rows ...string) *Program {
	t.Helper()
	code := strings.Join(rows, "\n")
	program, err := ParseProgram(code)
	if err != nil {
		t.Fatalf("ParseProgram: %v", err)
	}
	program.MaxTicks = 100
	return program
}

func TestParseProgramRejectsInvalidLiteralCharacters(t *testing.T) {
	tests := []struct {
		name string
		code string
	}{
		{
			name: "horizontal",
			code: "`12W3`",
		},
		{
			name: "vertical",
			code: "`\n1\nW\n3\n`",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			_, err := ParseProgram(test.code)
			if err == nil || !strings.Contains(err.Error(), "found 'W'") {
				t.Fatalf("ParseProgram error = %v, want invalid literal character", err)
			}
		})
	}
}

func TestSplitCopiesRegistersHeadingsAndOrder(t *testing.T) {
	program := testProgram(t,
		"+-------+",
		"|       |",
		"|   H   |",
		"| @>Y   |",
		"|   H   |",
		"|       |",
		"+-------+",
	)
	original := program.Men[0]
	original.A, original.B, original.BP = 11, 22, 33

	program.Step()
	program.Step()
	program.Step()

	if len(program.Men) != 2 {
		t.Fatalf("got %d men, want 2", len(program.Men))
	}
	right, left := program.Men[0], program.Men[1]
	if right.X != 4 || right.Y != 4 || right.DX != 0 || right.DY != 1 {
		t.Errorf("right copy = pos (%d,%d), heading (%d,%d)", right.X, right.Y, right.DX, right.DY)
	}
	if left.X != 4 || left.Y != 2 || left.DX != 0 || left.DY != -1 {
		t.Errorf("left copy = pos (%d,%d), heading (%d,%d)", left.X, left.Y, left.DX, left.DY)
	}
	for _, man := range program.Men {
		if man.A != 11 || man.B != 22 || man.BP != 33 {
			t.Errorf("copy registers = (%d,%d,%d), want (11,22,33)", man.A, man.B, man.BP)
		}
		if man.Halted {
			t.Error("newborn executed its H instruction on the split tick")
		}
	}

	program.Step()
	for _, man := range program.Men {
		if !man.Halted {
			t.Error("copy did not execute its birth-cell H on the following tick")
		}
	}
}

func TestSplitIntoWallIsError(t *testing.T) {
	room := &Room{MinX: 0, MinY: 0, MaxX: 5, MaxY: 4}
	program := &Program{
		Width: 6, Height: 5,
		Grid: [][]byte{
			[]byte("++++++"),
			[]byte("+    +"),
			[]byte("+Y   +"),
			[]byte("+    +"),
			[]byte("++++++"),
		},
		Rooms:    []*Room{room},
		Men:      []*LittleMan{{ID: 0, X: 1, Y: 2, DY: 1}},
		MaxTicks: 10,
	}

	program.Step()

	if program.Error == nil || !strings.Contains(program.Error.Error(), "split into a wall") {
		t.Fatalf("error = %v, want split wall error", program.Error)
	}
}

func TestSplitBirthCollisionKillsBornAndOccupant(t *testing.T) {
	room := &Room{MinX: 0, MinY: 0, MaxX: 6, MaxY: 6}
	splitter := &LittleMan{ID: 0, X: 3, Y: 3, DX: 1}
	occupant := &LittleMan{ID: 1, X: 3, Y: 2, DX: 1, Blocked: true}
	program := &Program{
		Width: 7, Height: 7,
		Grid: [][]byte{
			[]byte("+++++++"),
			[]byte("+     +"),
			[]byte("+     +"),
			[]byte("+  Y  +"),
			[]byte("+     +"),
			[]byte("+     +"),
			[]byte("+++++++"),
		},
		Rooms:     []*Room{room},
		Men:       []*LittleMan{splitter, occupant},
		MaxTicks:  10,
		NextManID: 2,
	}

	program.Step()

	right, left := program.Men[0], program.Men[2]
	if right.Halted {
		t.Error("unobstructed right copy died")
	}
	if !left.Halted || !occupant.Halted {
		t.Errorf("birth collision states: left=%t occupant=%t, want both halted", left.Halted, occupant.Halted)
	}
}

func TestMovementSwapCollision(t *testing.T) {
	room := &Room{MinX: 0, MinY: 0, MaxX: 5, MaxY: 4}
	first := &LittleMan{ID: 0, X: 2, Y: 2, DX: 1}
	second := &LittleMan{ID: 1, X: 3, Y: 2, DX: -1}
	program := &Program{
		Width: 6, Height: 5,
		Grid: [][]byte{
			[]byte("++++++"),
			[]byte("+    +"),
			[]byte("+    +"),
			[]byte("+    +"),
			[]byte("++++++"),
		},
		Rooms:    []*Room{room},
		Men:      []*LittleMan{first, second},
		MaxTicks: 10,
	}

	program.Step()

	if !first.Halted || !second.Halted {
		t.Errorf("swap collision states: first=%t second=%t, want both halted", first.Halted, second.Halted)
	}
}

func TestDisplayWritesAndClearsNextBuffer(t *testing.T) {
	program := testProgram(t,
		"+---+  +====+",
		"|@ H|  :    :",
		"+---+  :    :",
		"       +====+",
	)
	display := program.Displays[0]
	source := program.Rooms[0]
	addPipe := func(point, segment Point, value int64) {
		stored := value
		pipe := &Pipe{
			Path:        []Point{point},
			Values:      []*int64{&stored},
			SourceRoom:  source,
			DestRoom:    display.Room,
			DestSegment: segment,
		}
		program.Pipes = append(program.Pipes, pipe)
		program.SetPipeVal(point, &stored)
	}
	addPipe(Point{20, 1}, Point{display.Room.MinX + 2, display.Room.MinY}, 5)
	addPipe(Point{21, 1}, Point{display.Room.MinX, display.Room.MinY + 1}, 15)
	addPipe(Point{22, 1}, Point{display.Room.MinX + 2, display.Room.MaxY}, 1)
	if err := program.stepDisplay(display); err != nil {
		t.Fatal(err)
	}
	if len(display.Frames) != 1 || display.Frames[0][5] != 15 {
		t.Fatalf("frames = %v, want one frame with pixel 5 set to 15", display.Frames)
	}

	swapPipe := program.Pipes[len(program.Pipes)-1]
	zero := int64(0)
	program.SetPipeVal(swapPipe.Path[0], &zero)
	if err := program.stepDisplay(display); err != nil {
		t.Fatal(err)
	}
	if display.Next[0] != 0 || display.Cursor != 0 {
		t.Fatalf("next buffer was not cleared: next[0]=%d cursor=%d", display.Next[0], display.Cursor)
	}
}
