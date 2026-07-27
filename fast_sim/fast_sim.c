#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(PROFILE_MODE) && !defined(FAST_MODE)
#error "PROFILE_MODE requires FAST_MODE"
#undef PROFILE_MODE
#endif
#if defined(PROFILE_MODE) && !defined(COMPUTED_GOTO)
#error "PROFILE_MODE requires COMPUTED_GOTO"
#undef PROFILE_MODE
#endif
#if defined(PROFILE_MODE) && !defined(__GNUC__) && !defined(__clang__)
#error "PROFILE_MODE requires computed-goto compiler support"
#undef PROFILE_MODE
#endif

#ifdef TV_MODE
#include <SDL3/SDL.h>
#endif

#ifndef FAST_MODE
#define MAX_LIVE_MEN 65536
#else
typedef enum {
    DIR_EAST,
    DIR_SOUTH,
    DIR_WEST,
    DIR_NORTH,
} Direction;

typedef enum {
    TRACE_NOP,
    TRACE_HALT,
    TRACE_MOVE_A_TO_B,
    TRACE_SWAP,
    TRACE_ADD,
    TRACE_SUB,
    TRACE_MUL,
    TRACE_MOD,
    TRACE_DIV,
    TRACE_NEG,
    TRACE_AND,
    TRACE_OR,
    TRACE_XOR,
    TRACE_SHIFT_LEFT,
    TRACE_SHIFT_RIGHT,
    TRACE_LOAD,
    TRACE_BRANCH_SIGN,
    TRACE_SET_BP,
    TRACE_DEC_BP,
    TRACE_BRANCH_BP_POS_CW,
    TRACE_BRANCH_BP_POS_CCW,
    TRACE_SHIFT_BP,
    TRACE_BRANCH_BP_PARITY,
    TRACE_PIPE_COUNT,
    TRACE_SEND,
    TRACE_SEND_ALL,
    TRACE_READ,
    TRACE_READ_ANY,
    TRACE_READ_TURN,
    TRACE_INVALID_LITERAL,
    TRACE_UNSUPPORTED,
#ifdef PROFILE_MODE
    TRACE_OPCODE_COUNT,
#endif
} TraceOpcode;

typedef struct {
    int32_t next;
    int32_t branch;
    int32_t operand;
    uint8_t opcode;
} TraceOp;

_Static_assert(sizeof(TraceOp) == 16, "TraceOp must stay cache-compact");

typedef struct {
    int32_t positive;
    int32_t negative;
} TraceSignTargets;

#endif

typedef struct {
    int x, y;
} Point;

#ifdef FAST_MODE
typedef struct {
    int room_id;
    Point point;
    int *pipe_targets;
} TraceReadInfo;
#endif

typedef enum {
    ROOM_MAIN,
    ROOM_INPUT,
    ROOM_OUTPUT,
    ROOM_DISPLAY,
} RoomType;

typedef struct {
    int min_x, min_y, max_x, max_y;
    RoomType type;
    int *incoming;
    int incoming_count;
    int incoming_cap;
    int *outgoing;
    int outgoing_count;
    int outgoing_cap;
} Room;

typedef struct {
    Point *path;
    int length;
    int *token_positions;
    int token_count;
#ifdef FAST_MODE
    int queue_head;
    int64_t *queued_values;
    uint64_t *queued_arrivals;
    bool source_full;
    bool dest_full;
    bool source_release_pending;
    bool arrival_pending;
#endif
    int source_room;
    int dest_room;
    Point source_segment;
    Point dest_segment;
} Pipe;

#ifdef FAST_MODE
typedef enum {
    PIPE_SOURCE_RELEASE,
    PIPE_ARRIVAL,
} PipeEventType;

typedef struct {
    uint64_t tick;
    int pipe_id;
    PipeEventType type;
} PipeEvent;

typedef struct {
    uint64_t tick;
    int man_index;
} ManEvent;
#endif

typedef struct {
    int min_x, min_y, max_x, max_y;
    bool horizontal;
    int64_t forward;
    int64_t backward;
    bool forward_valid;
    bool backward_valid;
} Literal;

typedef struct {
    int id;
    int x, y;
    int dx, dy;
#ifdef FAST_MODE
    int pc;
#endif
    int64_t a, b, bp;
    uint64_t born_tick;
    bool halted;
    bool blocked;
} Man;

typedef struct {
    int room;
    int width, height;
    int cursor;
    int addr_pipe;
    int data_pipe;
    int swap_pipe;
    int64_t *current;
    int64_t *next;
#ifdef TV_MODE
    uint8_t *painted;
#endif
    uint64_t writes;
    uint64_t swaps;
} Display;

typedef struct {
    int width, height, cells;
    char *grid;
    int *room_at;
    int *literal_h;
    int *literal_v;
    int *nearest_in;
    int *nearest_out;

    Room *rooms;
    int room_count;
    int room_cap;
    Pipe *pipes;
    int pipe_count;
    int pipe_cap;
    Literal *literals;
    int literal_count;
    int literal_cap;
    Man *men;
    int man_count;
    int man_cap;
#ifndef FAST_MODE
    Point *old_positions;
    uint8_t *moved;
    uint8_t *collided;
    int *old_occupant;
    uint32_t *old_occupant_stamp;
    int *new_occupant;
    uint32_t *new_occupant_stamp;
    uint32_t movement_generation;
#else
    int *sleeping_readers;
    int *sleeping_writers;
    PipeEvent *pipe_events;
    int pipe_event_count;
    int pipe_event_cap;
    ManEvent *man_events;
    int man_event_count;
    int man_event_cap;
    uint8_t *man_event_pending;
    TraceOp *trace_ops;
    int trace_op_count;
    int trace_op_cap;
    int64_t *trace_constants;
    int trace_constant_count;
    int trace_constant_cap;
    TraceSignTargets *trace_sign_targets;
    int trace_sign_count;
    int trace_sign_cap;
    TraceReadInfo *trace_reads;
    int trace_read_count;
    int trace_read_cap;
    uint64_t *runnable_men;
    int runnable_word_count;
    int live_man_count;
    int *display_by_room;
    uint8_t *dirty_displays;
    int dirty_display_count;
#ifdef PROFILE_MODE
    bool profile_enabled;
    uint64_t *profile_active_ticks;
    uint64_t *profile_opcode_counts;
    uint64_t *profile_wait_started;
    int *profile_wait_pipe;
    uint8_t *profile_wait_reader;
    uint64_t *profile_wait_ticks;
    uint64_t *profile_wait_events;
    uint64_t *profile_pipe_sends;
    uint64_t *profile_pipe_consumes;
#endif
#endif
    Display *displays;
    int display_count;
    int display_cap;

    int *pipe_next;
    int *pipe_order;
    int pipe_order_count;
    int64_t *pipe_value;
    uint8_t *pipe_full;

    int input_room;
    int output_room;
    uint64_t ticks;
    int next_man_id;
    bool halted;
    char error[256];
} Program;

static void die(const char *message) {
    fprintf(stderr, "%s\n", message);
    exit(1);
}

#ifdef TV_MODE
typedef struct {
    SDL_Window *window;
    SDL_Renderer *renderer;
    SDL_Texture *texture;
    uint64_t last_present_ms;
    uint64_t last_swaps;
    unsigned poll_counter;
    bool swap_only;
} VisualDisplay;

static const uint32_t c64_colors_abgr[] = {
    0xFF000000, 0xFFFFFFFF, 0xFF444E9F, 0xFFC6BF6A,
    0xFFA357A0, 0xFF5EAB5C, 0xFF9B4550, 0xFF87D4C9,
    0xFF3C68A1, 0xFF12546D, 0xFF757ECB, 0xFF626262,
    0xFF898989, 0xFF9BE29A, 0xFFCB7E88, 0xFFADADAD,
};

static void visual_fail(const char *message) {
    fprintf(stderr, "%s: %s\n", message, SDL_GetError());
    exit(1);
}

static SDL_FRect visual_draw_rect(
    SDL_Renderer *renderer, int source_width, int source_height
) {
    int output_width, output_height;
    if (!SDL_GetCurrentRenderOutputSize(
            renderer, &output_width, &output_height)) {
        visual_fail("SDL_GetCurrentRenderOutputSize failed");
    }
    float source_aspect = (float)source_width / (float)source_height;
    float output_aspect = (float)output_width / (float)output_height;
    SDL_FRect result;
    if (output_aspect > source_aspect) {
        result.h = (float)output_height;
        result.w = result.h * source_aspect;
        result.x = ((float)output_width - result.w) * 0.5f;
        result.y = 0;
    } else {
        result.w = (float)output_width;
        result.h = result.w / source_aspect;
        result.x = 0;
        result.y = ((float)output_height - result.h) * 0.5f;
    }
    return result;
}

static void visual_present(
    VisualDisplay *visual, const Display *display
) {
    void *pixels;
    int pitch;
    if (!SDL_LockTexture(visual->texture, NULL, &pixels, &pitch)) {
        visual_fail("SDL_LockTexture failed");
    }
    for (int y = 0; y < display->height; y++) {
        uint32_t *row =
            (uint32_t *)((uint8_t *)pixels + (size_t)y * (size_t)pitch);
        for (int x = 0; x < display->width; x++) {
            int index = y * display->width + x;
            int64_t color =
                !visual->swap_only && display->painted[index]
                    ? display->next[index]
                    : display->current[index];
            row[x] = c64_colors_abgr[color];
        }
    }
    SDL_UnlockTexture(visual->texture);

    SDL_FRect destination = visual_draw_rect(
        visual->renderer, display->width, display->height);
    if (!SDL_SetRenderDrawColor(visual->renderer, 0, 0, 0, 255) ||
        !SDL_RenderClear(visual->renderer) ||
        !SDL_RenderTexture(
            visual->renderer, visual->texture, NULL, &destination) ||
        !SDL_RenderPresent(visual->renderer)) {
        visual_fail("SDL rendering failed");
    }
    visual->last_present_ms = SDL_GetTicks();
}

static void visual_init(
    VisualDisplay *visual, const Display *display, bool swap_only
) {
    memset(visual, 0, sizeof(*visual));
    visual->swap_only = swap_only;
    if (!SDL_Init(SDL_INIT_VIDEO)) {
        visual_fail("SDL_Init failed");
    }
    int scale = 8;
    int window_width = display->width * scale;
    int window_height = display->height * scale;
    if (!SDL_CreateWindowAndRenderer(
            "Little Man TV", window_width, window_height,
            SDL_WINDOW_RESIZABLE, &visual->window, &visual->renderer)) {
        visual_fail("SDL_CreateWindowAndRenderer failed");
    }
    if (!SDL_SetRenderVSync(visual->renderer, 1)) {
        fprintf(
            stderr, "warning: SDL_SetRenderVSync failed: %s\n",
            SDL_GetError());
    }
    visual->texture = SDL_CreateTexture(
        visual->renderer, SDL_PIXELFORMAT_ABGR8888,
        SDL_TEXTUREACCESS_STREAMING, display->width, display->height);
    if (!visual->texture) {
        visual_fail("SDL_CreateTexture failed");
    }
    if (!SDL_SetTextureScaleMode(
            visual->texture, SDL_SCALEMODE_NEAREST)) {
        visual_fail("SDL_SetTextureScaleMode failed");
    }
    visual->last_swaps = display->swaps;
    visual_present(visual, display);
}

static bool visual_update(
    VisualDisplay *visual, const Display *display, bool force
) {
    if (!force && ++visual->poll_counter < 1024) {
        return true;
    }
    visual->poll_counter = 0;
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_EVENT_QUIT ||
            (event.type == SDL_EVENT_KEY_DOWN &&
             event.key.key == SDLK_ESCAPE)) {
            return false;
        }
    }

    uint64_t now = SDL_GetTicks();
    bool swapped = display->swaps != visual->last_swaps;
    if (!force && !swapped && now - visual->last_present_ms < 16) {
        return true;
    }
    if (swapped) {
        visual->last_swaps = display->swaps;
    }
    visual_present(visual, display);
    return true;
}

static void visual_destroy(VisualDisplay *visual) {
    SDL_DestroyTexture(visual->texture);
    SDL_DestroyRenderer(visual->renderer);
    SDL_DestroyWindow(visual->window);
    SDL_Quit();
}
#endif

static void *xmalloc(size_t size) {
    void *ptr = malloc(size ? size : 1);
    if (!ptr) {
        die("out of memory");
    }
    return ptr;
}

static void *xcalloc(size_t count, size_t size) {
    void *ptr = calloc(count ? count : 1, size ? size : 1);
    if (!ptr) {
        die("out of memory");
    }
    return ptr;
}

static void *xrealloc(void *ptr, size_t size) {
    void *result = realloc(ptr, size ? size : 1);
    if (!result) {
        die("out of memory");
    }
    return result;
}

static int cell_index(const Program *p, int x, int y) {
    return y * p->width + x;
}

static bool in_bounds(const Program *p, int x, int y) {
    return x >= 0 && y >= 0 && x < p->width && y < p->height;
}

static char grid_at(const Program *p, int x, int y) {
    return in_bounds(p, x, y) ? p->grid[cell_index(p, x, y)] : ' ';
}

static bool room_contains(const Room *room, int x, int y) {
    return x >= room->min_x && x <= room->max_x &&
           y >= room->min_y && y <= room->max_y;
}

static bool room_border(const Room *room, int x, int y) {
    return room_contains(room, x, y) &&
           (x == room->min_x || x == room->max_x ||
            y == room->min_y || y == room->max_y);
}

static void set_error(Program *p, const char *message) {
    if (!p->error[0]) {
        snprintf(p->error, sizeof(p->error), "%s", message);
    }
    p->halted = true;
}

static void set_error_at(Program *p, const char *message, int x, int y) {
    if (!p->error[0]) {
        snprintf(p->error, sizeof(p->error), "%s at %d,%d", message, x, y);
    }
    p->halted = true;
}

static void room_add_pipe(int **items, int *count, int *capacity, int pipe) {
    if (*count == *capacity) {
        *capacity = *capacity ? *capacity * 2 : 4;
        *items = xrealloc(*items, (size_t)*capacity * sizeof(**items));
    }
    (*items)[(*count)++] = pipe;
}

static int add_room(Program *p, Room room) {
    if (p->room_count == p->room_cap) {
        p->room_cap = p->room_cap ? p->room_cap * 2 : 32;
        p->rooms = xrealloc(p->rooms, (size_t)p->room_cap * sizeof(*p->rooms));
    }
    p->rooms[p->room_count] = room;
    return p->room_count++;
}

static int add_pipe(Program *p, Pipe pipe) {
    if (p->pipe_count == p->pipe_cap) {
        p->pipe_cap = p->pipe_cap ? p->pipe_cap * 2 : 64;
        p->pipes = xrealloc(p->pipes, (size_t)p->pipe_cap * sizeof(*p->pipes));
    }
    p->pipes[p->pipe_count] = pipe;
    return p->pipe_count++;
}

