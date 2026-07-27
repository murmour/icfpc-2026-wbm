package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"strconv"
	"strings"
)

type Point struct {
	X int `json:"x"`
	Y int `json:"y"`
}

type PortDef struct {
	Type        string `json:"type"`
	Side        string `json:"side"`
	OffsetRange []int  `json:"offset_range"`
	LengthRange []int  `json:"length_range"`
}

type BlockDef struct {
	Name     string             `json:"name"`
	Size     string             `json:"size"`
	Interior []string           `json:"interior"`
	Ports    map[string]PortDef `json:"ports"`
}

type LayoutBlock struct {
	ID   string `json:"id"`
	File string `json:"file,omitempty"`
	Type string `json:"type,omitempty"`
	X    int    `json:"x"`
	Y    int    `json:"y"`
	Size string `json:"size,omitempty"`
}

type LayoutConn struct {
	Src           string    `json:"src"`
	Dst           string    `json:"dst"`
	SrcSide       string    `json:"src_side,omitempty"`
	DstSide       string    `json:"dst_side,omitempty"`
	SrcOffset     *int      `json:"src_offset,omitempty"`
	DstOffset     *int      `json:"dst_offset,omitempty"`
	Route         string    `json:"route,omitempty"`
	Waypoints     []Point   `json:"waypoints,omitempty"`
	Snake         *SnakeDef `json:"snake,omitempty"`
	TailWaypoints []Point   `json:"tail_waypoints,omitempty"`
}

type SnakeDef struct {
	X      int    `json:"x"`
	Y      int    `json:"y"`
	Width  int    `json:"width"`
	Height int    `json:"height"`
	Axis   string `json:"axis,omitempty"`
	Start  string `json:"start,omitempty"`
}

type Layout struct {
	GridWidth   int           `json:"grid_width"`
	GridHeight  int           `json:"grid_height"`
	Blocks      []LayoutBlock `json:"blocks"`
	Connections []LayoutConn  `json:"connections"`
}

func buildGrid(w, h int) [][]byte {
	grid := make([][]byte, h)
	for i := range grid {
		grid[i] = make([]byte, w)
		for j := range grid[i] {
			grid[i][j] = ' '
		}
	}
	return grid
}

func drawRoom(grid [][]byte, x, y, w, h int, interior []string) {
	for i := 0; i < w; i++ {
		grid[y][x+i] = '-'
		grid[y+h-1][x+i] = '-'
	}
	for i := 0; i < h; i++ {
		grid[y+i][x] = '|'
		grid[y+i][x+w-1] = '|'
	}
	grid[y][x] = '+'
	grid[y][x+w-1] = '+'
	grid[y+h-1][x] = '+'
	grid[y+h-1][x+w-1] = '+'

	if interior != nil {
		for i, row := range interior {
			for j := 0; j < len(row); j++ {
				grid[y+1+i][x+1+j] = row[j]
			}
		}
	}
}

func drawDisplay(grid [][]byte, x, y, width, height int) {
	for px := 0; px < width+2; px++ {
		grid[y][x+px] = '='
		grid[y+height+1][x+px] = '='
	}
	for py := 0; py < height+2; py++ {
		grid[y+py][x] = ':'
		grid[y+py][x+width+1] = ':'
	}
	grid[y][x] = '+'
	grid[y][x+width+1] = '+'
	grid[y+height+1][x] = '+'
	grid[y+height+1][x+width+1] = '+'
}

type PortLoc struct {
	Border Point
	Adj    Point
}

func getPortLocs(x, y, w, h int, side string, offsetRange []int) []PortLoc {
	var locs []PortLoc
	minOff := offsetRange[0]
	maxOff := offsetRange[1]
	if len(offsetRange) == 1 {
		maxOff = minOff
	}

	for off := minOff; off <= maxOff; off++ {
		if side == "top" {
			locs = append(locs, PortLoc{Point{x + 1 + off, y}, Point{x + 1 + off, y - 1}})
		} else if side == "bottom" {
			locs = append(locs, PortLoc{Point{x + 1 + off, y + h - 1}, Point{x + 1 + off, y + h}})
		} else if side == "left" {
			locs = append(locs, PortLoc{Point{x, y + 1 + off}, Point{x - 1, y + 1 + off}})
		} else if side == "right" {
			locs = append(locs, PortLoc{Point{x + w - 1, y + 1 + off}, Point{x + w, y + 1 + off}})
		}
	}
	return locs
}

func abs(a int) int {
	if a < 0 {
		return -a
	}
	return a
}

type Node struct {
	pt   Point
	path []Point
}

