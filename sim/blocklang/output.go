package main

type PortDef struct {
	Type        string `json:"type"`
	Side        string `json:"side"`
	OffsetRange []int  `json:"offset_range"`
	LengthRange []int  `json:"length_range"`
}

type TestDef struct {
	Name      string             `json:"name"`
	Inputs    map[string][]int64 `json:"inputs"`
	Expected  map[string][]int64 `json:"expected"`
	Loopbacks map[string]string  `json:"loopbacks,omitempty"`
}

type BlockDef struct {
	Name     string             `json:"name"`
	Size     string             `json:"size"`
	Interior []string           `json:"interior"`
	Ports    map[string]PortDef `json:"ports"`
	Tests    []TestDef          `json:"tests,omitempty"`
}