static int add_literal(Program *p, Literal literal) {
    if (p->literal_count == p->literal_cap) {
        p->literal_cap = p->literal_cap ? p->literal_cap * 2 : 128;
        p->literals = xrealloc(
            p->literals, (size_t)p->literal_cap * sizeof(*p->literals));
    }
    p->literals[p->literal_count] = literal;
    return p->literal_count++;
}

static void add_man(Program *p, Man man) {
    if (p->man_count == p->man_cap) {
        p->man_cap = p->man_cap ? p->man_cap * 2 : 32;
        p->men = xrealloc(p->men, (size_t)p->man_cap * sizeof(*p->men));
    }
    p->men[p->man_count++] = man;
}

static int add_display(Program *p, Display display) {
    if (p->display_count == p->display_cap) {
        p->display_cap = p->display_cap ? p->display_cap * 2 : 2;
        p->displays = xrealloc(
            p->displays, (size_t)p->display_cap * sizeof(*p->displays));
    }
    p->displays[p->display_count] = display;
    return p->display_count++;
}

static char *read_file(const char *path, size_t *size_out) {
    FILE *file = fopen(path, "rb");
    if (!file) {
        fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
        exit(1);
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        die("fseek failed");
    }
    long length = ftell(file);
    if (length < 0 || fseek(file, 0, SEEK_SET) != 0) {
        die("ftell/fseek failed");
    }
    char *data = xmalloc((size_t)length + 1);
    size_t got = fread(data, 1, (size_t)length, file);
    if (got != (size_t)length && ferror(file)) {
        die("file read failed");
    }
    fclose(file);
    data[got] = '\0';
    *size_out = got;
    return data;
}

static void parse_grid(Program *p, const char *path) {
    size_t size;
    char *source = read_file(path, &size);
    while (size && (source[size - 1] == ' ' || source[size - 1] == '\t' ||
                    source[size - 1] == '\r' || source[size - 1] == '\n')) {
        size--;
    }
    int width = 0;
    int height = size ? 1 : 0;
    int line_width = 0;
    for (size_t i = 0; i < size; i++) {
        if (source[i] == '\n') {
            if (line_width > width) {
                width = line_width;
            }
            line_width = 0;
            height++;
        } else if (source[i] != '\r') {
            line_width++;
        }
    }
    if (line_width > width) {
        width = line_width;
    }
    if (!width || !height) {
        die("empty program");
    }

    p->width = width;
    p->height = height;
    p->cells = width * height;
    p->grid = xmalloc((size_t)p->cells);
    memset(p->grid, ' ', (size_t)p->cells);

    int x = 0, y = 0;
    for (size_t i = 0; i < size; i++) {
        char ch = source[i];
        if (ch == '\n') {
            x = 0;
            y++;
        } else if (ch != '\r' && y < height && x < width) {
            p->grid[cell_index(p, x++, y)] = ch;
        }
    }
    free(source);
}

static void parse_rooms(Program *p) {
    uint8_t *visited = xcalloc((size_t)p->cells, 1);
    for (int y = 0; y < p->height; y++) {
        for (int x = 0; x < p->width; x++) {
            if (grid_at(p, x, y) != '+' || visited[cell_index(p, x, y)]) {
                continue;
            }
            int w = 1;
            while (x + w < p->width && grid_at(p, x + w, y) == '-') {
                w++;
            }
            if (x + w >= p->width || grid_at(p, x + w, y) != '+') {
                continue;
            }
            int h = 1;
            while (y + h < p->height && grid_at(p, x, y + h) == '|') {
                h++;
            }
            if (y + h >= p->height || grid_at(p, x, y + h) != '+') {
                continue;
            }
            bool valid = grid_at(p, x + w, y + h) == '+';
            for (int i = 1; valid && i < w; i++) {
                valid = grid_at(p, x + i, y + h) == '-';
            }
            for (int i = 1; valid && i < h; i++) {
                valid = grid_at(p, x + w, y + i) == '|';
            }
            if (!valid) {
                continue;
            }
            for (int i = 0; i <= w; i++) {
                visited[cell_index(p, x + i, y)] = 1;
                visited[cell_index(p, x + i, y + h)] = 1;
            }
            for (int i = 0; i <= h; i++) {
                visited[cell_index(p, x, y + i)] = 1;
                visited[cell_index(p, x + w, y + i)] = 1;
            }
            Room room = {
                .min_x = x, .min_y = y, .max_x = x + w, .max_y = y + h,
                .type = ROOM_MAIN,
            };
            for (int ry = y + 1; ry < y + h; ry++) {
                for (int rx = x + 1; rx < x + w; rx++) {
                    char ch = grid_at(p, rx, ry);
                    if (ch == 'I') {
                        room.type = ROOM_INPUT;
                    } else if (ch == 'O') {
                        room.type = ROOM_OUTPUT;
                    }
                }
            }
            add_room(p, room);
        }
    }
    free(visited);
}

static void parse_displays(Program *p) {
    for (int y = 0; y < p->height; y++) {
        for (int x = 0; x < p->width; x++) {
            if (grid_at(p, x, y) != '+' || grid_at(p, x + 1, y) != '=' ||
                grid_at(p, x, y + 1) != ':') {
                continue;
            }
            int right = x + 1;
            while (right < p->width && grid_at(p, right, y) == '=') {
                right++;
            }
            int bottom = y + 1;
            while (bottom < p->height && grid_at(p, x, bottom) == ':') {
                bottom++;
            }
            if (right >= p->width || bottom >= p->height ||
                grid_at(p, right, y) != '+' || grid_at(p, x, bottom) != '+') {
                die("malformed display");
            }
            int width = right - x - 1;
            int height = bottom - y - 1;
            Room room = {
                .min_x = x, .min_y = y, .max_x = right, .max_y = bottom,
                .type = ROOM_DISPLAY,
            };
            int room_id = add_room(p, room);
            Display display = {
                .room = room_id,
                .width = width,
                .height = height,
                .addr_pipe = -1,
                .data_pipe = -1,
                .swap_pipe = -1,
                .current = xcalloc((size_t)width * height, sizeof(int64_t)),
                .next = xcalloc((size_t)width * height, sizeof(int64_t)),
#ifdef TV_MODE
                .painted = xcalloc((size_t)width * height, 1),
#endif
            };
            add_display(p, display);
        }
    }
}

static int arrow_dir(char ch, int *dx, int *dy) {
    switch (ch) {
    case '>': *dx = 1; *dy = 0; return 1;
    case '<': *dx = -1; *dy = 0; return 1;
    case '^': *dx = 0; *dy = -1; return 1;
    case 'v':
    case 'V': *dx = 0; *dy = 1; return 1;
    default: return 0;
    }
}

static int trace_pipe(
    Program *p, int source_room, Point source_segment, Point start, int dx, int dy,
    Pipe *result
) {
    Point *path = xmalloc((size_t)p->cells * sizeof(*path));
    int length = 1;
    path[0] = start;
    Point current = start;
    for (int steps = 0; steps < p->cells; steps++) {
        Point next = {current.x + dx, current.y + dy};
        if (!in_bounds(p, next.x, next.y)) {
            free(path);
            return 0;
        }
        int destination = p->room_at[cell_index(p, next.x, next.y)];
        if (destination >= 0) {
            if (destination == source_room) {
                free(path);
                return -1;
            }
            if (!room_border(&p->rooms[destination], next.x, next.y) ||
                !arrow_dir(grid_at(p, current.x, current.y), &(int){0}, &(int){0}) ||
                length < 2) {
                free(path);
                return 0;
            }
            path = xrealloc(path, (size_t)length * sizeof(*path));
            *result = (Pipe){
                .path = path,
                .length = length,
                .token_positions = xmalloc((size_t)length * sizeof(int)),
                .source_room = source_room,
                .dest_room = destination,
                .source_segment = source_segment,
                .dest_segment = next,
            };
            return 1;
        }
        current = next;
        char ch = grid_at(p, current.x, current.y);
        int ndx, ndy;
        if (arrow_dir(ch, &ndx, &ndy)) {
            if (ndx == -dx && ndy == -dy) {
                free(path);
                return 0;
            }
            dx = ndx;
            dy = ndy;
        } else if ((ch == '-' && dy == 0) || (ch == '|' && dx == 0)) {
            /* straight body */
        } else {
            free(path);
            return 0;
        }
        path[length++] = current;
    }
    free(path);
    return 0;
}

static bool point_equal(Point a, Point b) {
    return a.x == b.x && a.y == b.y;
}

static void build_room_map(Program *p) {
    p->room_at = xmalloc((size_t)p->cells * sizeof(*p->room_at));
    for (int i = 0; i < p->cells; i++) {
        p->room_at[i] = -1;
    }
    for (int room_id = 0; room_id < p->room_count; room_id++) {
        Room *room = &p->rooms[room_id];
        for (int y = room->min_y; y <= room->max_y; y++) {
            for (int x = room->min_x; x <= room->max_x; x++) {
                int index = cell_index(p, x, y);
                if (p->room_at[index] < 0) {
                    p->room_at[index] = room_id;
                }
            }
        }
    }
}

static void parse_pipes(Program *p) {
    const int directions[4][2] = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
    for (int room_id = 0; room_id < p->room_count; room_id++) {
        Room *room = &p->rooms[room_id];
        for (int y = room->min_y; y <= room->max_y; y++) {
            for (int x = room->min_x; x <= room->max_x; x++) {
                if (!room_border(room, x, y)) {
                    continue;
                }
                for (int d = 0; d < 4; d++) {
                    int dx = directions[d][0], dy = directions[d][1];
                    int px = x + dx, py = y + dy;
                    if (!in_bounds(p, px, py) || room_contains(room, px, py)) {
                        continue;
                    }
                    int adx, ady;
                    if (!arrow_dir(grid_at(p, px, py), &adx, &ady) ||
                        adx != dx || ady != dy) {
                        continue;
                    }
                    Pipe pipe;
                    int traced = trace_pipe(
                        p, room_id, (Point){x, y}, (Point){px, py}, dx, dy, &pipe);
                    if (traced > 0) {
                        add_pipe(p, pipe);
                    }
                }
            }
        }
    }

    uint8_t *ghost = xcalloc((size_t)p->pipe_count, 1);
    for (int b = 0; b < p->pipe_count; b++) {
        for (int a = 0; a < p->pipe_count && !ghost[b]; a++) {
            if (a == b) {
                continue;
            }
            for (int i = 1; i < p->pipes[a].length; i++) {
                if (point_equal(p->pipes[a].path[i], p->pipes[b].path[0])) {
                    ghost[b] = 1;
                    break;
                }
            }
        }
    }
    int kept = 0;
    for (int i = 0; i < p->pipe_count; i++) {
        if (ghost[i]) {
            free(p->pipes[i].path);
            free(p->pipes[i].token_positions);
        } else {
            p->pipes[kept++] = p->pipes[i];
        }
    }
    p->pipe_count = kept;
    free(ghost);

    p->pipe_next = xmalloc((size_t)p->cells * sizeof(*p->pipe_next));
    p->pipe_value = xcalloc((size_t)p->cells, sizeof(*p->pipe_value));
    p->pipe_full = xcalloc((size_t)p->cells, 1);
    p->pipe_order = xmalloc((size_t)p->cells * sizeof(*p->pipe_order));
    uint8_t *visited = xcalloc((size_t)p->cells, 1);
    for (int i = 0; i < p->cells; i++) {
        p->pipe_next[i] = -1;
    }
    for (int pipe_id = 0; pipe_id < p->pipe_count; pipe_id++) {
        Pipe *pipe = &p->pipes[pipe_id];
#ifdef FAST_MODE
        pipe->queued_values =
            xmalloc((size_t)pipe->length * sizeof(*pipe->queued_values));
        pipe->queued_arrivals =
            xmalloc((size_t)pipe->length * sizeof(*pipe->queued_arrivals));
#endif
        room_add_pipe(
            &p->rooms[pipe->source_room].outgoing,
            &p->rooms[pipe->source_room].outgoing_count,
            &p->rooms[pipe->source_room].outgoing_cap,
            pipe_id);
        room_add_pipe(
            &p->rooms[pipe->dest_room].incoming,
            &p->rooms[pipe->dest_room].incoming_count,
            &p->rooms[pipe->dest_room].incoming_cap,
            pipe_id);
        for (int i = pipe->length - 1; i >= 0; i--) {
            int index = cell_index(p, pipe->path[i].x, pipe->path[i].y);
            if (i + 1 < pipe->length) {
                p->pipe_next[index] = cell_index(
                    p, pipe->path[i + 1].x, pipe->path[i + 1].y);
            }
            if (!visited[index]) {
                visited[index] = 1;
                p->pipe_order[p->pipe_order_count++] = index;
            }
        }
    }
    free(visited);
}

static int64_t parse_literal_value(
    const Program *p, Point min, Point max, bool horizontal, bool backward,
    bool *valid
) {
    char digits[128];
    int count = 0;
    int length = horizontal ? max.x - min.x - 1 : max.y - min.y - 1;
    for (int step = 0; step < length; step++) {
        int offset = backward ? length - 1 - step : step;
        int x = min.x + (horizontal ? offset + 1 : 0);
        int y = min.y + (horizontal ? 0 : offset + 1);
        char ch = grid_at(p, x, y);
        if (ch == ' ') {
            continue;
        }
        if (ch < '0' || ch > '9' || count + 1 >= (int)sizeof(digits)) {
            die("invalid numeric literal");
        }
        digits[count++] = ch;
    }
    digits[count] = '\0';
    errno = 0;
    char *end;
    int64_t value = strtoll(digits, &end, 10);
    if (errno || end == digits || *end) {
        *valid = false;
        return 0;
    }
    *valid = true;
    return value;
}

