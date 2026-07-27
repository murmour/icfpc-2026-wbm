"""A small reference model used by tests and the simulator verifier."""

from __future__ import annotations

from collections.abc import Iterable


class InputError(ValueError):
    pass


def run_memory_stream(values: Iterable[int], capacity: int = 100) -> list[int]:
    stream = iter(values)
    memory = [0] * capacity
    output: list[int] = []
    while True:
        try:
            operation = next(stream)
        except StopIteration:
            return output
        try:
            address = next(stream)
        except StopIteration as error:
            raise InputError("truncated operation: missing address") from error
        if not 0 <= address < capacity:
            raise InputError(f"address {address} is outside 0..{capacity - 1}")
        if operation == 0:
            output.append(memory[address])
        elif operation == 1:
            try:
                memory[address] = next(stream)
            except StopIteration as error:
                raise InputError("truncated WRITE: missing value") from error
        else:
            raise InputError(f"unsupported operation {operation}")


def run_sudoku_stream(values: Iterable[int]) -> list[int]:
    stream = iter(values)
    row_masks = [0] * 9
    column_masks = [0] * 9
    box_masks = [0] * 9
    seen_cells: set[tuple[int, int]] = set()
    output: list[int] = []

    while True:
        try:
            row = next(stream)
        except StopIteration:
            return output
        try:
            column = next(stream)
            value = next(stream)
        except StopIteration as error:
            raise InputError("truncated Sudoku round") from error
        if not 0 <= row <= 8 or not 0 <= column <= 8:
            raise InputError(f"cell ({row}, {column}) is outside the Sudoku grid")
        if not 1 <= value <= 9:
            raise InputError(f"Sudoku value {value} is outside 1..9")
        if (row, column) in seen_cells:
            raise InputError(f"cell ({row}, {column}) was submitted twice")
        seen_cells.add((row, column))

        bit = 1 << (value - 1)
        box = (row // 3) * 3 + column // 3
        if (row_masks[row] | column_masks[column] | box_masks[box]) & bit:
            output.append(0)
            return output

        row_masks[row] |= bit
        column_masks[column] |= bit
        box_masks[box] |= bit
        output.append(1)


def run_sort_stream(values: Iterable[int]) -> list[int]:
    stream = iter(values)
    output: list[int] = []
    while True:
        try:
            length = next(stream)
        except StopIteration:
            return output
        if not 1 <= length <= 16:
            raise InputError(f"Sort length {length} is outside 1..16")
        items: list[int] = []
        for _ in range(length):
            try:
                item = next(stream)
            except StopIteration as error:
                raise InputError("truncated Sort list") from error
            if not -10_000 <= item <= 10_000:
                raise InputError(f"Sort value {item} is outside -10000..10000")
            items.append(item)
        output.extend(sorted(items))


def run_packet_stream(values: Iterable[int]) -> list[int]:
    stream = iter(values)

    def read(label: str) -> int:
        try:
            return next(stream)
        except StopIteration as error:
            raise InputError(
                f"truncated Packet Reassembly input: missing {label}"
            ) from error

    packet_count = read("packet count")
    if not 1 <= packet_count <= 48:
        raise InputError(
            f"Packet Reassembly count {packet_count} is outside 1..48"
        )

    waiting = 0
    window = [0] * 16
    present = 0
    seen: set[int] = set()
    output: list[int] = []

    for _ in range(packet_count):
        sequence = read("sequence number")
        value = read("packet value")
        if not 0 <= sequence < packet_count:
            raise InputError(
                f"Packet sequence {sequence} is outside 0..{packet_count - 1}"
            )
        if sequence in seen:
            raise InputError(f"duplicate Packet sequence {sequence}")
        if not 1 <= value <= 999:
            raise InputError(f"Packet value {value} is outside 1..999")
        seen.add(sequence)

        offset = sequence - waiting
        if offset >= 16:
            output.append(-1)
            return output
        if offset < 0:
            raise InputError(
                f"Packet sequence {sequence} is behind waiting={waiting}"
            )

        window[offset] = value
        present |= 1 << offset
        while present & 1:
            output.append(window[0])
            window = window[1:] + window[:1]
            present >>= 1
            waiting += 1

    return output


def run_gradebook_stream(values: Iterable[int]) -> list[int]:
    stream = iter(values)

    def read(label: str) -> int:
        try:
            return next(stream)
        except StopIteration as error:
            raise InputError(f"truncated Grade Book input: missing {label}") from error

    student_count = read("student count")
    subject_count = read("subject count")
    if not 4 <= student_count <= 16:
        raise InputError(
            f"Grade Book student count {student_count} is outside 4..16"
        )
    if not 1 <= subject_count <= 4:
        raise InputError(
            f"Grade Book subject count {subject_count} is outside 1..4"
        )

    grades: dict[int, list[int]] = {}
    for _ in range(student_count):
        student_id = read("student id")
        if not 1000 <= student_id <= 9999:
            raise InputError(f"student id {student_id} is outside 1000..9999")
        if student_id in grades:
            raise InputError(f"duplicate student id {student_id}")
        row = [read("grade") for _ in range(subject_count)]
        if any(not 0 <= grade <= 100 for grade in row):
            raise InputError(f"grade outside 0..100 in row for {student_id}")
        grades[student_id] = row

    output: list[int] = []
    while True:
        try:
            operation_count = next(stream)
        except StopIteration:
            return output
        if not 1 <= operation_count <= 8:
            raise InputError(
                f"Grade Book operation count {operation_count} is outside 1..8"
            )
        for _ in range(operation_count):
            opcode = read("operation code")
            if opcode == 1:
                student_id = read("GET student id")
                subject = read("GET subject")
                _validate_gradebook_reference(
                    grades,
                    subject_count,
                    student_id,
                    subject,
                )
                output.append(grades[student_id][subject - 1])
            elif opcode == 2:
                student_id = read("SET student id")
                subject = read("SET subject")
                value = read("SET value")
                _validate_gradebook_reference(
                    grades,
                    subject_count,
                    student_id,
                    subject,
                )
                if not 0 <= value <= 100:
                    raise InputError(f"SET grade {value} is outside 0..100")
                grades[student_id][subject - 1] = value
            elif opcode == 3:
                subject = read("AVG subject")
                _validate_gradebook_subject(subject_count, subject)
                output.append(
                    sum(row[subject - 1] for row in grades.values())
                    // student_count
                )
            elif opcode == 4:
                subject = read("TOP subject")
                _validate_gradebook_subject(subject_count, subject)
                output.append(
                    min(
                        grades,
                        key=lambda student_id: (
                            -grades[student_id][subject - 1],
                            student_id,
                        ),
                    )
                )
            else:
                raise InputError(f"unsupported Grade Book operation {opcode}")


def _validate_gradebook_subject(subject_count: int, subject: int) -> None:
    if not 1 <= subject <= subject_count:
        raise InputError(
            f"Grade Book subject {subject} is outside 1..{subject_count}"
        )


def _validate_gradebook_reference(
    grades: dict[int, list[int]],
    subject_count: int,
    student_id: int,
    subject: int,
) -> None:
    if student_id not in grades:
        raise InputError(f"unknown student id {student_id}")
    _validate_gradebook_subject(subject_count, subject)
