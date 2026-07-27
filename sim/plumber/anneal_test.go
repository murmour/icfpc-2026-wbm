package main

import "testing"

func TestAnnealCostPenalizesOverlap(t *testing.T) {
	separate := []annealRoom{
		{block: floorBlock{ID: "a", X: 0, Y: 0}, width: 4, height: 4},
		{block: floorBlock{ID: "b", X: 8, Y: 0}, width: 4, height: 4},
	}
	overlapping := cloneCandidate(annealCandidate{rooms: separate}).rooms
	overlapping[1].block.X = 2
	if annealCost(overlapping, nil, 100, true) <=
		annealCost(separate, nil, 100, true) {
		t.Fatal("overlapping placement did not receive a larger cost")
	}
}

func TestAnnealCostPenalizesVerticalLiteralConflicts(t *testing.T) {
	separate := []annealRoom{
		{
			block:  floorBlock{ID: "a", X: 0, Y: 0},
			width:  4,
			height: 4,
			ticks:  []int{0},
		},
		{
			block:  floorBlock{ID: "b", X: 5, Y: 5},
			width:  4,
			height: 4,
			ticks:  []int{0},
		},
	}
	aligned := cloneCandidate(annealCandidate{rooms: separate}).rooms
	aligned[1].block.X = 0
	if annealCost(aligned, nil, 100, true) <=
		annealCost(separate, nil, 100, true) {
		t.Fatal("aligned backticks did not receive a larger cost")
	}
}

func TestAlignedPortOffsetMatchesFixedEndpoint(t *testing.T) {
	flexible := annealRoom{
		block: floorBlock{ID: "encoder", X: 7, Y: 10},
		width: 26,
	}
	fixed := annealRoom{
		block: floorBlock{ID: "sorter", X: 3, Y: 20},
		width: 37,
		ports: map[string]generatedPort{
			"from_encoder": {
				Side:        "top",
				OffsetRange: []int{4, 4},
			},
		},
	}

	offset, ok := alignedPortOffset(
		flexible,
		"bottom",
		fixed,
		"from_encoder",
	)
	if !ok {
		t.Fatal("expected aligned port offset")
	}
	if offset != 0 {
		t.Fatalf("aligned offset = %d, want 0", offset)
	}
}

func TestAlignedPortOffsetRejectsDifferentAxes(t *testing.T) {
	room := annealRoom{
		block: floorBlock{ID: "a", X: 0, Y: 0},
		width: 10,
	}
	target := annealRoom{
		block: floorBlock{ID: "b", X: 20, Y: 0},
		ports: map[string]generatedPort{
			"in": {
				Side:        "left",
				OffsetRange: []int{1, 1},
			},
		},
	}
	if _, ok := alignedPortOffset(room, "bottom", target, "in"); ok {
		t.Fatal("aligned ports on different axes")
	}
}