func getDir(from, to Point) Point {
	dx := to.X - from.X
	if dx != 0 {
		dx /= abs(dx)
	}
	dy := to.Y - from.Y
	if dy != 0 {
		dy /= abs(dy)
	}
	return Point{dx, dy}
}

func getArrow(dir Point) byte {
	if dir.X == 1 {
		return '>'
	} else if dir.X == -1 {
		return '<'
	} else if dir.Y == 1 {
		return 'v'
	} else {
		return '^'
	}
}

func appendStraight(path []Point, dst Point) ([]Point, error) {
	src := path[len(path)-1]
	if src.X != dst.X && src.Y != dst.Y {
		return nil, fmt.Errorf("route segment from %v to %v is not orthogonal", src, dst)
	}
	dir := getDir(src, dst)
	for src != dst {
		src = Point{src.X + dir.X, src.Y + dir.Y}
		path = append(path, src)
	}
	return path, nil
}

func closestPort(locs []PortLoc, target Point) PortLoc {
	best := locs[0]
	bestDistance := abs(best.Adj.X-target.X) + abs(best.Adj.Y-target.Y)
	for _, loc := range locs[1:] {
		distance := abs(loc.Adj.X-target.X) + abs(loc.Adj.Y-target.Y)
		if distance < bestDistance {
			best = loc
			bestDistance = distance
		}
	}
	return best
}

func waypointPath(srcLocs, dstLocs []PortLoc, waypoints []Point) ([]Point, error) {
	src := closestPort(srcLocs, waypoints[0])
	dst := closestPort(dstLocs, waypoints[len(waypoints)-1])
	path := []Point{src.Border, src.Adj}

	var err error
	for _, waypoint := range waypoints {
		path, err = appendStraight(path, waypoint)
		if err != nil {
			return nil, err
		}
	}
	path, err = appendStraight(path, dst.Adj)
	if err != nil {
		return nil, err
	}
	return append(path, dst.Border), nil
}

func snakePoints(def SnakeDef) ([]Point, error) {
	if def.Width <= 0 || def.Height <= 0 {
		return nil, fmt.Errorf("snake dimensions must be positive")
	}
	if def.Axis == "" {
		def.Axis = "horizontal"
	}
	if def.Start == "" {
		def.Start = "top-left"
	}

	var points []Point
	switch def.Axis {
	case "horizontal":
		topDown := strings.HasPrefix(def.Start, "top-")
		leftFirst := strings.HasSuffix(def.Start, "-left")
		if !topDown && !strings.HasPrefix(def.Start, "bottom-") {
			return nil, fmt.Errorf("invalid snake start %q", def.Start)
		}
		for rowIndex := 0; rowIndex < def.Height; rowIndex++ {
			row := rowIndex
			if !topDown {
				row = def.Height - 1 - rowIndex
			}
			leftToRight := leftFirst
			if rowIndex%2 == 1 {
				leftToRight = !leftToRight
			}
			for columnIndex := 0; columnIndex < def.Width; columnIndex++ {
				column := columnIndex
				if !leftToRight {
					column = def.Width - 1 - columnIndex
				}
				points = append(points, Point{def.X + column, def.Y + row})
			}
		}
	case "vertical":
		leftRight := strings.HasSuffix(def.Start, "-left")
		topFirst := strings.HasPrefix(def.Start, "top-")
		if !topFirst && !strings.HasPrefix(def.Start, "bottom-") {
			return nil, fmt.Errorf("invalid snake start %q", def.Start)
		}
		for columnIndex := 0; columnIndex < def.Width; columnIndex++ {
			column := columnIndex
			if !leftRight {
				column = def.Width - 1 - columnIndex
			}
			topToBottom := topFirst
			if columnIndex%2 == 1 {
				topToBottom = !topToBottom
			}
			for rowIndex := 0; rowIndex < def.Height; rowIndex++ {
				row := rowIndex
				if !topToBottom {
					row = def.Height - 1 - rowIndex
				}
				points = append(points, Point{def.X + column, def.Y + row})
			}
		}
	default:
		return nil, fmt.Errorf("invalid snake axis %q", def.Axis)
	}
	return points, nil
}

func structuredPath(srcLocs, dstLocs []PortLoc, conn LayoutConn) ([]Point, error) {
	routePoints := append([]Point(nil), conn.Waypoints...)
	if conn.Snake != nil {
		snake, err := snakePoints(*conn.Snake)
		if err != nil {
			return nil, err
		}
		routePoints = append(routePoints, snake...)
	}
	routePoints = append(routePoints, conn.TailWaypoints...)
	return waypointPath(srcLocs, dstLocs, routePoints)
}

