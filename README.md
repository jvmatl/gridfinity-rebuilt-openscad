# STOP!

This is a personal fork my own hacking - you are absolutely free to use it if it interests you, but it's not really meant to be a public project. 

The interesting work is not on main, but on the codex_bin_automation branch, where I have been messing around with OpenAI's codex and vibe-coding some useful (to me) modifications to how gridfinity bins are generated. This is **100% AI-generated code**, because that was the whole point - to see whether it could generate useful, reusable code to solve a real problem for me. Some code is better than others. In case you are interested, this is what Codex and I have done:

* Enhanced the bin-generation code to embed labels right into the bin (I have a Snapmaker U1 multi-nozzle printer, so I like embedding colored text directly into my prints)
* added an option to tweak the shape of the front of the bin, because previously, when you added the top stacking lip, it would block the otherwise smooth curve at the front of the bin and make it hard to pull our snall parts like screws washers.
* scripts to take a json description of the bins you want to make and pipeline from json description to .3mf file with one or more labeled bins, ready to slice and print.

Here's an example prompt: In its current state, I can ask Codex to: 

```
Make me a pair of gridfinity bins for my M3 hardware.
I need a 1x3x4U bin partitioned into 5 equal parts, labeled "M3x{4,5,6,8,10}",
and another 1x3x4U bin partitioned 30/70, where the left bin is "M3x14" and the right bin is "M3x30"
```

.. and it does the right thing, generating a single .3MF file with two ready-to-print, multi-material correctly-labeled bins. The model shows white bins with black text, but you can, of course, swap in whatever filaments you want.

Feel free to make suggestions, please don't be offended if I don't respond or don't implement your feature requests or accept pull requests - this is not my life, it's a 1% free-time project that will probably be abandoned in a year. If it's useful to you, have at it!

You probably want to check out the original work by the actual author, who did all the heavy lifting and made this amazingly useful library possible, and did it without an AI minion: https://github.com/kennetek/gridfinity-rebuilt-openscad

**Original README follows:**

--- 

# Gridfinity Rebuilt in OpenSCAD

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A ground-up port (with a few extra features) of the stock [gridfinity](https://www.youtube.com/watch?v=ra_9zU-mnl8) bins in OpenSCAD. Open to feedback, because I could not feasibly test all combinations of bins. I tried my best to exactly match the original gridfinity dimensions, but some of the geometry is slightly incorrect (mainly fillets). However, I think they are negligible differences, and will not appear in the printed model.

Full documentation can be found at the project's [website](https://kennetek.github.io/gridfinity-rebuilt-openscad/).

The project can also be found on [Printables](https://www.printables.com/model/274917-gridfinity-rebuilt-in-openscad) if you want to support the project.

[<img src="./images/base_dimension.gif" width="320">]()
[<img src="./images/compartment_dimension.gif" width="320">]()
[<img src="./images/height_dimension.gif" width="320">]()
[<img src="./images/tab_dimension.gif" width="320">]()
[<img src="./images/holes_dimension.gif" width="320">]()
[<img src="./images/custom_dimension.gif" width="320">]()

## Features
- any size of bin (width/length/height)
- height by units, internal depth, or overall size
- any number of compartments (along both X and Y axis)
- togglable scoop
- togglable tabs, split tabs, and tab alignment
- togglable holes (with togglable supportless printing hole structures)
- manual compartment construction (make the most wacky bins imaginable)
- togglable lip (if you don't care for stackability)
- dividing bases (if you want a 1.5 unit long bin, for instance)
- removed material from bases to save filament
- vase mode bins

### Printable Holes
The printable holes allow your slicer to bridge the gap inside the countersunk magnet hole (using the technique shown [here](https://www.youtube.com/watch?v=W8FbHTcB05w)) so that supports are not needed.

[<img src="./images/slicer_holes.png" height="200">]()
[<img src="./images/slicer_holes_top.png" height="200">]()

## Recommendations
For best results, use a [development snapshots](https://openscad.org/downloads.html#snapshots) version of OpenSCAD. This can speed up rendering from 10 minutes down to a couple of seconds, even for comically large bins. It is not a requirement to use development versions of OpenSCAD.

## External libraries

- `threads-scad` (https://github.com/rcolyer/threads-scad) is used for creating threaded holes, and is included in this project under `external/threads-scad/threads.scad`.

## Enjoy!

[<img src="./images/spin.gif" width="160">]()

[Gridfinity](https://www.youtube.com/watch?v=ra_9zU-mnl8) by [Zack Freedman](https://www.youtube.com/c/ZackFreedman/about)

This work is licensed under the same license as Gridfinity, being a
[MIT License](https://opensource.org/licenses/MIT).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
