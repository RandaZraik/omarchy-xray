from __future__ import annotations

import json
from pathlib import Path
import subprocess


REVISIONS = {
    "bandwhich": "1899870cea8bb377948f05cfea64733ec6ea2cd6",
    "sniffnet": "6b4562554841631e00c56576c2c439b8de6e1747",
}


def build_reference(checkouts: Path, build: Path) -> Path:
    for name, revision in REVISIONS.items():
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=checkouts / name, text=True
        ).strip()
        if actual != revision:
            raise ValueError(f"{name} reference is {actual}, expected {revision}")
    build.mkdir(parents=True, exist_ok=True)
    source = build / "src"
    source.mkdir(exist_ok=True)
    template = Path(__file__).with_suffix(".rs").read_text()
    lookup_source = (
        checkouts / "sniffnet/src/networking/types/program_lookup.rs"
    ).read_text()
    lookup = lookup_source[
        lookup_source.index("pub fn lookup_program(") : lookup_source.index(
            "pub fn get_picon("
        )
    ]
    (source / "main.rs").write_text(
        template.replace("@BANDWHICH@", str(checkouts / "bandwhich")).replace(
            "@SNIFFNET_LOOKUP@", lookup
        )
    )
    manifest = f"""[package]
name = "xray-network-reference"
version = "0.1.0"
edition = "2021"

[dependencies]
pnet = "0.35.0"
procfs = "0.18.0"
listeners = "=0.6.1"
serde_json = "1"
pcap = "2"
sniffnet-packet-parser = {{ path = {json.dumps(str(checkouts / "sniffnet/lib/sniffnet-packet-parser"))} }}
"""
    (build / "Cargo.toml").write_text(manifest)
    subprocess.run(
        ["cargo", "build", "--quiet", "--manifest-path", str(build / "Cargo.toml")],
        check=True,
    )
    return build / "target/debug/xray-network-reference"


def compare(
    reference: Path, frames: list[dict[str, object]], ports: list[int] | None = None
) -> dict[str, object]:
    completed = subprocess.run(
        [str(reference)],
        input=json.dumps({"frames": frames, "ports": ports or []}),
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    return json.loads(completed.stdout)