static void parse_literals(Program *p) {
    p->literal_h = xmalloc((size_t)p->cells * sizeof(*p->literal_h));
    p->literal_v = xmalloc((size_t)p->cells * sizeof(*p->literal_v));
    for (int i = 0; i < p->cells; i++) {
        p->literal_h[i] = -1;
        p->literal_v[i] = -1;
    }
    for (int y = 0; y < p->height; y++) {
        int start = -1;
        for (int x = 0; x < p->width; x++) {
            if (grid_at(p, x, y) != '`') {
                continue;
            }
            if (start < 0) {
                start = x;
            } else {
                Literal literal = {
                    .min_x = start, .min_y = y, .max_x = x, .max_y = y,
                    .horizontal = true,
                };
                literal.forward = parse_literal_value(
                    p, (Point){start, y}, (Point){x, y}, true, false,
                    &literal.forward_valid);
                literal.backward = parse_literal_value(
                    p, (Point){start, y}, (Point){x, y}, true, true,
                    &literal.backward_valid);
                int id = add_literal(p, literal);
                for (int px = start; px <= x; px++) {
                    p->literal_h[cell_index(p, px, y)] = id;
                }
                start = -1;
            }
        }
    }
    for (int x = 0; x < p->width; x++) {
        int start = -1;
        for (int y = 0; y < p->height; y++) {
            if (grid_at(p, x, y) != '`') {
                continue;
            }
            if (start < 0) {
                start = y;
            } else {
                Literal literal = {
                    .min_x = x, .min_y = start, .max_x = x, .max_y = y,
                    .horizontal = false,
                };
                literal.forward = parse_literal_value(
                    p, (Point){x, start}, (Point){x, y}, false, false,
                    &literal.forward_valid);
                literal.backward = parse_literal_value(
                    p, (Point){x, start}, (Point){x, y}, false, true,
                    &literal.backward_valid);
                int id = add_literal(p, literal);
                for (int py = start; py <= y; py++) {
                    p->literal_v[cell_index(p, x, py)] = id;
                }
                start = -1;
            }
        }
    }
}

static int point_distance(Point a, Point b) {
    int dx = a.x - b.x;
    int dy = a.y - b.y;
    return (dx < 0 ? -dx : dx) + (dy < 0 ? -dy : dy);
}

static bool reading_order_before(Point a, Point b) {
    return a.y < b.y || (a.y == b.y && a.x < b.x);
}

static int nearest_pipe(const Program *p, int room_id, Point point, bool incoming) {
    const Room *room = &p->rooms[room_id];
    int *ids = incoming ? room->incoming : room->outgoing;
    int count = incoming ? room->incoming_count : room->outgoing_count;
    int best = -1;
    Point best_segment = {0, 0};
    for (int i = 0; i < count; i++) {
        int id = ids[i];
        const Pipe *pipe = &p->pipes[id];
        Point segment = incoming ? pipe->path[pipe->length - 1] : pipe->path[0];
        if (best < 0 ||
            point_distance(point, segment) < point_distance(point, best_segment) ||
            (point_distance(point, segment) == point_distance(point, best_segment) &&
             reading_order_before(segment, best_segment))) {
            best = id;
            best_segment = segment;
        }
    }
    return best;
}

static void precompute_nearest(Program *p) {
    p->nearest_in = xmalloc((size_t)p->cells * sizeof(*p->nearest_in));
    p->nearest_out = xmalloc((size_t)p->cells * sizeof(*p->nearest_out));
    for (int i = 0; i < p->cells; i++) {
        p->nearest_in[i] = -1;
        p->nearest_out[i] = -1;
        int room_id = p->room_at[i];
        if (room_id >= 0) {
            Point point = {i % p->width, i / p->width};
            p->nearest_in[i] = nearest_pipe(p, room_id, point, true);
            p->nearest_out[i] = nearest_pipe(p, room_id, point, false);
        }
    }
}

static void configure_displays(Program *p) {
#ifdef FAST_MODE
    p->display_by_room =
        xmalloc((size_t)p->room_count * sizeof(*p->display_by_room));
    for (int i = 0; i < p->room_count; i++) {
        p->display_by_room[i] = -1;
    }
    p->dirty_displays = xcalloc((size_t)p->display_count, 1);
#endif
    for (int i = 0; i < p->display_count; i++) {
        Display *display = &p->displays[i];
#ifdef FAST_MODE
        p->display_by_room[display->room] = i;
#endif
        Room *room = &p->rooms[display->room];
        for (int j = 0; j < room->incoming_count; j++) {
            int pipe_id = room->incoming[j];
            Point segment = p->pipes[pipe_id].dest_segment;
            if (segment.y == room->min_y) {
                display->addr_pipe = pipe_id;
            } else if (segment.x == room->min_x) {
                display->data_pipe = pipe_id;
            } else if (segment.y == room->max_y) {
                display->swap_pipe = pipe_id;
            }
        }
    }
}

static void spawn_men(Program *p) {
    for (int room_id = 0; room_id < p->room_count; room_id++) {
        Room *room = &p->rooms[room_id];
        for (int y = room->min_y + 1; y < room->max_y; y++) {
            for (int x = room->min_x + 1; x < room->max_x; x++) {
                if (grid_at(p, x, y) == '@') {
                    add_man(p, (Man){
                        .id = p->next_man_id++,
                        .x = x, .y = y, .dx = 1, .dy = 0,
#ifdef FAST_MODE
                        .pc = cell_index(p, x, y) * 4 + DIR_EAST,
#endif
                    });
                }
            }
        }
    }
    if (!p->man_count) {
        die("no little men found");
    }
#ifdef FAST_MODE
    for (int i = 0; i < p->cells; i++) {
        if (p->grid[i] == 'Y') {
            die("FAST_MODE does not support Y");
        }
    }
    for (int i = 0; i < p->man_count; i++) {
        int room = p->room_at[cell_index(p, p->men[i].x, p->men[i].y)];
        for (int j = 0; j < i; j++) {
            int other_room =
                p->room_at[cell_index(p, p->men[j].x, p->men[j].y)];
            if (room == other_room) {
                die("FAST_MODE requires at most one little man per room");
            }
        }
    }
    p->sleeping_readers =
        xmalloc((size_t)p->room_count * sizeof(*p->sleeping_readers));
    p->sleeping_writers =
        xmalloc((size_t)p->room_count * sizeof(*p->sleeping_writers));
    for (int i = 0; i < p->room_count; i++) {
        p->sleeping_readers[i] = -1;
        p->sleeping_writers[i] = -1;
    }
    p->live_man_count = p->man_count;
    p->runnable_word_count = (p->man_count + 63) / 64;
    p->runnable_men =
        xcalloc((size_t)p->runnable_word_count, sizeof(*p->runnable_men));
    p->man_event_pending = xcalloc((size_t)p->man_count, 1);
#else
    p->men = xrealloc(p->men, (size_t)MAX_LIVE_MEN * sizeof(*p->men));
    p->man_cap = MAX_LIVE_MEN;
    p->old_positions =
        xmalloc((size_t)MAX_LIVE_MEN * sizeof(*p->old_positions));
    p->moved = xcalloc(MAX_LIVE_MEN, 1);
    p->collided = xcalloc(MAX_LIVE_MEN, 1);
    p->old_occupant = xmalloc((size_t)p->cells * sizeof(*p->old_occupant));
    p->old_occupant_stamp =
        xcalloc((size_t)p->cells, sizeof(*p->old_occupant_stamp));
    p->new_occupant = xmalloc((size_t)p->cells * sizeof(*p->new_occupant));
    p->new_occupant_stamp =
        xcalloc((size_t)p->cells, sizeof(*p->new_occupant_stamp));
#endif
}

#ifdef FAST_MODE
static const int direction_dx[4] = {1, 0, -1, 0};
static const int direction_dy[4] = {0, 1, 0, -1};

typedef struct {
    Program *program;
    int *state_to_pc;
    int *pc_states;
    int pc_state_cap;
} TraceCompiler;

static int add_trace_constant(Program *p, int64_t value) {
    if (p->trace_constant_count == p->trace_constant_cap) {
        p->trace_constant_cap =
            p->trace_constant_cap ? p->trace_constant_cap * 2 : 64;
        p->trace_constants = xrealloc(
            p->trace_constants,
            (size_t)p->trace_constant_cap * sizeof(*p->trace_constants));
    }
    p->trace_constants[p->trace_constant_count] = value;
    return p->trace_constant_count++;
}

static int add_trace_sign_targets(
    Program *p, int positive, int negative
) {
    if (p->trace_sign_count == p->trace_sign_cap) {
        p->trace_sign_cap = p->trace_sign_cap ? p->trace_sign_cap * 2 : 32;
        p->trace_sign_targets = xrealloc(
            p->trace_sign_targets,
            (size_t)p->trace_sign_cap * sizeof(*p->trace_sign_targets));
    }
    p->trace_sign_targets[p->trace_sign_count] = (TraceSignTargets){
        .positive = positive,
        .negative = negative,
    };
    return p->trace_sign_count++;
}

static int add_trace_read(Program *p, TraceReadInfo read) {
    if (p->trace_read_count == p->trace_read_cap) {
        p->trace_read_cap = p->trace_read_cap ? p->trace_read_cap * 2 : 32;
        p->trace_reads = xrealloc(
            p->trace_reads,
            (size_t)p->trace_read_cap * sizeof(*p->trace_reads));
    }
    p->trace_reads[p->trace_read_count] = read;
    return p->trace_read_count++;
}

static int intern_trace_state(
    TraceCompiler *compiler, int cell, Direction direction
) {
    Program *p = compiler->program;
    int state = cell * 4 + direction;
    if (compiler->state_to_pc[state] >= 0) {
        return compiler->state_to_pc[state];
    }
    if (p->trace_op_count == p->trace_op_cap) {
        p->trace_op_cap = p->trace_op_cap ? p->trace_op_cap * 2 : 256;
        p->trace_ops = xrealloc(
            p->trace_ops,
            (size_t)p->trace_op_cap * sizeof(*p->trace_ops));
    }
    if (p->trace_op_count == compiler->pc_state_cap) {
        compiler->pc_state_cap =
            compiler->pc_state_cap ? compiler->pc_state_cap * 2 : 256;
        compiler->pc_states = xrealloc(
            compiler->pc_states,
            (size_t)compiler->pc_state_cap * sizeof(*compiler->pc_states));
    }
    int pc = p->trace_op_count++;
    compiler->state_to_pc[state] = pc;
    compiler->pc_states[pc] = state;
    return pc;
}

static int trace_target(
    TraceCompiler *compiler, int cell, Direction direction
) {
    Program *p = compiler->program;
    int x = cell % p->width + direction_dx[direction];
    int y = cell / p->width + direction_dy[direction];
    if (!in_bounds(p, x, y)) {
        return -(cell * 4 + (int)direction) - 1;
    }
    int target_cell = cell_index(p, x, y);
    int room_id = p->room_at[target_cell];
    if (room_id < 0 || room_border(&p->rooms[room_id], x, y)) {
        return -(cell * 4 + (int)direction) - 1;
    }
    return intern_trace_state(compiler, target_cell, direction);
}

static bool compile_trace_literal(
    TraceCompiler *compiler, TraceOp *op, int cell, Direction direction
) {
    Program *p = compiler->program;
    bool horizontal = direction == DIR_EAST || direction == DIR_WEST;
    int literal_id = horizontal ? p->literal_h[cell] : p->literal_v[cell];
    if (literal_id < 0) {
        if (p->grid[cell] != '`') {
            return false;
        }
        op->next = trace_target(compiler, cell, direction);
        return true;
    }
    const Literal *literal = &p->literals[literal_id];
    int x = cell % p->width;
    int y = cell / p->width;
    bool load = false;
    bool valid = true;
    int64_t value = 0;
    if (literal->horizontal) {
        if (direction == DIR_EAST && x == literal->min_x) {
            load = true;
            valid = literal->forward_valid;
            value = literal->forward;
        } else if (direction == DIR_WEST && x == literal->max_x) {
            load = true;
            valid = literal->backward_valid;
            value = literal->backward;
        }
    } else if (direction == DIR_SOUTH && y == literal->min_y) {
        load = true;
        valid = literal->forward_valid;
        value = literal->forward;
    } else if (direction == DIR_NORTH && y == literal->max_y) {
        load = true;
        valid = literal->backward_valid;
        value = literal->backward;
    }
    if (load) {
        op->opcode = valid ? TRACE_LOAD : TRACE_INVALID_LITERAL;
        op->operand = valid ? add_trace_constant(p, value) : cell;
    }
    if (valid) {
        op->next = trace_target(compiler, cell, direction);
    }
    return true;
}

static void compile_trace_op(
    TraceCompiler *compiler, int cell, Direction direction, TraceOp *op
) {
    Program *p = compiler->program;
    *op = (TraceOp){
        .opcode = TRACE_NOP,
        .branch = -1,
        .operand = -1,
    };
    if (compile_trace_literal(compiler, op, cell, direction)) {
        return;
    }

    Direction clockwise = (Direction)((direction + 1) & 3);
    Direction counterclockwise = (Direction)((direction + 3) & 3);
    char ch = p->grid[cell];
    if (ch == 'H') {
        op->opcode = TRACE_HALT;
        return;
    }
    if (!(ch == '@' || ch == '.' || ch == ' ' || ch == 'M' || ch == 'W' ||
          ch == '+' || ch == '-' || ch == '*' || ch == '%' || ch == '/' ||
          ch == 'N' || ch == '&' || ch == '|' || ch == '~' || ch == '{' ||
          ch == '}' || ch == '>' || ch == '<' || ch == '^' || ch == 'v' ||
          ch == 'V' || ch == 'X' || ch == 'b' || ch == 'm' || ch == 'd' ||
          ch == 'a' || ch == ']' || ch == 'x' || ch == 'q' || ch == 's' ||
          ch == 'S' || ch == 'r' || ch == 'R' || ch == 'U' ||
          (ch >= '0' && ch <= '9'))) {
        op->opcode = TRACE_UNSUPPORTED;
        op->operand = cell;
        return;
    }
    op->next = trace_target(compiler, cell, direction);
    switch (ch) {
    case '@':
    case '.':
    case ' ':
        break;
    case 'M':
        op->opcode = TRACE_MOVE_A_TO_B;
        break;
    case 'W':
        op->opcode = TRACE_SWAP;
        break;
    case '+': op->opcode = TRACE_ADD; break;
    case '-': op->opcode = TRACE_SUB; break;
    case '*': op->opcode = TRACE_MUL; break;
    case '%': op->opcode = TRACE_MOD; break;
    case '/': op->opcode = TRACE_DIV; break;
    case 'N': op->opcode = TRACE_NEG; break;
    case '&': op->opcode = TRACE_AND; break;
    case '|': op->opcode = TRACE_OR; break;
    case '~': op->opcode = TRACE_XOR; break;
    case '{': op->opcode = TRACE_SHIFT_LEFT; break;
    case '}': op->opcode = TRACE_SHIFT_RIGHT; break;
    case '>':
        op->next = trace_target(compiler, cell, DIR_EAST);
        break;
    case '<':
        op->next = trace_target(compiler, cell, DIR_WEST);
        break;
    case '^':
        op->next = trace_target(compiler, cell, DIR_NORTH);
        break;
    case 'v':
    case 'V':
        op->next = trace_target(compiler, cell, DIR_SOUTH);
        break;
    case 'X': {
        op->opcode = TRACE_BRANCH_SIGN;
        int positive = trace_target(compiler, cell, clockwise);
        int negative = trace_target(compiler, cell, counterclockwise);
        op->operand = add_trace_sign_targets(p, positive, negative);
        break;
    }
    case 'b':
        op->opcode = TRACE_SET_BP;
        break;
    case 'm':
        op->opcode = TRACE_DEC_BP;
        break;
    case 'd':
        op->opcode = TRACE_BRANCH_BP_POS_CW;
        op->branch = trace_target(compiler, cell, clockwise);
        break;
    case 'a':
        op->opcode = TRACE_BRANCH_BP_POS_CCW;
        op->branch = trace_target(compiler, cell, counterclockwise);
        break;
    case ']':
        op->opcode = TRACE_SHIFT_BP;
        break;
    case 'x':
        op->opcode = TRACE_BRANCH_BP_PARITY;
        op->next = trace_target(compiler, cell, counterclockwise);
        op->branch = trace_target(compiler, cell, clockwise);
        break;
    case 'q':
        op->opcode = TRACE_PIPE_COUNT;
        op->operand = p->nearest_in[cell];
        op->branch = cell;
        break;
    case 's':
        op->opcode = TRACE_SEND;
        op->operand = p->nearest_out[cell];
        op->branch = cell;
        break;
    case 'S':
        op->opcode = TRACE_SEND_ALL;
        op->operand = p->room_at[cell];
        op->branch = cell;
        break;
    case 'r':
        op->opcode = TRACE_READ;
        op->operand = p->nearest_in[cell];
        op->branch = cell;
        break;
    case 'R': {
        op->opcode = TRACE_READ_ANY;
        op->operand = add_trace_read(p, (TraceReadInfo){
            .room_id = p->room_at[cell],
            .point = {cell % p->width, cell / p->width},
        });
        break;
    }
    case 'U': {
        op->opcode = TRACE_READ_TURN;
        TraceReadInfo read = {
            .room_id = p->room_at[cell],
            .point = {cell % p->width, cell / p->width},
            .pipe_targets =
                xmalloc((size_t)p->pipe_count * sizeof(*read.pipe_targets)),
        };
        for (int i = 0; i < p->pipe_count; i++) {
            read.pipe_targets[i] = -1;
        }
        if (read.room_id >= 0) {
            Room *room = &p->rooms[read.room_id];
            int x = cell % p->width;
            int y = cell / p->width;
            for (int i = 0; i < room->incoming_count; i++) {
                int pipe_id = room->incoming[i];
                Point segment =
                    p->pipes[pipe_id].path[p->pipes[pipe_id].length - 1];
                Direction exit_direction;
                if (x != segment.x) {
                    exit_direction = x < segment.x ? DIR_WEST : DIR_EAST;
                } else {
                    exit_direction = y < segment.y ? DIR_NORTH : DIR_SOUTH;
                }
                read.pipe_targets[pipe_id] =
                    trace_target(compiler, cell, exit_direction);
            }
        }
        op->operand = add_trace_read(p, read);
        break;
    }
    default:
        if (ch >= '0' && ch <= '9') {
            op->opcode = TRACE_LOAD;
            op->operand = add_trace_constant(p, ch - '0');
        }
    }
}

