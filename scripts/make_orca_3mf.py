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
    parser.add_argument("--object", action="append", default=[], metavar="OBJECT=PART,PART", help="Group parts into a named slicer object. Repeat for multiple objects. If omitted, all parts become one object.")
    parser.add_argument("--extruder", action="append", required=True, metavar="NAME=N", help="1-based Orca extruder/filament slot for a part.")
    parser.add_argument("--filament-color", action="append", default=[], metavar="N=#RRGGBB", help="1-based filament slot display color.")
    parser.add_argument("--template", help="Optional Orca/Bambu 3MF to copy thumbnails from.")
    parser.add_argument("--copy-template-project-settings", action="store_true", help="Also copy project settings from --template. This may carry printer custom G-code.")
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


def parse_object_groups(values: list[str], parts: list[dict], assembly_name: str) -> list[dict]:
    part_by_name = {part["name"]: part for part in parts}
    if not values:
        return [{"id": 3, "name": assembly_name, "parts": parts}]

    groups = []
    assigned = set()
    for index, value in enumerate(values):
        object_name, raw_parts = parse_name_value(value, "--object")
        part_names = [name.strip() for name in raw_parts.split(",") if name.strip()]
        if not part_names:
            raise SystemExit(f"--object must list at least one part: {value}")
        object_parts = []
        for part_name in part_names:
            if part_name not in part_by_name:
                raise SystemExit(f"--object {object_name} references unknown part: {part_name}")
            if part_name in assigned:
                raise SystemExit(f"part appears in more than one --object group: {part_name}")
            assigned.add(part_name)
            object_parts.append(part_by_name[part_name])
        groups.append({"id": 3 + index, "name": object_name, "parts": object_parts})

    missing = [part["name"] for part in parts if part["name"] not in assigned]
    if missing:
        raise SystemExit(f"parts missing from --object groups: {', '.join(missing)}")
    return groups


def object_bbox(group: dict) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    parts = group["parts"]
    mins = [min(part["bbox_min"][axis] for part in parts) for axis in range(3)]
    maxs = [max(part["bbox_max"][axis] for part in parts) for axis in range(3)]
    return tuple(mins), tuple(maxs)


def arrange_object_groups(groups: list[dict], build_transform: str, spacing: float = 10.0) -> None:
    if len(groups) == 1:
        groups[0]["build_transform"] = build_transform
        return

    bed_x, bed_y = 135.5, 136.0
    widths = []
    bboxes = []
    for group in groups:
        bbox_min, bbox_max = object_bbox(group)
        bboxes.append((bbox_min, bbox_max))
        widths.append(bbox_max[0] - bbox_min[0])
    total_width = sum(widths) + spacing * (len(groups) - 1)
    cursor = bed_x - total_width / 2
    for group, width, (bbox_min, bbox_max) in zip(groups, widths, bboxes):
        translate_x = cursor - bbox_min[0]
        translate_y = bed_y - (bbox_min[1] + bbox_max[1]) / 2
        group["build_transform"] = f"1 0 0 0 1 0 0 0 1 {fmt(translate_x)} {fmt(translate_y)} 0"
        cursor += width + spacing


def prepare_meshes(parts: list[dict]) -> None:
    for part in parts:
        vertices, triangles = helper.read_stl(part["path"])
        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        zs = [v[2] for v in vertices]
        bbox_min = (min(xs), min(ys), min(zs))
        bbox_max = (max(xs), max(ys), max(zs))
        center = ((bbox_min[0] + bbox_max[0]) / 2, (bbox_min[1] + bbox_max[1]) / 2, (bbox_min[2] + bbox_max[2]) / 2)
        part["bbox_min"] = bbox_min
        part["bbox_max"] = bbox_max
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


