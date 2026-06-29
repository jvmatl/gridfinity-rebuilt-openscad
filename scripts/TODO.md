# TODO

- Remove the need for `orca_multimaterial_template.3mf` by teaching `make_orca_3mf.py` to emit all Orca/Bambu project metadata needed for filament assignments from scratch.

- Add the opposite split direction with a `rows` DSL parallel to `columns`. Keep `rows` and `columns` mutually exclusive. The geometry is straightforward along Y, but label placement needs a deliberate policy: current tabs sit on each compartment's +Y edge, which means only the back row has an outer-wall label while earlier rows get internal divider labels. Consider a future `label_edge` option (`north`, `south`, `auto`) before implementing row labels broadly.