static void collapse_nop_traces(Program *p) {
    int *collapsed_next =
        xmalloc((size_t)p->trace_op_count * sizeof(*collapsed_next));
    int *durations =
        xmalloc((size_t)p->trace_op_count * sizeof(*durations));
    for (int pc = 0; pc < p->trace_op_count; pc++) {
        collapsed_next[pc] = p->trace_ops[pc].next;
        durations[pc] = 1;
        if (p->trace_ops[pc].opcode != TRACE_NOP) {
            continue;
        }
        int next = p->trace_ops[pc].next;
        int duration = 1;
        bool cycle = false;
        while (next >= 0 && p->trace_ops[next].opcode == TRACE_NOP &&
               p->trace_ops[next].next >= 0) {
            if (next == pc || duration >= p->trace_op_count) {
                cycle = true;
                break;
            }
            next = p->trace_ops[next].next;
            duration++;
        }
        if (!cycle) {
            collapsed_next[pc] = next;
            durations[pc] = duration;
        }
    }
    for (int pc = 0; pc < p->trace_op_count; pc++) {
        if (p->trace_ops[pc].opcode == TRACE_NOP) {
            p->trace_ops[pc].next = collapsed_next[pc];
            p->trace_ops[pc].operand = durations[pc];
        }
    }
    free(collapsed_next);
    free(durations);
}

static void compile_traces(Program *p) {
    TraceCompiler compiler = {
        .program = p,
        .state_to_pc =
            xmalloc((size_t)p->cells * 4 * sizeof(*compiler.state_to_pc)),
    };
    for (int i = 0; i < p->cells * 4; i++) {
        compiler.state_to_pc[i] = -1;
    }
    for (int i = 0; i < p->man_count; i++) {
        int cell = cell_index(p, p->men[i].x, p->men[i].y);
        p->men[i].pc = intern_trace_state(&compiler, cell, DIR_EAST);
    }
    for (int pc = 0; pc < p->trace_op_count; pc++) {
        int state = compiler.pc_states[pc];
        TraceOp op;
        compile_trace_op(
            &compiler, state / 4, (Direction)(state % 4), &op);
        p->trace_ops[pc] = op;
    }
    collapse_nop_traces(p);
    free(compiler.state_to_pc);
    free(compiler.pc_states);
}
#endif

static Program parse_program(const char *path) {
    Program p = {.input_room = -1, .output_room = -1};
    parse_grid(&p, path);
    parse_rooms(&p);
    parse_displays(&p);
    build_room_map(&p);
    parse_literals(&p);
    parse_pipes(&p);
    precompute_nearest(&p);
    configure_displays(&p);
    spawn_men(&p);
#ifdef FAST_MODE
    compile_traces(&p);
#endif
    for (int i = 0; i < p.room_count; i++) {
        if (p.rooms[i].type == ROOM_INPUT) {
            p.input_room = i;
        } else if (p.rooms[i].type == ROOM_OUTPUT) {
            p.output_room = i;
        }
    }
    return p;
}

#ifndef FAST_MODE
static int pipe_endpoint_index(const Program *p, int pipe_id, bool incoming) {
    const Pipe *pipe = &p->pipes[pipe_id];
    Point point = incoming ? pipe->path[pipe->length - 1] : pipe->path[0];
    return cell_index(p, point.x, point.y);
}
#endif

#ifdef FAST_MODE
static void set_man_runnable(Program *p, int man_index, bool runnable) {
    uint64_t mask = UINT64_C(1) << (man_index % 64);
    uint64_t *word = &p->runnable_men[man_index / 64];
    if (runnable) {
        *word |= mask;
    } else {
        *word &= ~mask;
    }
}

static bool man_event_before(ManEvent a, ManEvent b) {
    return a.tick < b.tick ||
           (a.tick == b.tick && a.man_index < b.man_index);
}

static void schedule_man_event(Program *p, int man_index, uint64_t tick) {
    if (p->man_event_pending[man_index]) {
        set_error(p, "little man already has a scheduled event");
        return;
    }
    if (p->man_event_count == p->man_event_cap) {
        p->man_event_cap = p->man_event_cap ? p->man_event_cap * 2 : 64;
        p->man_events = xrealloc(
            p->man_events,
            (size_t)p->man_event_cap * sizeof(*p->man_events));
    }
    ManEvent event = {.tick = tick, .man_index = man_index};
    int index = p->man_event_count++;
    while (index > 0) {
        int parent = (index - 1) / 2;
        if (!man_event_before(event, p->man_events[parent])) {
            break;
        }
        p->man_events[index] = p->man_events[parent];
        index = parent;
    }
    p->man_events[index] = event;
    p->man_event_pending[man_index] = 1;
}

static ManEvent pop_man_event(Program *p) {
    ManEvent result = p->man_events[0];
    ManEvent last = p->man_events[--p->man_event_count];
    if (p->man_event_count) {
        int index = 0;
        for (;;) {
            int left = index * 2 + 1;
            if (left >= p->man_event_count) {
                break;
            }
            int child = left;
            int right = left + 1;
            if (right < p->man_event_count &&
                man_event_before(p->man_events[right], p->man_events[left])) {
                child = right;
            }
            if (!man_event_before(p->man_events[child], last)) {
                break;
            }
            p->man_events[index] = p->man_events[child];
            index = child;
        }
        p->man_events[index] = last;
    }
    p->man_event_pending[result.man_index] = 0;
    return result;
}

static void wake_sleeping_man(Program *p, int *sleepers, int room_id) {
    int man_index = sleepers[room_id];
    if (man_index < 0) {
        return;
    }
    sleepers[room_id] = -1;
    Man *man = &p->men[man_index];
    if (!man->halted) {
#ifdef PROFILE_MODE
        if (p->profile_enabled) {
            int pipe_slot = p->profile_wait_pipe[man_index] + 1;
            size_t slot =
                (size_t)man_index * (size_t)(p->pipe_count + 1) +
                (size_t)pipe_slot;
            p->profile_wait_ticks[slot] +=
                p->ticks - p->profile_wait_started[man_index];
            p->profile_wait_pipe[man_index] = -2;
        }
#endif
        man->blocked = false;
        schedule_man_event(p, man_index, p->ticks);
    }
}

static void mark_display_ready(Program *p, int room_id) {
    int display_id = p->display_by_room[room_id];
    if (display_id >= 0 && !p->dirty_displays[display_id]) {
        p->dirty_displays[display_id] = 1;
        p->dirty_display_count++;
    }
}

static bool pipe_event_before(PipeEvent a, PipeEvent b) {
    if (a.tick != b.tick) {
        return a.tick < b.tick;
    }
    if (a.pipe_id != b.pipe_id) {
        return a.pipe_id < b.pipe_id;
    }
    return a.type < b.type;
}

static void push_pipe_event(Program *p, PipeEvent event) {
    if (p->pipe_event_count == p->pipe_event_cap) {
        p->pipe_event_cap = p->pipe_event_cap ? p->pipe_event_cap * 2 : 64;
        p->pipe_events = xrealloc(
            p->pipe_events,
            (size_t)p->pipe_event_cap * sizeof(*p->pipe_events));
    }
    int index = p->pipe_event_count++;
    while (index > 0) {
        int parent = (index - 1) / 2;
        if (!pipe_event_before(event, p->pipe_events[parent])) {
            break;
        }
        p->pipe_events[index] = p->pipe_events[parent];
        index = parent;
    }
    p->pipe_events[index] = event;
}

static PipeEvent pop_pipe_event(Program *p) {
    PipeEvent result = p->pipe_events[0];
    PipeEvent last = p->pipe_events[--p->pipe_event_count];
    if (!p->pipe_event_count) {
        return result;
    }
    int index = 0;
    for (;;) {
        int left = index * 2 + 1;
        if (left >= p->pipe_event_count) {
            break;
        }
        int child = left;
        int right = left + 1;
        if (right < p->pipe_event_count &&
            pipe_event_before(p->pipe_events[right], p->pipe_events[left])) {
            child = right;
        }
        if (!pipe_event_before(p->pipe_events[child], last)) {
            break;
        }
        p->pipe_events[index] = p->pipe_events[child];
        index = child;
    }
    p->pipe_events[index] = last;
    return result;
}

static void schedule_source_release(Program *p, int pipe_id) {
    Pipe *pipe = &p->pipes[pipe_id];
    if (pipe->source_release_pending || !pipe->source_full ||
        pipe->token_count >= pipe->length) {
        return;
    }
    pipe->source_release_pending = true;
    push_pipe_event(p, (PipeEvent){
        .tick = p->ticks + 1,
        .pipe_id = pipe_id,
        .type = PIPE_SOURCE_RELEASE,
    });
}

static void schedule_arrival(Program *p, int pipe_id, uint64_t earliest) {
    Pipe *pipe = &p->pipes[pipe_id];
    if (pipe->arrival_pending || pipe->dest_full || !pipe->token_count) {
        return;
    }
    if (earliest <= p->ticks) {
        earliest = p->ticks + 1;
    }
    pipe->arrival_pending = true;
    push_pipe_event(p, (PipeEvent){
        .tick = earliest,
        .pipe_id = pipe_id,
        .type = PIPE_ARRIVAL,
    });
}
#endif

static bool pipe_source_full(const Program *p, int pipe_id) {
#ifdef FAST_MODE
    return p->pipes[pipe_id].source_full;
#else
    return p->pipe_full[pipe_endpoint_index(p, pipe_id, false)];
#endif
}

static bool pipe_dest_full(const Program *p, int pipe_id) {
#ifdef FAST_MODE
    return p->pipes[pipe_id].dest_full;
#else
    return p->pipe_full[pipe_endpoint_index(p, pipe_id, true)];
#endif
}

static bool consume_pipe(Program *p, int pipe_id, int64_t *value) {
    if (pipe_id < 0) {
        return false;
    }
#ifdef FAST_MODE
    Pipe *pipe = &p->pipes[pipe_id];
    if (!pipe->dest_full || pipe->token_count <= 0) {
        return false;
    }
    *value = pipe->queued_values[pipe->queue_head];
    pipe->dest_full = false;
    pipe->queue_head = (pipe->queue_head + 1) % pipe->length;
    pipe->token_count--;
#ifdef PROFILE_MODE
    if (p->profile_enabled) {
        p->profile_pipe_consumes[pipe_id]++;
    }
#endif
    schedule_source_release(p, pipe_id);
    if (pipe->token_count) {
        schedule_arrival(
            p, pipe_id, pipe->queued_arrivals[pipe->queue_head]);
    }
#else
    int index = pipe_endpoint_index(p, pipe_id, true);
    if (!p->pipe_full[index]) {
        return false;
    }
    *value = p->pipe_value[index];
    p->pipe_full[index] = 0;
    Pipe *pipe = &p->pipes[pipe_id];
    if (pipe->token_count <= 0 ||
        pipe->token_positions[0] != pipe->length - 1) {
        set_error(p, "pipe token index is inconsistent");
        return false;
    }
    pipe->token_count--;
    if (pipe->token_count) {
        memmove(
            pipe->token_positions,
            pipe->token_positions + 1,
            (size_t)pipe->token_count * sizeof(*pipe->token_positions));
    }
#endif
    return true;
}

