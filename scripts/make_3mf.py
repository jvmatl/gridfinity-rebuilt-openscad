#!/usr/bin/env python3
"""Package aligned STL parts into one simple multi-object 3MF file."""
from __future__ import annotations

import argparse
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

MODEL_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Output .3mf path")
    parser.add_argument(
        "--part",
        action="append",
        required=True,
        metavar="NAME=PATH",
        help="Part name and STL path. Repeat for every object.",
    )
    parser.add_argument(
        "--assembly-name",
        help="If set, create one build item as an assembly containing all parts.",
    )
    parser.add_argument(
        "--material",
        action="append",
        default=[],
        metavar="PART=MATERIAL_NAME:HEX",
        help="Assign a Core 3MF base material and display color to a part, e.g. body='Filament 1 White:#FFFFFF'.",
    )
    return parser.parse_args()


def parse_material(value: str) -> tuple[str, tuple[str, str]]:
    if "=" not in value or ":" not in value:
        raise SystemExit(f"--material must be PART=MATERIAL_NAME:HEX, got: {value}")
    part, rest = value.split("=", 1)
    material_name, color = rest.rsplit(":", 1)
    part = part.strip()
    material_name = material_name.strip()
    color = normalize_color(color.strip())
    if not part or not material_name:
        raise SystemExit(f"invalid material assignment: {value}")
    return part, (material_name, color)


def normalize_color(color: str) -> str:
    if not color.startswith("#"):
        color = "#" + color
    digits = color[1:]
    if len(digits) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in digits):
        raise SystemExit(f"material color must be #RRGGBB or #RRGGBBAA, got: {color}")
    return "#" + digits.upper()


