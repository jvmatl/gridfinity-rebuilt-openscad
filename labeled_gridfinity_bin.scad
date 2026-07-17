include <src/core/standard.scad>
use <src/core/gridfinity-rebuilt-utility.scad>
use <src/core/gridfinity-rebuilt-holes.scad>
use <src/core/bin.scad>
use <src/core/cutouts.scad>

// Reusable labeled Gridfinity bin with optional two-material label text.
// Multiline labels are passed as arrays, for example:
//   label_lines = ["Misc M3 junk", "do not lose!"];
// Column subdivisions are passed as weights plus one label array per column:
//   column_weights = [20, 60, 20];
//   compartment_label_lines = [["X"], ["Y"], ["Z"]];
// scripts/generate_labeled_bins.py is the preferred wrapper for ordinary bins.

part = "preview"; // "body", "text", "full", or "preview"
label_lines = ["M3x12"];
grid_size = [1, 1];
gridz = 4;
include_lip = true;
label_surface = true;
magnet_holes = true;
flush_front_wall = true;
column_weights = [];
compartment_label_lines = [];

$fa = 4;
$fs = 0.25;

module labeled_gridfinity_bin(
    label_lines = ["M3x12"],
    compartment_label_lines = [],
    column_weights = [],
    part = "preview",
    grid_size = [1, 1],
    gridz = 4,
    gridz_define = 0,
    enable_zsnap = true,
    include_lip = true,
    label_surface = true,
    magnet_holes = true,
    screw_holes = false,
    flush_front_wall = true,
    label_font = "Liberation Sans:style=Bold",
    label_text_depth = 0.8,
    label_area_width = 30,
    label_area_height = 8.5,
    label_tab_style = 0,
    label_char_width_ratio = 0.86,
    label_line_spacing = 1.15,
    label_tab_depth_margin = 2.5
) {
    assert(len(column_weights) == 0 || min(column_weights) > 0,
        "column_weights must be empty or contain positive numbers.");
    assert(len(column_weights) == 0 || len(compartment_label_lines) == len(column_weights),
        "compartment_label_lines must match column_weights length.");

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
    front_wall_flush_inset = include_lip && flush_front_wall ? max(STACKING_LIP_SIZE.x - d_wall, 0) : 0;
    has_text = _lgb_has_any_text(label_lines, compartment_label_lines, column_weights);

    if (part == "body") {
        _lgb_body(
            labeled_bin, infill_size, pocket_top_z, label_surface,
            label_lines, compartment_label_lines, column_weights, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth, label_tab_style, front_wall_flush_inset
        );
    } else if (part == "text") {
        if (has_text)
        _lgb_text_inserts(
            labeled_bin, infill_size, pocket_top_z, label_surface,
            label_lines, compartment_label_lines, column_weights, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth, label_tab_style, front_wall_flush_inset
        );
    } else if (part == "full") {
        _lgb_finished(labeled_bin, infill_size, label_surface, column_weights, label_tab_style, front_wall_flush_inset);
    } else if (part == "preview") {
        color("#e5e5e5")
        _lgb_body(
            labeled_bin, infill_size, pocket_top_z, label_surface,
            label_lines, compartment_label_lines, column_weights, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth, label_tab_style, front_wall_flush_inset
        );
        if (has_text)
        color("black")
        _lgb_text_inserts(
            labeled_bin, infill_size, pocket_top_z, label_surface,
            label_lines, compartment_label_lines, column_weights, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth, label_tab_style, front_wall_flush_inset
        );
    } else {
        assert(false, str("Unknown part: ", part));
    }
}

module _lgb_body(
    labeled_bin, infill_size, pocket_top_z, label_surface,
    label_lines, compartment_label_lines, column_weights, label_font,
    label_text_depth, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
    label_lip_occlusion_depth, label_tab_style, front_wall_flush_inset
) {
    difference() {
        _lgb_finished(labeled_bin, infill_size, label_surface, column_weights, label_tab_style, front_wall_flush_inset);
        if (_lgb_has_any_text(label_lines, compartment_label_lines, column_weights))
        _lgb_text_inserts(
            labeled_bin, infill_size, pocket_top_z, label_surface,
            label_lines, compartment_label_lines, column_weights, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth, label_tab_style, front_wall_flush_inset
        );
    }
}

