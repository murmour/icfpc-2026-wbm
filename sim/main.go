package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Usage: sim <filename.man> [input integers...]")
		os.Exit(1)
	}

	content, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Printf("Error reading file: %v\n", err)
		os.Exit(1)
	}

	prog, err := ParseProgram(string(content))
	if err != nil {
		fmt.Printf("Error parsing program: %v\n", err)
		os.Exit(1)
	}

	prog.MaxTicks = 5000000

	if len(os.Args) > 2 {
		inputsStr := strings.Join(os.Args[2:], " ")
		for _, s := range strings.Fields(inputsStr) {
			val, err := strconv.ParseInt(s, 10, 64)
			if err == nil {
				prog.InputQueue = append(prog.InputQueue, val)
			}
		}
	}

	fmt.Printf("Loaded program %dx%d. Footprint = %d\n", prog.Width, prog.Height, max(prog.Width, prog.Height)*max(prog.Width, prog.Height))
	fmt.Printf("Found %d rooms, %d pipes, %d little men.\n", len(prog.Rooms), len(prog.Pipes), len(prog.Men))

	for !prog.Halted {
		prevOuts := len(prog.OutputQueue)
		prog.Step()
		if len(prog.OutputQueue) > prevOuts {
			fmt.Printf("Tick %d: Output emitted: %d\n", prog.TickCount, prog.OutputQueue[len(prog.OutputQueue)-1])
		}
	}

	if prog.Error != nil {
		fmt.Printf("Run ended with error at tick %d: %v\n", prog.TickCount, prog.Error)
	} else {
		fmt.Printf("Run halted successfully at tick %d.\n", prog.TickCount)
	}
	
	fmt.Printf("Final Output: %v\n", prog.OutputQueue)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