func main() {
	layoutPath := flag.String("layout", "layout.floor", "layout JSON file")
	outputPath := flag.String("output", "2_memory_solution.man", "generated program path")
	flag.Parse()

	b, err := os.ReadFile(*layoutPath)
	if err != nil {
		panic(err)
	}
	var layout Layout
	if err := json.Unmarshal(b, &layout); err != nil {
		panic(err)
	}

	grid := buildGrid(layout.GridWidth, layout.GridHeight)
	temporaryBuffers := make(map[Point]bool)

	portMap := make(map[string][]PortLoc)
	portLengthRanges := make(map[string][]int)

	for _, lb := range layout.Blocks {
		if lb.Type == "I" || lb.Type == "O" {
			drawRoom(grid, lb.X, lb.Y, 3, 3, []string{lb.Type})
			// I/O rooms can connect on any side, any offset (0)
			for _, side := range []string{"top", "bottom", "left", "right"} {
				name := lb.ID + ".out"
				if lb.Type == "O" {
					name = lb.ID + ".in"
				}
				portMap[name] = append(portMap[name], getPortLocs(lb.X, lb.Y, 3, 3, side, []int{0, 0})...)
				portLengthRanges[name] = []int{2, layout.GridWidth * layout.GridHeight}
			}
		} else if lb.Type == "D" {
			parts := strings.Split(lb.Size, "x")
			if len(parts) != 2 {
				panic(fmt.Errorf("display %s has invalid size %q", lb.ID, lb.Size))
			}
			width, widthErr := strconv.Atoi(parts[0])
			height, heightErr := strconv.Atoi(parts[1])
			if widthErr != nil || heightErr != nil || width < 1 || height < 1 || width > 64 || height > 64 {
				panic(fmt.Errorf("display %s has invalid size %q", lb.ID, lb.Size))
			}
			drawDisplay(grid, lb.X, lb.Y, width, height)
			portMap[lb.ID+".addr"] = getPortLocs(lb.X, lb.Y, width+2, height+2, "top", []int{0, width - 1})
			portMap[lb.ID+".data"] = getPortLocs(lb.X, lb.Y, width+2, height+2, "left", []int{0, height - 1})
			portMap[lb.ID+".swap"] = getPortLocs(lb.X, lb.Y, width+2, height+2, "bottom", []int{0, width - 1})
			for _, name := range []string{"addr", "data", "swap"} {
				portLengthRanges[lb.ID+"."+name] = []int{2, layout.GridWidth * layout.GridHeight}
			}
		} else {
			db, err := os.ReadFile(lb.File)
			if err != nil {
				panic(err)
			}
			var bdef BlockDef
			if err := json.Unmarshal(db, &bdef); err != nil {
				panic(err)
			}
			parts := strings.Split(bdef.Size, "x")
			w, _ := strconv.Atoi(parts[0])
			h, _ := strconv.Atoi(parts[1])

			for i, row := range bdef.Interior {
				if len(row) < w {
					bdef.Interior[i] = row + strings.Repeat(" ", w-len(row))
				}
			}

			drawRoom(grid, lb.X, lb.Y, w+2, h+2, bdef.Interior)

			for pname, pdef := range bdef.Ports {
				side := pdef.Side
				offsetRange := append([]int(nil), pdef.OffsetRange...)
				// If layout overrides side
				overrideName := lb.ID + "." + pname

				for _, conn := range layout.Connections {
					if conn.Src == overrideName && conn.SrcSide != "" {
						side = conn.SrcSide
					}
					if conn.Src == overrideName && conn.SrcOffset != nil {
						offsetRange = []int{*conn.SrcOffset}
					}
					if conn.Dst == overrideName && conn.DstSide != "" {
						side = conn.DstSide
					}
					if conn.Dst == overrideName && conn.DstOffset != nil {
						offsetRange = []int{*conn.DstOffset}
					}
				}
				if side == "any" {
					side = "bottom" // fallback
				}

				offMax := offsetRange[0]
				if len(offsetRange) > 1 {
					offMax = offsetRange[1]
				}

				if side == "top" || side == "bottom" {
					if offsetRange[0] < 0 || offMax >= w {
						panic(fmt.Errorf("port %s offset %v does not fit width %d", overrideName, offsetRange, w))
					}
				} else {
					if offsetRange[0] < 0 || offMax >= h {
						panic(fmt.Errorf("port %s offset %v does not fit height %d", overrideName, offsetRange, h))
					}
				}

				locs := getPortLocs(lb.X, lb.Y, w+2, h+2, side, []int{offsetRange[0], offMax})
				portMap[overrideName] = locs
				portLengthRanges[overrideName] = pdef.LengthRange
			}
		}
	}

	// Keep routes one cell away from unrelated room walls. Port-adjacent cells
	// remain valid BFS starts and destinations.
	for _, lb := range layout.Blocks {
		w, h := 3, 3
		if lb.Type == "D" {
			parts := strings.Split(lb.Size, "x")
			displayWidth, _ := strconv.Atoi(parts[0])
			displayHeight, _ := strconv.Atoi(parts[1])
			w, h = displayWidth+2, displayHeight+2
		} else if lb.Type != "I" && lb.Type != "O" {
			db, readErr := os.ReadFile(lb.File)
			if readErr != nil {
				panic(readErr)
			}
			var bdef BlockDef
			if unmarshalErr := json.Unmarshal(db, &bdef); unmarshalErr != nil {
				panic(unmarshalErr)
			}
			parts := strings.Split(bdef.Size, "x")
			interiorW, _ := strconv.Atoi(parts[0])
			interiorH, _ := strconv.Atoi(parts[1])
			w, h = interiorW+2, interiorH+2
		}
		for x := lb.X; x < lb.X+w; x++ {
			for _, y := range []int{lb.Y - 1, lb.Y + h} {
				if y >= 0 && y < layout.GridHeight && grid[y][x] == ' ' {
					grid[y][x] = '*'
					temporaryBuffers[Point{x, y}] = true
				}
			}
		}
		for y := lb.Y; y < lb.Y+h; y++ {
			for _, x := range []int{lb.X - 1, lb.X + w} {
				if x >= 0 && x < layout.GridWidth && grid[y][x] == ' ' {
					grid[y][x] = '*'
					temporaryBuffers[Point{x, y}] = true
				}
			}
		}
	}

	for _, conn := range layout.Connections {
		srcLocs := portMap[conn.Src]
		dstLocs := portMap[conn.Dst]
		if len(srcLocs) == 0 || len(dstLocs) == 0 {
			fmt.Printf("Error: Unknown connection endpoint %s or %s\n", conn.Src, conn.Dst)
			os.Exit(1)
		}

		var bestPath []Point
		found := false
		structuredRoute := len(conn.Waypoints) > 0 || conn.Snake != nil || len(conn.TailWaypoints) > 0
		if structuredRoute {
			bestPath, err = structuredPath(srcLocs, dstLocs, conn)
			if err != nil {
				fmt.Printf("Error: Could not route %s to %s: %v\n", conn.Src, conn.Dst, err)
				os.Exit(1)
			}
			found = true
		}

		// BFS
		var q []Point
		visited := make(map[Point]bool)
		parent := make(map[Point]Point)
		starts := make(map[Point]Point) // To know which border a start node came from

		if !found {
			for _, sl := range srcLocs {
				if sl.Adj.X >= 0 && sl.Adj.Y >= 0 && sl.Adj.X < layout.GridWidth && sl.Adj.Y < layout.GridHeight {
					if grid[sl.Adj.Y][sl.Adj.X] == ' ' || grid[sl.Adj.Y][sl.Adj.X] == '*' {
						q = append(q, sl.Adj)
						visited[sl.Adj] = true
						starts[sl.Adj] = sl.Border
					}
				}
			}
		}

		for len(q) > 0 {
			curr := q[0]
			q = q[1:]

			// Check if we reached any dstLocs.Adj
			isDst := false
			var matchingDst PortLoc
			for _, dl := range dstLocs {
				if curr == dl.Adj {
					isDst = true
					matchingDst = dl
					break
				}
			}
			if isDst {
				// Reconstruct path
				bestPath = append(bestPath, matchingDst.Border)
				pt := curr
				for {
					bestPath = append(bestPath, pt)
					if p, ok := parent[pt]; ok {
						pt = p
					} else {
						break
					}
				}
				bestPath = append(bestPath, starts[pt])
				// Reverse path
				for i, j := 0, len(bestPath)-1; i < j; i, j = i+1, j-1 {
					bestPath[i], bestPath[j] = bestPath[j], bestPath[i]
				}
				found = true
				break
			}

			dirs := []Point{{0, 1}, {0, -1}, {1, 0}, {-1, 0}}
			if conn.Route == "horizontal-first" {
				dirs = []Point{{1, 0}, {-1, 0}, {0, 1}, {0, -1}}
			}
			for _, d := range dirs {
				npt := Point{curr.X + d.X, curr.Y + d.Y}
				if npt.X >= 0 && npt.Y >= 0 && npt.X < layout.GridWidth && npt.Y < layout.GridHeight {
					if (grid[npt.Y][npt.X] == ' ' || grid[npt.Y][npt.X] == '*') && !visited[npt] {
						// we only allow '*' if it's the final destination
						isDest := false
						for _, dl := range dstLocs {
							if npt == dl.Adj {
								isDest = true
								break
							}
						}

						if grid[npt.Y][npt.X] == ' ' || isDest {
							visited[npt] = true
							parent[npt] = curr
							q = append(q, npt)
						}
					}
				}
			}
		}

		if !found {
			fmt.Printf("Error: Could not route %s to %s\n", conn.Src, conn.Dst)
			os.Exit(1)
		}

		if len(bestPath) < 4 || getDir(bestPath[0], bestPath[1]) != getDir(bestPath[1], bestPath[2]) {
			fmt.Printf("Error: Route %s to %s does not depart its source straight outward\n", conn.Src, conn.Dst)
			os.Exit(1)
		}

		routeCells := make(map[Point]bool)
		for index, pt := range bestPath[1 : len(bestPath)-1] {
			if pt.X < 0 || pt.Y < 0 || pt.X >= layout.GridWidth || pt.Y >= layout.GridHeight {
				fmt.Printf("Error: Route %s to %s leaves the grid at %v\n", conn.Src, conn.Dst, pt)
				os.Exit(1)
			}
			if routeCells[pt] {
				fmt.Printf("Error: Route %s to %s intersects itself at %v\n", conn.Src, conn.Dst, pt)
				os.Exit(1)
			}
			routeCells[pt] = true
			allowedBufferCell := structuredRoute && grid[pt.Y][pt.X] == '*'
			if grid[pt.Y][pt.X] != ' ' && !allowedBufferCell && !(index == 0 || index == len(bestPath)-3) {
				fmt.Printf("Error: Route %s to %s intersects %q at %v\n",
					conn.Src, conn.Dst, grid[pt.Y][pt.X], pt)
				os.Exit(1)
			}
		}

		pipeLength := len(bestPath) - 2
		for _, endpoint := range []string{conn.Src, conn.Dst} {
			lengthRange := portLengthRanges[endpoint]
			if len(lengthRange) > 0 && pipeLength < lengthRange[0] {
				fmt.Printf("Error: Pipe %s to %s has length %d, below %s minimum %d\n",
					conn.Src, conn.Dst, pipeLength, endpoint, lengthRange[0])
				os.Exit(1)
			}
			if len(lengthRange) > 1 && pipeLength > lengthRange[1] {
				fmt.Printf("Error: Pipe %s to %s has length %d, above %s maximum %d\n",
					conn.Src, conn.Dst, pipeLength, endpoint, lengthRange[1])
				os.Exit(1)
			}
		}

		fmt.Printf("Routed %s to %s (pipe len %d)\n", conn.Src, conn.Dst, pipeLength)

		// Draw pipe
		pipeCells := bestPath[1 : len(bestPath)-1]
		for i := 0; i < len(pipeCells); i++ {
			pt := pipeCells[i]
			prevPt := bestPath[i]
			nextPt := bestPath[i+2]

			prevDir := getDir(prevPt, pt)
			nextDir := getDir(pt, nextPt)

			if i == 0 || i == len(pipeCells)-1 || prevDir != nextDir {
				grid[pt.Y][pt.X] = getArrow(nextDir)
			} else {
				if prevDir.X != 0 {
					grid[pt.Y][pt.X] = '-'
				} else {
					grid[pt.Y][pt.X] = '|'
				}
			}
		}
	}

	for point := range temporaryBuffers {
		if grid[point.Y][point.X] == '*' {
			grid[point.Y][point.X] = ' '
		}
	}

	// Trim empty rows/cols
	minX, maxX, minY, maxY := layout.GridWidth, 0, layout.GridHeight, 0
	for y := 0; y < layout.GridHeight; y++ {
		for x := 0; x < layout.GridWidth; x++ {
			if grid[y][x] != ' ' {
				if x < minX {
					minX = x
				}
				if x > maxX {
					maxX = x
				}
				if y < minY {
					minY = y
				}
				if y > maxY {
					maxY = y
				}
			}
		}
	}

	if minX > maxX {
		fmt.Println("Grid is empty!")
		return
	}

	var out []string
	for y := minY; y <= maxY; y++ {
		out = append(out, string(grid[y][minX:maxX+1]))
	}

	if err := os.WriteFile(*outputPath, []byte(strings.Join(out, "\n")), 0644); err != nil {
		panic(err)
	}
	fmt.Printf("Wrote %s\n", *outputPath)
}
