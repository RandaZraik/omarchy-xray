from __future__ import annotations

from pathlib import Path


def stat_line(
    pid: int,
    name: str,
    ppid: int,
    start: int,
    *,
    ticks: int = 1,
    rss_pages: int = 0,
) -> str:
    fields = (
        ["S", str(ppid)]
        + ["0"] * 9
        + [str(ticks), "0"]
        + ["0"] * 4
        + ["1", "0", str(start), "0", str(rss_pages)]
    )
    return f"{pid} ({name}) " + " ".join(fields) + "\n"


def write_process(
    root: Path,
    pid: int,
    name: str,
    ppid: int,
    *,
    start: int = 10,
    uid: int = 1000,
    gid: int = 1000,
    ticks: int = 1,
    rss_pages: int = 0,
    command: bytes | None = None,
    environ: bytes | None = None,
    cgroup: str | None = None,
    executable: str | None = None,
    working_directory: str | None = None,
    status_lines: tuple[str, ...] = (),
) -> Path:
    process = root / str(pid)
    process.mkdir(exist_ok=True)
    (process / "stat").write_text(
        stat_line(pid, name, ppid, start, ticks=ticks, rss_pages=rss_pages),
        encoding="utf-8",
    )
    status = [
        f"Name:\t{name}",
        f"Uid:\t{uid} {uid} {uid} {uid}",
        f"Gid:\t{gid} {gid} {gid} {gid}",
        *status_lines,
    ]
    (process / "status").write_text("\n".join(status) + "\n", encoding="utf-8")
    if command is not None:
        (process / "cmdline").write_bytes(command)
    if environ is not None:
        (process / "environ").write_bytes(environ)
    if cgroup is not None:
        (process / "cgroup").write_text(cgroup, encoding="utf-8")
    if executable is not None:
        (process / "exe").symlink_to(executable)
    if working_directory is not None:
        (process / "cwd").symlink_to(working_directory)
    return process