def parse_part(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise SystemExit(f"--part must be NAME=PATH, got: {value}")
    name, path = value.split("=", 1)
    name = name.strip()
    if not name:
        raise SystemExit(f"empty part name in: {value}")
    stl_path = Path(path)
    if not stl_path.is_file():
        raise SystemExit(f"STL file not found: {stl_path}")
    return name, stl_path


def read_stl(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    data = path.read_bytes()
    if looks_like_binary_stl(data):
        triangles = read_binary_stl(data, path)
    else:
        triangles = read_ascii_stl(data.decode("utf-8", errors="replace"), path)
    return dedupe_vertices(triangles)


def looks_like_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    count = struct.unpack_from("<I", data, 80)[0]
    return 84 + count * 50 == len(data)


def read_binary_stl(data: bytes, path: Path) -> list[tuple[tuple[float, float, float], ...]]:
    count = struct.unpack_from("<I", data, 80)[0]
    triangles = []
    offset = 84
    for _ in range(count):
        values = struct.unpack_from("<12fH", data, offset)
        triangles.append((values[3:6], values[6:9], values[9:12]))
        offset += 50
    if not triangles:
        raise SystemExit(f"no triangles found in {path}")
    return triangles


def read_ascii_stl(text: str, path: Path) -> list[tuple[tuple[float, float, float], ...]]:
    vertices = []
    triangles = []
    for line in text.splitlines():
        fields = line.strip().split()
        if len(fields) == 4 and fields[0].lower() == "vertex":
            vertices.append(tuple(float(v) for v in fields[1:4]))
            if len(vertices) == 3:
                triangles.append(tuple(vertices))
                vertices = []
    if not triangles:
        raise SystemExit(f"no ASCII STL triangles found in {path}")
    return triangles


def dedupe_vertices(triangles_in):
    vertices: list[tuple[float, float, float]] = []
    vertex_ids: dict[tuple[float, float, float], int] = {}
    triangles: list[tuple[int, int, int]] = []
    for tri in triangles_in:
        ids = []
        for vertex in tri:
            key = tuple(round(float(c), 6) for c in vertex)
            if key not in vertex_ids:
                vertex_ids[key] = len(vertices)
                vertices.append(key)
            ids.append(vertex_ids[key])
        if len(set(ids)) == 3:
            triangles.append(tuple(ids))
    if not triangles:
        raise SystemExit("all triangles were degenerate")
    return vertices, triangles


def fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def object_xml(object_id: int, name: str, vertices, triangles, property_ref: tuple[int, int] | None = None) -> str:
    property_attrs = "" if property_ref is None else f' pid="{property_ref[0]}" pindex="{property_ref[1]}"'
    lines = [f'    <object id="{object_id}" type="model" name="{escape(name)}"{property_attrs}>', "      <mesh>", "        <vertices>"]
    for x, y, z in vertices:
        lines.append(f'          <vertex x="{fmt(x)}" y="{fmt(y)}" z="{fmt(z)}" />')
    lines.append("        </vertices>")
    lines.append("        <triangles>")
    triangle_property_attrs = ""
    if property_ref is not None:
        triangle_property_attrs = f' pid="{property_ref[0]}" p1="{property_ref[1]}" p2="{property_ref[1]}" p3="{property_ref[1]}"'
    for v1, v2, v3 in triangles:
        lines.append(f'          <triangle v1="{v1}" v2="{v2}" v3="{v3}"{triangle_property_attrs} />')
    lines.extend(["        </triangles>", "      </mesh>", "    </object>"])
    return "\n".join(lines)


def components_object_xml(object_id: int, name: str, component_ids: list[int]) -> str:
    lines = [f'    <object id="{object_id}" type="model" name="{escape(name)}">', "      <components>"]
    for component_id in component_ids:
        lines.append(f'        <component objectid="{component_id}" />')
    lines.extend(["      </components>", "    </object>"])
    return "\n".join(lines)


def base_materials_xml(resource_id: int, materials: list[tuple[str, str]]) -> str:
    lines = [f'    <basematerials id="{resource_id}">']
    for name, color in materials:
        lines.append(f'      <base name="{escape(name)}" displaycolor="{color}" />')
    lines.append("    </basematerials>")
    return "\n".join(lines)


def model_xml(parts, assembly_name: str | None = None, material_by_part: dict[str, tuple[str, str]] | None = None) -> str:
    material_by_part = material_by_part or {}
    objects = []
    mesh_object_ids = []
    base_materials = []
    material_index_by_part = {}

    if material_by_part:
        for part_name, _path in parts:
            if part_name in material_by_part:
                material_index_by_part[part_name] = len(base_materials)
                base_materials.append(material_by_part[part_name])

    material_resource_id = len(parts) + 2 if base_materials else None

    for object_id, (name, path) in enumerate(parts, start=1):
        vertices, triangles = read_stl(path)
        property_ref = None
        if material_resource_id is not None and name in material_index_by_part:
            property_ref = (material_resource_id, material_index_by_part[name])
        objects.append(object_xml(object_id, name, vertices, triangles, property_ref))
        mesh_object_ids.append(object_id)

    if assembly_name:
        assembly_id = len(parts) + 1
        objects.append(components_object_xml(assembly_id, assembly_name, mesh_object_ids))
        build_items = [f'      <item objectid="{assembly_id}" />']
    else:
        build_items = [f'      <item objectid="{object_id}" />' for object_id in mesh_object_ids]

    material_resources = [] if material_resource_id is None else [base_materials_xml(material_resource_id, base_materials)]

    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{MODEL_NS}">',
        "  <resources>",
        *material_resources,
        *objects,
        "  </resources>",
        "  <build>",
        *build_items,
        "  </build>",
        "</model>",
        "",
    ])


def write_3mf(output: Path, parts, assembly_name: str | None = None, material_by_part: dict[str, tuple[str, str]] | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "\n".join([
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />',
            '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />',
            '</Types>',
            '',
        ]))
        zf.writestr("_rels/.rels", "\n".join([
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<Relationships xmlns="{REL_NS}">',
            '  <Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" />',
            '</Relationships>',
            '',
        ]))
        zf.writestr("3D/3dmodel.model", model_xml(parts, assembly_name, material_by_part))


def main() -> None:
    args = parse_args()
    parts = [parse_part(value) for value in args.part]
    material_by_part = dict(parse_material(value) for value in args.material)
    known_parts = {name for name, _path in parts}
    unknown_parts = sorted(set(material_by_part) - known_parts)
    if unknown_parts:
        raise SystemExit(f"material assignments reference unknown parts: {', '.join(unknown_parts)}")
    write_3mf(Path(args.output), parts, args.assembly_name, material_by_part)


if __name__ == "__main__":
    main()