def top_model_xml(groups: list[dict], nested_name: str) -> str:
    resource_lines = []
    build_lines = []
    for group_index, group in enumerate(groups):
        resource_lines.extend([
            f'  <object id="{group["id"]}" p:UUID="0000000{group_index + 1}-61cb-4c03-9d28-80fed5dfa1dc" type="model">',
            '   <components>',
        ])
        for part in group["parts"]:
            resource_lines.append(
                f'    <component p:path="/3D/Objects/{nested_name}" objectid="{part["id"]}" '
                f'p:UUID="0001000{part["id"] - 1}-b206-40ff-9872-83e8017abed1" '
                f'transform="{transform12(part["center"])}"/>'
            )
        resource_lines.extend(['   </components>', '  </object>'])
        build_lines.append(
            f'  <item objectid="{group["id"]}" p:UUID="0000000{group_index + 3}-b1ec-4553-aec9-835e5b724bb4" '
            f'transform="{group["build_transform"]}" printable="1"/>'
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
        *resource_lines,
        ' </resources>',
        ' <build p:UUID="2c7c17d8-22b5-4d84-8835-1976022ea369">',
        *build_lines,
        ' </build>',
        '</model>',
        '',
    ])


def model_settings_xml(groups: list[dict], output: Path) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<config>',
    ]
    source_volume_id = 0
    for group in groups:
        lines.extend([
            f'  <object id="{group["id"]}">',
            f'    <metadata key="name" value="{escape(group["name"])}"/>',
            '    <metadata key="extruder" value="0"/>',
        ])
        for part in group["parts"]:
            center = part["center"]
            lines.extend([
                f'    <part id="{part["id"]}" subtype="normal_part">',
                f'      <metadata key="name" value="{escape(part["name"])}"/>',
                f'      <metadata key="matrix" value="{matrix16(center)}"/>',
                f'      <metadata key="source_file" value="{escape(str(output))}"/>',
                '      <metadata key="source_object_id" value="0"/>',
                f'      <metadata key="source_volume_id" value="{source_volume_id}"/>',
                f'      <metadata key="source_offset_x" value="{fmt(center[0])}"/>',
                f'      <metadata key="source_offset_y" value="{fmt(center[1])}"/>',
                f'      <metadata key="source_offset_z" value="{fmt(center[2])}"/>',
                f'      <metadata key="extruder" value="{part["extruder"]}"/>',
                '      <mesh_stat edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>',
                '    </part>',
            ])
            source_volume_id += 1
        lines.append('  </object>')
    lines.extend([
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
    ])
    for index, group in enumerate(groups):
        lines.extend([
            '    <model_instance>',
            f'      <metadata key="object_id" value="{group["id"]}"/>',
            '      <metadata key="instance_id" value="0"/>',
            f'      <metadata key="identify_id" value="{259 + index}"/>',
            '    </model_instance>',
        ])
    lines.extend([
        '  </plate>',
        '  <assemble>',
    ])
    for group in groups:
        lines.append(f'   <assemble_item object_id="{group["id"]}" instance_id="0" transform="{group["build_transform"]}" offset="0 0 0" />')
    lines.extend([
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


def load_template_data(template: str | None, copy_project_settings: bool):
    png_data = {}
    project_settings = None
    if template:
        with zipfile.ZipFile(template) as src:
            names = set(src.namelist())
            if copy_project_settings and 'Metadata/project_settings.config' in names:
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
    groups = parse_object_groups(args.object, parts, args.assembly_name)
    arrange_object_groups(groups, args.build_transform)

    max_slot = max([part['extruder'] for part in parts] + list(filament_colors) + [1])
    project_settings, png_data = load_template_data(args.template, args.copy_template_project_settings)
    if project_settings is None:
        project_settings = default_project_settings(max_slot, filament_colors)
    apply_filament_colors(project_settings, filament_colors, max_slot)

    nested_name = f"{args.assembly_name}_1.model"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types_xml(bool(png_data)))
        zf.writestr('_rels/.rels', root_rels_xml(bool(png_data)))
        zf.writestr('3D/3dmodel.model', top_model_xml(groups, nested_name))
        zf.writestr('3D/_rels/3dmodel.model.rels', model_rels_xml(nested_name))
        zf.writestr(f'3D/Objects/{nested_name}', nested_model_xml(parts))
        zf.writestr('Metadata/project_settings.config', json.dumps(project_settings, indent=4))
        zf.writestr('Metadata/model_settings.config', model_settings_xml(groups, output))
        zf.writestr('Metadata/slice_info.config', slice_info_xml())
        for name, data in png_data.items():
            zf.writestr(name, data)


if __name__ == '__main__':
    main()
