package main

import (
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type annealRoom struct {
	block  floorBlock
	width  int
	height int
	ticks  []int
	ports  map[string]generatedPort
}

type annealCandidate struct {
	rooms    []annealRoom
	cost     int64
	topology bool
}

func searchAnnealedFloorplan(
	simRoot string,
	tempDir string,
	blocks []compiledBlock,
	edges []directedEdge,
	startSide int,
) ([]byte, int, error) {
	minSide := 1
	for _, block := range blocks {
		minSide = max(minSide, max(block.Width+2, block.Height+2))
	}

	var best []byte
	bestSide := 0
	var seed []annealRoom
	side := startSide
	for side >= minSide {
		code, measuredSide, placement, ok := annealAtSide(
			simRoot,
			tempDir,
			blocks,
			edges,
			side,
			seed,
		)
		if ok {
			best = code
			bestSide = measuredSide
			seed = placement
			side = min(side-1, measuredSide-1)
			continue
		}
		side--
	}
	if best == nil {
		return nil, 0, fmt.Errorf(
			"annealing floorplan: no valid placement fits a %dx%d grid",
			startSide,
			startSide,
		)
	}
	return best, bestSide, nil
}

func annealAtSide(
	simRoot string,
	tempDir string,
	blocks []compiledBlock,
	edges []directedEdge,
	side int,
	seed []annealRoom,
) ([]byte, int, []annealRoom, bool) {
	connections := floorConnections(edges)
	random := rand.New(rand.NewSource(int64(20260727 + side*1009)))
	var candidates []annealCandidate
	for variant := 0; variant < 9; variant++ {
		if rooms, ok := topologyAnnealRooms(blocks, edges, side, variant); ok {
			candidates = append(candidates, annealCandidate{
				rooms:    rooms,
				cost:     annealCost(rooms, edges, side, true),
				topology: true,
			})
		}
	}

	for restart := 0; restart < 12; restart++ {
		compact := restart < 8
		var rooms []annealRoom
		var ok bool
		if restart == 0 && len(seed) != 0 {
			rooms, ok = normalizeAnnealRooms(seed, side)
		} else {
			rooms, ok = randomAnnealRooms(random, blocks, side)
		}
		if !ok {
			continue
		}
		current := annealCandidate{
			rooms: rooms,
			cost:  annealCost(rooms, edges, side, compact),
		}
		best := cloneCandidate(current)
		candidates = append(candidates, cloneCandidate(current))
		temperature := 2_000_000.0
		for iteration := 0; iteration < 8000; iteration++ {
			next := cloneCandidate(current)
			index := random.Intn(len(next.rooms))
			room := &next.rooms[index]
			mutation := random.Intn(20)
			switch {
			case mutation == 0:
				room.block.X = random.Intn(side - room.width + 1)
				room.block.Y = random.Intn(side - room.height + 1)
			case mutation == 1:
				otherIndex := random.Intn(len(next.rooms))
				other := &next.rooms[otherIndex]
				roomX, roomY := room.block.X, room.block.Y
				room.block.X = clamp(other.block.X, 0, side-room.width)
				room.block.Y = clamp(other.block.Y, 0, side-room.height)
				other.block.X = clamp(roomX, 0, side-other.width)
				other.block.Y = clamp(roomY, 0, side-other.height)
			default:
				distance := 1 + random.Intn(max(2, side/8))
				if random.Intn(2) == 0 {
					distance = -distance
				}
				if random.Intn(2) == 0 {
					room.block.X = clamp(
						room.block.X+distance,
						0,
						side-room.width,
					)
				} else {
					room.block.Y = clamp(
						room.block.Y+distance,
						0,
						side-room.height,
					)
				}
			}
			next.cost = annealCost(next.rooms, edges, side, compact)
			delta := float64(next.cost - current.cost)
			if delta <= 0 || random.Float64() < math.Exp(-delta/temperature) {
				current = next
				if current.cost < best.cost {
					best = cloneCandidate(current)
				}
			}
			temperature *= 0.9992
		}
		candidates = append(candidates, best)
	}

	sort.Slice(candidates, func(left, right int) bool {
		return candidates[left].cost < candidates[right].cost
	})
	if len(candidates) > 16 {
		shortlist := make([]annealCandidate, 0, 24)
		for _, candidate := range candidates {
			if candidate.topology {
				shortlist = append(shortlist, candidate)
			}
		}
		for _, candidate := range candidates {
			if !candidate.topology && len(shortlist) < 24 {
				shortlist = append(shortlist, candidate)
			}
		}
		candidates = shortlist
	}
	var routedCode []byte
	var routedRooms []annealRoom
	routedWidth, routedHeight := 0, 0
	for index, candidate := range candidates {
		if hasRoomOverlap(candidate.rooms) {
			continue
		}
		for orderIndex, order := range connectionOrders(connections) {
			order = adaptivePortConnections(order, candidate.rooms, edges, side)
			floor := floorDescription{
				GridWidth:   side,
				GridHeight:  side,
				Blocks:      candidateFloorBlocks(candidate.rooms),
				Connections: order,
			}
			data, err := json.MarshalIndent(floor, "", "  ")
			if err != nil {
				continue
			}
			base := fmt.Sprintf("anneal-%d-%d-%d", side, index, orderIndex)
			floorPath := filepath.Join(tempDir, base+".floor")
			manPath := filepath.Join(tempDir, base+".man")
			if os.WriteFile(floorPath, data, 0644) != nil {
				continue
			}
			if runGoFile(
				simRoot,
				"floorplan.go",
				"-layout", floorPath,
				"-output", manPath,
			) != nil {
				continue
			}
			if validateGeneratedMan(simRoot, manPath) != nil {
				continue
			}
			code, err := os.ReadFile(manPath)
			if err != nil {
				continue
			}
			width, height := manDimensions(code)
			if width > side || height > side {
				continue
			}
			if routedCode == nil ||
				max(width, height) < max(routedWidth, routedHeight) ||
				max(width, height) == max(routedWidth, routedHeight) &&
					width*height < routedWidth*routedHeight {
				routedCode = code
				routedRooms = candidate.rooms
				routedWidth = width
				routedHeight = height
			}
		}
	}
	if routedCode == nil {
		return nil, 0, nil, false
	}
	return routedCode,
		max(routedWidth, routedHeight),
		routedRooms,
		true
}

func adaptivePortConnections(
	connections []floorConnection,
	rooms []annealRoom,
	edges []directedEdge,
	side int,
) []floorConnection {
	result := append([]floorConnection(nil), connections...)
	byName := make(map[string]annealRoom)
	incoming := make(map[string]int)
	outgoing := make(map[string]int)
	for _, room := range rooms {
		byName[room.block.ID] = room
	}
	for _, edge := range edges {
		if edge.Source != "input" {
			outgoing[edge.Source]++
		}
		if edge.Destination != "output" {
			incoming[edge.Destination]++
		}
	}
	for index := range result {
		sourceName := connectionBlockName(result[index].Src)
		destinationName := connectionBlockName(result[index].Dst)
		source, sourceOK := byName[sourceName]
		destination, destinationOK := byName[destinationName]
		if !sourceOK || !destinationOK {
			continue
		}
		if outgoing[sourceName] == 1 &&
			source.block.Type == "" &&
			!strings.HasPrefix(sourceName, "__pipe_") {
			side := facingSide(source, destination)
			result[index].SrcSide = side
			offset := sideOffset(source, side)
			if aligned, ok := alignedPortOffset(
				source,
				side,
				destination,
				connectionPortName(result[index].Dst),
			); ok {
				offset = aligned
			}
			result[index].SrcOffset = &offset
		}
		if incoming[destinationName] == 1 &&
			destination.block.Type == "" &&
			!strings.HasPrefix(destinationName, "__pipe_") {
			side := facingSide(destination, source)
			result[index].DstSide = side
			offset := sideOffset(destination, side)
			if aligned, ok := alignedPortOffset(
				destination,
				side,
				source,
				connectionPortName(result[index].Src),
			); ok {
				offset = aligned
			}
			result[index].DstOffset = &offset
		}
	}
	addStorageChannelWaypoints(result, byName, edges, side)
	return result
}

func addStorageChannelWaypoints(
	connections []floorConnection,
	rooms map[string]annealRoom,
	edges []directedEdge,
	side int,
) {
	var core, relay, consumer annealRoom
	foundCore, foundRelay, foundConsumer := false, false, false
	for _, edge := range edges {
		if strings.HasPrefix(edge.Destination, "__pipe_") {
			core, foundCore = rooms[edge.Source]
			relay, foundRelay = rooms[edge.Destination]
		}
	}
	if !foundCore || !foundRelay {
		return
	}
	for _, edge := range edges {
		if edge.Source == core.block.ID &&
			edge.Destination != relay.block.ID &&
			edge.Destination != "output" {
			if room, ok := rooms[edge.Destination]; ok &&
				room.block.Y > core.block.Y {
				consumer = room
				foundConsumer = true
				break
			}
		}
	}
	if !foundConsumer ||
		relay.block.X <= consumer.block.X+consumer.width ||
		consumer.block.Y < core.block.Y+core.height+2 {
		return
	}

	outPort, outOK := core.ports[connectionPortName(
		findConnectionSource(connections, core.block.ID, relay.block.ID),
	)]
	relayIn, relayInOK := relay.ports[connectionPortName(
		findConnectionDestination(connections, core.block.ID, relay.block.ID),
	)]
	relayOut, relayOutOK := relay.ports[connectionPortName(
		findConnectionSource(connections, relay.block.ID, core.block.ID),
	)]
	coreIn, coreInOK := core.ports[connectionPortName(
		findConnectionDestination(connections, relay.block.ID, core.block.ID),
	)]
	if !outOK || !relayInOK || !relayOutOK || !coreInOK ||
		outPort.Side != "top" ||
		relayIn.Side != "right" ||
		relayOut.Side != "left" ||
		coreIn.Side != "left" {
		return
	}

	outX := core.block.X + 1 + outPort.OffsetRange[0]
	outY := core.block.Y - 2
	rightX := relay.block.X + relay.width + 1
	relayInY := relay.block.Y + 1 + relayIn.OffsetRange[0]
	relayOutY := relay.block.Y + 1 + relayOut.OffsetRange[0]
	returnX := relay.block.X - 2
	bottomY := consumer.block.Y + consumer.height
	leftX := core.block.X - 2
	coreInY := core.block.Y + 1 + coreIn.OffsetRange[0]
	if leftX < 0 || rightX >= side || bottomY >= side {
		return
	}

	for index := range connections {
		source := connectionBlockName(connections[index].Src)
		destination := connectionBlockName(connections[index].Dst)
		switch {
		case source == core.block.ID && destination == relay.block.ID:
			connections[index].Waypoints = []floorPoint{
				{X: outX, Y: outY},
				{X: rightX, Y: outY},
				{X: rightX, Y: relayInY},
			}
		case source == relay.block.ID && destination == core.block.ID:
			connections[index].Waypoints = []floorPoint{
				{X: returnX, Y: relayOutY},
				{X: returnX, Y: bottomY},
				{X: leftX, Y: bottomY},
				{X: leftX, Y: coreInY},
			}
		}
	}
}

func findConnectionSource(
	connections []floorConnection,
	sourceBlock string,
	destinationBlock string,
) string {
	for _, connection := range connections {
		if connectionBlockName(connection.Src) == sourceBlock &&
			connectionBlockName(connection.Dst) == destinationBlock {
			return connection.Src
		}
	}
	return ""
}

func findConnectionDestination(
	connections []floorConnection,
	sourceBlock string,
	destinationBlock string,
) string {
	for _, connection := range connections {
		if connectionBlockName(connection.Src) == sourceBlock &&
			connectionBlockName(connection.Dst) == destinationBlock {
			return connection.Dst
		}
	}
	return ""
}

func connectionBlockName(endpoint string) string {
	name, _, _ := strings.Cut(endpoint, ".")
	return name
}

func connectionPortName(endpoint string) string {
	_, name, _ := strings.Cut(endpoint, ".")
	return name
}

func roomsFitSide(rooms []annealRoom, side int) bool {
	for _, room := range rooms {
		if room.block.X < 0 || room.block.Y < 0 ||
			room.block.X+room.width > side ||
			room.block.Y+room.height > side {
			return false
		}
	}
	return true
}

func alignedPortOffset(
	room annealRoom,
	side string,
	target annealRoom,
	targetPortName string,
) (int, bool) {
	port, ok := target.ports[targetPortName]
	if !ok || len(port.OffsetRange) == 0 {
		return 0, false
	}
	targetOffset := port.OffsetRange[0]
	var coordinate int
	switch port.Side {
	case "top", "bottom":
		coordinate = target.block.X + 1 + targetOffset
	case "left", "right":
		coordinate = target.block.Y + 1 + targetOffset
	default:
		return 0, false
	}

	var offset, limit int
	switch side {
	case "top", "bottom":
		if port.Side != "top" && port.Side != "bottom" {
			return 0, false
		}
		offset = coordinate - room.block.X - 1
		limit = room.width - 2
	case "left", "right":
		if port.Side != "left" && port.Side != "right" {
			return 0, false
		}
		offset = coordinate - room.block.Y - 1
		limit = room.height - 2
	default:
		return 0, false
	}
	if offset < 0 || offset >= limit {
		return 0, false
	}
	return offset, true
}

func facingSide(room, target annealRoom) string {
	roomX := room.block.X + room.width/2
	roomY := room.block.Y + room.height/2
	targetX := target.block.X + target.width/2
	targetY := target.block.Y + target.height/2
	deltaX := targetX - roomX
	deltaY := targetY - roomY
	if absInt(deltaX) >= absInt(deltaY) {
		if deltaX < 0 {
			return "left"
		}
		return "right"
	}
	if deltaY < 0 {
		return "top"
	}
	return "bottom"
}

func sideOffset(room annealRoom, side string) int {
	if side == "top" || side == "bottom" {
		return max(0, (room.width-2)/2)
	}
	return max(0, (room.height-2)/2)
}

func topologyAnnealRooms(
	blocks []compiledBlock,
	edges []directedEdge,
	side int,
	variant int,
) ([]annealRoom, bool) {
	rooms, ok := randomAnnealRooms(rand.New(rand.NewSource(1)), blocks, side)
	if !ok {
		return nil, false
	}
	byName := make(map[string]*annealRoom)
	for index := range rooms {
		byName[rooms[index].block.ID] = &rooms[index]
	}

	var core *annealRoom
	for index := range rooms {
		room := &rooms[index]
		if room.block.Type == "" &&
			(core == nil || room.width > core.width) {
			core = room
		}
	}
	if core == nil {
		return nil, false
	}
	core.block.X = 3
	core.block.Y = clamp(side/2-core.height/2, 3, side-core.height-3)

	var producer, consumer, relay *annealRoom
	for _, edge := range edges {
		if edge.Destination == core.block.ID &&
			edge.Source != "input" &&
			!strings.HasPrefix(edge.Source, "__pipe_") {
			producer = byName[edge.Source]
		}
		if edge.Source == core.block.ID &&
			edge.Destination != "output" &&
			!strings.HasPrefix(edge.Destination, "__pipe_") {
			consumer = byName[edge.Destination]
		}
	}
	for name, room := range byName {
		if strings.HasPrefix(name, "__pipe_") {
			relay = room
		}
	}
	input := byName["input"]
	output := byName["output"]
	if variant == 8 {
		core.block.X = 2
		core.block.Y = 9
		if producer == nil || consumer == nil || relay == nil ||
			input == nil || output == nil {
			return nil, false
		}
		producer.block.X = 2
		producer.block.Y = 0
		consumer.block.X = 2
		consumer.block.Y = core.block.Y + core.height + 2
		relay.block.X = side - relay.width - 2
		relay.block.Y = consumer.block.Y - 1
		input.block.X = producer.block.X + producer.width + 3
		input.block.Y = producer.block.Y
		output.block.X = consumer.block.X + consumer.width + 3
		output.block.Y = consumer.block.Y
		if hasRoomOverlap(rooms) || !roomsFitSide(rooms, side) {
			return nil, false
		}
		return rooms, true
	}
	gap := 1 + variant%4

	if producer != nil {
		producer.block.X = 3 + variant%2*4
		producer.block.Y = core.block.Y - producer.height - gap
	}
	if consumer != nil {
		consumer.block.X = 3 + variant%2*5
		consumer.block.Y = core.block.Y + core.height + gap
	}
	if relay != nil {
		relay.block.X = 35 + variant%2*8
		if variant < 4 {
			relay.block.Y = core.block.Y - relay.height - 2
		} else {
			relay.block.Y = core.block.Y + core.height + 2
		}
	}
	if input != nil && producer != nil {
		input.block.X = producer.block.X + producer.width + 3
		input.block.Y = producer.block.Y
	}
	if output != nil && consumer != nil {
		output.block.X = consumer.block.X + consumer.width + 3
		output.block.Y = consumer.block.Y
	}
	for _, room := range rooms {
		if room.block.X < 0 || room.block.Y < 0 ||
			room.block.X+room.width > side ||
			room.block.Y+room.height > side {
			return nil, false
		}
	}
	if hasRoomOverlap(rooms) {
		return nil, false
	}
	return rooms, true
}

func connectionOrders(
	connections []floorConnection,
) [][]floorConnection {
	if len(connections) == 0 {
		return [][]floorConnection{nil}
	}
	count := min(len(connections), 5)
	orders := make([][]floorConnection, 0, count)
	for shift := 0; shift < count; shift++ {
		order := make([]floorConnection, 0, len(connections))
		order = append(order, connections[shift:]...)
		order = append(order, connections[:shift]...)
		orders = append(orders, order)
	}
	return orders
}

func normalizeAnnealRooms(
	rooms []annealRoom,
	side int,
) ([]annealRoom, bool) {
	result := append([]annealRoom(nil), rooms...)
	minX, minY := math.MaxInt, math.MaxInt
	maxX, maxY := 0, 0
	for _, room := range result {
		minX = min(minX, room.block.X)
		minY = min(minY, room.block.Y)
		maxX = max(maxX, room.block.X+room.width)
		maxY = max(maxY, room.block.Y+room.height)
	}
	if maxX-minX+2 > side || maxY-minY+2 > side {
		return nil, false
	}
	for index := range result {
		result[index].block.X = result[index].block.X - minX + 1
		result[index].block.Y = result[index].block.Y - minY + 1
	}
	return result, true
}

func randomAnnealRooms(
	random *rand.Rand,
	blocks []compiledBlock,
	side int,
) ([]annealRoom, bool) {
	rooms := make([]annealRoom, 0, len(blocks)+2)
	for _, block := range blocks {
		rooms = append(rooms, annealRoom{
			block:  floorBlock{ID: block.Name, File: block.File},
			width:  block.Width + 2,
			height: block.Height + 2,
			ticks:  append([]int(nil), block.BacktickOffsets...),
			ports:  block.Ports,
		})
	}
	rooms = append(rooms,
		annealRoom{
			block:  floorBlock{ID: "input", Type: "I"},
			width:  3,
			height: 3,
		},
		annealRoom{
			block:  floorBlock{ID: "output", Type: "O"},
			width:  3,
			height: 3,
		},
	)
	sort.SliceStable(rooms, func(left, right int) bool {
		return rooms[left].width*rooms[left].height >
			rooms[right].width*rooms[right].height
	})

	placed := make([]annealRoom, 0, len(rooms))
	for _, room := range rooms {
		if room.width > side || room.height > side {
			return nil, false
		}
		found := false
		for attempt := 0; attempt < 2000; attempt++ {
			room.block.X = random.Intn(side - room.width + 1)
			room.block.Y = random.Intn(side - room.height + 1)
			trial := append(append([]annealRoom(nil), placed...), room)
			if !hasRoomOverlap(trial) {
				placed = append(placed, room)
				found = true
				break
			}
		}
		if !found {
			return nil, false
		}
	}
	return placed, true
}

func annealCost(
	rooms []annealRoom,
	edges []directedEdge,
	side int,
	compact bool,
) int64 {
	var cost int64
	minX, minY := math.MaxInt, math.MaxInt
	maxX, maxY := 0, 0
	for left := 0; left < len(rooms); left++ {
		for _, clearance := range []int{
			rooms[left].block.X,
			rooms[left].block.Y,
			side - rooms[left].block.X - rooms[left].width,
			side - rooms[left].block.Y - rooms[left].height,
		} {
			if clearance < 3 {
				cost += int64(3-clearance) * 10_000_000
			}
		}
		minX = min(minX, rooms[left].block.X)
		minY = min(minY, rooms[left].block.Y)
		maxX = max(maxX, rooms[left].block.X+rooms[left].width)
		maxY = max(maxY, rooms[left].block.Y+rooms[left].height)
		for right := left + 1; right < len(rooms); right++ {
			overlap := overlapArea(rooms[left], rooms[right], 0)
			cost += int64(overlap) * 100_000_000
			clearance := overlapArea(rooms[left], rooms[right], 1)
			cost += int64(clearance-overlap) * 100_000
		}
	}
	if compact {
		boundingWidth := maxX - minX
		boundingHeight := maxY - minY
		boundingSide := max(boundingWidth, boundingHeight)
		cost += int64(boundingSide) * 500_000
		cost += int64(boundingWidth*boundingHeight) * 1_000
	}

	byName := make(map[string]annealRoom)
	tickColumns := make(map[int]int)
	for _, room := range rooms {
		byName[room.block.ID] = room
		for _, offset := range room.ticks {
			column := room.block.X + 1 + offset
			tickColumns[column]++
		}
	}
	for _, count := range tickColumns {
		if count > 1 {
			cost += int64(count-1) * 5_000_000
		}
	}
	for _, edge := range edges {
		source, sourceOK := byName[edge.Source]
		destination, destinationOK := byName[edge.Destination]
		if !sourceOK || !destinationOK {
			continue
		}
		sourceX := source.block.X + source.width/2
		sourceY := source.block.Y + source.height/2
		destinationX := destination.block.X + destination.width/2
		destinationY := destination.block.Y + destination.height/2
		distance := absInt(sourceX-destinationX) +
			absInt(sourceY-destinationY)
		if edge.MinSize > 0 && distance < edge.MinSize {
			cost += int64(edge.MinSize-distance) * 5_000_000
		}
		cost += int64(distance) * 1_000
	}
	return cost
}

func overlapArea(left, right annealRoom, padding int) int {
	leftX := left.block.X - padding
	leftY := left.block.Y - padding
	leftRight := left.block.X + left.width + padding
	leftBottom := left.block.Y + left.height + padding
	rightX := right.block.X - padding
	rightY := right.block.Y - padding
	rightRight := right.block.X + right.width + padding
	rightBottom := right.block.Y + right.height + padding
	width := min(leftRight, rightRight) - max(leftX, rightX)
	height := min(leftBottom, rightBottom) - max(leftY, rightY)
	if width <= 0 || height <= 0 {
		return 0
	}
	return width * height
}

func hasRoomOverlap(rooms []annealRoom) bool {
	for left := 0; left < len(rooms); left++ {
		for right := left + 1; right < len(rooms); right++ {
			if overlapArea(rooms[left], rooms[right], 0) != 0 {
				return true
			}
		}
	}
	return false
}

func cloneCandidate(candidate annealCandidate) annealCandidate {
	return annealCandidate{
		rooms:    append([]annealRoom(nil), candidate.rooms...),
		cost:     candidate.cost,
		topology: candidate.topology,
	}
}

func candidateFloorBlocks(rooms []annealRoom) []floorBlock {
	result := make([]floorBlock, len(rooms))
	for index, room := range rooms {
		result[index] = room.block
	}
	return result
}

func floorConnections(edges []directedEdge) []floorConnection {
	var connections []floorConnection
	for _, category := range []string{"input", "output", "internal"} {
		for _, edge := range edges {
			isInput := edge.Source == "input"
			isOutput := edge.Destination == "output"
			if category == "input" && !isInput ||
				category == "output" && !isOutput ||
				category == "internal" && (isInput || isOutput) {
				continue
			}
			switch {
			case isInput:
				connections = append(connections, floorConnection{
					Src: "input.out",
					Dst: edge.Destination + "." + inputPort("input"),
				})
			case isOutput:
				connections = append(connections, floorConnection{
					Src: edge.Source + "." + outputPort("output"),
					Dst: "output.in",
				})
			default:
				connections = append(connections, floorConnection{
					Src: edge.Source + "." + outputPort(edge.Destination),
					Dst: edge.Destination + "." + inputPort(edge.Source),
				})
			}
		}
	}
	return connections
}

func clamp(value, minimum, maximum int) int {
	return min(max(value, minimum), maximum)
}

func absInt(value int) int {
	if value < 0 {
		return -value
	}
	return value
}
