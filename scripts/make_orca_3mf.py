#!/usr/bin/env python3
"""Package aligned STL parts into an Orca/Bambu project-style 3MF with per-part extruders."""
from __future__ import annotations

import argparse
import importlib.util
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

MODEL_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
BAMBU_NS = "http://schemas.bambulab.com/package/2021"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DEFAULT_BUILD_TRANSFORM = "1 0 0 0 1 0 0 0 1 135.5 136 0"


def load_core_helper():
    helper_path = Path(__file__).with_name("make_3mf.py")
    spec = importlib.util.spec_from_file_location("make_3mf_helper", helper_path)
    helper = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(helper)
    return helper


helper = load_core_helper()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Output Orca/Bambu project-style .3mf path")
    parser.add_argument("--part", action="append", required=True, metavar="NAME=PATH", help="Part name and STL path. Repeat for every mesh.")
    parser.add_argument("--extruder", action="append", required=True, metavar="NAME=N", help="1-based Orca extruder/filament slot for a part.")
    parser.add_argument("--filament-color", action="append", default=[], metavar="N=#RRGGBB", help="1-based filament slot display color.")
    parser.add_argument("--template", help="Optional Orca/Bambu 3MF to copy project settings and thumbnails from.")
    parser.add_argument("--assembly-name", default="assembled_model", help="Object/assembly name shown in OrcaSlicer.")
    parser.add_argument("--build-transform", default=DEFAULT_BUILD_TRANSFORM, help="Top-level build transform. Default places object near a common bed center.")
    return parser.parse_args()


def parse_name_value(value: str, option: str) -> tuple[str, str]:
    if "=" not in value:
        raise SystemExit(f"{option} must be NAME=VALUE, got: {value}")
    name, raw = value.split("=", 1)
    name = name.strip()
    raw = raw.strip()
    if not name or not raw:
        raise SystemExit(f"invalid {option}: {value}")
    return name, raw


def parse_parts(values: list[str]) -> list[dict]:
    parts = []
    for i, value in enumerate(values, start=1):
        name, raw_path = parse_name_value(value, "--part")
        path = Path(raw_path)
        if not path.is_file():
            raise SystemExit(f"STL not found for part {name}: {path}")
        parts.append({"id": i, "name": name, "path": path})
    return parts


def apply_extruders(parts: list[dict], values: list[str]) -> None:
    part_by_name = {part["name"]: part for part in parts}
    for value in values:
        name, raw = parse_name_value(value, "--extruder")
        if name not in part_by_name:
            raise SystemExit(f"--extruder references unknown part: {name}")
        extruder = int(raw)
        if extruder < 1:
            raise SystemExit(f"extruder slots are 1-based; got {extruder} for {name}")
        part_by_name[name]["extruder"] = extruder
    missing = [part["name"] for part in parts if "extruder" not in part]
    if missing:
        raise SystemExit(f"missing --extruder assignments for: {', '.join(missing)}")


def parse_filament_colors(values: list[str]) -> dict[int, str]:
    colors = {}
    for value in values:
        slot_raw, color = parse_name_value(value, "--filament-color")
        slot = int(slot_raw)
        if slot < 1:
            raise SystemExit(f"filament color slots are 1-based; got {slot}")
        colors[slot] = helper.normalize_color(color)
    return colors


def prepare_meshes(parts: list[dict]) -> None:
    for part in parts:
        vertices, triangles = helper.read_stl(part["path"])
        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        zs = [v[2] for v in vertices]
        center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
        part["center"] = center
        part["vertices"] = [(x - center[0], y - center[1], z - center[2]) for x, y, z in vertices]
        part["triangles"] = triangles


def fmt(value: float) -> str:
    return helper.fmt(value)


def transform12(center) -> str:
    return f"1 0 0 0 1 0 0 0 1 {fmt(center[0])} {fmt(center[1])} {fmt(center[2])}"


def matrix16(center) -> str:
    return f"1 0 0 {fmt(center[0])} 0 1 0 {fmt(center[1])} 0 0 1 {fmt(center[2])} 0 0 0 1"


