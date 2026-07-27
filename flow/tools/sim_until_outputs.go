package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
)

func main() {
	if len(os.Args) < 4 {
		fmt.Fprintln(os.Stderr, "usage: sim PROGRAM OUTPUT_COUNT TICK_LIMIT [INPUT...]")
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
	outputCount, err := strconv.Atoi(os.Args[2])
	if err != nil {
		panic(err)
	}
	tickLimit, err := strconv.Atoi(os.Args[3])
	if err != nil {
		panic(err)
	}
	program.MaxTicks = tickLimit
	for _, raw := range os.Args[4:] {
		value, parseErr := strconv.ParseInt(raw, 10, 64)
		if parseErr != nil {
			panic(parseErr)
		}
		program.InputQueue = append(program.InputQueue, value)
	}

	for !program.Halted && len(program.OutputQueue) < outputCount {
		program.Step()
	}
	if program.Error != nil {
		fmt.Fprintf(
			os.Stderr,
			"simulation failed at tick %d: %v\n",
			program.TickCount,
			program.Error,
		)
		os.Exit(1)
	}
	encoded, err := json.Marshal(program.OutputQueue)
	if err != nil {
		panic(err)
	}
	fmt.Printf("TICKS %d\n", program.TickCount)
	fmt.Printf("OUTPUT %s\n", encoded)
}