module _lgb_text_inserts(
    labeled_bin, infill_size, pocket_top_z, label_surface,
    label_lines, compartment_label_lines, column_weights, label_font,
    label_text_depth, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
    label_lip_occlusion_depth, label_tab_style, front_wall_flush_inset
) {
    intersection() {
        _lgb_finished(labeled_bin, infill_size, label_surface, column_weights, label_tab_style, front_wall_flush_inset);
        _lgb_all_text_raw(
            infill_size, pocket_top_z, label_lines, compartment_label_lines, column_weights, label_font,
            label_text_depth, label_area_width, label_area_height,
            label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
            label_lip_occlusion_depth
        );
    }
}

module _lgb_finished(labeled_bin, infill_size, label_surface = true, column_weights = [], label_tab_style = 0, front_wall_flush_inset = 0) {
    bin_render(labeled_bin) {
        _lgb_compartment_cutters(infill_size, label_surface, column_weights, label_tab_style, front_wall_flush_inset);
    }
}

module _lgb_compartment_cutters(infill_size, label_surface, column_weights, label_tab_style, front_wall_flush_inset) {
    column_count = _lgb_column_count(column_weights);
    for (i = [0 : column_count - 1]) {
        comp_size = _lgb_compartment_size(infill_size, column_weights, i, front_wall_flush_inset);
        comp_center = _lgb_compartment_center(infill_size, column_weights, i, front_wall_flush_inset);
        translate([comp_center.x, comp_center.y, 0])
        cut_compartment_auto(
            size_mm = comp_size,
            style_tab = label_surface ? label_tab_style : 5,
            scoop_percent = 1
        );
    }
}

module _lgb_all_text_raw(
    infill_size, pocket_top_z, label_lines, compartment_label_lines, column_weights, label_font,
    label_text_depth, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
    label_lip_occlusion_depth
) {
    column_count = _lgb_column_count(column_weights);
    shared_label_size = column_count == 1 ? undef : _lgb_fitted_compartment_label_size(
        infill_size, compartment_label_lines, column_weights,
        label_area_width, label_area_height, label_char_width_ratio,
        label_line_spacing, label_tab_depth_margin, label_lip_occlusion_depth
    );
    for (i = [0 : column_count - 1]) {
        lines = column_count == 1 ? label_lines : compartment_label_lines[i];
        if (_lgb_has_text(lines)) {
            comp_size = _lgb_compartment_size(infill_size, column_weights, i);
            comp_center = _lgb_compartment_center(infill_size, column_weights, i);
            _lgb_text_raw(
                comp_center, comp_size, pocket_top_z, lines, label_font,
                label_text_depth, label_area_width, label_area_height,
                label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
                label_lip_occlusion_depth, shared_label_size
            );
        }
    }
}