def nested_object_xml(part: dict) -> str:
    lines = [
        f'  <object id="{part["id"]}" p:UUID="0001000{part["id"] - 1}-81cb-4c03-9d28-80fed5dfa1dc" type="model" name="{escape(part["name"])}">',
        "   <mesh>",
        "    <vertices>",
    ]
    for x, y, z in part["vertices"]:
        lines.append(f'     <vertex x="{fmt(x)}" y="{fmt(y)}" z="{fmt(z)}"/>')
    lines.extend(["    </vertices>", "    <triangles>"])
    for v1, v2, v3 in part["triangles"]:
        lines.append(f'     <triangle v1="{v1}" v2="{v2}" v3="{v3}"/>')
    lines.extend(["    </triangles>", "   </mesh>", "  </object>"])
    return "\n".join(lines)


def nested_model_xml(parts: list[dict]) -> str:
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{MODEL_NS}" xmlns:BambuStudio="{BAMBU_NS}" xmlns:p="{PROD_NS}" requiredextensions="p">',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        ' <resources>',
        *(nested_object_xml(part) for part in parts),
        ' </resources>',
        '</model>',
        '',
    ])


def top_model_xml(parts: list[dict], nested_name: str, assembly_name: str, build_transform: str) -> str:
    component_lines = []
    for part in parts:
        component_lines.append(
            f'    <component p:path="/3D/Objects/{nested_name}" objectid="{part["id"]}" '
            f'p:UUID="0001000{part["id"] - 1}-b206-40ff-9872-83e8017abed1" '
            f'transform="{transform12(part["center"])}"/>'
        )
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<model unit="millimeter" xml:lang="en-US" xmlns="{MODEL_NS}" xmlns:BambuStudio="{BAMBU_NS}" xmlns:p="{PROD_NS}" requiredextensions="p">',
        ' <metadata name="Application">BambuStudio-2.3.3</metadata>',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        ' <metadata name="Copyright"></metadata>',
        ' <metadata name="CreationDate"></metadata>',
        ' <metadata name="Description"></metadata>',
        ' <metadata name="Designer"></metadata>',
        ' <metadata name="DesignerCover"></metadata>',
        ' <metadata name="DesignerUserId"></metadata>',
        ' <metadata name="License"></metadata>',
        ' <metadata name="ModificationDate"></metadata>',
        ' <metadata name="Origin"></metadata>',
        ' <metadata name="Title"></metadata>',
        ' <resources>',
        '  <object id="3" p:UUID="00000001-61cb-4c03-9d28-80fed5dfa1dc" type="model">',
        '   <components>',
        *component_lines,
        '   </components>',
        '  </object>',
        ' </resources>',
        ' <build p:UUID="2c7c17d8-22b5-4d84-8835-1976022ea369">',
        f'  <item objectid="3" p:UUID="00000003-b1ec-4553-aec9-835e5b724bb4" transform="{build_transform}" printable="1"/>',
        ' </build>',
        '</model>',
        '',
    ])


def model_settings_xml(parts: list[dict], assembly_name: str, output: Path, build_transform: str) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
        '  <object id="3">',
        f'    <metadata key="name" value="{escape(assembly_name)}"/>',
        '    <metadata key="extruder" value="0"/>',
    ]
    for index, part in enumerate(parts):
        center = part["center"]
        lines.extend([
            f'    <part id="{part["id"]}" subtype="normal_part">',
            f'      <metadata key="name" value="{escape(part["name"])}"/>',
            f'      <metadata key="matrix" value="{matrix16(center)}"/>',
            f'      <metadata key="source_file" value="{escape(str(output))}"/>',
            '      <metadata key="source_object_id" value="0"/>',
            f'      <metadata key="source_volume_id" value="{index}"/>',
            f'      <metadata key="source_offset_x" value="{fmt(center[0])}"/>',
            f'      <metadata key="source_offset_y" value="{fmt(center[1])}"/>',
            f'      <metadata key="source_offset_z" value="{fmt(center[2])}"/>',
            f'      <metadata key="extruder" value="{part["extruder"]}"/>',
            '      <mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>',
            '    </part>',
        ])
    lines.extend([
        '  </object>',
        '  <plate>',
        '    <metadata key="plater_id" value="1"/>',
        '    <metadata key="plater_name" value=""/>',
        '    <metadata key="locked" value="false"/>',
        '    <metadata key="filament_map_mode" value="Auto For Flush"/>',
        '    <metadata key="filament_maps" value="1 1 1"/>',
        '    <metadata key="thumbnail_file" value="Metadata/plate_1.png"/>',
        '    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_1.png"/>',
        '    <metadata key="top_file" value="Metadata/top_1.png"/>',
        '    <metadata key="pick_file" value="Metadata/pick_1.png"/>',
        '    <model_instance>',
        '      <metadata key="object_id" value="3"/>',
        '      <metadata key="instance_id" value="0"/>',
        '      <metadata key="identify_id" value="259"/>',
        '    </model_instance>',
        '  </plate>',
        '  <assemble>',
        f'   <assemble_item object_id="3" instance_id="0" transform="{build_transform}" offset="0 0 0" />',
        '  </assemble>',
        '</config>',
        '',
    ])
    return "\n".join(lines)