static void shift_pipes(Program *p) {
#ifdef FAST_MODE
    while (p->pipe_event_count &&
           p->pipe_events[0].tick <= p->ticks) {
        PipeEvent event = pop_pipe_event(p);
        Pipe *pipe = &p->pipes[event.pipe_id];
        if (event.type == PIPE_SOURCE_RELEASE) {
            pipe->source_release_pending = false;
            if (pipe->source_full && pipe->token_count < pipe->length) {
                pipe->source_full = false;
                wake_sleeping_man(
                    p, p->sleeping_writers, pipe->source_room);
            }
        } else {
            pipe->arrival_pending = false;
            if (!pipe->dest_full && pipe->token_count) {
                pipe->dest_full = true;
                mark_display_ready(p, pipe->dest_room);
                wake_sleeping_man(
                    p, p->sleeping_readers, pipe->dest_room);
            }
        }
    }
#else
    for (int pipe_id = 0; pipe_id < p->pipe_count; pipe_id++) {
        Pipe *pipe = &p->pipes[pipe_id];
        for (int token = 0; token < pipe->token_count; token++) {
            int position = pipe->token_positions[token];
            if (position + 1 >= pipe->length) {
                continue;
            }
            Point current_point = pipe->path[position];
            Point next_point = pipe->path[position + 1];
            int current = cell_index(p, current_point.x, current_point.y);
            int next = cell_index(p, next_point.x, next_point.y);
            if (!p->pipe_full[next]) {
                p->pipe_value[next] = p->pipe_value[current];
                p->pipe_full[next] = 1;
                p->pipe_full[current] = 0;
                pipe->token_positions[token]++;
            }
        }
    }
#endif
}

static void send_pipe(Program *p, int pipe_id, int64_t value) {
    Pipe *pipe = &p->pipes[pipe_id];
#ifdef FAST_MODE
    if (pipe->source_full || pipe->token_count >= pipe->length) {
        set_error(p, "send to a full pipe");
        return;
    }
    int tail = (pipe->queue_head + pipe->token_count) % pipe->length;
    pipe->queued_values[tail] = value;
    pipe->queued_arrivals[tail] = p->ticks + (uint64_t)pipe->length - 1;
    pipe->token_count++;
#ifdef PROFILE_MODE
    if (p->profile_enabled) {
        p->profile_pipe_sends[pipe_id]++;
    }
#endif
    pipe->source_full = true;
    schedule_source_release(p, pipe_id);
    if (pipe->token_count == 1) {
        schedule_arrival(p, pipe_id, pipe->queued_arrivals[tail]);
    }
#else
    int endpoint = pipe_endpoint_index(p, pipe_id, false);
    p->pipe_value[endpoint] = value;
    p->pipe_full[endpoint] = 1;
    pipe->token_positions[pipe->token_count++] = 0;
#endif
}

static void consume_displays(Program *p) {
    for (int i = 0; i < p->display_count; i++) {
#ifdef FAST_MODE
        if (!p->dirty_displays[i]) {
            continue;
        }
        p->dirty_displays[i] = 0;
        p->dirty_display_count--;
#endif
        Display *display = &p->displays[i];
        int64_t value;
        if (consume_pipe(p, display->addr_pipe, &value)) {
            if (value < 0 || value >= (int64_t)display->width * display->height) {
                set_error(p, "display ADDR value out of range");
                return;
            }
            display->cursor = (int)value;
        }
        if (consume_pipe(p, display->data_pipe, &value)) {
            if (value < 0 || value > 15) {
                if (!p->error[0]) {
                    snprintf(
                        p->error,
                        sizeof(p->error),
                        "display DATA value out of range: %" PRId64,
                        value);
                }
                p->halted = true;
                return;
            }
            display->next[display->cursor] = value;
#ifdef TV_MODE
            display->painted[display->cursor] = 1;
#endif
            display->cursor =
                (display->cursor + 1) % (display->width * display->height);
            display->writes++;
        }
        if (consume_pipe(p, display->swap_pipe, &value)) {
            if (value != 0 && value != 1) {
                set_error(p, "display SWAP value out of range");
                return;
            }
            memcpy(
                display->current, display->next,
                (size_t)display->width * display->height * sizeof(int64_t));
            display->swaps++;
#ifdef TV_MODE
            memset(
                display->painted, 0,
                (size_t)display->width * display->height);
#endif
            if (value == 0) {
                memset(
                    display->next, 0,
                    (size_t)display->width * display->height * sizeof(int64_t));
                display->cursor = 0;
            }
        }
    }
}

#ifndef FAST_MODE
static bool handle_literal(Program *p, Man *man, int index) {
    int literal_id = man->dx ? p->literal_h[index] : p->literal_v[index];
    if (literal_id < 0) {
        return p->grid[index] == '`';
    }
    Literal *literal = &p->literals[literal_id];
    if (literal->horizontal) {
        if (man->dx > 0 && man->x == literal->min_x) {
            if (!literal->forward_valid) {
                set_error_at(p, "invalid numeric literal", man->x, man->y);
                return true;
            }
            man->a = literal->forward;
        } else if (man->dx < 0 && man->x == literal->max_x) {
            if (!literal->backward_valid) {
                set_error_at(p, "invalid numeric literal", man->x, man->y);
                return true;
            }
            man->a = literal->backward;
        }
    } else if (man->dy > 0 && man->y == literal->min_y) {
        if (!literal->forward_valid) {
            set_error_at(p, "invalid numeric literal", man->x, man->y);
            return true;
        }
        man->a = literal->forward;
    } else if (man->dy < 0 && man->y == literal->max_y) {
        if (!literal->backward_valid) {
            set_error_at(p, "invalid numeric literal", man->x, man->y);
            return true;
        }
        man->a = literal->backward;
    }
    return true;
}

static void turn_clockwise(Man *man) {
    int dx = -man->dy;
    man->dy = man->dx;
    man->dx = dx;
}

static void turn_counterclockwise(Man *man) {
    int dx = man->dy;
    man->dy = -man->dx;
    man->dx = dx;
}

static void split_man(Program *p, int man_index, int room_id) {
    Man original = p->men[man_index];
    int left_dx = original.dy;
    int left_dy = -original.dx;
    int right_dx = -original.dy;
    int right_dy = original.dx;
    if (room_id < 0 || (!left_dx && !left_dy)) {
        set_error(p, "little man split with an invalid heading");
        return;
    }

    Point right_point = {original.x + right_dx, original.y + right_dy};
    Point left_point = {original.x + left_dx, original.y + left_dy};
    Room *room = &p->rooms[room_id];
    if (!room_contains(room, right_point.x, right_point.y) ||
        room_border(room, right_point.x, right_point.y) ||
        !room_contains(room, left_point.x, left_point.y) ||
        room_border(room, left_point.x, left_point.y)) {
        set_error(p, "little man split into a wall");
        return;
    }

    int live = 0;
    for (int i = 0; i < p->man_count; i++) {
        live += !p->men[i].halted;
    }
    if (live + 1 > MAX_LIVE_MEN || p->man_count >= MAX_LIVE_MEN) {
        set_error(p, "split exceeded the live little man limit");
        return;
    }

    Man right = original;
    right.id = p->next_man_id++;
    right.x = right_point.x;
    right.y = right_point.y;
    right.dx = right_dx;
    right.dy = right_dy;
    right.born_tick = p->ticks;
    right.halted = false;
    right.blocked = false;

    Man left = original;
    left.id = p->next_man_id++;
    left.x = left_point.x;
    left.y = left_point.y;
    left.dx = left_dx;
    left.dy = left_dy;
    left.born_tick = p->ticks;
    left.halted = false;
    left.blocked = false;

    for (int i = 0; i < p->man_count; i++) {
        if (i == man_index || p->men[i].halted) {
            continue;
        }
        if (p->men[i].x == right.x && p->men[i].y == right.y) {
            p->men[i].halted = true;
            right.halted = true;
        }
        if (p->men[i].x == left.x && p->men[i].y == left.y) {
            p->men[i].halted = true;
            left.halted = true;
        }
    }
    p->men[man_index] = right;
    p->men[p->man_count++] = left;
}
#endif

static int ready_incoming(const Program *p, int room_id, Point point) {
    const Room *room = &p->rooms[room_id];
    int best = -1;
    Point best_segment = {0, 0};
    for (int i = 0; i < room->incoming_count; i++) {
        int pipe_id = room->incoming[i];
        if (!pipe_dest_full(p, pipe_id)) {
            continue;
        }
        Point segment = p->pipes[pipe_id].path[p->pipes[pipe_id].length - 1];
        if (best < 0 ||
            point_distance(point, segment) < point_distance(point, best_segment) ||
            (point_distance(point, segment) == point_distance(point, best_segment) &&
             reading_order_before(segment, best_segment))) {
            best = pipe_id;
            best_segment = segment;
        }
    }
    return best;
}

#ifdef PROFILE_MODE
static void profile_begin_wait(
    Program *p, int man_index, int pipe_id, bool reader
) {
    if (!p->profile_enabled) {
        return;
    }
    int pipe_slot = pipe_id + 1;
    size_t slot =
        (size_t)man_index * (size_t)(p->pipe_count + 1) +
        (size_t)pipe_slot;
    p->profile_wait_started[man_index] = p->ticks;
    p->profile_wait_pipe[man_index] = pipe_id;
    p->profile_wait_reader[man_index] = reader;
    p->profile_wait_events[slot]++;
}
#endif

#ifdef FAST_MODE
static void sleep_man(Program *p, int man_index, int room_id, bool reader) {
    if (reader) {
        p->sleeping_readers[room_id] = man_index;
    } else {
        p->sleeping_writers[room_id] = man_index;
    }
}

static bool commit_trace_target(Program *p, Man *man, int target) {
    if (target >= 0) {
        man->pc = target;
        return true;
    }
    int state = -target - 1;
    int cell = state / 4;
    Direction direction = (Direction)(state % 4);
    int x = cell % p->width + direction_dx[direction];
    int y = cell / p->width + direction_dy[direction];
    if (!in_bounds(p, x, y)) {
        set_error_at(p, "little man left grid", x, y);
    } else {
        set_error_at(p, "little man hit a wall", x, y);
    }
    return false;
}

static bool trace_is_terminal(uint8_t opcode) {
    switch (opcode) {
    case TRACE_HALT:
    case TRACE_PIPE_COUNT:
    case TRACE_SEND:
    case TRACE_SEND_ALL:
    case TRACE_READ:
    case TRACE_READ_ANY:
    case TRACE_READ_TURN:
    case TRACE_INVALID_LITERAL:
    case TRACE_UNSUPPORTED:
        return true;
    default:
        return false;
    }
}

static int execute_local_trace(Program *p, Man *man, const TraceOp *op) {
    int target = op->next;
    switch (op->opcode) {
    case TRACE_NOP:
        break;
    case TRACE_MOVE_A_TO_B:
        man->b = man->a;
        break;
    case TRACE_SWAP: {
        int64_t tmp = man->a;
        man->a = man->b;
        man->b = tmp;
        break;
    }
    case TRACE_ADD:
        man->a = (int64_t)((uint64_t)man->a + (uint64_t)man->b);
        break;
    case TRACE_SUB:
        man->a = (int64_t)((uint64_t)man->a - (uint64_t)man->b);
        break;
    case TRACE_MUL:
        man->a = (int64_t)((uint64_t)man->a * (uint64_t)man->b);
        break;
    case TRACE_MOD:
        if (!man->b) {
            man->a = 0;
        } else if (man->a == INT64_MIN && man->b == -1) {
            man->a = 0;
        } else {
            int64_t result = man->a % man->b;
            if ((result < 0 && man->b > 0) ||
                (result > 0 && man->b < 0)) {
                result += man->b;
            }
            man->a = result;
        }
        break;
    case TRACE_DIV:
        if (!man->b) {
            man->a = 0;
        } else if (man->a == INT64_MIN && man->b == -1) {
            man->a = INT64_MIN;
            man->b = 0;
        } else {
            int64_t quotient = man->a / man->b;
            int64_t remainder = man->a % man->b;
            if ((man->a < 0) != (man->b < 0) && remainder) {
                quotient--;
                remainder += man->b;
            }
            man->a = quotient;
            man->b = remainder;
        }
        break;
    case TRACE_NEG:
        man->a = (int64_t)(0 - (uint64_t)man->a);
        break;
    case TRACE_AND:
        man->a &= man->b;
        break;
    case TRACE_OR:
        man->a |= man->b;
        break;
    case TRACE_XOR:
        man->a ^= man->b;
        break;
    case TRACE_SHIFT_LEFT:
        man->a = (man->b < 0 || man->b > 63)
                     ? 0
                     : (int64_t)((uint64_t)man->a << man->b);
        break;
    case TRACE_SHIFT_RIGHT:
        if (man->b < 0) {
            man->a = 0;
        } else if (man->b > 63) {
            man->a = man->a < 0 ? -1 : 0;
        } else {
            man->a >>= man->b;
        }
        break;
    case TRACE_LOAD:
        man->a = p->trace_constants[op->operand];
        break;
    case TRACE_BRANCH_SIGN: {
        TraceSignTargets branches = p->trace_sign_targets[op->operand];
        if (man->a > 0) {
            target = branches.positive;
        } else if (man->a < 0) {
            target = branches.negative;
        }
        break;
    }
    case TRACE_SET_BP:
        man->bp = man->a;
        break;
    case TRACE_DEC_BP:
        man->bp--;
        break;
    case TRACE_BRANCH_BP_POS_CW:
    case TRACE_BRANCH_BP_POS_CCW:
        if (man->bp > 0) {
            target = op->branch;
        }
        break;
    case TRACE_SHIFT_BP:
        man->bp >>= 1;
        break;
    case TRACE_BRANCH_BP_PARITY:
        if (man->bp & 1) {
            target = op->branch;
        }
        break;
    default:
        break;
    }
    return target;
}

