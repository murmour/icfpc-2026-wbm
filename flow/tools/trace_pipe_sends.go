package main

import (
	"fmt"
	"os"
	"sort"
	"strconv"
)

func main() {
	if len(os.Args) < 4 {
		fmt.Fprintln(os.Stderr, "usage: trace PROGRAM OUTPUT_COUNT TICK_LIMIT [INPUT...]")
		os.Exit(2)
	}
	code, err := os.ReadFile(os.Args[1])
	if err != nil {
		panic(err)
	}
	program, err := ParseProgram(string(code))
	if err != nil {
		panic(err)
	}
	outputCount, _ := strconv.Atoi(os.Args[2])
	tickLimit, _ := strconv.Atoi(os.Args[3])
	program.MaxTicks = tickLimit
	for _, raw := range os.Args[4:] {
		value, parseErr := strconv.ParseInt(raw, 10, 64)
		if parseErr != nil {
			panic(parseErr)
		}
		program.InputQueue = append(program.InputQueue, value)
	}

	var collector *Room
	for _, room := range program.Rooms {
		for y := room.MinY + 1; y < room.MaxY; y++ {
			for x := room.MinX + 1; x < room.MaxX; x++ {
				if program.GetAt(Point{X: x, Y: y}) == 'R' {
					collector = room
				}
			}
		}
	}
	if collector == nil {
		panic("collector room with R not found")
	}
	var resultPipes []*Pipe
	for _, pipe := range program.Pipes {
		if pipe.DestRoom == collector {
			resultPipes = append(resultPipes, pipe)
		}
	}
	sort.Slice(resultPipes, func(i, j int) bool {
		return resultPipes[i].SourceSegment.X < resultPipes[j].SourceSegment.X
	})
	previous := make([]*int64, len(resultPipes))

	for !program.Halted && len(program.OutputQueue) < outputCount {
		for index, pipe := range resultPipes {
			previous[index] = pipe.Values[0]
		}
		beforeOutputs := len(program.OutputQueue)
		program.Step()
		for index, pipe := range resultPipes {
			current := pipe.Values[0]
			if current != nil && current != previous[index] {
				fmt.Printf("SEND %d %d %d\n", program.TickCount, index, *current)
			}
		}
		for index := beforeOutputs; index < len(program.OutputQueue); index++ {
			fmt.Printf("OUT %d %d %d\n", program.TickCount, index, program.OutputQueue[index])
		}
	}
	if program.Error != nil {
		panic(program.Error)
	}
}
