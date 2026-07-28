package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"os"
)

func main() {
	input := flag.String("input", "", "Blang source file")
	output := flag.String("output", "", "Generated .block file; stdout when omitted")
	flag.Parse()

	if *input == "" {
		flag.Usage()
		os.Exit(2)
	}
	program, err := parseFile(*input)
	if err != nil {
		fatal(err)
	}
	block, err := compileProgram(program)
	if err != nil {
		fatal(err)
	}
	var data bytes.Buffer
	encoder := json.NewEncoder(&data)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(block); err != nil {
		fatal(err)
	}
	if *output == "" {
		_, err = os.Stdout.Write(data.Bytes())
	} else {
		err = os.WriteFile(*output, data.Bytes(), 0644)
	}
	if err != nil {
		fatal(err)
	}
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "blang:", err)
	os.Exit(1)
}