#if defined(COMPUTED_GOTO) && (defined(__GNUC__) || defined(__clang__))
static void __attribute__((unused)) execute_trace(
    Program *p, int man_index
) {
#else
static void execute_trace(Program *p, int man_index) {
#endif
    Man *man = &p->men[man_index];
    if (man->pc < 0 || man->pc >= p->trace_op_count) {
        set_error(p, "compiled trace PC is out of range");
        return;
    }
    const TraceOp *op = &p->trace_ops[man->pc];
    if (!trace_is_terminal(op->opcode)) {
        int target = execute_local_trace(p, man, op);
        commit_trace_target(p, man, target);
        return;
    }
    int target = op->next;
    bool unblocked = true;
    bool reader = false;
    int sleep_room = -1;

    switch (op->opcode) {
    case TRACE_NOP:
        break;
    case TRACE_HALT:
        man->halted = true;
        set_man_runnable(p, man_index, false);
        p->live_man_count--;
        if (!p->live_man_count) {
            p->halted = true;
        }
        return;
    case TRACE_MOVE_A_TO_B:
        man->b = man->a;
        break;
    case TRACE_SWAP: {
        int64_t tmp = man->a;
        man->a = man->b;
        man->b = tmp;
        break;
    }
    case TRACE_ADD:
        man->a = (int64_t)((uint64_t)man->a + (uint64_t)man->b);
        break;
    case TRACE_SUB:
        man->a = (int64_t)((uint64_t)man->a - (uint64_t)man->b);
        break;
    case TRACE_MUL:
        man->a = (int64_t)((uint64_t)man->a * (uint64_t)man->b);
        break;
    case TRACE_MOD:
        if (!man->b) {
            man->a = 0;
        } else if (man->a == INT64_MIN && man->b == -1) {
            man->a = 0;
        } else {
            int64_t result = man->a % man->b;
            if ((result < 0 && man->b > 0) ||
                (result > 0 && man->b < 0)) {
                result += man->b;
            }
            man->a = result;
        }
        break;
    case TRACE_DIV:
        if (!man->b) {
            man->a = 0;
        } else if (man->a == INT64_MIN && man->b == -1) {
            man->a = INT64_MIN;
            man->b = 0;
        } else {
            int64_t quotient = man->a / man->b;
            int64_t remainder = man->a % man->b;
            if ((man->a < 0) != (man->b < 0) && remainder) {
                quotient--;
                remainder += man->b;
            }
            man->a = quotient;
            man->b = remainder;
        }
        break;
    case TRACE_NEG:
        man->a = (int64_t)(0 - (uint64_t)man->a);
        break;
    case TRACE_AND:
        man->a &= man->b;
        break;
    case TRACE_OR:
        man->a |= man->b;
        break;
    case TRACE_XOR:
        man->a ^= man->b;
        break;
    case TRACE_SHIFT_LEFT:
        man->a = (man->b < 0 || man->b > 63)
                     ? 0
                     : (int64_t)((uint64_t)man->a << man->b);
        break;
    case TRACE_SHIFT_RIGHT:
        if (man->b < 0) {
            man->a = 0;
        } else if (man->b > 63) {
            man->a = man->a < 0 ? -1 : 0;
        } else {
            man->a >>= man->b;
        }
        break;
    case TRACE_LOAD:
        man->a = p->trace_constants[op->operand];
        break;
    case TRACE_BRANCH_SIGN: {
        TraceSignTargets branches = p->trace_sign_targets[op->operand];
        if (man->a > 0) {
            target = branches.positive;
        } else if (man->a < 0) {
            target = branches.negative;
        }
        break;
    }
    case TRACE_SET_BP:
        man->bp = man->a;
        break;
    case TRACE_DEC_BP:
        man->bp--;
        break;
    case TRACE_BRANCH_BP_POS_CW:
    case TRACE_BRANCH_BP_POS_CCW:
        if (man->bp > 0) {
            target = op->branch;
        }
        break;
    case TRACE_SHIFT_BP:
        man->bp >>= 1;
        break;
    case TRACE_BRANCH_BP_PARITY:
        if (man->bp & 1) {
            target = op->branch;
        }
        break;
    case TRACE_PIPE_COUNT:
        if (op->operand < 0) {
            int cell = op->branch;
            set_error_at(
                p, "q with no incoming pipe",
                cell % p->width, cell / p->width);
            return;
        }
        man->bp = p->pipes[op->operand].token_count;
        break;
    case TRACE_SEND:
        if (op->operand < 0) {
            int cell = op->branch;
            set_error_at(
                p, "s with no outgoing pipe",
                cell % p->width, cell / p->width);
            return;
        }
        sleep_room = p->pipes[op->operand].source_room;
        if (pipe_source_full(p, op->operand)) {
            unblocked = false;
        } else {
            send_pipe(p, op->operand, man->a);
        }
        break;
    case TRACE_SEND_ALL: {
        if (op->operand < 0 ||
            !p->rooms[op->operand].outgoing_count) {
            int cell = op->branch;
            set_error_at(
                p, "S with no outgoing pipes",
                cell % p->width, cell / p->width);
            return;
        }
        sleep_room = op->operand;
        Room *room = &p->rooms[op->operand];
        for (int i = 0; i < room->outgoing_count; i++) {
            if (pipe_source_full(p, room->outgoing[i])) {
                unblocked = false;
                break;
            }
        }
        if (unblocked) {
            for (int i = 0; i < room->outgoing_count; i++) {
                send_pipe(p, room->outgoing[i], man->a);
            }
        }
        break;
    }
    case TRACE_READ:
        reader = true;
        if (op->operand < 0) {
            int cell = op->branch;
            set_error_at(
                p, "r with no incoming pipe",
                cell % p->width, cell / p->width);
            return;
        }
        sleep_room = p->pipes[op->operand].dest_room;
        if (!pipe_dest_full(p, op->operand)) {
            unblocked = false;
        } else {
            consume_pipe(p, op->operand, &man->a);
        }
        break;
    case TRACE_READ_ANY:
    case TRACE_READ_TURN: {
        reader = true;
        TraceReadInfo *read = &p->trace_reads[op->operand];
        if (read->room_id < 0) {
            set_error_at(
                p, "R with no room",
                read->point.x, read->point.y);
            return;
        }
        sleep_room = read->room_id;
        int pipe_id = ready_incoming(
            p, read->room_id, read->point);
        if (pipe_id < 0) {
            unblocked = false;
        } else {
            consume_pipe(p, pipe_id, &man->a);
            if (op->opcode == TRACE_READ_TURN) {
                target = read->pipe_targets[pipe_id];
            }
        }
        break;
    }
    case TRACE_INVALID_LITERAL: {
        int cell = op->operand;
        set_error_at(
            p, "invalid numeric literal",
            cell % p->width, cell / p->width);
        return;
    }
    case TRACE_UNSUPPORTED: {
        int cell = op->operand;
        set_error_at(
            p, "unsupported instruction",
            cell % p->width, cell / p->width);
        return;
    }
    }

    man->blocked = !unblocked;
    if (!unblocked) {
        set_man_runnable(p, man_index, false);
        sleep_man(p, man_index, sleep_room, reader);
        return;
    }
    if (!p->halted) {
        commit_trace_target(p, man, target);
    }
}

#if defined(COMPUTED_GOTO) && (defined(__GNUC__) || defined(__clang__))
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wpedantic"
static void run_man_event(
    Program *p, int man_index, uint64_t tick_limit
) {
    static const void *dispatch[] = {
        [TRACE_NOP] = &&op_nop,
        [TRACE_HALT] = &&op_halt,
        [TRACE_MOVE_A_TO_B] = &&op_move_a_to_b,
        [TRACE_SWAP] = &&op_swap,
        [TRACE_ADD] = &&op_add,
        [TRACE_SUB] = &&op_sub,
        [TRACE_MUL] = &&op_mul,
        [TRACE_MOD] = &&op_mod,
        [TRACE_DIV] = &&op_div,
        [TRACE_NEG] = &&op_neg,
        [TRACE_AND] = &&op_and,
        [TRACE_OR] = &&op_or,
        [TRACE_XOR] = &&op_xor,
        [TRACE_SHIFT_LEFT] = &&op_shift_left,
        [TRACE_SHIFT_RIGHT] = &&op_shift_right,
        [TRACE_LOAD] = &&op_load,
        [TRACE_BRANCH_SIGN] = &&op_branch_sign,
        [TRACE_SET_BP] = &&op_set_bp,
        [TRACE_DEC_BP] = &&op_dec_bp,
        [TRACE_BRANCH_BP_POS_CW] = &&op_branch_bp_positive,
        [TRACE_BRANCH_BP_POS_CCW] = &&op_branch_bp_positive,
        [TRACE_SHIFT_BP] = &&op_shift_bp,
        [TRACE_BRANCH_BP_PARITY] = &&op_branch_bp_parity,
        [TRACE_PIPE_COUNT] = &&op_pipe_count,
        [TRACE_SEND] = &&op_send,
        [TRACE_SEND_ALL] = &&op_send_all,
        [TRACE_READ] = &&op_read,
        [TRACE_READ_ANY] = &&op_read_any,
        [TRACE_READ_TURN] = &&op_read_turn,
        [TRACE_INVALID_LITERAL] = &&op_invalid_literal,
        [TRACE_UNSUPPORTED] = &&op_unsupported,
    };
    Man *man = &p->men[man_index];
    const TraceOp *ops = p->trace_ops;
    const int64_t *constants = p->trace_constants;
    const TraceSignTargets *sign_targets = p->trace_sign_targets;
    const TraceOp *op;
    uint64_t virtual_tick = p->ticks;
    int64_t a = man->a;
    int64_t b = man->b;
    int64_t bp = man->bp;
    int pc = man->pc;
    int target;
    int sleep_room;
#ifdef PROFILE_MODE
    int sleep_pipe = -1;
#endif

#define FLUSH_MAN()                                                         \
    do {                                                                    \
        man->pc = pc;                                                       \
        man->a = a;                                                         \
        man->b = b;                                                         \
        man->bp = bp;                                                       \
    } while (0)

#define FIXED_HANDLER(label, action)                                        \
    label:                                                                  \
        target = op->next;                                                  \
        if (target < 0 && virtual_tick > p->ticks) goto defer;             \
        do { action; } while (0);                                           \
        goto commit

dispatch_next:
    if (__builtin_expect(
            p->halted || man->halted || man->blocked, 0)) {
        FLUSH_MAN();
        return;
    }
    if (__builtin_expect(virtual_tick > tick_limit, 0)) {
        goto defer;
    }
    op = &ops[pc];
    goto *dispatch[op->opcode];

op_nop:
    target = op->next;
    if (target < 0 && virtual_tick > p->ticks) {
        goto defer;
    }
    if (op->operand > 1) {
        if (__builtin_expect(target < 0, 0)) {
            goto movement_error;
        }
        pc = target;
#ifdef PROFILE_MODE
        if (p->profile_enabled) {
            p->profile_active_ticks[man_index] += (uint64_t)op->operand;
            p->profile_opcode_counts[
                (size_t)man_index * TRACE_OPCODE_COUNT + TRACE_NOP
            ] += (uint64_t)op->operand;
        }
#endif
        if (__builtin_expect(
                UINT64_MAX - virtual_tick < (uint64_t)op->operand, 0)) {
            FLUSH_MAN();
            return;
        }
        virtual_tick += (uint64_t)op->operand;
        goto dispatch_next;
    }
    goto commit;

    FIXED_HANDLER(op_move_a_to_b, b = a);
    FIXED_HANDLER(op_swap, {
        int64_t tmp = a;
        a = b;
        b = tmp;
    });
    FIXED_HANDLER(
        op_add,
        a = (int64_t)((uint64_t)a + (uint64_t)b));
    FIXED_HANDLER(
        op_sub,
        a = (int64_t)((uint64_t)a - (uint64_t)b));
    FIXED_HANDLER(
        op_mul,
        a = (int64_t)((uint64_t)a * (uint64_t)b));
    FIXED_HANDLER(op_mod, {
        if (!b) {
            a = 0;
        } else if (a == INT64_MIN && b == -1) {
            a = 0;
        } else {
            int64_t result = a % b;
            if ((result < 0 && b > 0) ||
                (result > 0 && b < 0)) {
                result += b;
            }
            a = result;
        }
    });
    FIXED_HANDLER(op_div, {
        if (!b) {
            a = 0;
        } else if (a == INT64_MIN && b == -1) {
            a = INT64_MIN;
            b = 0;
        } else {
            int64_t quotient = a / b;
            int64_t remainder = a % b;
            if ((a < 0) != (b < 0) && remainder) {
                quotient--;
                remainder += b;
            }
            a = quotient;
            b = remainder;
        }
    });
    FIXED_HANDLER(op_neg, a = (int64_t)(0 - (uint64_t)a));
    FIXED_HANDLER(op_and, a &= b);
    FIXED_HANDLER(op_or, a |= b);
    FIXED_HANDLER(op_xor, a ^= b);
    FIXED_HANDLER(
        op_shift_left,
        a = (b < 0 || b > 63)
                ? 0
                : (int64_t)((uint64_t)a << b));
    FIXED_HANDLER(op_shift_right, {
        if (b < 0) {
            a = 0;
        } else if (b > 63) {
            a = a < 0 ? -1 : 0;
        } else {
            a >>= b;
        }
    });
    FIXED_HANDLER(op_load, a = constants[op->operand]);
    FIXED_HANDLER(op_set_bp, bp = a);
    FIXED_HANDLER(op_dec_bp, bp--);
    FIXED_HANDLER(op_shift_bp, bp >>= 1);

op_branch_sign: {
    TraceSignTargets branches = sign_targets[op->operand];
    target = a > 0
                 ? branches.positive
                 : (a < 0 ? branches.negative : op->next);
    if (target < 0 && virtual_tick > p->ticks) {
        goto defer;
    }
    goto commit;
}

op_branch_bp_positive:
    target = bp > 0 ? op->branch : op->next;
    if (target < 0 && virtual_tick > p->ticks) {
        goto defer;
    }
    goto commit;

op_branch_bp_parity:
    target = (bp & 1) ? op->branch : op->next;
    if (target < 0 && virtual_tick > p->ticks) {
        goto defer;
    }
    goto commit;

op_halt:
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    FLUSH_MAN();
#ifdef PROFILE_MODE
    if (p->profile_enabled) {
        p->profile_active_ticks[man_index]++;
        p->profile_opcode_counts[
            (size_t)man_index * TRACE_OPCODE_COUNT + TRACE_HALT
        ]++;
    }
#endif
    man->halted = true;
    set_man_runnable(p, man_index, false);
    p->live_man_count--;
    if (!p->live_man_count) {
        p->halted = true;
    }
    return;

op_pipe_count:
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    if (__builtin_expect(op->operand < 0, 0)) {
        int cell = op->branch;
        FLUSH_MAN();
        set_error_at(
            p, "q with no incoming pipe",
            cell % p->width, cell / p->width);
        return;
    }
    bp = p->pipes[op->operand].token_count;
    target = op->next;
    goto commit;

op_send:
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    if (__builtin_expect(op->operand < 0, 0)) {
        int cell = op->branch;
        FLUSH_MAN();
        set_error_at(
            p, "s with no outgoing pipe",
            cell % p->width, cell / p->width);
        return;
    }
    sleep_room = p->pipes[op->operand].source_room;
#ifdef PROFILE_MODE
    sleep_pipe = op->operand;
#endif
    if (__builtin_expect(pipe_source_full(p, op->operand), 0)) {
        goto block_writer;
    }
    send_pipe(p, op->operand, a);
    if (__builtin_expect(p->halted, 0)) {
        FLUSH_MAN();
        return;
    }
    target = op->next;
    goto commit;

op_send_all: {
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    if (__builtin_expect(
            op->operand < 0 ||
                !p->rooms[op->operand].outgoing_count,
            0)) {
        int cell = op->branch;
        FLUSH_MAN();
        set_error_at(
            p, "S with no outgoing pipes",
            cell % p->width, cell / p->width);
        return;
    }
    sleep_room = op->operand;
    Room *room = &p->rooms[op->operand];
    for (int i = 0; i < room->outgoing_count; i++) {
        if (__builtin_expect(
                pipe_source_full(p, room->outgoing[i]), 0)) {
            goto block_writer;
        }
    }
    for (int i = 0; i < room->outgoing_count; i++) {
        send_pipe(p, room->outgoing[i], a);
    }
    if (__builtin_expect(p->halted, 0)) {
        FLUSH_MAN();
        return;
    }
    target = op->next;
    goto commit;
}

op_read:
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    if (__builtin_expect(op->operand < 0, 0)) {
        int cell = op->branch;
        FLUSH_MAN();
        set_error_at(
            p, "r with no incoming pipe",
            cell % p->width, cell / p->width);
        return;
    }
    sleep_room = p->pipes[op->operand].dest_room;
#ifdef PROFILE_MODE
    sleep_pipe = op->operand;
#endif
    if (__builtin_expect(!pipe_dest_full(p, op->operand), 0)) {
        goto block_reader;
    }
    consume_pipe(p, op->operand, &a);
    target = op->next;
    goto commit;

op_read_any:
op_read_turn: {
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    TraceReadInfo *read = &p->trace_reads[op->operand];
    if (__builtin_expect(read->room_id < 0, 0)) {
        FLUSH_MAN();
        set_error_at(
            p, "R with no room",
            read->point.x, read->point.y);
        return;
    }
    sleep_room = read->room_id;
    int pipe_id = ready_incoming(
        p, read->room_id, read->point);
    if (__builtin_expect(pipe_id < 0, 0)) {
        goto block_reader;
    }
    consume_pipe(p, pipe_id, &a);
    target = op->opcode == TRACE_READ_TURN
                 ? read->pipe_targets[pipe_id]
                 : op->next;
    goto commit;
}

op_invalid_literal: {
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    int cell = op->operand;
    FLUSH_MAN();
    set_error_at(
        p, "invalid numeric literal",
        cell % p->width, cell / p->width);
    return;
}

op_unsupported: {
    if (virtual_tick > p->ticks) {
        goto defer;
    }
    int cell = op->operand;
    FLUSH_MAN();
    set_error_at(
        p, "unsupported instruction",
        cell % p->width, cell / p->width);
    return;
}

commit:
#ifdef PROFILE_MODE
    if (p->profile_enabled) {
        p->profile_active_ticks[man_index]++;
        p->profile_opcode_counts[
            (size_t)man_index * TRACE_OPCODE_COUNT + op->opcode
        ]++;
    }
#endif
    if (__builtin_expect(target >= 0, 1)) {
        pc = target;
    } else {
        goto movement_error;
    }
    if (__builtin_expect(virtual_tick == UINT64_MAX, 0)) {
        FLUSH_MAN();
        return;
    }
    virtual_tick++;
    goto dispatch_next;

movement_error:
    FLUSH_MAN();
    commit_trace_target(p, man, target);
    return;

block_reader:
    FLUSH_MAN();
    man->blocked = true;
    set_man_runnable(p, man_index, false);
#ifdef PROFILE_MODE
    profile_begin_wait(p, man_index, sleep_pipe, true);
#endif
    sleep_man(p, man_index, sleep_room, true);
    return;

block_writer:
    FLUSH_MAN();
    man->blocked = true;
    set_man_runnable(p, man_index, false);
#ifdef PROFILE_MODE
    profile_begin_wait(p, man_index, sleep_pipe, false);
#endif
    sleep_man(p, man_index, sleep_room, false);
    return;

defer:
    FLUSH_MAN();
    schedule_man_event(p, man_index, virtual_tick);

#undef FIXED_HANDLER
#undef FLUSH_MAN
}
#pragma GCC diagnostic pop
#else
static void run_man_event(
    Program *p, int man_index, uint64_t tick_limit
) {
    Man *man = &p->men[man_index];
    uint64_t virtual_tick = p->ticks;

    while (!p->halted && !man->halted && !man->blocked) {
        if (virtual_tick > tick_limit) {
            schedule_man_event(p, man_index, virtual_tick);
            return;
        }
        const TraceOp *op = &p->trace_ops[man->pc];
        if (op->opcode == TRACE_NOP && op->operand > 1) {
            man->pc = op->next;
            if (UINT64_MAX - virtual_tick < (uint64_t)op->operand) {
                return;
            }
            virtual_tick += (uint64_t)op->operand;
            continue;
        }
        if (trace_is_terminal(op->opcode)) {
            if (virtual_tick > p->ticks) {
                schedule_man_event(p, man_index, virtual_tick);
                return;
            }
            execute_trace(p, man_index);
            if (p->halted || man->halted || man->blocked) {
                return;
            }
        } else {
            Man before = *man;
            int target = execute_local_trace(p, man, op);
            if (target < 0 && virtual_tick > p->ticks) {
                *man = before;
                schedule_man_event(p, man_index, virtual_tick);
                return;
            }
            if (!commit_trace_target(p, man, target)) {
                return;
            }
        }
        if (virtual_tick == UINT64_MAX) {
            return;
        }
        virtual_tick++;
    }
}
#endif

#else
static void execute_man(Program *p, int man_index) {
    Man *man = &p->men[man_index];
    int index = cell_index(p, man->x, man->y);
    if (handle_literal(p, man, index)) {
        return;
    }
    char ch = p->grid[index];
    int room_id = p->room_at[index];
    bool unblocked = true;
    switch (ch) {
    case '@':
    case '.':
    case ' ':
        break;
    case 'Y':
#ifdef FAST_MODE
        set_error_at(p, "Y is unavailable in FAST_MODE", man->x, man->y);
#else
        split_man(p, man_index, room_id);
#endif
        return;
    case 'H':
        man->halted = true;
        break;
    case 'M':
        man->b = man->a;
        break;
    case 'W': {
        int64_t tmp = man->a;
        man->a = man->b;
        man->b = tmp;
        break;
    }
    case '+': man->a = (int64_t)((uint64_t)man->a + (uint64_t)man->b); break;
    case '-': man->a = (int64_t)((uint64_t)man->a - (uint64_t)man->b); break;
    case '*': man->a = (int64_t)((uint64_t)man->a * (uint64_t)man->b); break;
    case '%':
        if (!man->b) {
            man->a = 0;
        } else if (man->a == INT64_MIN && man->b == -1) {
            man->a = 0;
        } else {
            int64_t result = man->a % man->b;
            if ((result < 0 && man->b > 0) || (result > 0 && man->b < 0)) {
                result += man->b;
            }
            man->a = result;
        }
        break;
    case '/':
        if (!man->b) {
            man->a = 0;
        } else if (man->a == INT64_MIN && man->b == -1) {
            man->a = INT64_MIN;
            man->b = 0;
        } else {
            int64_t quotient = man->a / man->b;
            int64_t remainder = man->a % man->b;
            if ((man->a < 0) != (man->b < 0) && remainder) {
                quotient--;
                remainder += man->b;
            }
            man->a = quotient;
            man->b = remainder;
        }
        break;
    case 'N': man->a = (int64_t)(0 - (uint64_t)man->a); break;
    case '&': man->a &= man->b; break;
    case '|': man->a |= man->b; break;
    case '~': man->a ^= man->b; break;
    case '{':
        man->a = (man->b < 0 || man->b > 63)
                     ? 0
                     : (int64_t)((uint64_t)man->a << man->b);
        break;
    case '}':
        if (man->b < 0) {
            man->a = 0;
        } else if (man->b > 63) {
            man->a = man->a < 0 ? -1 : 0;
        } else {
            man->a >>= man->b;
        }
        break;
    case '>': man->dx = 1; man->dy = 0; break;
    case '<': man->dx = -1; man->dy = 0; break;
    case '^': man->dx = 0; man->dy = -1; break;
    case 'v':
    case 'V': man->dx = 0; man->dy = 1; break;
    case 'X':
        if (man->a > 0) turn_clockwise(man);
        else if (man->a < 0) turn_counterclockwise(man);
        break;
    case 'b': man->bp = man->a; break;
    case 'm': man->bp--; break;
    case 'd': if (man->bp > 0) turn_clockwise(man); break;
    case 'a': if (man->bp > 0) turn_counterclockwise(man); break;
    case ']': man->bp >>= 1; break;
    case 'x':
        if (man->bp & 1) turn_clockwise(man);
        else turn_counterclockwise(man);
        break;
    case 'q': {
        int pipe_id = p->nearest_in[index];
        if (pipe_id < 0) {
            set_error_at(p, "q with no incoming pipe", man->x, man->y);
            return;
        }
        int64_t count = 0;
        Pipe *pipe = &p->pipes[pipe_id];
        count = pipe->token_count;
        man->bp = count;
        break;
    }
    case 's': {
        int pipe_id = p->nearest_out[index];
        if (pipe_id < 0) {
            set_error_at(p, "s with no outgoing pipe", man->x, man->y);
            return;
        }
        if (pipe_source_full(p, pipe_id)) {
            unblocked = false;
        } else {
            send_pipe(p, pipe_id, man->a);
        }
        break;
    }
    case 'S': {
        Room *room = room_id >= 0 ? &p->rooms[room_id] : NULL;
        if (!room || !room->outgoing_count) {
            set_error_at(p, "S with no outgoing pipes", man->x, man->y);
            return;
        }
        for (int i = 0; i < room->outgoing_count; i++) {
            if (pipe_source_full(p, room->outgoing[i])) {
                unblocked = false;
                break;
            }
        }
        if (unblocked) {
            for (int i = 0; i < room->outgoing_count; i++) {
                send_pipe(p, room->outgoing[i], man->a);
            }
        }
        break;
    }
    case 'r': {
        int pipe_id = p->nearest_in[index];
        if (pipe_id < 0) {
            set_error_at(p, "r with no incoming pipe", man->x, man->y);
            return;
        }
        if (!pipe_dest_full(p, pipe_id)) {
            unblocked = false;
        } else {
            consume_pipe(p, pipe_id, &man->a);
        }
        break;
    }
    case 'R':
    case 'U': {
        int pipe_id = ready_incoming(p, room_id, (Point){man->x, man->y});
        if (pipe_id < 0) {
            unblocked = false;
        } else {
            consume_pipe(p, pipe_id, &man->a);
            if (ch == 'U') {
                Point segment = p->pipes[pipe_id].path[p->pipes[pipe_id].length - 1];
                int dx = man->x - segment.x;
                int dy = man->y - segment.y;
                if (dx) {
                    man->dx = dx < 0 ? -1 : 1;
                    man->dy = 0;
                } else if (dy) {
                    man->dx = 0;
                    man->dy = dy < 0 ? -1 : 1;
                }
            }
        }
        break;
    }
    default:
        if (ch >= '0' && ch <= '9') {
            man->a = ch - '0';
        } else {
            set_error_at(p, "unsupported instruction", man->x, man->y);
            return;
        }
    }
    man->blocked = !unblocked;
}
#endif

#ifndef FAST_MODE
static void move_men(Program *p) {
    Point *old = p->old_positions;
    uint8_t *moved = p->moved;
    uint8_t *collided = p->collided;
    memset(moved, 0, (size_t)p->man_count);
    memset(collided, 0, (size_t)p->man_count);
    uint32_t generation = ++p->movement_generation;

    for (int i = 0; i < p->man_count; i++) {
        Man *man = &p->men[i];
        old[i] = (Point){man->x, man->y};
        if (!man->halted) {
            int index = cell_index(p, man->x, man->y);
            p->old_occupant[index] = i;
            p->old_occupant_stamp[index] = generation;
        }
    }

    for (int i = 0; i < p->man_count; i++) {
        Man *man = &p->men[i];
        if (!man->halted && !man->blocked && man->born_tick < p->ticks) {
            moved[i] = 1;
            man->x += man->dx;
            man->y += man->dy;
            if (!in_bounds(p, man->x, man->y)) {
                set_error_at(p, "little man left grid", man->x, man->y);
                goto done;
            }
            int room_id = p->room_at[cell_index(p, man->x, man->y)];
            if (room_id < 0 || room_border(&p->rooms[room_id], man->x, man->y)) {
                set_error_at(p, "little man hit a wall", man->x, man->y);
                goto done;
            }
        }
    }

    for (int i = 0; i < p->man_count; i++) {
        if (p->men[i].halted) continue;
        int index = cell_index(p, p->men[i].x, p->men[i].y);
        if (p->new_occupant_stamp[index] == generation) {
            collided[i] = 1;
            collided[p->new_occupant[index]] = 1;
        } else {
            p->new_occupant[index] = i;
            p->new_occupant_stamp[index] = generation;
        }
    }

    for (int i = 0; i < p->man_count; i++) {
        if (p->men[i].halted || !moved[i]) continue;
        int new_index = cell_index(p, p->men[i].x, p->men[i].y);
        if (p->old_occupant_stamp[new_index] != generation) continue;
        int other = p->old_occupant[new_index];
        if (other != i && moved[other] &&
            p->men[other].x == old[i].x && p->men[other].y == old[i].y) {
            collided[i] = 1;
            collided[other] = 1;
        }
    }

    bool any_active = false;
    for (int i = 0; i < p->man_count; i++) {
        if (collided[i]) {
            p->men[i].halted = true;
        }
        any_active |= !p->men[i].halted;
    }
    if (!any_active) {
        p->halted = true;
    }
done:
    return;
}
#endif

#ifdef FAST_MODE
static void initialize_man_events(Program *p) {
    for (int i = 0; i < p->man_count; i++) {
        schedule_man_event(p, i, 1);
    }
}

static bool step_program(Program *p, uint64_t tick_limit) {
    uint64_t next_tick = UINT64_MAX;
    if (p->pipe_event_count && p->pipe_events[0].tick < next_tick) {
        next_tick = p->pipe_events[0].tick;
    }
    if (p->man_event_count && p->man_events[0].tick < next_tick) {
        next_tick = p->man_events[0].tick;
    }
    if (next_tick == UINT64_MAX) {
        if (tick_limit != UINT64_MAX) {
            p->ticks = tick_limit;
            return false;
        }
        set_error(p, "event queue is empty while little men are still alive");
        return false;
    }
    if (next_tick > tick_limit) {
        p->ticks = tick_limit;
        return false;
    }
    p->ticks = next_tick;
    shift_pipes(p);
    if (p->dirty_display_count) {
        consume_displays(p);
    }
    if (p->halted) {
        return false;
    }

    while (p->man_event_count && p->man_events[0].tick <= p->ticks) {
        ManEvent event = pop_man_event(p);
        set_man_runnable(p, event.man_index, true);
    }
    for (int word = 0; word < p->runnable_word_count; word++) {
        uint64_t runnable = p->runnable_men[word];
        while (runnable) {
            int bit = __builtin_ctzll(runnable);
            int man_index = word * 64 + bit;
            runnable &= runnable - 1;
            set_man_runnable(p, man_index, false);
            run_man_event(p, man_index, tick_limit);
            if (p->halted) {
                return false;
            }
        }
    }
    return true;
}
#else
static void step_program(Program *p) {
    p->ticks++;
    shift_pipes(p);
    consume_displays(p);
    if (p->halted) {
        return;
    }
    int executing = p->man_count;
    for (int i = 0; i < executing; i++) {
        if (!p->men[i].halted) {
            execute_man(p, i);
            if (p->halted) {
                return;
            }
        }
    }
    move_men(p);
}
#endif

static uint64_t total_swaps(const Program *p) {
    uint64_t swaps = 0;
    for (int i = 0; i < p->display_count; i++) {
        swaps += p->displays[i].swaps;
    }
    return swaps;
}

static double now_seconds(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        die("clock_gettime failed");
    }
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static uint64_t parse_u64(const char *text, const char *name) {
    errno = 0;
    char *end;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno || end == text || *end) {
        fprintf(stderr, "invalid %s: %s\n", name, text);
        exit(2);
    }
    return (uint64_t)value;
}