def content_types_xml(include_png: bool) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>',
    ]
    if include_png:
        lines.append(' <Default Extension="png" ContentType="image/png"/>')
    lines.extend([' <Default Extension="gcode" ContentType="text/x.gcode"/>', '</Types>', ''])
    return "\n".join(lines)


def root_rels_xml(include_png: bool) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<Relationships xmlns="{REL_NS}">',
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>',
    ]
    if include_png:
        lines.extend([
            ' <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>',
            ' <Relationship Target="/Metadata/plate_1.png" Id="rel-4" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-middle"/>',
            ' <Relationship Target="/Metadata/plate_1_small.png" Id="rel-5" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-small"/>',
        ])
    lines.extend(['</Relationships>', ''])
    return "\n".join(lines)


def model_rels_xml(nested_name: str) -> str:
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<Relationships xmlns="{REL_NS}">',
        f' <Relationship Target="/3D/Objects/{nested_name}" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>',
        '</Relationships>',
        '',
    ])


def default_project_settings(max_slot: int, filament_colors: dict[int, str]) -> dict:
    colors = ['#FFFFFF'] * max(max_slot, 1)
    for slot, color in filament_colors.items():
        while len(colors) < slot:
            colors.append('#FFFFFF')
        colors[slot - 1] = color
    return {"filament_colour": colors, "filament_type": ["PLA"] * len(colors)}


def load_template_data(template: str | None, filament_colors: dict[int, str]):
    png_data = {}
    project_settings = None
    if template:
        with zipfile.ZipFile(template) as src:
            names = set(src.namelist())
            if 'Metadata/project_settings.config' in names:
                project_settings = json.loads(src.read('Metadata/project_settings.config'))
            for name in [
                'Metadata/plate_1.png',
                'Metadata/plate_1_small.png',
                'Metadata/plate_no_light_1.png',
                'Metadata/top_1.png',
                'Metadata/pick_1.png',
            ]:
                if name in names:
                    png_data[name] = src.read(name)
    return project_settings, png_data


def apply_filament_colors(project_settings: dict, filament_colors: dict[int, str], min_slots: int) -> None:
    colors = list(project_settings.get('filament_colour', []))
    while len(colors) < min_slots:
        colors.append('#FFFFFF')
    for slot, color in filament_colors.items():
        while len(colors) < slot:
            colors.append('#FFFFFF')
        colors[slot - 1] = color
    project_settings['filament_colour'] = colors


def slice_info_xml() -> str:
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
        '  <header>',
        '    <header_item key="X-BBL-Client-Type" value="slicer"/>',
        '    <header_item key="X-BBL-Client-Version" value=""/>',
        '  </header>',
        '</config>',
        '',
    ])


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    parts = parse_parts(args.part)
    apply_extruders(parts, args.extruder)
    filament_colors = parse_filament_colors(args.filament_color)
    prepare_meshes(parts)

    max_slot = max([part['extruder'] for part in parts] + list(filament_colors) + [1])
    project_settings, png_data = load_template_data(args.template, filament_colors)
    if project_settings is None:
        project_settings = default_project_settings(max_slot, filament_colors)
    apply_filament_colors(project_settings, filament_colors, max_slot)

    nested_name = f"{args.assembly_name}_1.model"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types_xml(bool(png_data)))
        zf.writestr('_rels/.rels', root_rels_xml(bool(png_data)))
        zf.writestr('3D/3dmodel.model', top_model_xml(parts, nested_name, args.assembly_name, args.build_transform))
        zf.writestr('3D/_rels/3dmodel.model.rels', model_rels_xml(nested_name))
        zf.writestr(f'3D/Objects/{nested_name}', nested_model_xml(parts))
        zf.writestr('Metadata/project_settings.config', json.dumps(project_settings, indent=4))
        zf.writestr('Metadata/model_settings.config', model_settings_xml(parts, args.assembly_name, output, args.build_transform))
        zf.writestr('Metadata/slice_info.config', slice_info_xml())
        for name, data in png_data.items():
            zf.writestr(name, data)


if __name__ == '__main__':
    main()
