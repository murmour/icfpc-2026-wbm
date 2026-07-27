package main

import (
	"fmt"
	"os"
)

func main() {
	b, _ := os.ReadFile("2_clean.man")
	prog, _ := ParseProgram(string(b))
	
	for _, r := range prog.Rooms {
		if r.Type == 0 {
			for y := r.MinY + 1; y < r.MaxY; y++ {
				for x := r.MinX + 1; x < r.MaxX; x++ {
					fmt.Printf("%c", prog.Grid[y][x])
				}
				fmt.Println()
			}
			fmt.Println("-----")
		}
	}
}
