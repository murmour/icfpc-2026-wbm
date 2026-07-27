package main

import (
	"flag"
	"fmt"
	"os"
	"strconv"
)

func main() {
	programPath := flag.String("program", "", "Little Man program to trace")
	tickLimit := flag.Int("ticks", 500, "number of ticks to trace")
	manID := flag.Int("man", -1, "little man ID to trace; -1 traces every man")
	activeOnly := flag.Bool("active-only", false, "omit ticks executing spaces")
	topology := flag.Bool("topology", false, "print rooms and pipes, then exit")
	flag.Parse()

	if *programPath == "" {
		flag.Usage()
		os.Exit(2)
	}

	code, err := os.ReadFile(*programPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read program: %v\n", err)
		os.Exit(1)
	}
	program, err := ParseProgram(string(code))
	if err != nil {
		fmt.Fprintf(os.Stderr, "parse program: %v\n", err)
		os.Exit(1)
	}
	program.MaxTicks = *tickLimit
	if *topology {
		for index, room := range program.Rooms {
			fmt.Printf(
				"room=%d bounds=(%d,%d)-(%d,%d) type=%d\n",
				index, room.MinX, room.MinY, room.MaxX, room.MaxY, room.Type,
			)
		}
		for index, pipe := range program.Pipes {
			source, destination := -1, -1
			for roomIndex, room := range program.Rooms {
				if pipe.SourceRoom == room {
					source = roomIndex
				}
				if pipe.DestRoom == room {
					destination = roomIndex
				}
			}
			fmt.Printf(
				"pipe=%d rooms=%d->%d length=%d source=(%d,%d) destination=(%d,%d)\n",
				index,
				source,
				destination,
				len(pipe.Path),
				pipe.SourceSegment.X,
				pipe.SourceSegment.Y,
				pipe.DestSegment.X,
				pipe.DestSegment.Y,
			)
		}
		return
	}
	for _, raw := range flag.Args() {
		value, parseErr := strconv.ParseInt(raw, 10, 64)
		if parseErr != nil {
			fmt.Fprintf(os.Stderr, "parse input %q: %v\n", raw, parseErr)
			os.Exit(1)
		}
		program.InputQueue = append(program.InputQueue, value)
	}

	for !program.Halted && program.Error == nil {
		for _, man := range program.Men {
			if *manID >= 0 && man.ID != *manID {
				continue
			}
			instruction := program.GetAt(Point{X: man.X, Y: man.Y})
			if *activeOnly && instruction == ' ' {
				continue
			}
			fmt.Printf(
				"tick=%d man=%d pos=(%d,%d) dir=(%d,%d) ins=%q A=%d B=%d BP=%d blocked=%t\n",
				program.TickCount+1,
				man.ID,
				man.X,
				man.Y,
				man.DX,
				man.DY,
				instruction,
				man.A,
				man.B,
				man.BP,
				man.Blocked,
			)
		}
		outputCount := len(program.OutputQueue)
		program.Step()
		for _, value := range program.OutputQueue[outputCount:] {
			fmt.Printf("tick=%d output=%d\n", program.TickCount, value)
		}
	}
	if program.Error != nil {
		fmt.Printf("ended tick=%d error=%v\n", program.TickCount, program.Error)
	}
}
