# Floorplan

Floorplan composes compiled Little Man [`blocks`](../blocks) into standalone `.man` programs. Given fixed room coordinates and logical connections, it assembles the rooms, chooses ports, routes pipes, and trims the unused canvas.

It is a compositor and router, not a placement optimizer. Tools such as [Plumber](../plumber/README.md) search for good room coordinates and call Floorplan to test whether the resulting connections can actually be routed.


## Example

This floor connects the external input to a compiled FIFO room, then connects that room to the external output:

```json
{
  "grid_width": 16,
  "grid_height": 8,
  "blocks": [
    { "id": "input", "type": "I", "x": 0, "y": 4 },
    { "id": "relay", "file": "../blocks/fifo_relay.block", "x": 3, "y": 4 },
    { "id": "output", "type": "O", "x": 10, "y": 4 }
  ],
  "connections": [
    { "src": "input.out", "dst": "relay.input" },
    { "src": "relay.output", "dst": "output.in" }
  ]
}
```

Floorplan produces:

```text
 >----v>---v
 ^    v^   v
+-++-----++-+
|I||>@rsv||O|
+-+|^   <|+-+
   +-----+
```


## Routing

By default, each connection is routed with breadth-first search. The router:

- Considers every location allowed by the source and destination port ranges.
- Keeps pipes one cell away from unrelated room walls.
- Treats rooms and previously routed pipes as obstacles.
- Enforces the minimum and maximum pipe lengths declared by both ports.
- Requires a pipe to leave its source wall straight outward.

Connections are routed in file order, so difficult or highly constrained connections should usually appear first.

`route: "horizontal-first"` changes the BFS neighbor preference; the default preference is vertical first.

A connection may override its selected port geometry with `src_side`, `dst_side`, `src_offset`, and `dst_offset`.

For exact control, `waypoints` define an orthogonal route:
```json
{
  "src": "producer.output",
  "dst": "consumer.input",
  "waypoints": [
    {"x": 20, "y": 4},
    {"x": 20, "y": 18},
    {"x": 35, "y": 18}
  ]
}
```

Every consecutive segment must be horizontal or vertical. Floorplan checks the resulting path for bounds, self-intersections, occupied cells, and pipe length, but does not move explicit waypoints around obstacles.

Long storage pipes can be described as a rectangular snake:
```json
{
  "src": "engine.storage_out",
  "dst": "engine.storage_in",
  "waypoints": [{"x": 8, "y": 12}],
  "snake": {
    "x": 8,
    "y": 13,
    "width": 20,
    "height": 6,
    "axis": "horizontal",
    "start": "top-left"
  },
  "tail_waypoints": [{"x": 30, "y": 10}]
}
```

The route visits the initial waypoints, every cell of the snake, and then the tail waypoints. `axis` may be `horizontal` or `vertical`; `start` may be any corner such as `top-left` or `bottom-right`.


## Algorithm

Floorplan performs one deterministic pass:

1. Load every `.block` and draw all room or display borders and interiors.
2. Expand each port definition into its legal border and adjacent cells.
3. Reserve a one-cell routing clearance around every room.
4. Route connections sequentially with BFS or their structured paths.
5. Check path geometry and both endpoints' pipe-length contracts.
6. Remove temporary clearances and trim empty outer rows and columns.

On success, the result always fits within the specified area, which makes Floorplan useful for fixed-outline placements.