static int64_t *parse_inputs(const char *text, int *count) {
    size_t length = strlen(text);
    char *copy = xmalloc(length + 1);
    memcpy(copy, text, length + 1);
    int capacity = 8;
    int64_t *values = xmalloc((size_t)capacity * sizeof(*values));
    *count = 0;
    for (char *token = strtok(copy, ","); token; token = strtok(NULL, ",")) {
        errno = 0;
        char *end;
        long long value = strtoll(token, &end, 10);
        if (errno || end == token || *end) {
            fprintf(stderr, "invalid input value: %s\n", token);
            exit(2);
        }
        if (*count == capacity) {
            capacity *= 2;
            values = xrealloc(values, (size_t)capacity * sizeof(*values));
        }
        values[(*count)++] = (int64_t)value;
    }
    free(copy);
    return values;
}

static bool send_external_input(Program *p, int64_t value) {
    if (p->input_room < 0) {
        set_error(p, "input values supplied to a program without an input room");
        return false;
    }
    Room *room = &p->rooms[p->input_room];
    for (int i = 0; i < room->outgoing_count; i++) {
        int pipe_id = room->outgoing[i];
        if (!pipe_source_full(p, pipe_id)) {
            send_pipe(p, pipe_id, value);
            return true;
        }
    }
    return false;
}

