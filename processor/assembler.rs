use std::collections::{HashMap, VecDeque};
use std::env;
use std::fs;
use std::io;

#[derive(Clone, Debug)]
enum Word {
    Value(i64),
    Offset { label: String, after: usize },
}

#[derive(Clone, Debug)]
struct Program {
    words: Vec<i64>,
    register_count: usize,
    uses_memory: bool,
}

#[derive(Clone, Debug)]
struct Build {
    program: Program,
    register_count: usize,
    memory_size: usize,
    memory_pipe_cells: usize,
    screen: Option<ScreenSpec>,
    program_kind: ProgramKind,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct ScreenSpec {
    width: usize,
    height: usize,
}

impl ScreenSpec {
    const PLOTTER: Self = Self {
        width: 32,
        height: 24,
    };
}

#[derive(Clone, Copy, Debug, Default)]
struct Target {
    screen: Option<ScreenSpec>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ProgramKind {
    Generic,
    Plotter,
    Snake,
    Pathfinder,
    Lllm,
    Llm,
    Matmul,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RegisterBankMode {
    SingleLane,
    TwoLane,
}

#[derive(Clone, Copy, Debug)]
enum Directive {
    Memory { size: usize, pipe_cells: usize },
    Screen(ScreenSpec),
    Kind(ProgramKind),
}

fn strip_comment(line: &str) -> &str {
    let semi = line.find(';');
    let hash = line.find('#');
    let cut = match (semi, hash) {
        (Some(a), Some(b)) => a.min(b),
        (Some(a), None) | (None, Some(a)) => a,
        (None, None) => line.len(),
    };
    &line[..cut]
}

fn tokenize(line: &str) -> Vec<String> {
    line.replace(',', " ")
        .split_whitespace()
        .map(|s| s.to_ascii_lowercase())
        .collect()
}

fn expand_repeats(source: &str) -> Result<String, String> {
    let mut output = String::new();
    let mut repeat: Option<(usize, usize, Vec<&str>)> = None;

    for raw in source.lines() {
        let tokens = tokenize(strip_comment(raw));
        if let Some((start, end, body)) = &mut repeat {
            if tokens.as_slice() == [".endrepeat"] {
                for index in *start..=*end {
                    for line in body.iter() {
                        output.push_str(&line.replace("{i}", &index.to_string()));
                        output.push('\n');
                    }
                }
                repeat = None;
            } else {
                body.push(raw);
            }
            continue;
        }

        if let [directive, start, end] = tokens.as_slice() {
            if directive == ".repeat" {
                let start = start
                    .parse::<usize>()
                    .map_err(|_| format!("bad repeat start `{start}`"))?;
                let end = end
                    .parse::<usize>()
                    .map_err(|_| format!("bad repeat end `{end}`"))?;
                if start > end {
                    return Err(format!("repeat start {start} exceeds end {end}"));
                }
                repeat = Some((start, end, Vec::new()));
                continue;
            }
        }

        output.push_str(raw);
        output.push('\n');
    }
    if repeat.is_some() {
        return Err("unterminated `.repeat` block".to_string());
    }
    Ok(output)
}

fn parse_reg(s: &str) -> Result<i64, String> {
    let raw = s.strip_prefix('r').unwrap_or(s);
    raw.parse::<i64>()
        .map_err(|_| format!("expected register, got `{s}`"))
        .and_then(|v| {
            if v >= 0 {
                Ok(v)
            } else {
                Err(format!("register must be non-negative, got `{s}`"))
            }
        })
}

fn parse_int(s: &str) -> Result<i64, String> {
    s.parse::<i64>()
        .map_err(|_| format!("expected integer, got `{s}`"))
}

const MATMUL_B_BASE: i64 = 10;

fn parse_directive(toks: &[String]) -> Result<Option<Directive>, String> {
    match toks {
        [name, size] | [name, size, _] if name == ".memory" || name == "memory" => {
            let size = size
                .parse::<usize>()
                .map_err(|_| format!("bad memory size `{size}`"))?;
            if size == 0 {
                return Err("memory size must be positive".to_string());
            }
            let minimum = size
                .checked_mul(2)
                .ok_or_else(|| format!("memory size `{size}` is too large"))?;
            let pipe_cells = if let [_, _, pipe_cells] = toks {
                pipe_cells
                    .parse::<usize>()
                    .map_err(|_| format!("bad memory pipe size `{pipe_cells}`"))?
            } else {
                minimum
            };
            if pipe_cells < minimum {
                return Err(format!(
                    "memory pipe requires at least {minimum} cells for {size} slots, got {pipe_cells}"
                ));
            }
            if pipe_cells % 2 != 0 {
                return Err(format!("memory pipe size must be even, got {pipe_cells}"));
            }
            Ok(Some(Directive::Memory { size, pipe_cells }))
        }
        [name] if name == ".screen" || name == "screen" => {
            Ok(Some(Directive::Screen(ScreenSpec::PLOTTER)))
        }
        [name, width, height] if name == ".screen" || name == "screen" => {
            let parse_dimension = |raw: &str| {
                raw.parse::<usize>()
                    .map_err(|_| format!("bad screen dimension `{raw}`"))
                    .and_then(|value| {
                        if (1..=64).contains(&value) {
                            Ok(value)
                        } else {
                            Err(format!("screen dimension must be in 1..=64, got {value}"))
                        }
                    })
            };
            Ok(Some(Directive::Screen(ScreenSpec {
                width: parse_dimension(width)?,
                height: parse_dimension(height)?,
            })))
        }
        [name, kind] if name == ".kind" && kind == "snake" => {
            Ok(Some(Directive::Kind(ProgramKind::Snake)))
        }
        [name, kind] if name == ".kind" && kind == "pathfinder" => {
            Ok(Some(Directive::Kind(ProgramKind::Pathfinder)))
        }
        [name, kind] if name == ".kind" && kind == "lllm" => {
            Ok(Some(Directive::Kind(ProgramKind::Lllm)))
        }
        [name, kind] if name == ".kind" && kind == "llm" => {
            Ok(Some(Directive::Kind(ProgramKind::Llm)))
        }
        [name, kind] if name == ".kind" && kind == "matmul" => {
            Ok(Some(Directive::Kind(ProgramKind::Matmul)))
        }
        [name, kind] if name == ".kind" => Err(format!("unknown program kind `{kind}`")),
        [name, ..] if name.starts_with('.') => Err(format!("unknown directive `{name}`")),
        _ => Ok(None),
    }
}

fn alu_code(op: &str) -> Result<i64, String> {
    match op {
        "add" | "+" => Ok(0),
        "mul" | "*" => Ok(1),
        "sub" | "-" => Ok(2),
        "div" | "/" => Ok(3),
        "and" | "&" => Ok(4),
        "shr" | "}" => Ok(5),
        "xor" | "~" => Ok(6),
        _ => Err(format!("unknown ALU op `{op}`")),
    }
}

fn alu0_code(op: &str) -> Option<(i64, bool)> {
    let (base, immediate) = if let Some(base) = op.strip_suffix("i0") {
        (base, true)
    } else if let Some(base) = op.strip_suffix('0') {
        (base, false)
    } else {
        return None;
    };
    alu_code(base).ok().map(|code| (code, immediate))
}

struct Assembler {
    labels: HashMap<String, usize>,
    words: Vec<Word>,
    gensym: usize,
    target: Target,
    max_register: usize,
    uses_memory: bool,
}

impl Assembler {
    fn new(target: Target) -> Self {
        Self {
            labels: HashMap::new(),
            words: Vec::new(),
            gensym: 0,
            target,
            max_register: 0,
            uses_memory: false,
        }
    }

    fn pos(&self) -> usize {
        self.words.len()
    }

    fn label(&mut self, name: &str) -> Result<(), String> {
        if self.labels.insert(name.to_string(), self.pos()).is_some() {
            return Err(format!("duplicate label `{name}`"));
        }
        Ok(())
    }

    fn gen_label(&mut self, prefix: &str) -> String {
        let label = format!("__{prefix}_{}", self.gensym);
        self.gensym += 1;
        label
    }

    fn value(&mut self, value: i64) {
        self.words.push(Word::Value(value));
    }

    fn offset(&mut self, label: &str, after: usize) {
        self.words.push(Word::Offset {
            label: label.to_string(),
            after,
        });
    }

    fn use_register(&mut self, register: i64) {
        self.max_register = self.max_register.max(register as usize);
    }

    fn mov(&mut self, dst: i64, src: i64) {
        self.use_register(dst);
        self.use_register(src);
        self.value(0);
        self.value(dst);
        self.value(src);
    }

    fn store(&mut self, addr: i64, src: i64) {
        self.use_register(addr);
        self.use_register(src);
        self.uses_memory = true;
        self.value(1);
        self.value(addr);
        self.value(src);
    }

    fn load(&mut self, dst: i64, addr: i64) {
        self.use_register(dst);
        self.use_register(addr);
        self.uses_memory = true;
        self.value(2);
        self.value(dst);
        self.value(addr);
    }

    fn imm(&mut self, dst: i64, value: i64) {
        self.use_register(dst);
        self.value(3);
        self.value(value);
        self.value(dst);
    }

    fn read(&mut self, dst: i64) {
        self.use_register(dst);
        self.value(4);
        self.value(dst);
    }

    fn write(&mut self, src: i64) {
        self.use_register(src);
        self.value(5);
        self.value(src);
    }

    fn screen_swap(&mut self, src: i64) -> Result<(), String> {
        if self.target.screen.is_none() {
            return Err("screen_swap requires `.screen`".to_string());
        }
        self.use_register(src);
        self.value(5);
        self.value(src);
        Ok(())
    }

    fn screen_addr(&mut self, src: i64) -> Result<(), String> {
        if self.target.screen.is_none() {
            return Err("screen_addr requires `.screen`".to_string());
        }
        self.use_register(src);
        self.value(6);
        self.value(src);
        Ok(())
    }

    fn screen_data(&mut self, src: i64) -> Result<(), String> {
        if self.target.screen.is_none() {
            return Err("screen_data requires `.screen`".to_string());
        }
        self.use_register(src);
        self.value(7);
        self.value(src);
        Ok(())
    }

    fn alu0(&mut self, op: i64, src: i64) {
        self.use_register(0);
        self.use_register(src);
        self.value(if self.target.screen.is_some() { 8 } else { 6 });
        self.value(op);
        self.value(src);
    }

    fn alu(&mut self, op: i64) {
        self.alu0(op, 1);
    }

    fn alu3(&mut self, dst: i64, lhs: i64, rhs: i64, op: i64) {
        if lhs != 0 {
            self.mov(0, lhs);
        }
        self.alu0(op, rhs);
        if dst != 0 {
            self.mov(dst, 0);
        }
    }

    fn jc(&mut self, cond: i64, label: &str) {
        self.use_register(cond);
        let after = self.pos() + 3;
        self.value(if self.target.screen.is_some() { 9 } else { 7 });
        self.offset(label, after);
        self.value(cond);
    }

    fn jmp(&mut self, label: &str) {
        let after = self.pos() + 2;
        self.value(if self.target.screen.is_some() { 10 } else { 8 });
        self.offset(label, after);
    }

    fn add3(&mut self, dst: i64, lhs: i64, rhs: i64) {
        self.alu3(dst, lhs, rhs, 0);
    }

    fn sub3(&mut self, dst: i64, lhs: i64, rhs: i64) {
        self.alu3(dst, lhs, rhs, 2);
    }

    fn mul3(&mut self, dst: i64, lhs: i64, rhs: i64) {
        self.alu3(dst, lhs, rhs, 1);
    }

    fn div3(&mut self, dst: i64, lhs: i64, rhs: i64) {
        self.alu3(dst, lhs, rhs, 3);
    }

    fn and3(&mut self, dst: i64, lhs: i64, rhs: i64) {
        self.alu3(dst, lhs, rhs, 4);
    }

    fn shr3(&mut self, dst: i64, lhs: i64, rhs: i64) {
        self.alu3(dst, lhs, rhs, 5);
    }

    fn alu_imm(&mut self, dst: i64, lhs: i64, value: i64, op: i64) {
        if lhs != 0 {
            self.mov(0, lhs);
        }
        self.imm(1, value);
        self.alu0(op, 1);
        if dst != 0 {
            self.mov(dst, 0);
        }
    }

    fn inc(&mut self, reg: i64) {
        self.alu_imm(reg, reg, 1, 0);
    }

    fn dec(&mut self, reg: i64) {
        self.alu_imm(reg, reg, 1, 2);
    }

    fn neg_reg(&mut self, reg: i64) {
        if reg == 0 {
            self.mov(1, 0);
        }
        self.imm(0, 0);
        self.alu0(2, if reg == 0 { 1 } else { reg });
        if reg != 0 {
            self.mov(reg, 0);
        }
    }

    fn jeq_const(&mut self, reg: i64, value: i64, label: &str) -> Result<(), String> {
        let not_equal = self.gen_label("neq");
        self.mov(0, reg);
        self.imm(1, value);
        self.alu(2);
        self.jc(0, &not_equal);
        self.imm(0, value);
        self.mov(1, reg);
        self.alu(2);
        self.jc(0, &not_equal);
        self.jmp(label);
        self.label(&not_equal)
    }

    fn jeq_small_const(&mut self, reg: i64, value: i64, label: &str) -> Result<(), String> {
        let not_equal = self.gen_label("small_neq");
        self.mov(0, reg);
        self.imm(1, value);
        self.alu(6);
        self.jc(0, &not_equal);
        self.jmp(label);
        self.label(&not_equal)
    }

    fn jeq_reg(&mut self, lhs: i64, rhs: i64, label: &str) -> Result<(), String> {
        let not_equal = self.gen_label("jeqr_not_equal");
        self.sub3(0, lhs, rhs);
        self.mov(1, 0);
        self.alu(1);
        self.jc(0, &not_equal);
        self.jmp(label);
        self.label(&not_equal)
    }

    fn jeq_small_reg(&mut self, lhs: i64, rhs: i64, label: &str) -> Result<(), String> {
        let not_equal = self.gen_label("jeqrs_not_equal");
        self.mov(0, lhs);
        self.mov(1, rhs);
        self.alu(6);
        self.jc(0, &not_equal);
        self.jmp(label);
        self.label(&not_equal)
    }

    fn load_packed4(
        &mut self,
        dst: i64,
        position: i64,
        address: i64,
        index: i64,
        _factor: i64,
        _quotient: i64,
    ) -> Result<(), String> {
        self.alu_imm(address, position, 4, 3);
        self.alu_imm(index, position, 3, 4);
        self.load(dst, address);
        self.alu_imm(index, index, 7, 1);
        self.shr3(dst, dst, index);
        self.alu_imm(dst, dst, 127, 4);
        Ok(())
    }

    fn load_packed8(
        &mut self,
        dst: i64,
        position: i64,
        address: i64,
        index: i64,
        _factor: i64,
        quotient: i64,
    ) -> Result<(), String> {
        self.alu_imm(address, position, 8, 3);
        self.alu_imm(index, position, 7, 4);
        self.load(dst, address);

        // The evaluator appears to apply 32-bit shift-count semantics even
        // though the language specifies counts through 63. Keep every shift
        // at 0..24 by selecting the low or high 32-bit half first.
        let high_label = self.gen_label("load8_high");
        let extract_label = self.gen_label("load8_extract");
        self.mov(quotient, dst);
        self.alu_imm(0, index, 3, 2);
        self.jc(0, &high_label);
        self.jmp(&extract_label);
        self.label(&high_label)?;
        self.alu_imm(quotient, quotient, 4_294_967_296, 3);
        self.alu_imm(index, index, 4, 2);
        self.label(&extract_label)?;
        self.alu_imm(index, index, 8, 1);
        self.shr3(dst, quotient, index);
        self.alu_imm(dst, dst, 255, 4);
        Ok(())
    }

    fn if_reg_gt_const<F>(&mut self, reg: i64, value: i64, mut body: F) -> Result<(), String>
    where
        F: FnMut(&mut Assembler) -> Result<(), String>,
    {
        let then_label = self.gen_label("gt_then");
        let end_label = self.gen_label("gt_end");
        self.mov(0, reg);
        self.imm(1, value);
        self.alu(2);
        self.jc(0, &then_label);
        self.jmp(&end_label);
        self.label(&then_label)?;
        body(self)?;
        self.label(&end_label)
    }

    fn emit_matmul(&mut self) -> Result<(), String> {
        let halt = "halt";
        self.read(2); // N
        self.read(3); // M
        self.read(4); // K

        self.mov(0, 2);
        self.mov(1, 3);
        self.alu(1);
        self.mov(5, 0); // remaining A cells
        self.imm(6, 0); // memory index

        self.label("read_a")?;
        self.jc(5, "read_a_body");
        self.jmp("read_b");
        self.label("read_a_body")?;
        self.read(7);
        self.store(6, 7);
        self.inc(6);
        self.dec(5);
        self.jmp("read_a");

        self.label("read_b")?;
        for t in 0..16 {
            self.if_reg_gt_const(3, t, |asm| {
                for j in 0..16 {
                    asm.if_reg_gt_const(4, j, |asm| {
                        asm.read(MATMUL_B_BASE + (t * 16 + j) as i64);
                        Ok(())
                    })?;
                }
                Ok(())
            })?;
        }

        self.label("output_c")?;
        for i in 0..16 {
            self.if_reg_gt_const(2, i, |asm| {
                for j in 0..16 {
                    asm.if_reg_gt_const(4, j, |asm| {
                        asm.imm(7, 0); // sum
                        for t in 0..16 {
                            asm.if_reg_gt_const(3, t, |asm| {
                                if i == 0 {
                                    asm.imm(8, t);
                                } else {
                                    asm.mov(0, 3);
                                    asm.imm(1, i);
                                    asm.alu(1);
                                    asm.imm(1, t);
                                    asm.alu(0);
                                    asm.mov(8, 0);
                                }
                                asm.load(9, 8);
                                asm.mov(0, 9);
                                asm.mov(1, MATMUL_B_BASE + (t * 16 + j) as i64);
                                asm.alu(1);
                                asm.mov(1, 7);
                                asm.alu(0);
                                asm.mov(7, 0);
                                Ok(())
                            })?;
                        }
                        asm.write(7);
                        Ok(())
                    })?;
                }
                Ok(())
            })?;
        }
        self.label(halt)?;
        self.jmp(halt);
        Ok(())
    }

    fn emit_tokens(&mut self, toks: &[String]) -> Result<(), String> {
        if let [op, operand] = toks {
            if let Some((alu, immediate)) = alu0_code(op) {
                if immediate {
                    self.imm(1, parse_int(operand)?);
                    self.alu0(alu, 1);
                } else {
                    self.alu0(alu, parse_reg(operand)?);
                }
                return Ok(());
            }
        }
        match toks {
            [op, dst, src] if op == "mov" => self.mov(parse_reg(dst)?, parse_reg(src)?),
            [op, addr, src] if op == "store" => self.store(parse_reg(addr)?, parse_reg(src)?),
            [op, dst, addr] if op == "load" => self.load(parse_reg(dst)?, parse_reg(addr)?),
            [op, dst, value] if op == "imm" => self.imm(parse_reg(dst)?, parse_int(value)?),
            [op, dst] if op == "read" => self.read(parse_reg(dst)?),
            [op, src] if op == "write" => {
                if self.target.screen.is_some() {
                    return Err(
                        "write is unavailable for `.screen`; use screen_addr/screen_data/screen_swap"
                            .to_string(),
                    );
                }
                self.write(parse_reg(src)?)
            }
            [op, src] if op == "screen_swap" || op == "screen_commit" => {
                self.screen_swap(parse_reg(src)?)?
            }
            [op, src] if op == "screen_addr" => self.screen_addr(parse_reg(src)?)?,
            [op, src] if op == "screen_data" => self.screen_data(parse_reg(src)?)?,
            [op, alu] if op == "alu" => self.alu(alu_code(alu)?),
            [op, cond, label] if op == "jc" || op == "jpos" => self.jc(parse_reg(cond)?, label),
            [op, label] if op == "jmp" => self.jmp(label),
            [op, dst, lhs, rhs] if op == "add" => {
                self.add3(parse_reg(dst)?, parse_reg(lhs)?, parse_reg(rhs)?)
            }
            [op, dst, lhs, rhs] if op == "sub" => {
                self.sub3(parse_reg(dst)?, parse_reg(lhs)?, parse_reg(rhs)?)
            }
            [op, dst, lhs, rhs] if op == "mul" => {
                self.mul3(parse_reg(dst)?, parse_reg(lhs)?, parse_reg(rhs)?)
            }
            [op, dst, lhs, rhs] if op == "div" => {
                self.div3(parse_reg(dst)?, parse_reg(lhs)?, parse_reg(rhs)?)
            }
            [op, dst, lhs, rhs] if op == "and" => {
                self.and3(parse_reg(dst)?, parse_reg(lhs)?, parse_reg(rhs)?)
            }
            [op, dst, lhs, rhs] if op == "shr" => {
                self.shr3(parse_reg(dst)?, parse_reg(lhs)?, parse_reg(rhs)?)
            }
            [op, dst, lhs, value] if op == "addi" => {
                self.alu_imm(parse_reg(dst)?, parse_reg(lhs)?, parse_int(value)?, 0)
            }
            [op, dst, lhs, value] if op == "muli" => {
                self.alu_imm(parse_reg(dst)?, parse_reg(lhs)?, parse_int(value)?, 1)
            }
            [op, dst, lhs, value] if op == "subi" => {
                self.alu_imm(parse_reg(dst)?, parse_reg(lhs)?, parse_int(value)?, 2)
            }
            [op, dst, lhs, value] if op == "divi" => {
                self.alu_imm(parse_reg(dst)?, parse_reg(lhs)?, parse_int(value)?, 3)
            }
            [op, reg] if op == "neg" => self.neg_reg(parse_reg(reg)?),
            [op, reg] if op == "inc" => self.inc(parse_reg(reg)?),
            [op, reg] if op == "dec" => self.dec(parse_reg(reg)?),
            [op, reg, value, label] if op == "jeq" => {
                self.jeq_const(parse_reg(reg)?, parse_int(value)?, label)?
            }
            [op, reg, value, label] if op == "jeqs" => {
                self.jeq_small_const(parse_reg(reg)?, parse_int(value)?, label)?
            }
            [op, lhs, rhs, label] if op == "jeqr" => {
                self.jeq_reg(parse_reg(lhs)?, parse_reg(rhs)?, label)?
            }
            [op, lhs, rhs, label] if op == "jeqrs" => {
                self.jeq_small_reg(parse_reg(lhs)?, parse_reg(rhs)?, label)?
            }
            [op, dst, position, address, index, factor, quotient] if op == "load4" => self
                .load_packed4(
                    parse_reg(dst)?,
                    parse_reg(position)?,
                    parse_reg(address)?,
                    parse_reg(index)?,
                    parse_reg(factor)?,
                    parse_reg(quotient)?,
                )?,
            [op, dst, position, address, index, factor, quotient] if op == "load8" => self
                .load_packed8(
                    parse_reg(dst)?,
                    parse_reg(position)?,
                    parse_reg(address)?,
                    parse_reg(index)?,
                    parse_reg(factor)?,
                    parse_reg(quotient)?,
                )?,
            [op] if op == "matmul" => self.emit_matmul()?,
            [] => {}
            _ => return Err(format!("unknown instruction `{}`", toks.join(" "))),
        }
        Ok(())
    }

    fn resolve(self) -> Result<Program, String> {
        let total = self.words.len();
        if total == 0 {
            return Err("program is empty".to_string());
        }
        let mut out = Vec::with_capacity(total);
        for word in self.words {
            match word {
                Word::Value(value) => out.push(value),
                Word::Offset { label, after } => {
                    let target = *self
                        .labels
                        .get(&label)
                        .ok_or_else(|| format!("unknown label `{label}`"))?;
                    let offset = (target + total - (after % total)) % total;
                    out.push(offset as i64);
                }
            }
        }
        Ok(Program {
            words: out,
            register_count: self.max_register + 1,
            uses_memory: self.uses_memory,
        })
    }
}

fn assemble(src: &str, target: Target) -> Result<Program, String> {
    let mut asm = Assembler::new(target);
    for (idx, raw) in src.lines().enumerate() {
        let line_no = idx + 1;
        let mut line = strip_comment(raw).trim();
        while let Some((label, rest)) = line.split_once(':') {
            let label = label.trim();
            if label.is_empty() || label.split_whitespace().count() != 1 {
                return Err(format!("line {line_no}: bad label"));
            }
            asm.label(label)
                .map_err(|err| format!("line {line_no}: {err}"))?;
            line = rest.trim();
            if line.is_empty() {
                break;
            }
        }
        let toks = tokenize(line);
        if parse_directive(&toks)
            .map_err(|err| format!("line {line_no}: {err}"))?
            .is_some()
        {
            continue;
        }
        asm.emit_tokens(&toks)
            .map_err(|err| format!("line {line_no}: {err}"))?;
    }
    asm.resolve()
}

fn build(src: &str) -> Result<Build, String> {
    let expanded = expand_repeats(src)?;
    let mut memory_size = 8usize;
    let mut memory_pipe_cells = memory_size * 2;
    let mut target = Target::default();
    let mut program_kind = ProgramKind::Generic;
    for (idx, raw) in expanded.lines().enumerate() {
        let line_no = idx + 1;
        let toks = tokenize(strip_comment(raw).trim());
        if matches!(
            toks.as_slice(),
            [name] if name == ".screen" || name == "screen"
        ) {
            program_kind = ProgramKind::Plotter;
        }
        if let Some(directive) =
            parse_directive(&toks).map_err(|err| format!("line {line_no}: {err}"))?
        {
            match directive {
                Directive::Memory { size, pipe_cells } => {
                    memory_size = size;
                    memory_pipe_cells = pipe_cells;
                }
                Directive::Screen(screen) => target.screen = Some(screen),
                Directive::Kind(kind) => program_kind = kind,
            }
        }
    }
    let program = assemble(&expanded, target)?;
    let register_count = program.register_count;
    Ok(Build {
        memory_size: if program.uses_memory { memory_size } else { 0 },
        memory_pipe_cells: if program.uses_memory {
            memory_pipe_cells
        } else {
            0
        },
        program,
        register_count,
        screen: target.screen,
        program_kind,
    })
}

pub fn compile_screen_source(source: &str) -> Result<(Vec<i64>, usize, usize), String> {
    let build = build(source)?;
    let screen = build
        .screen
        .ok_or_else(|| "visual simulator requires a `.screen` declaration".to_string())?;
    Ok((build.program.words, screen.width, screen.height))
}

fn literal(value: i64) -> String {
    if (0..=9).contains(&value) {
        value.to_string()
    } else if value >= 0 {
        format!("`{value}`")
    } else {
        format!("`{}`N", value.saturating_abs())
    }
}

fn reverse_literal_text(text: &str) -> String {
    let mut chars: Vec<char> = text.chars().collect();
    chars.reverse();
    chars.into_iter().collect()
}

fn encode_program_tokens(words: &[i64]) -> Vec<String> {
    const BEAM_WIDTH: usize = 128;

    struct Node {
        a: i64,
        b: i64,
        cost: usize,
        parent: usize,
        token: String,
    }

    struct Candidate {
        a: i64,
        b: i64,
        cost: usize,
        parent: usize,
        token: String,
    }

    let mut nodes = vec![Node {
        a: 0,
        b: 0,
        cost: 0,
        parent: usize::MAX,
        token: String::new(),
    }];
    let mut beam = vec![0usize];

    for &word in words {
        let mut candidates: HashMap<(i64, i64), Candidate> = HashMap::new();
        for &parent in &beam {
            let node = &nodes[parent];
            let mut offer = |a: i64, b: i64, token: String| {
                let cost = node.cost + token.len();
                let key = (a, b);
                if candidates.get(&key).is_none_or(|old| cost < old.cost) {
                    candidates.insert(
                        key,
                        Candidate {
                            a,
                            b,
                            cost,
                            parent,
                            token,
                        },
                    );
                }
            };

            offer(word, node.b, format!("{}s", literal(word)));
            offer(word, word, format!("{}Ms", literal(word)));
            if word == node.a {
                offer(node.a, node.b, "s".to_string());
            }
            if word == node.b {
                offer(node.b, node.a, "Ws".to_string());
            }
            if word == node.a.wrapping_add(node.b) {
                offer(word, node.b, "+s".to_string());
            }
            if word == node.a.wrapping_sub(node.b) {
                offer(word, node.b, "-s".to_string());
            }
            if word == node.a.wrapping_mul(node.b) {
                offer(word, node.b, "*s".to_string());
            }
            if word == node.a.wrapping_neg() {
                offer(word, node.b, "Ns".to_string());
            }
            if word == node.a.wrapping_add(node.b) {
                offer(word, node.a, "W+s".to_string());
            }
            if word == node.b.wrapping_sub(node.a) {
                offer(word, node.a, "W-s".to_string());
            }
            if node.b != 0 && !(node.a == i64::MIN && node.b == -1) {
                let quotient = node.a.div_euclid(node.b);
                if word == quotient {
                    offer(quotient, node.a.rem_euclid(node.b), "/s".to_string());
                }
            }
        }

        let mut next: Vec<Candidate> = candidates.into_values().collect();
        next.sort_unstable_by(|left, right| {
            (left.cost, left.a, left.b, &left.token).cmp(&(
                right.cost,
                right.a,
                right.b,
                &right.token,
            ))
        });
        next.truncate(BEAM_WIDTH);
        beam.clear();
        for candidate in next {
            let index = nodes.len();
            nodes.push(Node {
                a: candidate.a,
                b: candidate.b,
                cost: candidate.cost,
                parent: candidate.parent,
                token: candidate.token,
            });
            beam.push(index);
        }
    }

    let Some(&best) = beam
        .iter()
        .min_by_key(|&&index| (nodes[index].cost, nodes[index].a, nodes[index].b))
    else {
        return Vec::new();
    };
    let mut tokens = Vec::with_capacity(words.len());
    let mut index = best;
    while nodes[index].parent != usize::MAX {
        tokens.push(nodes[index].token.clone());
        index = nodes[index].parent;
    }
    tokens.reverse();
    if let Some(first) = tokens.first_mut() {
        first.insert_str(0, "0M");
    }
    tokens
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum CodeOrientation {
    Horizontal,
    Vertical,
}

fn place_tokens_in_sweeps(
    tokens: &[String],
    grid: &mut [Vec<char>],
    sweeps: &[Vec<(usize, usize)>],
    orthogonal_size: usize,
    orthogonal_index: impl Fn(usize, usize) -> usize,
) -> bool {
    let mut token_idx = 0usize;
    let mut quote_parity = vec![false; orthogonal_size];
    for slots in sweeps {
        let mut i = 0usize;
        while token_idx < tokens.len() {
            let chars: Vec<char> = tokens[token_idx].chars().collect();
            let max_shift = if chars.contains(&'`') { 8 } else { 0 };
            let mut best: Option<(usize, usize, Vec<(usize, usize, char)>, Vec<bool>)> = None;
            for start_i in i..=i.saturating_add(max_shift).min(slots.len()) {
                let mut next_i = start_i;
                let mut placements = Vec::with_capacity(chars.len());
                let mut next_quote_parity = quote_parity.clone();
                let mut fits = true;
                for &ch in &chars {
                    let mut placed = false;
                    while next_i < slots.len() {
                        let (x, y) = slots[next_i];
                        let coordinate = orthogonal_index(x, y);
                        let safe_inside_literal = ch.is_ascii_digit() || ch == ' ' || ch == '`';
                        if safe_inside_literal || !next_quote_parity[coordinate] {
                            placements.push((x, y, ch));
                            if ch == '`' {
                                next_quote_parity[coordinate] = !next_quote_parity[coordinate];
                            }
                            next_i += 1;
                            placed = true;
                            break;
                        }
                        next_i += 1;
                    }
                    if !placed {
                        fits = false;
                        break;
                    }
                }
                if fits {
                    let open_quotes = next_quote_parity.iter().filter(|open| **open).count();
                    let score = next_i + 4 * open_quotes;
                    if best
                        .as_ref()
                        .is_none_or(|(best_score, best_end, _, _)| {
                            (score, next_i) < (*best_score, *best_end)
                        })
                    {
                        best = Some((score, next_i, placements, next_quote_parity));
                    }
                }
            }
            let Some((_, next_i, placements, next_quote_parity)) = best else {
                break;
            };
            for (x, y, ch) in placements {
                grid[y][x] = ch;
            }
            quote_parity = next_quote_parity;
            i = next_i;
            token_idx += 1;
        }
    }
    token_idx == tokens.len()
}

fn layout_horizontal_program_grid(tokens: &[String], w: usize, h: usize) -> Option<Vec<Vec<char>>> {
    if w < 6 || h < 2 {
        return None;
    }
    let mut grid = vec![vec![' '; w]; h];

    grid[0][0] = '>';
    grid[0][1] = '@';
    for y in 1..h - 1 {
        grid[y][0] = ' ';
    }
    grid[h - 1][0] = '^';

    for y in 0..h - 1 {
        if y % 2 == 0 {
            grid[y][w - 1] = 'v';
            if y > 0 {
                grid[y][1] = '>';
            }
        } else {
            grid[y][w - 1] = '<';
            grid[y][1] = 'v';
        }
    }
    grid[h - 1][w - 1] = '<';

    let sweeps: Vec<Vec<(usize, usize)>> = (0..h).map(|y| row_slots(w, h, y)).collect();
    if !place_tokens_in_sweeps(tokens, &mut grid, &sweeps, w, |x, _| x) {
        return None;
    }
    Some(grid)
}

fn layout_vertical_program_grid(tokens: &[String], w: usize, h: usize) -> Option<Vec<Vec<char>>> {
    if w < 5 || w % 2 == 0 || h < 4 {
        return None;
    }
    let mut grid = vec![vec![' '; w]; h];

    // The top row returns from the final upward sweep to the spawn point.
    // The man starts east, enters the first column, and then snakes vertically.
    grid[0][1] = 'v';
    grid[0][w - 1] = '<';
    grid[1][0] = '@';
    for x in 1..w {
        if x % 2 == 1 {
            grid[1][x] = 'v';
            grid[h - 1][x] = '>';
        } else {
            grid[h - 1][x] = '^';
            grid[1][x] = if x + 1 == w { '^' } else { '>' };
        }
    }

    let sweeps: Vec<Vec<(usize, usize)>> = (1..w)
        .map(|x| {
            if x % 2 == 1 {
                (2..h - 1).map(|y| (x, y)).collect()
            } else {
                (2..h - 1).rev().map(|y| (x, y)).collect()
            }
        })
        .collect();
    if !place_tokens_in_sweeps(tokens, &mut grid, &sweeps, h, |_, y| y) {
        return None;
    }
    Some(grid)
}

fn layout_oriented_program_grid(
    tokens: &[String],
    w: usize,
    h: usize,
    orientation: CodeOrientation,
) -> Option<Vec<Vec<char>>> {
    match orientation {
        CodeOrientation::Horizontal => layout_horizontal_program_grid(tokens, w, h),
        CodeOrientation::Vertical => layout_vertical_program_grid(tokens, w, h),
    }
}

fn valid_numeric_literals(grid: &[Vec<char>]) -> bool {
    fn valid_spelling(chars: impl Iterator<Item = char>) -> bool {
        let spelling: String = chars.filter(|ch| *ch != ' ').collect();
        if spelling.is_empty() {
            return true;
        }
        spelling.parse::<i64>().is_ok()
            && spelling
                .chars()
                .rev()
                .collect::<String>()
                .parse::<i64>()
                .is_ok()
    }

    let h = grid.len();
    let w = grid.iter().map(Vec::len).max().unwrap_or(0);
    for y in 0..h {
        let mut xs = Vec::new();
        for x in 0..grid[y].len() {
            if grid[y][x] == '`' {
                xs.push(x);
            }
        }
        for pair in xs.chunks(2) {
            if pair.len() == 2 {
                for x in pair[0] + 1..pair[1] {
                    let ch = grid[y][x];
                    if !ch.is_ascii_digit() && ch != ' ' {
                        return false;
                    }
                }
                if !valid_spelling((pair[0] + 1..pair[1]).map(|x| grid[y][x])) {
                    return false;
                }
            }
        }
    }
    for x in 0..w {
        let mut ys = Vec::new();
        for y in 0..h {
            if x < grid[y].len() && grid[y][x] == '`' {
                ys.push(y);
            }
        }
        for pair in ys.chunks(2) {
            if pair.len() == 2 {
                for y in pair[0] + 1..pair[1] {
                    let ch = grid[y][x];
                    if !ch.is_ascii_digit() && ch != ' ' {
                        return false;
                    }
                }
                if !valid_spelling((pair[0] + 1..pair[1]).map(|y| {
                    if x < grid[y].len() {
                        grid[y][x]
                    } else {
                        ' '
                    }
                })) {
                    return false;
                }
            }
        }
    }
    true
}

fn program_grid_loops(grid: &[Vec<char>]) -> bool {
    let height = grid.len();
    let width = grid.first().map(Vec::len).unwrap_or(0);
    let Some((mut x, mut y)) = grid.iter().enumerate().find_map(|(y, row)| {
        row.iter()
            .position(|ch| *ch == '@')
            .map(|x| (x as isize, y as isize))
    }) else {
        return false;
    };
    let (mut dx, mut dy) = (1isize, 0isize);
    let mut seen = HashMap::new();
    for _ in 0..width.saturating_mul(height).saturating_mul(4).max(1) {
        if x < 0 || y < 0 || x >= width as isize || y >= height as isize {
            return false;
        }
        let state = (x, y, dx, dy);
        if seen.insert(state, true).is_some() {
            return true;
        }
        match grid[y as usize][x as usize] {
            '>' => (dx, dy) = (1, 0),
            '<' => (dx, dy) = (-1, 0),
            'v' | 'V' => (dx, dy) = (0, 1),
            '^' => (dx, dy) = (0, -1),
            _ => {}
        }
        x += dx;
        y += dy;
    }
    false
}

fn room_grid(interior: &[Vec<char>]) -> Vec<Vec<char>> {
    let height = interior.len();
    let width = interior.first().map(Vec::len).unwrap_or(0);
    let mut room = vec![vec![' '; width + 2]; height + 2];
    room[0][0] = '+';
    room[0][width + 1] = '+';
    room[height + 1][0] = '+';
    room[height + 1][width + 1] = '+';
    for x in 1..=width {
        room[0][x] = '-';
        room[height + 1][x] = '-';
    }
    for y in 1..=height {
        room[y][0] = '|';
        room[y][width + 1] = '|';
        room[y][1..=width].copy_from_slice(&interior[y - 1]);
    }
    room
}

fn row_slots(w: usize, h: usize, y: usize) -> Vec<(usize, usize)> {
    if y == 0 {
        (2..w - 1).map(|x| (x, y)).collect()
    } else if y + 1 == h {
        (1..w - 1).rev().map(|x| (x, y)).collect()
    } else if y % 2 == 1 {
        (2..w - 1).rev().map(|x| (x, y)).collect()
    } else {
        (2..w - 1).map(|x| (x, y)).collect()
    }
}

fn string_grid(src: &str) -> Vec<Vec<char>> {
    let lines: Vec<&str> = src.lines().collect();
    let width = lines.iter().map(|line| line.len()).max().unwrap_or(0);
    lines
        .into_iter()
        .map(|line| {
            let mut row: Vec<char> = line.chars().collect();
            row.resize(width, ' ');
            row
        })
        .collect()
}

fn grid_to_string(grid: &[Vec<char>]) -> String {
    let mut lines: Vec<String> = grid
        .iter()
        .map(|row| {
            let mut s: String = row.iter().collect();
            while s.ends_with(' ') {
                s.pop();
            }
            s
        })
        .collect();
    while lines.last().is_some_and(|line| line.is_empty()) {
        lines.pop();
    }
    lines.join("\n") + "\n"
}

#[derive(Clone)]
struct Canvas {
    grid: Vec<Vec<char>>,
}

impl Canvas {
    fn new(width: usize, height: usize) -> Self {
        Self {
            grid: vec![vec![' '; width]; height],
        }
    }

    fn put(&mut self, x: usize, y: usize, ch: char) -> Result<(), String> {
        if ch == ' ' {
            return Ok(());
        }
        let cell = &mut self.grid[y][x];
        if *cell != ' ' && *cell != ch {
            return Err(format!(
                "layout collision at {x},{y}: `{}` vs `{ch}`",
                *cell
            ));
        }
        *cell = ch;
        Ok(())
    }

    fn paste(&mut self, x0: usize, y0: usize, src: &[Vec<char>]) -> Result<(), String> {
        for (y, row) in src.iter().enumerate() {
            for (x, &ch) in row.iter().enumerate() {
                self.put(x0 + x, y0 + y, ch)?;
            }
        }
        Ok(())
    }
}

fn draw_room(
    canvas: &mut Canvas,
    x: usize,
    y: usize,
    interior_width: usize,
    interior_height: usize,
) -> Result<(), String> {
    let right = x + interior_width + 1;
    let bottom = y + interior_height + 1;
    canvas.put(x, y, '+')?;
    canvas.put(right, y, '+')?;
    canvas.put(x, bottom, '+')?;
    canvas.put(right, bottom, '+')?;
    for px in x + 1..right {
        canvas.put(px, y, '-')?;
        canvas.put(px, bottom, '-')?;
    }
    for py in y + 1..bottom {
        canvas.put(x, py, '|')?;
        canvas.put(right, py, '|')?;
    }
    Ok(())
}

fn put_text(canvas: &mut Canvas, x: usize, y: usize, text: &str) -> Result<(), String> {
    for (offset, ch) in text.chars().enumerate() {
        canvas.put(x + offset, y, ch)?;
    }
    Ok(())
}

fn rotate_ccw(src: &[Vec<char>]) -> Vec<Vec<char>> {
    let height = src.len();
    let width = src.first().map(Vec::len).unwrap_or(0);
    let mut rotated = vec![vec![' '; height]; width];
    for (y, row) in src.iter().enumerate() {
        for (x, &ch) in row.iter().enumerate() {
            let rotated_ch = match ch {
                '>' => '^',
                '^' => '<',
                '<' => 'v',
                'v' | 'V' => '>',
                '-' => '|',
                '|' => '-',
                _ => ch,
            };
            rotated[width - 1 - x][y] = rotated_ch;
        }
    }
    rotated
}

fn make_horizontal_repeater_register_bank(register_count: usize) -> Result<Vec<Vec<char>>, String> {
    const BUS_Y: usize = 7;
    const BUS_HEIGHT: usize = 9;
    const STATION_START: usize = 13;
    const STATION_PITCH: usize = 5;
    let bus_width = 13 + 5 * register_count;

    let mut canvas = Canvas::new(bus_width + 2, BUS_Y + BUS_HEIGHT + 2);
    draw_room(&mut canvas, 0, BUS_Y, bus_width, BUS_HEIGHT)?;
    let ix = 1;
    let iy = BUS_Y + 1;

    canvas.put(ix, iy + 3, '>')?;
    canvas.put(ix + 1, iy + 3, '@')?;
    put_text(&mut canvas, ix + 2, iy + 3, "rbrX")?;
    canvas.put(ix + 9, iy + 3, '>')?;
    canvas.put(ix + 5, iy + 4, '>')?;
    put_text(&mut canvas, ix + 6, iy + 4, "rM1")?;
    canvas.put(ix + 9, iy + 4, '^')?;

    canvas.put(ix, iy, 'v')?;
    canvas.put(ix + 5, iy, 's')?;
    canvas.put(ix, iy + 8, '^')?;

    for address in 0..register_count {
        let base = STATION_START + address * STATION_PITCH;
        canvas.put(ix + base, iy + 3, 'd')?;
        canvas.put(ix + base, iy + 4, 'm')?;
        canvas.put(ix + base, iy + 5, '>')?;
        canvas.put(ix + base + 3, iy + 5, '^')?;
        canvas.put(ix + base + 3, iy + 3, '>')?;

        canvas.put(ix + base + 1, iy + 3, 'X')?;
        canvas.put(ix + base + 2, iy + 3, '^')?;
        canvas.put(ix + base + 2, iy + 2, 'r')?;
        canvas.put(ix + base + 2, iy + 1, 's')?;
        canvas.put(ix + base + 2, iy, '<')?;

        canvas.put(ix + base + 1, iy + 4, 'r')?;
        canvas.put(ix + base + 1, iy + 6, 'W')?;
        canvas.put(ix + base + 1, iy + 7, 's')?;
        put_text(&mut canvas, ix + base, iy + 8, "<<<<")?;

        let cell_x = base + 1;
        draw_room(&mut canvas, cell_x, 0, 3, 3)?;
        put_text(&mut canvas, cell_x + 1, 1, ">@v")?;
        put_text(&mut canvas, cell_x + 1, 2, "^ s")?;
        put_text(&mut canvas, cell_x + 1, 3, "U<<")?;
        for y in 5..BUS_Y {
            canvas.put(cell_x + 1, y, '^')?;
            canvas.put(cell_x + 3, y, 'v')?;
        }
    }

    Ok(canvas.grid)
}

fn make_compact_vertical_register_bank(register_count: usize) -> Result<Vec<Vec<char>>, String> {
    let horizontal = make_horizontal_repeater_register_bank(register_count)?;
    let rotated = rotate_ccw(&horizontal);
    const CONTROLLER: [&str; 9] = [
        "|         |",
        "|s  ^ <   |",
        "|     1   |",
        "|     M   |",
        "|     r   |",
        "|   ^ X<  |",
        "|>@>rbr^  |",
        "|  ^     <|",
        "+---------+",
    ];
    let mut compact = Vec::with_capacity(4 * register_count + 10);

    compact.push(rotated[0].clone());
    for address in 0..register_count {
        let station_top = 2 + address * 5;
        compact.extend_from_slice(&rotated[station_top..station_top + 4]);
    }
    compact.extend(CONTROLLER.iter().map(|row| row.chars().collect::<Vec<_>>()));

    // Preserve the counter-clockwise selector, with its controller at the
    // bottom, and attach the compact cells to its right.
    let mut bank = vec![vec![' '; 18]; compact.len()];
    for (y, row) in compact.iter().enumerate() {
        let selector = if row.len() == 11 { row } else { &row[7..18] };
        bank[y][..11].copy_from_slice(selector);
    }

    // One 3x2 repeater per four-row selector station, exactly as in
    // memory_banks_0: send the initial zero, then receive its replacement.
    for address in 0..register_count {
        let top = 1 + address * 4;
        for (x, ch) in "+---+".chars().enumerate() {
            bank[top][13 + x] = ch;
            bank[top + 3][13 + x] = ch;
        }
        bank[top + 1][11] = '>';
        bank[top + 1][12] = '>';
        for (x, ch) in "|U@v|".chars().enumerate() {
            bank[top + 1][13 + x] = ch;
        }
        bank[top + 2][11] = '<';
        bank[top + 2][12] = '<';
        for (x, ch) in "|^s<|".chars().enumerate() {
            bank[top + 2][13 + x] = ch;
        }
    }

    Ok(bank)
}

fn make_two_lane_register_selector(register_count: usize) -> Result<Vec<Vec<char>>, String> {
    if register_count < 2 || register_count % 2 != 0 {
        return Err("two-lane register selector requires a positive even count".to_string());
    }

    const HEIGHT: usize = 19;
    const STATION_START: usize = 16;
    const STATION_PITCH: usize = 4;
    let lanes = register_count / 2;
    let width = STATION_START + STATION_PITCH * lanes;
    let mut horizontal = Canvas::new(width, HEIGHT);

    horizontal.put(0, 0, 'v')?;
    for y in 1..9 {
        horizontal.put(0, y, 'v')?;
    }
    horizontal.put(0, 9, '>')?;
    for y in 10..HEIGHT - 1 {
        horizontal.put(0, y, '^')?;
    }
    horizontal.put(0, HEIGHT - 1, '^')?;

    horizontal.put(8, 8, ']')?;
    horizontal.put(8, 9, 'x')?;
    horizontal.put(8, 3, '>')?;
    horizontal.put(9, 3, 'X')?;

    horizontal.put(8, 10, ']')?;
    horizontal.put(8, 15, '>')?;
    horizontal.put(9, 15, 'X')?;

    horizontal.put(9, 4, 'v')?;
    horizontal.put(9, 5, 'v')?;
    horizontal.put(9, 6, '<')?;
    horizontal.put(3, 6, 'v')?;
    put_text(&mut horizontal, 3, 7, ">rM1")?;
    for y in 4..=7 {
        horizontal.put(15, y, '^')?;
    }
    horizontal.put(15, 3, '>')?;

    horizontal.put(9, 16, '<')?;
    horizontal.put(3, 16, '^')?;
    for y in 12..16 {
        horizontal.put(3, y, '^')?;
    }
    put_text(&mut horizontal, 3, 11, ">rM1N")?;
    for y in 11..15 {
        horizontal.put(15, y, 'v')?;
    }
    horizontal.put(15, 15, '>')?;

    for lane in 0..lanes {
        let base = STATION_START + lane * STATION_PITCH;

        horizontal.put(base, 3, 'd')?;
        horizontal.put(base + 1, 3, 'X')?;
        horizontal.put(base + 2, 3, '^')?;
        horizontal.put(base + 3, 3, '>')?;
        horizontal.put(base, 4, 'm')?;
        horizontal.put(base + 1, 4, 'r')?;
        horizontal.put(base, 5, '>')?;
        horizontal.put(base + 3, 5, '^')?;
        horizontal.put(base + 1, 6, 'W')?;
        horizontal.put(base + 1, 7, 's')?;
        put_text(&mut horizontal, base, 8, "<<<<")?;
        horizontal.put(base + 2, 2, 'r')?;
        horizontal.put(base + 2, 1, 's')?;
        horizontal.put(base + 2, 0, '<')?;

        horizontal.put(base, 15, 'a')?;
        horizontal.put(base + 1, 15, 'X')?;
        horizontal.put(base + 2, 15, 'v')?;
        horizontal.put(base + 3, 15, '>')?;
        horizontal.put(base, 14, 'm')?;
        horizontal.put(base + 1, 14, 'r')?;
        horizontal.put(base, 13, '>')?;
        horizontal.put(base + 3, 13, 'v')?;
        horizontal.put(base + 1, 12, 'W')?;
        horizontal.put(base + 1, 11, 's')?;
        put_text(&mut horizontal, base, 10, "<<<<")?;
        horizontal.put(base + 2, 16, 'r')?;
        horizontal.put(base + 2, 17, 's')?;
        horizontal.put(base + 2, 18, '<')?;
    }

    let mut vertical = rotate_ccw(&horizontal.grid);

    // A request can activate only one write path. Right-lane writes continue
    // west through the empty center column and join the left return trunk, so
    // a second down-pipe through every station is unnecessary.
    for station in 0..lanes {
        for row in 4 * station..4 * station + 4 {
            vertical[row][10] = ' ';
        }
    }

    let bottom = vertical.len() - 1;
    let controller_y = bottom - 1;
    let write_return_y = bottom - 2;
    let lower_bypass_y = bottom - 3;
    let parity_y = bottom - 8;

    for x in 0..HEIGHT {
        vertical[write_return_y][x] = ' ';
        vertical[controller_y][x] = ' ';
        vertical[bottom][x] = ' ';
    }
    for row in vertical
        .iter_mut()
        .take(lower_bypass_y + 1)
        .skip(parity_y + 1)
    {
        row[9] = ' ';
    }
    vertical[lower_bypass_y][2] = 'v';
    vertical[lower_bypass_y][8] = 'v';
    vertical[lower_bypass_y][10] = '<';
    vertical[write_return_y][2] = 'v';
    vertical[write_return_y][8] = '<';
    vertical[write_return_y][9] = '^';
    vertical[write_return_y][10] = '^';
    for (offset, ch) in ">s>@rbrM>^v".chars().enumerate() {
        vertical[controller_y][offset] = ch;
    }
    vertical[controller_y][18] = '<';
    vertical[bottom][0] = '^';
    vertical[bottom][10] = '<';

    // Rotation leaves five unused rows between the register stations and
    // controller. Removing them preserves every path while shortening both
    // request and response trips.
    let gap_start = 4 * lanes + 1;
    vertical.drain(gap_start..gap_start + 5);

    // The merged write return leaves two empty columns through every station.
    // Remove them and use a compact controller that keeps the right read
    // response on the outer column, separate from the right write setup.
    for row in &mut vertical {
        row.drain(9..11);
    }
    let compact_tail = [
        "   X>>v      Xv  ",
        "   ^    ]x]  ^   ",
        "           N     ",
        "       1   1     ",
        "       M   M     ",
        "       r   r     ",
        "  v   >^v <^<<< v",
        "  v     <^^      ",
        ">s>@rbrM>^v     <",
        "^         <      ",
    ];
    let tail_start = vertical.len() - compact_tail.len();
    for (row, text) in vertical[tail_start..].iter_mut().zip(compact_tail) {
        *row = text.chars().collect();
    }

    Ok(vertical)
}

fn make_two_lane_register_bank(register_count: usize) -> Result<Vec<Vec<char>>, String> {
    let physical_count = register_count + register_count % 2;
    let selector = make_two_lane_register_selector(physical_count)?;
    let selector_height = selector.len();
    const SELECTOR_LEFT: usize = 8;
    const SELECTOR_WIDTH: usize = 17;
    const BANK_WIDTH: usize = 34;
    let mut bank = Canvas::new(BANK_WIDTH, selector_height + 2);

    draw_room(&mut bank, SELECTOR_LEFT, 0, SELECTOR_WIDTH, selector_height)?;
    bank.paste(SELECTOR_LEFT + 1, 1, &selector)?;

    let lanes = physical_count / 2;
    for lane in 0..lanes {
        // Even registers use a right-facing repeater on the selector's left.
        // It sends the initial zero before waiting for its replacement.
        let even_output_offset = 4 * (lanes - lane - 1);
        draw_room(&mut bank, 0, even_output_offset, 4, 2)?;
        put_text(&mut bank, 1, even_output_offset + 1, ">@sv")?;
        put_text(&mut bank, 1, even_output_offset + 2, "^<U<")?;
        bank.put(6, even_output_offset + 1, '>')?;
        bank.put(7, even_output_offset + 1, '>')?;
        bank.put(6, even_output_offset + 2, '<')?;
        bank.put(7, even_output_offset + 2, '<')?;

        // Odd registers retain the standard left-facing repeater.
        let odd_input_offset = even_output_offset;
        draw_room(&mut bank, 29, odd_input_offset, 3, 2)?;
        put_text(&mut bank, 30, odd_input_offset + 1, "U@v")?;
        put_text(&mut bank, 30, odd_input_offset + 2, "^s<")?;
        bank.put(27, odd_input_offset + 1, '>')?;
        bank.put(28, odd_input_offset + 1, '>')?;
        bank.put(27, odd_input_offset + 2, '<')?;
        bank.put(28, odd_input_offset + 2, '<')?;
    }

    Ok(bank.grid)
}

fn set_literal_before(
    row: &mut [char],
    marker: &str,
    nth: usize,
    value: i64,
) -> Result<(), String> {
    set_literal_before_with(row, marker, nth, &literal(value))
}

fn set_reversed_literal_before(
    row: &mut [char],
    marker: &str,
    nth: usize,
    value: i64,
) -> Result<(), String> {
    set_literal_before_with(row, marker, nth, &reverse_literal_text(&literal(value)))
}

fn set_literal_before_with(
    row: &mut [char],
    marker: &str,
    nth: usize,
    lit: &str,
) -> Result<(), String> {
    let marker_chars: Vec<char> = marker.chars().collect();
    if lit.len() > 5 {
        return Err(format!("template capacity literal `{lit}` is too wide"));
    }
    let mut seen = 0usize;
    for x in 4..=row.len().saturating_sub(marker_chars.len()) {
        if row[x..x + marker_chars.len()] == marker_chars[..] {
            if seen == nth {
                let slot_width = lit.len().max(4);
                if x < slot_width {
                    return Err(format!(
                        "marker `{marker}` occurrence {nth} has no room for literal `{lit}`"
                    ));
                }
                for i in x - slot_width..x {
                    row[i] = ' ';
                }
                let start = x - lit.len();
                for (idx, ch) in lit.chars().enumerate() {
                    row[start + idx] = ch;
                }
                return Ok(());
            }
            seen += 1;
        }
    }
    Err(format!(
        "marker `{marker}` occurrence {nth} not found in template"
    ))
}

fn clear_rect(grid: &mut [Vec<char>], left: usize, top: usize, right: usize, bottom: usize) {
    for row in grid.iter_mut().take(bottom + 1).skip(top) {
        for cell in row.iter_mut().take(right + 1).skip(left) {
            *cell = ' ';
        }
    }
}

struct MemoryStoragePath {
    cells: Vec<(usize, usize)>,
    top_padding: usize,
}

fn memory_storage_path(memory_size: usize) -> Result<MemoryStoragePath, String> {
    if memory_size < 2 {
        return Err("an exact storage pipe requires at least 2 memory slots".to_string());
    }

    if memory_size <= 15 {
        let destination_x = memory_size + 2;
        let mut path = vec![(4, 4)];
        for x in 4..=destination_x {
            path.push((x, 5));
        }
        return Ok(MemoryStoragePath {
            cells: path,
            top_padding: 0,
        });
    }

    // A U fits lengths 9..=25 without growing beyond the main room.
    for right in 7..=17 {
        for span in 1..=4 {
            if right + 2 * span != memory_size {
                continue;
            }
            let top = 4 - span;
            let mut path = vec![(4, 4), (4, 5), (5, 5), (5, 4)];
            for y in (top..=4).rev() {
                path.push((6, y));
            }
            for x in 7..=right {
                path.push((x, top));
            }
            for y in top + 1..=5 {
                path.push((right, y));
            }
            return Ok(MemoryStoragePath {
                cells: path,
                top_padding: 0,
            });
        }
    }

    // Extend the existing accordion horizontally first. Once it reaches x=17,
    // distribute additional cells among the same vertical tooth pairs.
    // Slightly uneven tooth heights provide every exact even length without
    // changing the source, destination, or traversal topology.
    let destination_x = 6;
    let mut layout = None;
    for right in [17usize, 15, 13, 11, 9, 7] {
        for extend_tail in [true, false] {
            let maximum_x = right + usize::from(extend_tail);
            let pairs = (right - 5) / 2;
            let minimum_length =
                5 + pairs * 4 + (right - destination_x) + 2 * usize::from(extend_tail);
            if maximum_x <= 18
                && minimum_length <= memory_size
                && layout
                    .as_ref()
                    .is_none_or(|(best_x, _, _)| maximum_x > *best_x)
            {
                layout = Some((maximum_x, right, extend_tail));
            }
        }
    }
    if let Some((_, right, extend_tail)) = layout {
        let pairs = (right - 5) / 2;
        let fixed_cells =
            5 + pairs * 2 + (right - destination_x) + 2 * usize::from(extend_tail);
        let total_span = (memory_size - fixed_cells) / 2;
        let base_span = total_span / pairs;
        let taller_pairs = total_span % pairs;
        let spans: Vec<usize> = (0..pairs)
            .map(|index| base_span + usize::from(index < taller_pairs))
            .collect();
        let top_padding = spans
            .iter()
            .copied()
            .max()
            .unwrap_or(1)
            .saturating_sub(4);
        let bottom = 4 + top_padding;
        let return_y = bottom + 1;
        let mut path = vec![(4, bottom), (4, return_y), (5, return_y), (5, bottom)];
        for (pair, &span) in spans.iter().enumerate() {
            let left = 6 + pair * 2;
            let right = left + 1;
            let top = bottom - span;
            for y in (top..=bottom).rev() {
                path.push((left, y));
            }
            for y in top..=bottom {
                path.push((right, y));
            }
        }
        let return_x = right + usize::from(extend_tail);
        if extend_tail {
            path.push((return_x, bottom));
        }
        path.push((return_x, return_y));
        for x in (destination_x..return_x).rev() {
            path.push((x, return_y));
        }
        return Ok(MemoryStoragePath {
            cells: path,
            top_padding,
        });
    }

    Err(format!(
        "could not construct a {memory_size}-cell storage pipe"
    ))
}

fn pipe_char(outgoing: (isize, isize)) -> Result<char, String> {
    match outgoing {
        (1, 0) => Ok('>'),
        (-1, 0) => Ok('<'),
        (0, 1) => Ok('v'),
        (0, -1) => Ok('^'),
        _ => Err(format!("invalid pipe direction {outgoing:?}")),
    }
}

fn render_memory_module(
    memory_size: usize,
    pipe_cells: usize,
    module_src: &str,
) -> Result<Vec<Vec<char>>, String> {
    if !(1..=256).contains(&memory_size) {
        return Err(format!(
            "compact memory module supports 1..=256 slots, got {memory_size}"
        ));
    }
    let mut memory = string_grid(module_src);
    if memory.len() != 21 || memory.first().map(Vec::len).unwrap_or(0) < 19 {
        return Err("memory.mod must retain its 19x21 room and port geometry".to_string());
    }

    // The ring protocol can transiently hold both the resident values and
    // their replacements. The default is 2N; callers may request a longer
    // pipe to provide additional buffering and timing margin.
    let minimum_pipe_cells = memory_size
        .checked_mul(2)
        .ok_or_else(|| format!("memory size {memory_size} is too large"))?;
    if pipe_cells < minimum_pipe_cells {
        return Err(format!(
            "memory pipe requires at least {minimum_pipe_cells} cells for {memory_size} slots, got {pipe_cells}"
        ));
    }
    if pipe_cells % 2 != 0 {
        return Err(format!("memory pipe size must be even, got {pipe_cells}"));
    }

    // Both station loops operate on the physical resident count. The logical
    // size records how much memory the program uses, but this ring controller
    // cannot expose a smaller address modulus than its physical capacity.
    let resident_slots = pipe_cells / 2;
    set_literal_before(&mut memory[7], "b> 0d", 0, resident_slots as i64)?;
    set_reversed_literal_before(&mut memory[19], "Wbr<>^", 0, (resident_slots - 1) as i64)?;

    let storage = memory_storage_path(pipe_cells)?;
    let path = &storage.cells;
    if path.len() != pipe_cells {
        return Err(format!(
            "internal error: requested {pipe_cells} pipe cells for {memory_size} memory slots, generated {}",
            path.len()
        ));
    }
    for (index, point) in path.iter().enumerate() {
        if path[..index].contains(point) {
            return Err(format!(
                "internal error: storage pipe intersects itself at {point:?}"
            ));
        }
    }
    if path.iter().any(|&(x, _)| x > 18) {
        return Err("internal error: storage pipe exceeded the memory module width".to_string());
    }

    if storage.top_padding > 0 {
        let width = memory.first().map(Vec::len).unwrap_or(19);
        let mut expanded = vec![vec![' '; width]; storage.top_padding];
        expanded.extend(memory);
        memory = expanded;
    }

    let width = 19;
    for row in &mut memory {
        row.resize(width, ' ');
    }

    // Preserve the repeater room at (0,0)..(5,3), then regenerate both
    // inter-room pipes from their stable room-border ports.
    for (y, row) in memory
        .iter_mut()
        .enumerate()
        .skip(storage.top_padding)
        .take(6)
    {
        for (x, cell) in row.iter_mut().enumerate() {
            if y > storage.top_padding + 3 || x > 5 {
                *cell = ' ';
            }
        }
    }
    memory[storage.top_padding + 4][3] = '^';
    memory[storage.top_padding + 5][3] = '^';

    for (index, &(x, y)) in path.iter().enumerate() {
        let outgoing = if let Some(&(next_x, next_y)) = path.get(index + 1) {
            (next_x as isize - x as isize, next_y as isize - y as isize)
        } else {
            (0, 1)
        };
        let ch = if index > 0 && index + 1 < path.len() {
            let (previous_x, previous_y) = path[index - 1];
            let incoming = (
                x as isize - previous_x as isize,
                y as isize - previous_y as isize,
            );
            if incoming == outgoing {
                if outgoing.0 == 0 {
                    '|'
                } else {
                    '-'
                }
            } else {
                pipe_char(outgoing)?
            }
        } else {
            pipe_char(outgoing)?
        };
        memory[y][x] = ch;
    }
    Ok(memory)
}

fn draw_display(
    canvas: &mut Canvas,
    left: usize,
    top: usize,
    screen: ScreenSpec,
) -> Result<(), String> {
    let right = left + screen.width + 1;
    let bottom = top + screen.height + 1;
    canvas.put(left, top, '+')?;
    canvas.put(right, top, '+')?;
    canvas.put(left, bottom, '+')?;
    canvas.put(right, bottom, '+')?;
    for x in left + 1..right {
        canvas.put(x, top, '=')?;
        canvas.put(x, bottom, '=')?;
    }
    for y in top + 1..bottom {
        canvas.put(left, y, ':')?;
        canvas.put(right, y, ':')?;
    }
    Ok(())
}

struct FloorModules<'a> {
    meta: &'a str,
    cpu: &'a str,
    cpu_screen: &'a str,
    memory: &'a str,
}

const REGISTER_LEFT: usize = 71;
const TWO_LANE_REGISTER_LEFT: usize = 62;
const REGISTER_BOTTOM: usize = 2;
const MEMORY_LEFT: usize = 90;
const TWO_LANE_MEMORY_LEFT: usize = 97;
const MEMORY_BOTTOM: usize = 2;
const CPU_LEFT: usize = 56;
const CPU_TOP: usize = 5;
const CPU_CODE_INPUT_Y: usize = CPU_TOP + 5;
const DISPLAY_LEFT: usize = 97;
const DISPLAY_TOP: usize = 6;
const MIN_CODE_PIPE_CELLS: usize = 10;

struct FixedFloor {
    grid: Vec<Vec<char>>,
    code_target: (usize, usize),
}

fn trim_grid(mut grid: Vec<Vec<char>>) -> Vec<Vec<char>> {
    let height = grid
        .iter()
        .rposition(|row| row.iter().any(|ch| *ch != ' '))
        .map(|index| index + 1)
        .unwrap_or(0);
    grid.truncate(height);
    let width = grid
        .iter()
        .filter_map(|row| row.iter().rposition(|ch| *ch != ' '))
        .max()
        .map(|index| index + 1)
        .unwrap_or(0);
    for row in &mut grid {
        row.truncate(width);
    }
    grid
}

fn render_fixed_floor(
    build: &Build,
    modules: &FloorModules<'_>,
    register_mode: RegisterBankMode,
) -> Result<FixedFloor, String> {
    let registers = match register_mode {
        RegisterBankMode::SingleLane => make_compact_vertical_register_bank(build.register_count)?,
        RegisterBankMode::TwoLane => make_two_lane_register_bank(build.register_count)?,
    };
    let register_left = match register_mode {
        RegisterBankMode::SingleLane => REGISTER_LEFT,
        RegisterBankMode::TwoLane => TWO_LANE_REGISTER_LEFT,
    };
    let memory_left = match register_mode {
        RegisterBankMode::SingleLane => MEMORY_LEFT,
        RegisterBankMode::TwoLane => TWO_LANE_MEMORY_LEFT,
    };
    let memory = (build.memory_size > 0)
        .then(|| render_memory_module(build.memory_size, build.memory_pipe_cells, modules.memory))
        .transpose()?;
    let cpu = string_grid(if build.screen.is_some() {
        modules.cpu_screen
    } else {
        modules.cpu
    });

    let mut base = string_grid(modules.meta);
    clear_rect(&mut base, 0, 2, 70, 4);
    clear_rect(&mut base, 71, 0, 81, 2);
    clear_rect(&mut base, 90, 0, 108, 2);
    clear_rect(&mut base, 56, 5, 93, 36);
    clear_rect(&mut base, 97, 6, 162, 71);
    clear_rect(&mut base, 55, 5, 55, 10);

    // This is the size-dependent lower display route from the screen CPU.
    clear_rect(&mut base, 96, 39, 98, 72);

    if register_mode == RegisterBankMode::TwoLane {
        clear_rect(&mut base, 62, 0, 117, 2);
        clear_rect(&mut base, 89, 3, 102, 4);
        if memory.is_some() {
            base[3][89] = '>';
            for x in 90..99 {
                base[3][x] = '-';
            }
            base[3][99] = '^';
            base[3][102] = 'v';
            base[4][89] = '^';
            base[4][92] = 'v';
            for x in 93..102 {
                base[4][x] = '-';
            }
            base[4][102] = '<';
        }
    } else if memory.is_none() {
        clear_rect(&mut base, 89, 3, 95, 4);
    }
    if build.screen.is_none() {
        // Remove the display address/data routes and the screen CPU's lower
        // input position. The ordinary CPU gets adjacent I/O rooms below it.
        clear_rect(&mut base, 94, 5, 162, 72);
        clear_rect(&mut base, 80, 33, 96, 72);
    }

    let memory_height = memory.as_ref().map(Vec::len).unwrap_or(0);
    let expansion = registers
        .len()
        .saturating_sub(REGISTER_BOTTOM + 1)
        .max(memory_height.saturating_sub(MEMORY_BOTTOM + 1));
    let display_right = build
        .screen
        .map(|screen| DISPLAY_LEFT + screen.width + 1)
        .unwrap_or(0);
    let width = base
        .first()
        .map(Vec::len)
        .unwrap_or(0)
        .max(display_right + 1)
        .max(
            memory_left
                + memory
                    .as_ref()
                    .and_then(|module| module.first())
                    .map(Vec::len)
                    .unwrap_or(0),
        );
    let height = expansion + base.len();
    let mut canvas = Canvas::new(width, height);
    canvas.paste(0, expansion, &base)?;

    let bottom_aligned_y =
        |bottom: usize, module_height: usize| expansion + bottom + 1 - module_height;
    canvas.paste(
        register_left,
        bottom_aligned_y(REGISTER_BOTTOM, registers.len()),
        &registers,
    )?;
    if let Some(memory) = &memory {
        canvas.paste(
            memory_left,
            bottom_aligned_y(MEMORY_BOTTOM, memory.len()),
            memory,
        )?;
    }
    canvas.paste(CPU_LEFT, expansion + CPU_TOP, &cpu)?;

    if let Some(screen) = build.screen {
        let display_top = expansion + DISPLAY_TOP;
        draw_display(&mut canvas, DISPLAY_LEFT, display_top, screen)?;

        // The lower display source leaves the CPU at base row 34 and descends
        // through x=96. Bend below the CPU when the display is shorter, then
        // approach the display's bottom edge upward through x=98.
        let bend_y = expansion + 38;
        let turn_y = display_top + screen.height + 2;
        match turn_y.cmp(&bend_y) {
            std::cmp::Ordering::Greater => {
                for y in bend_y..=turn_y {
                    canvas.grid[y][96] = ' ';
                }
                for x in 96..=98 {
                    canvas.grid[turn_y][x] = ' ';
                }
                for y in bend_y..turn_y {
                    canvas.put(96, y, '|')?;
                }
                canvas.put(96, turn_y, '>')?;
                canvas.put(97, turn_y, '-')?;
                canvas.put(98, turn_y, '^')?;
            }
            std::cmp::Ordering::Less => {
                for x in 96..=98 {
                    canvas.grid[bend_y][x] = ' ';
                }
                for y in turn_y..=bend_y {
                    canvas.grid[y][98] = ' ';
                }
                canvas.put(96, bend_y, '>')?;
                canvas.put(97, bend_y, '-')?;
                canvas.put(98, bend_y, '^')?;
                for y in turn_y..bend_y {
                    canvas.put(98, y, if y == turn_y { '^' } else { '|' })?;
                }
            }
            std::cmp::Ordering::Equal => {
                canvas.put(96, bend_y, '>')?;
                canvas.put(97, bend_y, '-')?;
                canvas.put(98, bend_y, '^')?;
            }
        }
    } else {
        let peripheral_top = expansion + CPU_TOP + cpu.len() + 2;
        for y in expansion + CPU_TOP + cpu.len()..peripheral_top {
            canvas.put(81, y, 'v')?;
            canvas.put(85, y, '^')?;
        }
        draw_room(&mut canvas, 80, peripheral_top, 1, 1)?;
        draw_room(&mut canvas, 84, peripheral_top, 1, 1)?;
        canvas.put(81, peripheral_top + 1, 'O')?;
        canvas.put(85, peripheral_top + 1, 'I')?;
    }

    Ok(FixedFloor {
        grid: trim_grid(canvas.grid),
        code_target: (CPU_LEFT - 1, expansion + CPU_CODE_INPUT_Y),
    })
}

#[derive(Clone)]
struct QuoteParity {
    rows: Vec<bool>,
    columns: Vec<bool>,
}

fn quote_parity(grid: &[Vec<char>]) -> QuoteParity {
    let height = grid.len();
    let width = grid.first().map(Vec::len).unwrap_or(0);
    let rows = grid
        .iter()
        .map(|row| row.iter().filter(|ch| **ch == '`').count() % 2 != 0)
        .collect();
    let columns = (0..width)
        .map(|x| (0..height).filter(|y| grid[*y][x] == '`').count() % 2 != 0)
        .collect();
    QuoteParity { rows, columns }
}

fn quote_parity_conflicts(
    fixed: &QuoteParity,
    fixed_x: usize,
    fixed_y: usize,
    room: &QuoteParity,
    room_y: usize,
) -> bool {
    let top = fixed_y.min(room_y);
    let bottom = (fixed_y + fixed.rows.len()).max(room_y + room.rows.len());
    for y in top..bottom {
        let fixed_odd = y
            .checked_sub(fixed_y)
            .and_then(|index| fixed.rows.get(index))
            .copied()
            .unwrap_or(false);
        let room_odd = y
            .checked_sub(room_y)
            .and_then(|index| room.rows.get(index))
            .copied()
            .unwrap_or(false);
        if fixed_odd && room_odd {
            return true;
        }
    }
    (0..room.columns.len()).any(|x| {
        room.columns[x]
            && x.checked_sub(fixed_x)
                .and_then(|fixed_column| fixed.columns.get(fixed_column))
                .copied()
                .unwrap_or(false)
    })
}

struct CodeShape {
    room: Vec<Vec<char>>,
    parity: QuoteParity,
    orientation: CodeOrientation,
}

type CodeLayoutCache = HashMap<(usize, usize, CodeOrientation), Option<Vec<Vec<char>>>>;

fn code_layout_fits(
    tokens: &[String],
    width: usize,
    height: usize,
    orientation: CodeOrientation,
    cache: &mut CodeLayoutCache,
) -> bool {
    cache
        .entry((width, height, orientation))
        .or_insert_with(|| {
            layout_oriented_program_grid(tokens, width, height, orientation)
                .filter(|grid| valid_numeric_literals(grid) && program_grid_loops(grid))
        })
        .is_some()
}

#[derive(Clone, Copy)]
struct LeftBlock {
    top: usize,
    width: usize,
    height: usize,
}

fn maximal_left_blocks(grid: &[Vec<char>]) -> Vec<LeftBlock> {
    let height = grid.len();
    let width = grid.first().map(Vec::len).unwrap_or(0);
    let free_prefix: Vec<usize> = grid
        .iter()
        .map(|row| row.iter().position(|ch| *ch != ' ').unwrap_or(width))
        .collect();
    let mut blocks = Vec::new();
    let mut seen = HashMap::new();
    for top in 0..height {
        let mut block_width = width;
        for bottom in top..height {
            block_width = block_width.min(free_prefix[bottom]);
            if block_width < 3 {
                break;
            }
            let extend_up = top > 0 && free_prefix[top - 1] >= block_width;
            let extend_down = bottom + 1 < height && free_prefix[bottom + 1] >= block_width;
            if extend_up || extend_down {
                continue;
            }
            let block = LeftBlock {
                top,
                width: block_width,
                height: bottom - top + 1,
            };
            if seen
                .insert((block.top, block.width, block.height), true)
                .is_none()
            {
                blocks.push(block);
            }
        }
    }
    blocks.sort_unstable_by_key(|block| {
        (
            std::cmp::Reverse(block.width * block.height),
            std::cmp::Reverse(block.width.min(block.height)),
            block.top,
        )
    });
    blocks
}

fn largest_legal_interior(
    block: LeftBlock,
    orientation: CodeOrientation,
) -> Option<(usize, usize)> {
    let mut width = block.width.checked_sub(2)?;
    let mut height = block.height.checked_sub(2)?;
    match orientation {
        CodeOrientation::Horizontal => {
            height -= height % 2;
            (width >= 6 && height >= 2).then_some((width, height))
        }
        CodeOrientation::Vertical => {
            if width % 2 == 0 {
                width = width.saturating_sub(1);
            }
            (width >= 5 && height >= 4).then_some((width, height))
        }
    }
}

fn ceil_div(value: usize, divisor: usize) -> usize {
    value / divisor + usize::from(value % divisor != 0)
}

fn fitting_code_rooms(
    tokens: &[String],
    block: LeftBlock,
    orientation: CodeOrientation,
    cache: &mut CodeLayoutCache,
) -> Vec<CodeShape> {
    let Some((max_width, max_height)) = largest_legal_interior(block, orientation) else {
        return Vec::new();
    };
    let used: usize = tokens.iter().map(String::len).sum();
    let mut dimensions = HashMap::new();

    // Keep the shortest fitting room for every width.
    let widths: Box<dyn Iterator<Item = usize>> = match orientation {
        CodeOrientation::Horizontal => Box::new(6..=max_width),
        CodeOrientation::Vertical => Box::new((5..=max_width).step_by(2)),
    };
    for width in widths {
        let (mut height, step) = match orientation {
            CodeOrientation::Horizontal => {
                let mut height = ceil_div(used.saturating_sub(1), width - 3).max(2);
                height += height % 2;
                (height, 2)
            }
            CodeOrientation::Vertical => (ceil_div(used, width - 1).saturating_add(3).max(4), 1),
        };
        while height <= max_height {
            if code_layout_fits(tokens, width, height, orientation, cache) {
                dimensions.insert((width, height), ());
                break;
            }
            height += step;
        }
    }

    // Also keep the narrowest fitting room for every height. Together these
    // sweeps cover the aspect-ratio frontier that one greedy shrink path
    // cannot represent.
    let heights: Box<dyn Iterator<Item = usize>> = match orientation {
        CodeOrientation::Horizontal => Box::new((2..=max_height).step_by(2)),
        CodeOrientation::Vertical => Box::new(4..=max_height),
    };
    for height in heights {
        let (mut width, step) = match orientation {
            CodeOrientation::Horizontal => (
                ceil_div(used.saturating_sub(1), height)
                    .saturating_add(3)
                    .max(6),
                1,
            ),
            CodeOrientation::Vertical => {
                let mut width = ceil_div(used, height - 3).saturating_add(1).max(5);
                if width % 2 == 0 {
                    width += 1;
                }
                (width, 2)
            }
        };
        while width <= max_width {
            if code_layout_fits(tokens, width, height, orientation, cache) {
                dimensions.insert((width, height), ());
                break;
            }
            width += step;
        }
    }

    let mut dimensions = dimensions.into_keys().collect::<Vec<_>>();
    dimensions.sort_unstable_by_key(|&(width, height)| {
        (
            (width + 2) * (height + 2),
            (width + 2).max(height + 2),
            width,
        )
    });
    dimensions
        .into_iter()
        .filter_map(|(width, height)| {
            let interior = cache
                .get(&(width, height, orientation))
                .and_then(Option::as_ref)?;
            let room = room_grid(interior);
            Some(CodeShape {
                parity: quote_parity(&room),
                room,
                orientation,
            })
        })
        .collect()
}

#[derive(Clone, Copy)]
struct PipeNode {
    x: usize,
    y: usize,
    incoming: usize,
    parent: Option<usize>,
}

fn step_point(
    point: (usize, usize),
    direction: (isize, isize),
    width: usize,
    height: usize,
) -> Option<(usize, usize)> {
    let x = point.0.checked_add_signed(direction.0)?;
    let y = point.1.checked_add_signed(direction.1)?;
    (x < width && y < height).then_some((x, y))
}

fn route_code_pipe(
    canvas: &Canvas,
    room_y: usize,
    room_width: usize,
    room_height: usize,
    target: (usize, usize),
) -> Option<Vec<(usize, usize)>> {
    const DIRECTIONS: [(isize, isize); 4] = [(1, 0), (-1, 0), (0, 1), (0, -1)];
    const OPPOSITE: [usize; 4] = [1, 0, 3, 2];

    let height = canvas.grid.len();
    let width = canvas.grid.first().map(Vec::len).unwrap_or(0);
    if target.0 >= width || target.1 >= height || canvas.grid[target.1][target.0] != ' ' {
        return None;
    }

    let room_right = room_width - 1;
    let room_bottom = room_y + room_height - 1;
    let mut sources = Vec::new();
    if room_right + 1 < width {
        for y in room_y + 1..room_bottom {
            sources.push(((room_right + 1, y), 0usize));
        }
    }
    if room_bottom + 1 < height {
        for x in 1..room_right {
            sources.push(((x, room_bottom + 1), 2usize));
        }
    }
    if room_y > 0 {
        for x in 1..room_right {
            sources.push(((x, room_y - 1), 3usize));
        }
    }

    let mut queue = VecDeque::new();
    let mut nodes = Vec::new();
    let mut visited = vec![false; width * height * 4];
    for (source, direction) in sources {
        if canvas.grid[source.1][source.0] != ' ' {
            continue;
        }
        let distance = source.0.abs_diff(target.0) + source.1.abs_diff(target.1);
        if distance + 1 < MIN_CODE_PIPE_CELLS {
            continue;
        }
        let Some(next) = step_point(source, DIRECTIONS[direction], width, height) else {
            continue;
        };
        if next != target && canvas.grid[next.1][next.0] != ' ' {
            continue;
        }
        let source_index = nodes.len();
        nodes.push(PipeNode {
            x: source.0,
            y: source.1,
            incoming: direction,
            parent: None,
        });
        let state = (next.1 * width + next.0) * 4 + direction;
        if visited[state] {
            continue;
        }
        visited[state] = true;
        let next_index = nodes.len();
        nodes.push(PipeNode {
            x: next.0,
            y: next.1,
            incoming: direction,
            parent: Some(source_index),
        });
        queue.push_back(next_index);
    }

    while let Some(index) = queue.pop_front() {
        let node = nodes[index];
        if (node.x, node.y) == target && node.incoming != 1 {
            let mut path = Vec::new();
            let mut cursor = Some(index);
            while let Some(node_index) = cursor {
                let path_node = nodes[node_index];
                path.push((path_node.x, path_node.y));
                cursor = path_node.parent;
            }
            path.reverse();
            if path.len() >= MIN_CODE_PIPE_CELLS {
                return Some(path);
            }
        }

        for direction in 0..DIRECTIONS.len() {
            if direction == OPPOSITE[node.incoming] {
                continue;
            }
            let Some(next) = step_point((node.x, node.y), DIRECTIONS[direction], width, height)
            else {
                continue;
            };
            if next != target && canvas.grid[next.1][next.0] != ' ' {
                continue;
            }
            let state = (next.1 * width + next.0) * 4 + direction;
            if visited[state] {
                continue;
            }
            visited[state] = true;
            let next_index = nodes.len();
            nodes.push(PipeNode {
                x: next.0,
                y: next.1,
                incoming: direction,
                parent: Some(index),
            });
            queue.push_back(next_index);
        }
    }
    None
}

fn draw_code_pipe(canvas: &mut Canvas, path: &[(usize, usize)]) -> Result<(), String> {
    for (index, &(x, y)) in path.iter().enumerate() {
        let outgoing = path
            .get(index + 1)
            .map(|&(next_x, next_y)| (next_x as isize - x as isize, next_y as isize - y as isize))
            .unwrap_or((1, 0));
        let ch = if index == 0 || index + 1 == path.len() {
            pipe_char(outgoing)?
        } else {
            let (previous_x, previous_y) = path[index - 1];
            let incoming = (
                x as isize - previous_x as isize,
                y as isize - previous_y as isize,
            );
            if incoming == outgoing {
                if outgoing.0 == 0 {
                    '|'
                } else {
                    '-'
                }
            } else {
                pipe_char(outgoing)?
            }
        };
        canvas.put(x, y, ch)?;
    }
    Ok(())
}

struct FloorLayout {
    man: String,
    room: String,
    orientation: CodeOrientation,
    pipe_cells: usize,
}

fn render_meta_floor(
    build: &Build,
    modules: &FloorModules<'_>,
    register_mode: RegisterBankMode,
) -> Result<FloorLayout, String> {
    let fixed = render_fixed_floor(build, modules, register_mode)?;
    if !valid_numeric_literals(&fixed.grid) {
        return Err("fixed processor floor contains an invalid numeric literal".to_string());
    }
    let fixed_parity = quote_parity(&fixed.grid);
    let tokens = encode_program_tokens(&build.program.words);
    let fixed_width = fixed.grid.first().map(Vec::len).unwrap_or(0);
    let fixed_height = fixed.grid.len();
    let mut width = fixed_width;
    let mut height = fixed_height;
    let mut cache = CodeLayoutCache::new();

    while width <= 2048 && height <= 2048 {
        let fixed_x = width - fixed_width;
        let fixed_y = height - fixed_height;
        let mut fixed_canvas = Canvas::new(width, height);
        fixed_canvas.paste(fixed_x, fixed_y, &fixed.grid)?;
        let mut best: Option<((usize, usize), FloorLayout)> = None;

        for block in maximal_left_blocks(&fixed_canvas.grid) {
            for orientation in [CodeOrientation::Horizontal, CodeOrientation::Vertical] {
                for shape in fitting_code_rooms(&tokens, block, orientation, &mut cache) {
                    let room_width = shape.room[0].len();
                    let room_height = shape.room.len();
                    if room_width > block.width || room_height > block.height {
                        continue;
                    }
                    let last_room_y = block.top + block.height - room_height;
                    for room_y in block.top..=last_room_y {
                        if quote_parity_conflicts(
                            &fixed_parity,
                            fixed_x,
                            fixed_y,
                            &shape.parity,
                            room_y,
                        ) {
                            continue;
                        }

                        let mut canvas = fixed_canvas.clone();
                        if canvas.paste(0, room_y, &shape.room).is_err() {
                            continue;
                        }
                        let target = (fixed.code_target.0 + fixed_x, fixed.code_target.1 + fixed_y);
                        let Some(pipe) =
                            route_code_pipe(&canvas, room_y, room_width, room_height, target)
                        else {
                            continue;
                        };
                        if draw_code_pipe(&mut canvas, &pipe).is_err() {
                            continue;
                        }

                        // The parity profile rejects cross-room pairs cheaply. This
                        // catches insertion inside an existing pair and a pipe
                        // crossing an open literal.
                        if !valid_numeric_literals(&canvas.grid) {
                            continue;
                        }
                        let key = (pipe.len(), room_width * room_height);
                        let layout = FloorLayout {
                            man: grid_to_string(&canvas.grid),
                            room: grid_to_string(&shape.room),
                            orientation: shape.orientation,
                            pipe_cells: pipe.len(),
                        };
                        if best.as_ref().is_none_or(|(best_key, _)| key < *best_key) {
                            best = Some((key, layout));
                        }
                    }
                }
            }
        }
        if let Some((_, layout)) = best {
            return Ok(layout);
        }

        if width < height {
            width += 1;
        } else {
            height += 1;
        }
    }

    Err(
        "no quote-safe, collision-free code-room placement can reach the CPU with a 10-cell pipe"
            .to_string(),
    )
}

fn run_vm_until_outputs(
    program: &Program,
    input: &[i64],
    expected_outputs: usize,
    max_steps: usize,
) -> Result<Vec<i64>, String> {
    let mut regs = vec![0i64; 512];
    let mut mem = vec![0i64; 4096];
    let mut pc = 0usize;
    let mut ip = 0usize;
    let mut output = Vec::new();
    let words = &program.words;

    let fetch = |pc: &mut usize| -> i64 {
        let value = words[*pc];
        *pc = (*pc + 1) % words.len();
        value
    };

    for _ in 0..max_steps {
        let op = fetch(&mut pc);
        match op {
            0 => {
                let dst = fetch(&mut pc) as usize;
                let src = fetch(&mut pc) as usize;
                regs[dst] = regs[src];
            }
            1 => {
                let addr = fetch(&mut pc) as usize;
                let src = fetch(&mut pc) as usize;
                let idx = regs[addr] as usize;
                if idx >= mem.len() {
                    return Err(format!("memory write out of range: {idx}"));
                }
                mem[idx] = regs[src];
            }
            2 => {
                let dst = fetch(&mut pc) as usize;
                let addr = fetch(&mut pc) as usize;
                let idx = regs[addr] as usize;
                if idx >= mem.len() {
                    return Err(format!("memory read out of range: {idx}"));
                }
                regs[dst] = mem[idx];
            }
            3 => {
                let value = fetch(&mut pc);
                let dst = fetch(&mut pc) as usize;
                regs[dst] = value;
            }
            4 => {
                let dst = fetch(&mut pc) as usize;
                if ip >= input.len() {
                    return Err("input exhausted".to_string());
                }
                regs[dst] = input[ip];
                ip += 1;
            }
            5 => {
                let src = fetch(&mut pc) as usize;
                output.push(regs[src]);
                if output.len() >= expected_outputs {
                    return Ok(output);
                }
            }
            6 => {
                let subop = fetch(&mut pc);
                let src = fetch(&mut pc) as usize;
                let a = regs[0];
                let b = regs[src];
                regs[0] = match subop {
                    0 => a.wrapping_add(b),
                    1 => a.wrapping_mul(b),
                    2 => a.wrapping_sub(b),
                    3 => {
                        if b == 0 {
                            0
                        } else {
                            a.div_euclid(b)
                        }
                    }
                    4 => a & b,
                    5 => {
                        if !(0..=63).contains(&b) {
                            if b > 63 && a < 0 {
                                -1
                            } else {
                                0
                            }
                        } else {
                            a >> b
                        }
                    }
                    6 => a ^ b,
                    _ => return Err(format!("bad ALU op {subop}")),
                };
            }
            7 => {
                let offset = fetch(&mut pc);
                let cond = fetch(&mut pc) as usize;
                if regs[cond] > 0 {
                    pc = (pc + offset as usize) % words.len();
                }
            }
            8 => {
                let offset = fetch(&mut pc);
                pc = (pc + offset as usize) % words.len();
            }
            _ => {
                return Err(format!(
                    "bad opcode {op} at pc {}",
                    (pc + words.len() - 1) % words.len()
                ))
            }
        }
    }
    Err("step limit exceeded".to_string())
}

fn run_vm(program: &Program, input: &[i64], max_steps: usize) -> Result<Vec<i64>, String> {
    run_vm_until_outputs(program, input, 1, max_steps)
}

fn run_screen_vm_until_frames(
    program: &Program,
    screen: ScreenSpec,
    input: &[i64],
    expected_frames: usize,
    max_steps: usize,
) -> Result<Vec<Vec<i64>>, String> {
    let mut regs = vec![0i64; 512];
    let mut mem = vec![0i64; 4096];
    let mut pc = 0usize;
    let mut ip = 0usize;
    let mut cursor = 0usize;
    let screen_size = screen.width * screen.height;
    let mut next = vec![0i64; screen_size];
    let mut frames = Vec::new();
    let words = &program.words;

    let fetch = |pc: &mut usize| -> i64 {
        let value = words[*pc];
        *pc = (*pc + 1) % words.len();
        value
    };

    for _ in 0..max_steps {
        let op = fetch(&mut pc);
        match op {
            0 => {
                let dst = fetch(&mut pc) as usize;
                let src = fetch(&mut pc) as usize;
                regs[dst] = regs[src];
            }
            1 => {
                let addr = fetch(&mut pc) as usize;
                let src = fetch(&mut pc) as usize;
                let idx = regs[addr] as usize;
                if idx >= mem.len() {
                    return Err(format!("memory write out of range: {idx}"));
                }
                mem[idx] = regs[src];
            }
            2 => {
                let dst = fetch(&mut pc) as usize;
                let addr = fetch(&mut pc) as usize;
                let idx = regs[addr] as usize;
                if idx >= mem.len() {
                    return Err(format!("memory read out of range: {idx}"));
                }
                regs[dst] = mem[idx];
            }
            3 => {
                let value = fetch(&mut pc);
                let dst = fetch(&mut pc) as usize;
                regs[dst] = value;
            }
            4 => {
                let dst = fetch(&mut pc) as usize;
                if ip >= input.len() {
                    return Err("input exhausted".to_string());
                }
                regs[dst] = input[ip];
                ip += 1;
            }
            5 => {
                let src = fetch(&mut pc) as usize;
                let preserve = regs[src];
                if preserve != 0 && preserve != 1 {
                    return Err(format!("bad screen swap value {preserve}"));
                }
                frames.push(next.clone());
                if frames.len() >= expected_frames {
                    return Ok(frames);
                }
                if preserve == 0 {
                    next.fill(0);
                    cursor = 0;
                }
            }
            6 => {
                let src = fetch(&mut pc) as usize;
                let addr = regs[src];
                if !(0..screen_size as i64).contains(&addr) {
                    return Err(format!("bad screen address {addr}"));
                }
                cursor = addr as usize;
            }
            7 => {
                let src = fetch(&mut pc) as usize;
                let color = regs[src];
                if !(0..=15).contains(&color) {
                    return Err(format!("bad screen color {color}"));
                }
                next[cursor] = color;
                cursor = (cursor + 1) % next.len();
            }
            8 => {
                let subop = fetch(&mut pc);
                let src = fetch(&mut pc) as usize;
                let a = regs[0];
                let b = regs[src];
                regs[0] = match subop {
                    0 => a.wrapping_add(b),
                    1 => a.wrapping_mul(b),
                    2 => a.wrapping_sub(b),
                    3 => {
                        if b == 0 {
                            0
                        } else {
                            a.div_euclid(b)
                        }
                    }
                    4 => a & b,
                    5 => {
                        if !(0..=63).contains(&b) {
                            if b > 63 && a < 0 {
                                -1
                            } else {
                                0
                            }
                        } else {
                            a >> b
                        }
                    }
                    6 => a ^ b,
                    _ => return Err(format!("bad ALU op {subop}")),
                };
            }
            9 => {
                let offset = fetch(&mut pc);
                let cond = fetch(&mut pc) as usize;
                if regs[cond] > 0 {
                    pc = (pc + offset as usize) % words.len();
                }
            }
            10 => {
                let offset = fetch(&mut pc);
                pc = (pc + offset as usize) % words.len();
            }
            _ => {
                return Err(format!(
                    "bad opcode {op} at pc {}",
                    (pc + words.len() - 1) % words.len()
                ))
            }
        }
    }
    Err("step limit exceeded".to_string())
}

fn append_unique_test<T: PartialEq>(
    tests: &mut Vec<(Vec<i64>, T)>,
    input: Vec<i64>,
    expected: T,
    suite: &str,
) -> Result<(), String> {
    if let Some((_, existing)) = tests.iter().find(|(candidate, _)| candidate == &input) {
        if existing != &expected {
            return Err(format!("{suite} has conflicting expectations for one input"));
        }
    } else {
        tests.push((input, expected));
    }
    Ok(())
}

fn matmul_expected(input: &[i64]) -> Result<Vec<i64>, String> {
    if input.len() < 3 {
        return Err("matmul input is missing dimensions".to_string());
    }
    let n = input[0] as usize;
    let m = input[1] as usize;
    let k = input[2] as usize;
    let a_len = n * m;
    let b_len = m * k;
    if input.len() != 3 + a_len + b_len {
        return Err(format!(
            "matmul input length mismatch: got {}, expected {}",
            input.len(),
            3 + a_len + b_len
        ));
    }
    let a = &input[3..3 + a_len];
    let b = &input[3 + a_len..];
    let mut out = Vec::with_capacity(n * k);
    for i in 0..n {
        for j in 0..k {
            let mut sum = 0i64;
            for t in 0..m {
                sum += a[i * m + t] * b[t * k + j];
            }
            out.push(sum);
        }
    }
    Ok(out)
}

fn public_matmul_tests() -> Result<Vec<(Vec<i64>, Vec<i64>)>, String> {
    let mut full = vec![16, 16, 16];
    for i in 0..256 {
        full.push((i % 17) as i64 - 8);
    }
    for i in 0..256 {
        full.push(((i * 7) % 19) as i64 - 9);
    }
    let full_expected = matmul_expected(&full)?;
    let mut tests = vec![(full, full_expected)];
    for (input, expected) in public_test_cases(include_str!("../public_tests/matrix.json"))? {
        let modeled = matmul_expected(&input)?;
        if modeled != expected {
            return Err("matrix public test output does not match the reference model".to_string());
        }
        append_unique_test(&mut tests, input, expected, "matrix tests")?;
    }
    Ok(tests)
}

fn bresenham_frame(mut x0: i64, mut y0: i64, x1: i64, y1: i64) -> Vec<i64> {
    let mut frame = vec![0i64; 32 * 24];
    let dx = (x1 - x0).abs();
    let sx = if x0 < x1 { 1 } else { -1 };
    let dy = -(y1 - y0).abs();
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx + dy;
    loop {
        frame[(y0 * 32 + x0) as usize] = 15;
        if x0 == x1 && y0 == y1 {
            break;
        }
        let e2 = 2 * err;
        if e2 >= dy {
            err += dy;
            x0 += sx;
        }
        if e2 <= dx {
            err += dx;
            y0 += sy;
        }
    }
    frame
}

fn public_plotter_tests() -> Result<Vec<(Vec<i64>, Vec<Vec<i64>>)>, String> {
    public_test_inputs(include_str!("../public_tests/plotter.json"))?
        .into_iter()
        .map(|input| {
            if input.len() % 4 != 0 {
                return Err("plotter public test has an incomplete round".to_string());
            }
            let frames = input
                .chunks_exact(4)
                .map(|round| bresenham_frame(round[0], round[1], round[2], round[3]))
                .collect();
            Ok((input, frames))
        })
        .collect()
}

fn snake_frame(body: &VecDeque<(i64, i64)>, fruit: Option<(i64, i64)>, lost: bool) -> Vec<i64> {
    let mut frame = vec![0; 16 * 16];
    for &(x, y) in body {
        frame[(y * 16 + x) as usize] = if lost { 9 } else { 10 };
    }
    if let Some((x, y)) = fruit {
        frame[(y * 16 + x) as usize] = 9;
    }
    frame
}

fn snake_expected_frames(input: &[i64]) -> Result<Vec<Vec<i64>>, String> {
    if input.len() < 2 {
        return Err("snake input requires a starting position".to_string());
    }
    let mut body = VecDeque::from([(input[0], input[1])]);
    let mut direction = (1, 0);
    let mut fruit = None;
    let mut frames = vec![snake_frame(&body, fruit, false)];
    let mut index = 2;

    while index < input.len() {
        let command = input[index];
        index += 1;
        match command {
            0 => {
                let &(head_x, head_y) = body.back().unwrap();
                let next = (head_x + direction.0, head_y + direction.1);
                let growing = fruit == Some(next);
                let outside = !(0..16).contains(&next.0) || !(0..16).contains(&next.1);
                let occupied = body.contains(&next);
                let entering_tail = !growing && body.front() == Some(&next);
                if outside || (occupied && !entering_tail) {
                    frames.push(snake_frame(&body, fruit, true));
                    break;
                }
                if !growing {
                    body.pop_front();
                } else {
                    fruit = None;
                }
                body.push_back(next);
                frames.push(snake_frame(&body, fruit, false));
            }
            1 => {
                if index + 1 >= input.len() {
                    return Err("snake fruit command is missing coordinates".to_string());
                }
                fruit = Some((input[index], input[index + 1]));
                index += 2;
                frames.push(snake_frame(&body, fruit, false));
            }
            2 => direction = (0, -1),
            3 => direction = (1, 0),
            4 => direction = (0, 1),
            5 => direction = (-1, 0),
            _ => return Err(format!("bad snake command {command}")),
        }
    }
    Ok(frames)
}

fn public_snake_tests() -> Result<Vec<(Vec<i64>, Vec<Vec<i64>>)>, String> {
    let inputs = vec![
        vec![12, 3, 0, 0],
        vec![2, 2, 1, 3, 2, 0, 0],
        vec![15, 0, 0],
        vec![
            2, 2, 1, 3, 2, 0, 4, 1, 3, 3, 0, 5, 1, 2, 3, 0, 1, 1, 3, 0, 2, 1, 1, 2, 0, 3, 0,
            4, 0,
        ],
    ];
    let mut tests = inputs
        .into_iter()
        .map(|input| snake_expected_frames(&input).map(|frames| (input, frames)))
        .collect::<Result<Vec<_>, _>>()?;
    for input in public_test_inputs(include_str!("../public_tests/snake.json"))? {
        let frames = snake_expected_frames(&input)?;
        append_unique_test(&mut tests, input, frames, "snake tests")?;
    }
    Ok(tests)
}

fn pathfinder_expected_frames(input: &[i64]) -> Result<Vec<Vec<i64>>, String> {
    const CELLS: usize = 16 * 16;
    if input.len() < CELLS + 2 {
        return Err("pathfinder input is missing the board or robot position".to_string());
    }
    if (input.len() - (CELLS + 2)) % 2 != 0 {
        return Err("pathfinder input has an incomplete flag position".to_string());
    }

    let board = &input[..CELLS];
    if board.iter().any(|&cell| cell != 0 && cell != 1) {
        return Err("pathfinder board cells must be zero or one".to_string());
    }

    let position = |x: i64, y: i64| -> Result<usize, String> {
        if !(0..16).contains(&x) || !(0..16).contains(&y) {
            return Err(format!("pathfinder position is outside the board: {x},{y}"));
        }
        Ok((y * 16 + x) as usize)
    };

    let mut robot = position(input[CELLS], input[CELLS + 1])?;
    if board[robot] != 0 {
        return Err("pathfinder robot starts on a wall".to_string());
    }

    let mut frame = board
        .iter()
        .map(|&cell| if cell == 0 { 0 } else { 7 })
        .collect::<Vec<_>>();
    frame[robot] = 10;
    let mut frames = vec![frame.clone()];

    for flag_xy in input[CELLS + 2..].chunks_exact(2) {
        let flag = position(flag_xy[0], flag_xy[1])?;
        if flag == robot || board[flag] != 0 {
            return Err("pathfinder flag must be a different traversable cell".to_string());
        }

        let mut previous = vec![usize::MAX; CELLS];
        let mut previous_direction = vec![usize::MAX; CELLS];
        let mut queue = VecDeque::from([robot]);
        previous[robot] = robot;

        'search: while let Some(current) = queue.pop_front() {
            let x = current % 16;
            let y = current / 16;
            let neighbors = [
                (x, y.wrapping_sub(1), 0usize),
                (x + 1, y, 1usize),
                (x, y + 1, 2usize),
                (x.wrapping_sub(1), y, 3usize),
            ];
            for (next_x, next_y, direction) in neighbors {
                if next_x >= 16 || next_y >= 16 {
                    continue;
                }
                let next = next_y * 16 + next_x;
                if board[next] != 0 || previous[next] != usize::MAX {
                    continue;
                }
                previous[next] = current;
                previous_direction[next] = direction;
                if next == flag {
                    break 'search;
                }
                queue.push_back(next);
            }
        }

        if previous[flag] == usize::MAX {
            return Err("pathfinder flag is unreachable".to_string());
        }

        let mut moves = Vec::new();
        let mut current = flag;
        while current != robot {
            moves.push(previous_direction[current]);
            current = previous[current];
        }
        moves.reverse();
        if moves.is_empty() || moves.len() > 64 {
            return Err(format!("pathfinder path length is {}", moves.len()));
        }

        frame[flag] = 9;
        for direction in moves {
            frame[robot] = 0;
            robot = match direction {
                0 => robot - 16,
                1 => robot + 1,
                2 => robot + 16,
                3 => robot - 1,
                _ => unreachable!(),
            };
            frame[robot] = 10;
            frames.push(frame.clone());
        }
    }

    Ok(frames)
}

fn public_test_arrays(source: &str, field: &str) -> Result<Vec<Vec<i64>>, String> {
    let marker = format!("\"{field}\"");
    let mut remaining = source;
    let mut arrays = Vec::new();
    while let Some(marker_offset) = remaining.find(&marker) {
        remaining = &remaining[marker_offset + marker.len()..];
        let colon = remaining
            .find(':')
            .ok_or_else(|| format!("public test {field} has no value"))?;
        remaining = &remaining[colon + 1..];
        let open = remaining
            .find('[')
            .ok_or_else(|| format!("public test {field} is not an array"))?;
        remaining = &remaining[open + 1..];
        let close = remaining
            .find(']')
            .ok_or_else(|| format!("public test {field} array is not closed"))?;
        let values = remaining[..close]
            .split(',')
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(|value| {
                value
                    .parse::<i64>()
                    .map_err(|_| format!("bad public test value `{value}`"))
            })
            .collect::<Result<Vec<_>, _>>()?;
        arrays.push(values);
        remaining = &remaining[close + 1..];
    }
    if arrays.is_empty() {
        return Err(format!("public test JSON contains no {field} arrays"));
    }
    Ok(arrays)
}

fn public_test_inputs(source: &str) -> Result<Vec<Vec<i64>>, String> {
    public_test_arrays(source, "input")
}

fn public_test_cases(source: &str) -> Result<Vec<(Vec<i64>, Vec<i64>)>, String> {
    let inputs = public_test_inputs(source)?;
    let outputs = public_test_arrays(source, "output")?;
    if inputs.len() != outputs.len() {
        return Err(format!(
            "public test JSON contains {} inputs and {} outputs",
            inputs.len(),
            outputs.len()
        ));
    }
    Ok(inputs.into_iter().zip(outputs).collect())
}

fn public_bracket_tests() -> Result<Vec<(Vec<i64>, i64)>, String> {
    public_test_cases(include_str!("../public_tests/brackets.json"))?
        .into_iter()
        .map(|(input, output)| match output.as_slice() {
            [expected] => Ok((input, *expected)),
            _ => Err("brackets public test must have exactly one output".to_string()),
        })
        .collect()
}

fn published_pathfinder_tests() -> Result<Vec<(Vec<i64>, Vec<Vec<i64>>)>, String> {
    public_test_inputs(include_str!("../public_tests/pathfinder.json"))?
        .into_iter()
        .map(|input| {
            let expected = pathfinder_expected_frames(&input)?;
            Ok((input, expected))
        })
        .collect()
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct LlmPoint {
    x: usize,
    y: usize,
}

#[derive(Clone, Copy, Debug)]
struct LlmRoom {
    min: LlmPoint,
    max: LlmPoint,
}

impl LlmRoom {
    fn contains(self, point: LlmPoint) -> bool {
        point.x >= self.min.x
            && point.x <= self.max.x
            && point.y >= self.min.y
            && point.y <= self.max.y
    }

    fn border(self, point: LlmPoint) -> bool {
        self.contains(point)
            && (point.x == self.min.x
                || point.x == self.max.x
                || point.y == self.min.y
                || point.y == self.max.y)
    }
}

#[derive(Clone, Debug)]
struct LlmPipe {
    path: Vec<LlmPoint>,
    values: Vec<Option<i64>>,
    source_room: usize,
    dest_room: usize,
}

#[derive(Clone, Debug)]
struct LlmMan {
    point: LlmPoint,
    direction: usize,
    a: i64,
    b: i64,
    halted: bool,
    blocked: bool,
    room: usize,
}

fn llm_arrow(cell: i64) -> Option<(isize, isize)> {
    match cell {
        62 => Some((1, 0)),
        60 => Some((-1, 0)),
        118 => Some((0, 1)),
        94 => Some((0, -1)),
        _ => None,
    }
}

fn llm_step(point: LlmPoint, direction: (isize, isize)) -> Option<LlmPoint> {
    Some(LlmPoint {
        x: usize::try_from(point.x as isize + direction.0).ok()?,
        y: usize::try_from(point.y as isize + direction.1).ok()?,
    })
}

fn llm_parse(
    cells: &[i64],
    width: usize,
    height: usize,
) -> Result<(Vec<LlmRoom>, Vec<LlmPipe>, Vec<LlmMan>), String> {
    let at = |point: LlmPoint| -> Option<i64> {
        (point.x < width && point.y < height).then_some(cells[point.y * width + point.x])
    };

    let mut rooms = Vec::new();
    let mut visited = vec![false; width * height];
    for y in 0..height {
        for x in 0..width {
            if cells[y * width + x] != 43 || visited[y * width + x] {
                continue;
            }
            let mut room_width = 1usize;
            while x + room_width < width && cells[y * width + x + room_width] == 45 {
                room_width += 1;
            }
            if x + room_width >= width || cells[y * width + x + room_width] != 43 {
                continue;
            }
            let mut room_height = 1usize;
            while y + room_height < height && cells[(y + room_height) * width + x] == 124 {
                room_height += 1;
            }
            if y + room_height >= height || cells[(y + room_height) * width + x] != 43 {
                continue;
            }
            let valid_bottom =
                (1..room_width).all(|dx| cells[(y + room_height) * width + x + dx] == 45);
            let valid_right =
                (1..room_height).all(|dy| cells[(y + dy) * width + x + room_width] == 124);
            if !valid_bottom
                || !valid_right
                || cells[(y + room_height) * width + x + room_width] != 43
            {
                continue;
            }
            for dx in 0..=room_width {
                visited[y * width + x + dx] = true;
                visited[(y + room_height) * width + x + dx] = true;
            }
            for dy in 0..=room_height {
                visited[(y + dy) * width + x] = true;
                visited[(y + dy) * width + x + room_width] = true;
            }
            rooms.push(LlmRoom {
                min: LlmPoint { x, y },
                max: LlmPoint {
                    x: x + room_width,
                    y: y + room_height,
                },
            });
        }
    }
    if rooms.is_empty() || rooms.len() > 3 {
        return Err(format!("bad LLM room count {}", rooms.len()));
    }

    let room_at = |point: LlmPoint| rooms.iter().position(|room| room.contains(point));
    let directions = [(1, 0), (-1, 0), (0, 1), (0, -1)];
    let mut candidate_pipes = Vec::new();
    for (source_room, room) in rooms.iter().enumerate() {
        for y in room.min.y..=room.max.y {
            for x in room.min.x..=room.max.x {
                let segment = LlmPoint { x, y };
                if !room.border(segment) {
                    continue;
                }
                for direction in directions {
                    let Some(start) = llm_step(segment, direction) else {
                        continue;
                    };
                    if start.x >= width
                        || start.y >= height
                        || room.contains(start)
                        || llm_arrow(at(start).unwrap()) != Some(direction)
                    {
                        continue;
                    }

                    let mut current = start;
                    let mut heading = direction;
                    let mut path = vec![current];
                    let dest_room = loop {
                        let next = llm_step(current, heading)
                            .ok_or_else(|| "LLM pipe left the source grid".to_string())?;
                        if let Some(dest_room) = room_at(next) {
                            if !rooms[dest_room].border(next) || path.len() < 2 {
                                return Err("invalid LLM pipe attachment".to_string());
                            }
                            break dest_room;
                        }
                        let cell =
                            at(next).ok_or_else(|| "LLM pipe left the source grid".to_string())?;
                        if let Some(next_heading) = llm_arrow(cell) {
                            if next_heading == (-heading.0, -heading.1) {
                                return Err("LLM pipe arrow points backward".to_string());
                            }
                            heading = next_heading;
                        } else if !((cell == 45 && heading.1 == 0)
                            || (cell == 124 && heading.0 == 0))
                        {
                            return Err(format!(
                                "invalid LLM pipe cell {cell} at {},{}",
                                next.x, next.y
                            ));
                        }
                        current = next;
                        path.push(current);
                    };
                    candidate_pipes.push(LlmPipe {
                        values: vec![None; path.len()],
                        path,
                        source_room,
                        dest_room,
                    });
                }
            }
        }
    }

    let mut pipes = Vec::new();
    for (index, candidate) in candidate_pipes.iter().enumerate() {
        let ghost = candidate_pipes
            .iter()
            .enumerate()
            .any(|(other_index, other)| {
                other_index != index
                    && other
                        .path
                        .iter()
                        .skip(1)
                        .any(|&point| point == candidate.path[0])
            });
        if !ghost {
            pipes.push(candidate.clone());
        }
    }
    if pipes.len() > 2 || pipes.iter().map(|pipe| pipe.path.len()).sum::<usize>() > 20 {
        return Err("LLM pipe constraints exceeded".to_string());
    }

    let mut men = Vec::new();
    for (room_index, room) in rooms.iter().enumerate() {
        for y in room.min.y + 1..room.max.y {
            for x in room.min.x + 1..room.max.x {
                if cells[y * width + x] == 64 {
                    men.push(LlmMan {
                        point: LlmPoint { x, y },
                        direction: 1,
                        a: 0,
                        b: 0,
                        halted: false,
                        blocked: false,
                        room: room_index,
                    });
                }
            }
        }
    }
    if men.len() != rooms.len() {
        return Err(format!(
            "LLM expected one man per room, found {} men in {} rooms",
            men.len(),
            rooms.len()
        ));
    }
    Ok((rooms, pipes, men))
}

fn llm_static_color(cell: i64) -> Result<i64, String> {
    match cell {
        32 | 64 => Ok(0),
        43 | 45 => Ok(10),
        48..=57 => Ok(8),
        60 | 62 | 72 | 88 | 94 | 118 => Ok(3),
        77 => Ok(12),
        114 | 115 => Ok(13),
        _ => Err(format!("bad LLM instruction ASCII value {cell}")),
    }
}

fn llm_frame(
    cells: &[i64],
    width: usize,
    _height: usize,
    rooms: &[LlmRoom],
    pipes: &[LlmPipe],
    men: &[LlmMan],
) -> Result<Vec<i64>, String> {
    let mut frame = vec![0; 16 * 16];
    for room in rooms {
        for y in room.min.y..=room.max.y {
            for x in room.min.x..=room.max.x {
                frame[y * 16 + x] = if room.border(LlmPoint { x, y }) {
                    4
                } else {
                    llm_static_color(cells[y * width + x])?
                };
            }
        }
    }
    for pipe in pipes {
        for (index, point) in pipe.path.iter().enumerate() {
            frame[point.y * 16 + point.x] = if pipe.values[index].is_some() { 14 } else { 6 };
        }
    }
    for man in men {
        frame[man.point.y * 16 + man.point.x] = 9;
    }
    Ok(frame)
}

fn llm_nearest_pipe(pipes: &[LlmPipe], man: &LlmMan, outgoing: bool) -> Result<usize, String> {
    let mut candidates = pipes
        .iter()
        .enumerate()
        .filter(|(_, pipe)| {
            if outgoing {
                pipe.source_room == man.room
            } else {
                pipe.dest_room == man.room
            }
        })
        .map(|(index, pipe)| {
            let endpoint = if outgoing {
                pipe.path[0]
            } else {
                *pipe.path.last().unwrap()
            };
            let distance = man.point.x.abs_diff(endpoint.x) + man.point.y.abs_diff(endpoint.y);
            (distance, endpoint.y, endpoint.x, index)
        })
        .collect::<Vec<_>>();
    candidates.sort_unstable();
    candidates
        .first()
        .map(|candidate| candidate.3)
        .ok_or_else(|| "LLM instruction has no pipe in the required direction".to_string())
}

fn llm_expected_frames(input: &[i64]) -> Result<Vec<Vec<i64>>, String> {
    if input.len() < 2 {
        return Err("LLM input is missing its dimensions".to_string());
    }
    let width = usize::try_from(input[0]).map_err(|_| "negative LLM width")?;
    let height = usize::try_from(input[1]).map_err(|_| "negative LLM height")?;
    if !(4..=16).contains(&width) || !(4..=16).contains(&height) {
        return Err(format!("bad LLM dimensions {width}x{height}"));
    }
    let cell_count = width * height;
    if input.len() < 2 + cell_count {
        return Err("LLM input is missing program cells".to_string());
    }
    let cells = input[2..2 + cell_count].to_vec();
    let (rooms, mut pipes, mut men) = llm_parse(&cells, width, height)?;
    let mut halted = false;
    let mut frames = vec![llm_frame(&cells, width, height, &rooms, &pipes, &men)?];

    for &ticks in &input[2 + cell_count..] {
        if halted {
            return Err("LLM input contains a command after halt".to_string());
        }
        if !(1..=64).contains(&ticks) {
            return Err(format!("bad LLM tick command {ticks}"));
        }
        for _ in 0..ticks {
            for pipe in &mut pipes {
                for index in (0..pipe.path.len() - 1).rev() {
                    if pipe.values[index].is_some() && pipe.values[index + 1].is_none() {
                        pipe.values[index + 1] = pipe.values[index].take();
                    }
                }
            }

            for man_index in 0..men.len() {
                if men[man_index].halted {
                    continue;
                }
                let cell = cells[men[man_index].point.y * width + men[man_index].point.x];
                let mut blocked = false;
                match cell {
                    32 | 64 => {}
                    48..=57 => men[man_index].a = cell - 48,
                    77 => men[man_index].b = men[man_index].a,
                    43 => men[man_index].a = men[man_index].a.wrapping_add(men[man_index].b),
                    45 => men[man_index].a = men[man_index].a.wrapping_sub(men[man_index].b),
                    94 => men[man_index].direction = 0,
                    62 => men[man_index].direction = 1,
                    118 => men[man_index].direction = 2,
                    60 => men[man_index].direction = 3,
                    88 => {
                        if men[man_index].a > 0 {
                            men[man_index].direction = (men[man_index].direction + 1) % 4;
                        } else if men[man_index].a < 0 {
                            men[man_index].direction = (men[man_index].direction + 3) % 4;
                        }
                    }
                    72 => men[man_index].halted = true,
                    115 => {
                        let pipe_index = llm_nearest_pipe(&pipes, &men[man_index], true)?;
                        if pipes[pipe_index].values[0].is_none() {
                            pipes[pipe_index].values[0] = Some(men[man_index].a);
                        } else {
                            blocked = true;
                        }
                    }
                    114 => {
                        let pipe_index = llm_nearest_pipe(&pipes, &men[man_index], false)?;
                        let last = pipes[pipe_index].values.len() - 1;
                        if let Some(value) = pipes[pipe_index].values[last].take() {
                            men[man_index].a = value;
                        } else {
                            blocked = true;
                        }
                    }
                    _ => return Err(format!("executed invalid LLM cell {cell}")),
                }
                men[man_index].blocked = blocked;
            }

            let mut wall_hit = false;
            for man in &mut men {
                if man.halted || man.blocked {
                    continue;
                }
                match man.direction {
                    0 => man.point.y -= 1,
                    1 => man.point.x += 1,
                    2 => man.point.y += 1,
                    3 => man.point.x -= 1,
                    _ => unreachable!(),
                }
                if rooms[man.room].border(man.point) {
                    wall_hit = true;
                }
            }
            halted = wall_hit || men.iter().all(|man| man.halted);
            if halted {
                break;
            }
        }
        frames.push(llm_frame(&cells, width, height, &rooms, &pipes, &men)?);
    }
    Ok(frames)
}

fn lllm_color(cell: i64, x: usize, y: usize, width: usize, height: usize) -> Result<i64, String> {
    if x == 0 || x + 1 == width || y == 0 || y + 1 == height {
        return Ok(4);
    }
    match cell {
        32 => Ok(0),
        43 | 45 => Ok(10),
        48..=57 => Ok(8),
        60 | 62 | 72 | 88 | 94 | 118 => Ok(3),
        64 => Ok(9),
        77 => Ok(12),
        _ => Err(format!("bad LLLM cell ASCII value {cell}")),
    }
}

fn lllm_frame(
    cells: &[i64],
    width: usize,
    height: usize,
    man_x: usize,
    man_y: usize,
) -> Result<Vec<i64>, String> {
    let mut frame = vec![0; 16 * 16];
    for y in 0..height {
        for x in 0..width {
            frame[y * 16 + x] = lllm_color(cells[y * width + x], x, y, width, height)?;
        }
    }
    frame[man_y * 16 + man_x] = 9;
    Ok(frame)
}

fn lllm_expected_frames(input: &[i64]) -> Result<Vec<Vec<i64>>, String> {
    if input.len() < 2 {
        return Err("LLLM input is missing its dimensions".to_string());
    }
    let width = usize::try_from(input[0]).map_err(|_| "negative LLLM width")?;
    let height = usize::try_from(input[1]).map_err(|_| "negative LLLM height")?;
    if !(4..=16).contains(&width) || !(4..=16).contains(&height) {
        return Err(format!("bad LLLM dimensions {width}x{height}"));
    }
    let cell_count = width * height;
    if input.len() < 2 + cell_count {
        return Err("LLLM input is missing program cells".to_string());
    }
    let mut cells = input[2..2 + cell_count].to_vec();
    let start = cells
        .iter()
        .position(|&cell| cell == 64)
        .ok_or_else(|| "LLLM program has no @".to_string())?;
    let mut x = start % width;
    let mut y = start / width;
    cells[start] = 32;

    let mut a = 0i64;
    let mut b = 0i64;
    let mut direction = 1usize;
    let mut halted = false;
    let mut frames = vec![lllm_frame(&cells, width, height, x, y)?];

    for &ticks in &input[2 + cell_count..] {
        if halted {
            return Err("LLLM input contains a command after halt".to_string());
        }
        if !(1..=64).contains(&ticks) {
            return Err(format!("bad LLLM tick command {ticks}"));
        }
        for _ in 0..ticks {
            let cell = cells[y * width + x];
            match cell {
                32 => {}
                48..=57 => a = cell - 48,
                77 => b = a,
                43 => a = a.wrapping_add(b),
                45 => a = a.wrapping_sub(b),
                94 => direction = 0,
                62 => direction = 1,
                118 => direction = 2,
                60 => direction = 3,
                88 => {
                    if a > 0 {
                        direction = (direction + 1) % 4;
                    } else if a < 0 {
                        direction = (direction + 3) % 4;
                    }
                }
                72 => {
                    halted = true;
                    break;
                }
                _ => return Err(format!("executed invalid LLLM cell {cell}")),
            }

            match direction {
                0 => y -= 1,
                1 => x += 1,
                2 => y += 1,
                3 => x -= 1,
                _ => unreachable!(),
            }
            if x == 0 || x + 1 == width || y == 0 || y + 1 == height {
                halted = true;
                break;
            }
        }
        frames.push(lllm_frame(&cells, width, height, x, y)?);
    }
    Ok(frames)
}

fn lllm_case(rows: &[&str], commands: &[i64]) -> Result<(Vec<i64>, Vec<Vec<i64>>), String> {
    let height = rows.len();
    let width = rows.first().map(|row| row.len()).unwrap_or(0);
    if rows.iter().any(|row| row.len() != width) {
        return Err("ragged LLLM test room".to_string());
    }
    let mut input = vec![width as i64, height as i64];
    for row in rows {
        input.extend(row.bytes().map(i64::from));
    }
    input.extend(commands);
    let frames = lllm_expected_frames(&input)?;
    Ok((input, frames))
}

fn published_lllm_tests() -> Result<Vec<(Vec<i64>, Vec<Vec<i64>>)>, String> {
    public_test_inputs(include_str!("../public_tests/lllm.json"))?
        .into_iter()
        .map(|input| {
            let expected = lllm_expected_frames(&input)?;
            Ok((input, expected))
        })
        .collect()
}

fn public_lllm_tests() -> Result<Vec<(Vec<i64>, Vec<Vec<i64>>)>, String> {
    let mut tests = vec![
        lllm_case(
            &[
                "+---------+",
                "|         |",
                "|@1M3>-X H|",
                "|         |",
                "|    ^ <  |",
                "|         |",
                "+---------+",
            ],
            &[
                1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            ],
        )?,
        lllm_case(&["+--+", "|@v|", "| H|", "+--+"], &[1, 1, 1])?,
        lllm_case(
            &[
                "+--------------+",
                "|              |",
                "|@1M9>-  X  H  |",
                "|              |",
                "|              |",
                "|    ^   <     |",
                "|              |",
                "|              |",
                "|              |",
                "|              |",
                "|              |",
                "|              |",
                "|              |",
                "|              |",
                "|              |",
                "+--------------+",
            ],
            &[17, 18, 2, 5, 6, 6, 28, 22, 4, 10, 24],
        )?,
        lllm_case(
            &["+---+", "|@ v|", "|   |", "|^ <|", "+---+"],
            &[1, 2, 1, 3, 2],
        )?,
        lllm_case(
            &[
                "+---------+",
                "|@3M1-X  v|",
                "|         |",
                "| H      <|",
                "|         |",
                "|         |",
                "+---------+",
            ],
            &[1, 2, 2, 1],
        )?,
    ];
    tests.extend(published_lllm_tests()?);
    Ok(tests)
}

fn published_llm_tests() -> Result<Vec<(Vec<i64>, Vec<Vec<i64>>)>, String> {
    public_test_inputs(include_str!("../public_tests/llm.json"))?
        .into_iter()
        .map(|input| {
            let expected = llm_expected_frames(&input)?;
            Ok((input, expected))
        })
        .collect()
}

fn llm_case(rows: &[&str], commands: &[i64]) -> Result<(Vec<i64>, Vec<Vec<i64>>), String> {
    let height = rows.len();
    let width = rows.first().map(|row| row.len()).unwrap_or(0);
    if rows.iter().any(|row| row.len() != width) {
        return Err("ragged LLM test program".to_string());
    }
    let mut input = vec![width as i64, height as i64];
    for row in rows {
        input.extend(row.bytes().map(i64::from));
    }
    input.extend(commands);
    let frames = llm_expected_frames(&input)?;
    Ok((input, frames))
}

fn llm_tests() -> Result<Vec<(Vec<i64>, Vec<Vec<i64>>)>, String> {
    let mut tests = vec![
        llm_case(
            &[
                "+---+     +----+",
                "|@H |     |    |",
                "|   |     |    |",
                "|   |>--->|@rH |",
                "+---+|    +----+",
                "     |          ",
                "     |          ",
                "     ^          ",
                "    +----+      ",
                "    |@sH |      ",
                "    |    |      ",
                "    |    |      ",
                "    +----+      ",
            ],
            &[12],
        )?,
        llm_case(
            &[
                "+-------+   +--+",
                "|@1sssH |   |@H|",
                "|       |   |  |",
                "|       |>->|  |",
                "+-------+   +--+",
            ],
            &[5, 2],
        )?,
    ];
    tests.extend(published_llm_tests()?);
    Ok(tests)
}

fn program_room_output_path(output: &str) -> String {
    output
        .strip_suffix(".man")
        .map(|base| format!("{base}_program_room.txt"))
        .unwrap_or_else(|| "program_room.txt".to_string())
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    let register_mode = if args.iter().any(|arg| arg == "--two-lane-registers") {
        RegisterBankMode::TwoLane
    } else {
        RegisterBankMode::SingleLane
    };
    let positional = args
        .iter()
        .skip(1)
        .filter(|arg| !arg.starts_with("--"))
        .collect::<Vec<_>>();
    let input = positional
        .first()
        .map(|arg| arg.as_str())
        .unwrap_or("brackets.asm");
    let output = positional
        .get(1)
        .map(|arg| arg.as_str())
        .unwrap_or("brackets_processor.man");

    let source = fs::read_to_string(input)?;
    let build = build(&source).map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?;
    let template_path = "meta_template.mod";
    let meta = fs::read_to_string(template_path)?;
    let cpu = fs::read_to_string("cpu.mod")?;
    let cpu_screen = fs::read_to_string("cpu_screen.mod")?;
    let memory = fs::read_to_string("memory.mod")?;
    let modules = FloorModules {
        meta: &meta,
        cpu: &cpu,
        cpu_screen: &cpu_screen,
        memory: &memory,
    };
    let layout = render_meta_floor(&build, &modules, register_mode)
        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?;
    fs::write(output, layout.man.as_bytes())?;

    let room_output = program_room_output_path(output);
    fs::write(&room_output, layout.room.as_bytes())?;

    println!("assembled words: {}", build.program.words.len());
    println!("register slots: {}", build.register_count);
    println!(
        "register bank: {}",
        match register_mode {
            RegisterBankMode::SingleLane => "single-lane",
            RegisterBankMode::TwoLane => "two-lane",
        }
    );
    if register_mode == RegisterBankMode::TwoLane && build.register_count % 2 != 0 {
        println!("physical register cells: {}", build.register_count + 1);
    }
    println!("memory slots: {}", build.memory_size);
    if build.memory_size > 0 {
        println!("memory pipe cells: {}", build.memory_pipe_cells);
    }
    match build.screen {
        Some(screen) => println!("screen: {}x{}", screen.width, screen.height),
        None => println!("screen: none"),
    }
    println!("template: {}", template_path);
    println!("man file: {}", output);
    println!("program room file: {}", room_output);
    let interior = layout
        .room
        .lines()
        .nth(1)
        .map(|line| line.len() - 2)
        .unwrap_or(0);
    let height = layout.room.lines().count() - 2;
    println!("program room interior: {}x{}", interior, height);
    println!(
        "program room orientation: {}",
        match layout.orientation {
            CodeOrientation::Horizontal => "horizontal",
            CodeOrientation::Vertical => "vertical",
        }
    );
    println!("program pipe cells: {}", layout.pipe_cells);

    if args.iter().any(|arg| arg == "--test") {
        if let Some(screen) = build.screen {
            match build.program_kind {
                ProgramKind::Plotter => {
                    for (idx, (input, expected)) in public_plotter_tests()
                        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?
                        .into_iter()
                        .enumerate()
                    {
                        let got = run_screen_vm_until_frames(
                            &build.program,
                            screen,
                            &input,
                            expected.len(),
                            5_000_000,
                        )
                        .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                        if got != expected {
                            return Err(io::Error::new(
                                io::ErrorKind::Other,
                                format!("plotter test {} failed", idx + 1),
                            ));
                        }
                    }
                    println!("public plotter-style tests: ok");
                }
                ProgramKind::Snake => {
                    for (idx, (input, expected)) in public_snake_tests()
                        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?
                        .into_iter()
                        .enumerate()
                    {
                        let got = run_screen_vm_until_frames(
                            &build.program,
                            screen,
                            &input,
                            expected.len(),
                            5_000_000,
                        )
                        .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                        if got != expected {
                            return Err(io::Error::new(
                                io::ErrorKind::Other,
                                format!("snake test {} failed", idx + 1),
                            ));
                        }
                    }
                    println!("snake frame tests: ok");
                }
                ProgramKind::Pathfinder => {
                    for (idx, (input, expected)) in published_pathfinder_tests()
                        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?
                        .into_iter()
                        .enumerate()
                    {
                        let got = run_screen_vm_until_frames(
                            &build.program,
                            screen,
                            &input,
                            expected.len(),
                            20_000_000,
                        )
                        .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                        if got != expected {
                            let detail = got
                                .iter()
                                .zip(&expected)
                                .enumerate()
                                .find_map(|(frame, (actual, wanted))| {
                                    actual
                                        .iter()
                                        .zip(wanted)
                                        .position(|(a, b)| a != b)
                                        .map(|pixel| {
                                            format!(
                                                "frame {}, pixel {}: expected {}, got {}; robots expected {:?}, got {:?}",
                                                frame + 1,
                                                pixel,
                                                wanted[pixel],
                                                actual[pixel],
                                                wanted.iter().position(|&value| value == 10),
                                                actual.iter().position(|&value| value == 10)
                                            )
                                        })
                                })
                                .unwrap_or_else(|| {
                                    format!(
                                        "frame count: expected {}, got {}",
                                        expected.len(),
                                        got.len()
                                    )
                                });
                            return Err(io::Error::new(
                                io::ErrorKind::Other,
                                format!("Pathfinder test {} failed: {detail}", idx + 1),
                            ));
                        }
                    }
                    println!("Pathfinder frame tests: ok");
                }
                ProgramKind::Lllm => {
                    for (idx, (input, expected)) in public_lllm_tests()
                        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?
                        .into_iter()
                        .enumerate()
                    {
                        let got = run_screen_vm_until_frames(
                            &build.program,
                            screen,
                            &input,
                            expected.len(),
                            5_000_000,
                        )
                        .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                        if got != expected {
                            return Err(io::Error::new(
                                io::ErrorKind::Other,
                                format!("LLLM test {} failed", idx + 1),
                            ));
                        }
                    }
                    println!("LLLM frame tests: ok");
                }
                ProgramKind::Llm => {
                    for (idx, (input, expected)) in llm_tests()
                        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?
                        .into_iter()
                        .enumerate()
                    {
                        let got = run_screen_vm_until_frames(
                            &build.program,
                            screen,
                            &input,
                            expected.len(),
                            20_000_000,
                        )
                        .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                        if got != expected {
                            let frame = got
                                .iter()
                                .zip(&expected)
                                .position(|(actual, wanted)| actual != wanted)
                                .unwrap_or(got.len().min(expected.len()));
                            let pixel = got
                                .get(frame)
                                .zip(expected.get(frame))
                                .and_then(|(actual, wanted)| {
                                    actual
                                        .iter()
                                        .zip(wanted)
                                        .position(|(actual, wanted)| actual != wanted)
                                        .map(|pixel| (pixel, actual[pixel], wanted[pixel]))
                                });
                            return Err(io::Error::new(
                                io::ErrorKind::Other,
                                format!(
                                    "LLM test {} failed at frame {}{}",
                                    idx + 1,
                                    frame + 1,
                                    pixel.map_or_else(String::new, |(index, actual, wanted)| {
                                        format!(
                                            ", pixel {index}: expected {wanted}, got {actual}"
                                        )
                                    })
                                ),
                            ));
                        }
                    }
                    println!("LLM frame tests: ok");
                }
                ProgramKind::Generic | ProgramKind::Matmul => {
                    run_screen_vm_until_frames(&build.program, screen, &[], 1, 20_000_000)
                        .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                    println!("screen program smoke test: ok");
                }
            }
        } else if build.program_kind == ProgramKind::Matmul
            || source.lines().any(|line| {
                tokenize(strip_comment(line))
                    .iter()
                    .any(|tok| tok == "matmul")
            })
        {
            for (idx, (input, expected)) in public_matmul_tests()
                .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?
                .into_iter()
                .enumerate()
            {
                let got = run_vm_until_outputs(&build.program, &input, expected.len(), 200_000_000)
                    .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                if got != expected {
                    return Err(io::Error::new(
                        io::ErrorKind::Other,
                        format!(
                            "matmul test {} failed: expected {:?}, got {:?}",
                            idx + 1,
                            expected,
                            got
                        ),
                    ));
                }
            }
            println!("public matmul-style tests: ok");
        } else {
            for (idx, (input, expected)) in public_bracket_tests()
                .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?
                .into_iter()
                .enumerate()
            {
                let got = run_vm(&build.program, &input, 100_000)
                    .map_err(|err| io::Error::new(io::ErrorKind::Other, err))?;
                if got.first().copied() != Some(expected) {
                    return Err(io::Error::new(
                        io::ErrorKind::Other,
                        format!(
                            "test {} failed: expected {}, got {:?}",
                            idx + 1,
                            expected,
                            got
                        ),
                    ));
                }
            }
            println!("public bracket tests: ok");
        }
    }

    Ok(())
}
