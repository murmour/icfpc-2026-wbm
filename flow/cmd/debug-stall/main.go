package main

import (
	"fmt"
	"os"
	"strconv"

	lmsim "sim"
)

type eventKey struct {
	man         int
	x, y        int
	instruction byte
}

type eventSummary struct {
	count  int
	values []int64
}

// debug_stall runs a Little Man program for a fixed number of ticks and dumps
// the final men and pipe state.
func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "usage: debug_stall PROGRAM TICKS [INPUT...]")
		os.Exit(2)
	}
	code, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	program, err := lmsim.ParseProgram(string(code))
	if err != nil {
		panic(err)
	}
	ticks, err := strconv.Atoi(os.Args[2])
	if err != nil {
		panic(err)
	}
	program.MaxTicks = ticks
	for _, raw := range os.Args[3:] {
		value, parseErr := strconv.ParseInt(raw, 10, 64)
		if parseErr != nil {
			panic(parseErr)
		}
		program.InputQueue = append(program.InputQueue, value)
	}
	eventOrder := make([]eventKey, 0)
	events := make(map[eventKey]*eventSummary)
	for !program.Halted {
		oldPositions := make(map[int]lmsim.Point)
		oldInstructions := make(map[int]byte)
		for _, man := range program.Men {
			oldPositions[man.ID] = lmsim.Point{X: man.X, Y: man.Y}
			oldInstructions[man.ID] = program.GetAt(lmsim.Point{X: man.X, Y: man.Y})
		}
		program.Step()
		for _, man := range program.Men {
			oldPosition := oldPositions[man.ID]
			instruction := oldInstructions[man.ID]
			blocking := instruction == 'r' || instruction == 's' ||
				instruction == 'R' || instruction == 'U' ||
				instruction == 'S'
			if !blocking || man.Blocked ||
				(man.X == oldPosition.X && man.Y == oldPosition.Y) {
				continue
			}
			// Top routing is the interesting part of this diagnostic.  Also
			// include main-room sends so worker/reducer production is visible.
			if oldPosition.Y >= 29 && instruction != 's' &&
				instruction != 'r' {
				continue
			}
			key := eventKey{
				man:         man.ID,
				x:           oldPosition.X,
				y:           oldPosition.Y,
				instruction: instruction,
			}
			summary := events[key]
			if summary == nil {
				summary = &eventSummary{}
				events[key] = summary
				eventOrder = append(eventOrder, key)
			}
			summary.count++
			if len(summary.values) < 80 {
				summary.values = append(summary.values, man.A)
			}
		}
	}

	fmt.Printf(
		"tick=%d input=%d output=%v error=%v\n",
		program.TickCount,
		len(program.InputQueue),
		program.OutputQueue,
		program.Error,
	)
	for _, man := range program.Men {
		if man.Halted {
			continue
		}
		fmt.Printf(
			"man=%d pos=(%d,%d) dir=(%d,%d) ins=%q A=%d B=%d BP=%d blocked=%t\n",
			man.ID,
			man.X,
			man.Y,
			man.DX,
			man.DY,
			program.GetAt(lmsim.Point{X: man.X, Y: man.Y}),
			man.A,
			man.B,
			man.BP,
			man.Blocked,
		)
	}
	for _, key := range eventOrder {
		summary := events[key]
		fmt.Printf(
			"event man=%d pos=(%d,%d) ins=%q count=%d values=%v\n",
			key.man,
			key.x,
			key.y,
			key.instruction,
			summary.count,
			summary.values,
		)
	}
	for index, pipe := range program.Pipes {
		occupied := 0
		for _, value := range pipe.Values {
			if value != nil {
				occupied++
			}
		}
		if occupied == 0 {
			continue
		}
		first, last := "_", "_"
		if value := pipe.Values[0]; value != nil {
			first = strconv.FormatInt(*value, 10)
		}
		if value := pipe.Values[len(pipe.Values)-1]; value != nil {
			last = strconv.FormatInt(*value, 10)
		}
		fmt.Printf(
			"pipe=%d occupied=%d/%d first=%s last=%s source=(%d,%d) destination=(%d,%d)\n",
			index,
			occupied,
			len(pipe.Values),
			first,
			last,
			pipe.SourceSegment.X,
			pipe.SourceSegment.Y,
			pipe.DestSegment.X,
			pipe.DestSegment.Y,
		)
	}
}
