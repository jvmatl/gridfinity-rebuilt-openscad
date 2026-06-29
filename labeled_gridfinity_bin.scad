include <src/core/standard.scad>
use <src/core/gridfinity-rebuilt-utility.scad>
use <src/core/gridfinity-rebuilt-holes.scad>
use <src/core/bin.scad>
use <src/core/cutouts.scad>

// Reusable labeled Gridfinity bin with optional two-material label text.
// Multiline labels are passed as arrays, for example:
//   label_lines = ["Misc M3 junk", "do not lose!"];
// Export part="body" and part="text" with matching parameters, then package the STLs.
// scripts/generate_labeled_bins.py is the preferred wrapper for ordinary bins.

part = "preview"; // "body", "text", "full", or "preview"
label_lines = ["M3x12"];
grid_size = [1, 1];
gridz = 4;
include_lip = true;
label_surface = true;
magnet_holes = true;

$fa = 4;
$fs = 0.25;

module labeled_gridfinity_bin(
    label_lines = ["M3x12"],
    part = "preview",
    grid_size = [1, 1],
    gridz = 4,
    gridz_define = 0,
    enable_zsnap = true,
    include_lip = true,
    label_surface = true,
    magnet_holes = true,
    screw_holes = false,
    label_font = "Liberation Sans:style=Bold",
    label_text_depth = 0.8,
    label_area_width = 30,
    label_area_height = 8.5,
    label_char_width_ratio = 0.62,
    label_line_spacing = 1.15,
    label_tab_depth_margin = 2.5
) {
    hole_options = bundle_hole_options(
        refined_hole = false,
        magnet_hole = magnet_holes,
        screw_hole = screw_holes,
        crush_ribs = true,
        chamfer = true,
        supportless = true
    );

    labeled_bin = new_bin(
        grid_size = grid_size,
        height_mm = height(gridz, gridz_define, enable_zsnap),
        fill_height = 0,
        include_lip = include_lip,
        hole_options = hole_options,
        only_corners = false,
        thumbscrew = false,
        grid_dimensions = GRID_DIMENSIONS_MM
    );

    infill_size = bin_get_infill_size_mm(labeled_bin);
    pocket_top_z = BASE_HEIGHT + max(labeled_bin[3], 0);
    // Center labels in the visible tab area; the stacking lip hides the wall-side strip.
    label_lip_occlusion_depth = include_lip ? STACKING_LIP_SIZE.x : 0;

    has_text = _lgb_has_text(label_lines);

    if (part == "body") {
        _lgb_body(
            labeled_bin, infill_size, pocket_top_z, label_surface, label_lines, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth
        );
    } else if (part == "text") {
        if (has_text)
        _lgb_text_insert(
            labeled_bin, infill_size, pocket_top_z, label_surface, label_lines, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth
        );
    } else if (part == "full") {
        _lgb_finished(labeled_bin, infill_size, label_surface);
    } else if (part == "preview") {
        color("#e5e5e5")
        _lgb_body(
            labeled_bin, infill_size, pocket_top_z, label_surface, label_lines, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth
        );
        if (has_text)
        color("black")
        _lgb_text_insert(
            labeled_bin, infill_size, pocket_top_z, label_surface, label_lines, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth
        );
    } else {
        assert(false, str("Unknown part: ", part));
    }
}

module _lgb_body(
    labeled_bin, infill_size, pocket_top_z, label_surface, label_lines, label_font,
    label_text_depth, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
    label_lip_occlusion_depth
) {
    difference() {
        _lgb_finished(labeled_bin, infill_size, label_surface);
        if (_lgb_has_text(label_lines))
        _lgb_text_insert(
            labeled_bin, infill_size, pocket_top_z, label_surface, label_lines, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth
        );
    }
}

module _lgb_text_insert(
    labeled_bin, infill_size, pocket_top_z, label_surface, label_lines, label_font,
    label_text_depth, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
    label_lip_occlusion_depth
) {
    intersection() {
        _lgb_finished(labeled_bin, infill_size, label_surface);
        _lgb_text_raw(
            infill_size, pocket_top_z, label_lines, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth
        );
    }
}

module _lgb_finished(labeled_bin, infill_size, label_surface = true) {
    bin_render(labeled_bin) {
        compartment_cutter(
            size_mm = infill_size,
            scoop_percent = 1,
            tab_width = label_surface ? TAB_WIDTH_NOMINAL : 0,
            tab_angle = 90
        );
    }
}

module _lgb_text_raw(
    infill_size, pocket_top_z, label_lines, label_font,
    label_text_depth, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
    label_lip_occlusion_depth
) {
    label_depth = min(
        label_area_height,
        TAB_SIZE.x - label_lip_occlusion_depth - 2 * label_tab_depth_margin
    );
    label_size = _lgb_fitted_label_size(
        label_lines, label_area_width, label_depth,
        label_char_width_ratio, label_line_spacing
    );
    line_step = label_size * label_line_spacing;
    line_count = len(label_lines);
    label_center = [0, infill_size.y / 2 - (TAB_SIZE.x + label_lip_occlusion_depth) / 2];

    translate([label_center.x, label_center.y, pocket_top_z - label_text_depth])
    union() {
        for (i = [0 : line_count - 1]) {
            y = ((line_count - 1) / 2 - i) * line_step;
            translate([0, y, 0])
            linear_extrude(label_text_depth)
            text(
                label_lines[i],
                size = label_size,
                font = label_font,
                halign = "center",
                valign = "center"
            );
        }
    }
}

function _lgb_has_text(lines) = len(lines) > 0;

function _lgb_longest_label_line(lines) =
    len(lines) == 0 ? 0 : max([for (line = lines) len(line)]);

function _lgb_fitted_label_size(
    lines, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing
) =
    min(
        label_area_height / max(len(lines), 1) / label_line_spacing,
        label_area_width / max(_lgb_longest_label_line(lines), 1) / label_char_width_ratio
    );

labeled_gridfinity_bin(
    label_lines = label_lines,
    part = part,
    grid_size = grid_size,
    gridz = gridz,
    include_lip = include_lip,
    label_surface = label_surface,
    magnet_holes = magnet_holes
);