module _lgb_text_raw(
    comp_center, comp_size, pocket_top_z, label_lines, label_font,
    label_text_depth, label_area_width, label_area_height,
    label_char_width_ratio, label_line_spacing, label_tab_depth_margin,
    label_lip_occlusion_depth, label_size_override = undef
) {
    label_width = min(label_area_width, comp_size.x - 2 * label_tab_depth_margin);
    label_depth = min(
        label_area_height,
        TAB_SIZE.x - label_lip_occlusion_depth - 2 * label_tab_depth_margin
    );
    label_size = is_undef(label_size_override) ? _lgb_fitted_label_size(
        label_lines, label_width, label_depth,
        label_char_width_ratio, label_line_spacing
    ) : label_size_override;
    line_step = label_size * label_line_spacing;
    line_count = len(label_lines);
    label_center = [
        comp_center.x,
        comp_center.y + comp_size.y / 2 - (TAB_SIZE.x + label_lip_occlusion_depth) / 2
    ];

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

function _lgb_column_count(column_weights) = len(column_weights) == 0 ? 1 : len(column_weights);
function _lgb_weights(column_weights) = len(column_weights) == 0 ? [1] : column_weights;
function _lgb_sum(values, i = 0) = i >= len(values) ? 0 : values[i] + _lgb_sum(values, i + 1);
function _lgb_prefix_sum(values, i, j = 0) = j >= i ? 0 : values[j] + _lgb_prefix_sum(values, i, j + 1);

function _lgb_compartment_alloc_width(infill_size, column_weights, i) =
    let(weights = _lgb_weights(column_weights))
    infill_size.x * weights[i] / _lgb_sum(weights);

function _lgb_compartment_left(infill_size, column_weights, i) =
    let(weights = _lgb_weights(column_weights))
    -infill_size.x / 2 + infill_size.x * _lgb_prefix_sum(weights, i) / _lgb_sum(weights);

function _lgb_compartment_center(infill_size, column_weights, i, front_wall_flush_inset = 0) =
    let(alloc_width = _lgb_compartment_alloc_width(infill_size, column_weights, i))
    [
        _lgb_compartment_left(infill_size, column_weights, i) + alloc_width / 2,
        front_wall_flush_inset / 2
    ];

function _lgb_compartment_size(infill_size, column_weights, i, front_wall_flush_inset = 0) =
    let(column_count = _lgb_column_count(column_weights))
    let(divider_allowance = column_count > 1 ? d_div / 2 : 0)
    [
        _lgb_compartment_alloc_width(infill_size, column_weights, i) - divider_allowance,
        infill_size.y - divider_allowance - front_wall_flush_inset,
        infill_size.z
    ];

function _lgb_has_text(lines) = len(lines) > 0;
function _lgb_has_compartment_text(compartment_label_lines, i = 0) =
    i >= len(compartment_label_lines) ? false :
    _lgb_has_text(compartment_label_lines[i]) || _lgb_has_compartment_text(compartment_label_lines, i + 1);
function _lgb_has_any_text(label_lines, compartment_label_lines, column_weights) =
    _lgb_column_count(column_weights) == 1 ? _lgb_has_text(label_lines) : _lgb_has_compartment_text(compartment_label_lines);

function _lgb_label_depth(label_area_height, label_tab_depth_margin, label_lip_occlusion_depth) =
    min(
        label_area_height,
        TAB_SIZE.x - label_lip_occlusion_depth - 2 * label_tab_depth_margin
    );

function _lgb_compartment_label_width(infill_size, column_weights, i, label_area_width, label_tab_depth_margin) =
    let(comp_size = _lgb_compartment_size(infill_size, column_weights, i))
    min(label_area_width, comp_size.x - 2 * label_tab_depth_margin);

function _lgb_min_compartment_label_width(infill_size, column_weights, label_area_width, label_tab_depth_margin, i = 0) =
    i >= _lgb_column_count(column_weights) ? 1e9 :
    min(
        _lgb_compartment_label_width(infill_size, column_weights, i, label_area_width, label_tab_depth_margin),
        _lgb_min_compartment_label_width(infill_size, column_weights, label_area_width, label_tab_depth_margin, i + 1)
    );

function _lgb_max_compartment_line_count(compartment_label_lines, i = 0) =
    i >= len(compartment_label_lines) ? 1 :
    max(len(compartment_label_lines[i]), _lgb_max_compartment_line_count(compartment_label_lines, i + 1));

function _lgb_max_compartment_line_length(compartment_label_lines, i = 0) =
    i >= len(compartment_label_lines) ? 1 :
    max(_lgb_longest_label_line(compartment_label_lines[i]), _lgb_max_compartment_line_length(compartment_label_lines, i + 1));

function _lgb_fitted_compartment_label_size(
    infill_size, compartment_label_lines, column_weights,
    label_area_width, label_area_height, label_char_width_ratio,
    label_line_spacing, label_tab_depth_margin, label_lip_occlusion_depth
) =
    min(
        _lgb_label_depth(label_area_height, label_tab_depth_margin, label_lip_occlusion_depth)
            / max(_lgb_max_compartment_line_count(compartment_label_lines), 1)
            / label_line_spacing,
        _lgb_min_compartment_label_width(infill_size, column_weights, label_area_width, label_tab_depth_margin)
            / max(_lgb_max_compartment_line_length(compartment_label_lines), 1)
            / label_char_width_ratio
    );

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
    compartment_label_lines = compartment_label_lines,
    column_weights = column_weights,
    part = part,
    grid_size = grid_size,
    gridz = gridz,
    include_lip = include_lip,
    label_surface = label_surface,
    magnet_holes = magnet_holes,
    flush_front_wall = flush_front_wall
);