static void consume_external_output(Program *p) {
    if (p->output_room < 0) {
        return;
    }
    Room *room = &p->rooms[p->output_room];
    for (int i = 0; i < room->incoming_count; i++) {
        int64_t value;
        while (consume_pipe(p, room->incoming[i], &value)) {
            printf("output=%" PRId64 "\n", value);
        }
    }
}

static void usage(const char *argv0) {
    fprintf(
        stderr,
        "usage: %s PROGRAM [--frames N] [--ticks N] [--input V,...]"
        " [--display-gated N]"
#ifdef PROFILE_MODE
        " [--profile]"
#endif
        " [--visual] [--swap]\n"
        "  --frames N  stop after N display swaps (default 1)\n"
        "  --ticks N   stop after N ticks (default unlimited)\n"
        "  --input V,...  comma-separated external input values\n"
        "  --display-gated N  release N inputs initially, then one more"
        " after each display swap\n"
#ifdef PROFILE_MODE
        "  --profile   print per-man and per-pipe execution counters"
        "\n"
#endif
        "  --visual    show display 0; default to unlimited frames"
        " (requires TV_MODE)\n"
        "  --swap      show only completed frames (requires --visual)\n",
        argv0);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        usage(argv[0]);
        return 2;
    }
    uint64_t frame_limit = 1;
    uint64_t tick_limit = UINT64_MAX;
    int64_t *inputs = NULL;
    int input_count = 0;
    int input_index = 0;
    int display_gated_inputs = -1;
#ifdef PROFILE_MODE
    bool profile_requested = false;
#endif
#ifdef TV_MODE
    bool visual_requested = false;
    bool swap_requested = false;
    bool frame_limit_set = false;
#endif
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) {
            frame_limit = parse_u64(argv[++i], "frame count");
#ifdef TV_MODE
            frame_limit_set = true;
#endif
        } else if (!strcmp(argv[i], "--ticks") && i + 1 < argc) {
            tick_limit = parse_u64(argv[++i], "tick count");
        } else if (!strcmp(argv[i], "--input") && i + 1 < argc) {
            free(inputs);
            inputs = parse_inputs(argv[++i], &input_count);
            input_index = 0;
        } else if (!strcmp(argv[i], "--display-gated") && i + 1 < argc) {
            uint64_t value = parse_u64(argv[++i], "initial input count");
            if (value > INT_MAX) {
                die("initial input count is too large");
            }
            display_gated_inputs = (int)value;
        } else if (!strcmp(argv[i], "--profile")) {
#ifdef PROFILE_MODE
            profile_requested = true;
#else
            fprintf(
                stderr,
                "--profile is unavailable; rebuild with PROFILE_MODE=1\n");
            free(inputs);
            return 2;
#endif
        } else if (!strcmp(argv[i], "--visual")) {
#ifdef TV_MODE
            visual_requested = true;
#else
            fprintf(
                stderr,
                "--visual requires building with TV_MODE=1\n");
            free(inputs);
            return 2;
#endif
        } else if (!strcmp(argv[i], "--swap")) {
#ifdef TV_MODE
            swap_requested = true;
#else
            fprintf(
                stderr,
                "--swap requires building with TV_MODE=1\n");
            free(inputs);
            return 2;
#endif
        } else {
            usage(argv[0]);
            return 2;
        }
    }
#ifdef TV_MODE
    if (swap_requested && !visual_requested) {
        fprintf(stderr, "--swap requires --visual\n");
        free(inputs);
        return 2;
    }
    if (visual_requested && !frame_limit_set) {
        frame_limit = 0;
    }
#endif

    Program program = parse_program(argv[1]);
#ifdef PROFILE_MODE
    if (profile_requested) {
        size_t man_count = (size_t)program.man_count;
        size_t pipe_count = (size_t)program.pipe_count;
        size_t wait_slots = man_count * (pipe_count + 1);
        program.profile_enabled = true;
        program.profile_active_ticks =
            xcalloc(man_count, sizeof(*program.profile_active_ticks));
        program.profile_opcode_counts = xcalloc(
            man_count * TRACE_OPCODE_COUNT,
            sizeof(*program.profile_opcode_counts));
        program.profile_wait_started =
            xcalloc(man_count, sizeof(*program.profile_wait_started));
        program.profile_wait_pipe =
            xmalloc(man_count * sizeof(*program.profile_wait_pipe));
        program.profile_wait_reader =
            xcalloc(man_count, sizeof(*program.profile_wait_reader));
        program.profile_wait_ticks =
            xcalloc(wait_slots, sizeof(*program.profile_wait_ticks));
        program.profile_wait_events =
            xcalloc(wait_slots, sizeof(*program.profile_wait_events));
        program.profile_pipe_sends =
            xcalloc(pipe_count, sizeof(*program.profile_pipe_sends));
        program.profile_pipe_consumes =
            xcalloc(pipe_count, sizeof(*program.profile_pipe_consumes));
        for (int i = 0; i < program.man_count; i++) {
            program.profile_wait_pipe[i] = -2;
        }
    }
#endif
    if (display_gated_inputs > input_count) {
        die("initial display-gated input count exceeds supplied input count");
    }
    fprintf(
        stderr,
        "loaded %dx%d: rooms=%d pipes=%d men=%d displays=%d\n",
        program.width, program.height, program.room_count, program.pipe_count,
        program.man_count, program.display_count);

#ifdef TV_MODE
    VisualDisplay visual;
    bool visual_quit = false;
    if (visual_requested) {
        if (!program.display_count) {
            fprintf(stderr, "--visual requires a program with a display\n");
            free(inputs);
            return 2;
        }
        visual_init(
            &visual, &program.displays[0], swap_requested);
    }
#endif

    double start = now_seconds();
#ifdef FAST_MODE
    initialize_man_events(&program);
#endif
    while (!program.halted && program.ticks < tick_limit &&
           (!frame_limit || total_swaps(&program) < frame_limit)) {
        int available_inputs = input_count;
        if (display_gated_inputs >= 0) {
            uint64_t unlocked =
                (uint64_t)display_gated_inputs + total_swaps(&program);
            available_inputs =
                unlocked < (uint64_t)input_count ? (int)unlocked : input_count;
        }
        if (input_index < available_inputs &&
            send_external_input(&program, inputs[input_index])) {
            input_index++;
        }
#ifdef FAST_MODE
        if (!step_program(&program, tick_limit)) {
            break;
        }
#else
        step_program(&program);
#endif
        consume_external_output(&program);
#ifdef TV_MODE
        if (visual_requested &&
            !visual_update(&visual, &program.displays[0], false)) {
            visual_quit = true;
            break;
        }
#endif
    }
    double elapsed = now_seconds() - start;
    free(inputs);

#ifdef TV_MODE
    if (visual_requested) {
        if (!visual_quit) {
            visual_update(&visual, &program.displays[0], true);
        }
        visual_destroy(&visual);
    }
#endif

    printf("ticks=%" PRIu64 "\n", program.ticks);
    printf("seconds=%.6f\n", elapsed);
    printf("ticks_per_second=%.0f\n", elapsed > 0 ? program.ticks / elapsed : 0);
    for (int i = 0; i < program.display_count; i++) {
        Display *display = &program.displays[i];
        uint64_t hash = UINT64_C(1469598103934665603);
        int nonzero = 0;
        int pixels = display->width * display->height;
        for (int j = 0; j < pixels; j++) {
            hash ^= (uint64_t)display->current[j];
            hash *= UINT64_C(1099511628211);
            nonzero += display->current[j] != 0;
        }
        printf(
            "display=%d writes=%" PRIu64 " swaps=%" PRIu64
            " cursor=%d nonzero=%d hash=%" PRIu64 " current_prefix=",
            i, display->writes, display->swaps, display->cursor, nonzero, hash);
        int count = pixels;
        if (count > 16) count = 16;
        for (int j = 0; j < count; j++) {
            printf("%s%" PRId64, j ? "," : "", display->current[j]);
        }
        putchar('\n');
    }
#ifdef PROFILE_MODE
    if (program.profile_enabled) {
        for (int i = 0; i < program.man_count; i++) {
            int room_id = program.room_at[
                cell_index(&program, program.men[i].x, program.men[i].y)];
            Room *room = &program.rooms[room_id];
            uint64_t waits = 0;
            uint64_t blocks = 0;
            for (int slot = 0; slot <= program.pipe_count; slot++) {
                size_t index =
                    (size_t)i * (size_t)(program.pipe_count + 1) +
                    (size_t)slot;
                waits += program.profile_wait_ticks[index];
                blocks += program.profile_wait_events[index];
            }
            if (program.profile_wait_pipe[i] >= -1) {
                waits +=
                    program.ticks - program.profile_wait_started[i];
            }
            uint64_t *opcodes =
                &program.profile_opcode_counts[
                    (size_t)i * TRACE_OPCODE_COUNT];
            uint64_t alu_ops = 0;
            for (int opcode = TRACE_ADD; opcode <= TRACE_SHIFT_RIGHT; opcode++) {
                alu_ops += opcodes[opcode];
            }
            uint64_t branch_ops =
                opcodes[TRACE_BRANCH_SIGN] +
                opcodes[TRACE_BRANCH_BP_POS_CW] +
                opcodes[TRACE_BRANCH_BP_POS_CCW] +
                opcodes[TRACE_BRANCH_BP_PARITY];
            printf(
                "profile_man=%d room=%d bounds=%d,%d,%d,%d pos=%d,%d"
                " active=%" PRIu64 " wait=%" PRIu64
                " blocks=%" PRIu64 " send=%" PRIu64
                " read=%" PRIu64 " nop=%" PRIu64
                " load=%" PRIu64 " alu=%" PRIu64
                " branch=%" PRIu64 "\n",
                i, room_id, room->min_x, room->min_y,
                room->max_x, room->max_y,
                program.men[i].x, program.men[i].y,
                program.profile_active_ticks[i], waits, blocks,
                opcodes[TRACE_SEND], opcodes[TRACE_READ],
                opcodes[TRACE_NOP], opcodes[TRACE_LOAD],
                alu_ops, branch_ops);
            for (int slot = 0; slot <= program.pipe_count; slot++) {
                size_t index =
                    (size_t)i * (size_t)(program.pipe_count + 1) +
                    (size_t)slot;
                uint64_t edge_wait = program.profile_wait_ticks[index];
                uint64_t edge_events = program.profile_wait_events[index];
                int pipe_id = slot - 1;
                if (program.profile_wait_pipe[i] == pipe_id) {
                    edge_wait +=
                        program.ticks -
                        program.profile_wait_started[i];
                }
                if (edge_wait || edge_events) {
                    printf(
                        "profile_wait_man=%d pipe=%d ticks=%" PRIu64
                        " events=%" PRIu64 "\n",
                        i, pipe_id, edge_wait, edge_events);
                }
            }
        }
        for (int pipe_id = 0; pipe_id < program.pipe_count; pipe_id++) {
            uint64_t waits = 0;
            uint64_t blocks = 0;
            for (int man = 0; man < program.man_count; man++) {
                size_t index =
                    (size_t)man * (size_t)(program.pipe_count + 1) +
                    (size_t)(pipe_id + 1);
                waits += program.profile_wait_ticks[index];
                blocks += program.profile_wait_events[index];
                if (program.profile_wait_pipe[man] == pipe_id) {
                    waits +=
                        program.ticks -
                        program.profile_wait_started[man];
                }
            }
            if (!program.profile_pipe_sends[pipe_id] &&
                !program.profile_pipe_consumes[pipe_id] &&
                !waits && !blocks) {
                continue;
            }
            Pipe *pipe = &program.pipes[pipe_id];
            Room *source = &program.rooms[pipe->source_room];
            Room *dest = &program.rooms[pipe->dest_room];
            printf(
                "profile_pipe=%d length=%d source_room=%d"
                " source_bounds=%d,%d,%d,%d dest_room=%d"
                " dest_bounds=%d,%d,%d,%d sends=%" PRIu64
                " consumes=%" PRIu64 " wait=%" PRIu64
                " blocks=%" PRIu64 "\n",
                pipe_id, pipe->length, pipe->source_room,
                source->min_x, source->min_y, source->max_x, source->max_y,
                pipe->dest_room,
                dest->min_x, dest->min_y, dest->max_x, dest->max_y,
                program.profile_pipe_sends[pipe_id],
                program.profile_pipe_consumes[pipe_id],
                waits, blocks);
        }
    }
#endif
    if (program.error[0]) {
        fprintf(stderr, "error at tick %" PRIu64 ": %s\n", program.ticks, program.error);
        return 1;
    }
    return 0;
}
