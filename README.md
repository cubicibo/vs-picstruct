# VS-PicStruct
Tool to analyze a VFR clip and produce a list of H.26x "pic struct" instructions to store the VFR clip in a CFR container exploiting soft pulldown.

## Purpose
Use with this [x264 mod](https://github.com/cubicibo/x264), and more specifically the `--psfile` parameter.
x265 support is pending approval.

## Usage

```python
from vspicstruct import PicStructFileV1, CodecConfig, VideoFieldOrder, VideoCodec

psfile_out = 'some/path/psfile.txt'

#Interlaced pulldown in a 59.94i (29.97 fps) container, H.264 AVC
container_fps = Fraction(30000, 1001)
container_default_field_order = VideoFieldOrder.TOP_FIELD_FIRST # (or just 2: same enumeration as VS)
codec = CodecConfig(Fraction(30000, 1001), VideoFieldOrder.TOP_FIELD_FIRST, VideoCodec.AVC)

psf = PicStructFileV1(psfile_out)

# E.g. final 29.97 clip is made of five different parts:
#23.976p
clip1 = core.std.BlankClip(..., fpsnum=24000, fpsden=1001)
clip1 = core.std.SetFieldBased(clip1, 0) # optional, by default sections are assumed progressive

#59.94i TFF
clip2 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)
clip2 = core.std.SetFieldBased(clip2, 2)

#29.97p
clip3 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)

#18p
clip4 = core.std.BlankClip(..., fpsnum=18000, fpsden=1001)

#23.976, and prefer a progressive pull-down sequence over an interlaced one (more jarring to the viewer)
clip5 = core.std.BlankClip(..., fpsnum=24000, fpsden=1001)
clip5 = core.std.SetFrameProps(clip5, FavorProgressive=True)

clip = clip1 + clip2 + clip3 + clip4 + clip5

#write psfile from final VFR clip
psf.write_from_clip(codec, clip)

#output clip
clip.set_output()
```

Then, you can use the generated `psfile.txt` with the aforementionned custom x264/5 binary:<br/>
`x264 [...] --psfile "some/path/psfile.txt" --fps 30000/1001 [...] -o out.264`<br/>

- You must specify the container framerate via `--fps`.
- If your clip has temporally disjoint field pairs in some section, you must specify the field order (`--tff` or `--bff`) in the command.
- For BD exports, you must ensure the GOP duration does not exceed 1 second at any time. In these custom x26* builds, the `--keyint` unit is defined with respect to the container rate.
    - For one second GOP `--keyint` must equal the integer framerate of the container (e.g. 30 for 29.97 fps)
    - In other words, `--keyint` is no longer defined as a frame count but by the number of container refreshes. E.g. if you use `--pulldown 32` on a 23.976 input, then `--keyint` would no longer be 24, but 30!
- `--fake-interlaced` should be specified for progressive-only sequences in interlaced containers.
- x265 only supports progressive pulldowns. `VideoFieldOrder.PROGRESSIVE` must be set in `CodecConfig`.

## Mixing interlaced / progressive
By default VS-PicStruct refuses to mix interlaced and progressive sequences if the `CodecConfig` is configured to TFF/BFF
to maximize compatibility. This can be changed by forcing `only_interlaced_patterns=False` in `CodecConfig`. This flag is ignored if the codec is configured to progressive-only.

## Supported combination
Any pulldown is supported. The maximum error from the real framerate is at most half a frame (a field) duration (container timebase).

For NTSC, it's recommended to convert first the film content rate (18, 24, 48 fps...) to the closest NTSC framerate. E.g., `18 fps` in a `29.97` progressive container is not ideal, while `18000/1001 fps` only requires a cycle of three structures :
`Frame-Doubling -> Progressive Frame -> Frame-Doubling.`

## Example index
Here's the output index for the above example:
```
# picstruct format v1
# format: frame_num frame_field_order pic_struct

# (24000/1001), footage=PROGRESSIVE, pulldown_type=INTERLACED
0 0 5
1 0 4
2 0 6
3 0 3
4 0 5
5 0 4
...

# (30000/1001), footage=TOP_FIELD_FIRST, pulldown_type=INTERLACED
20 2 3
...

# (30000/1001), footage=PROGRESSIVE, pulldown_type=PROGRESSIVE
35 0 0
...

# (18000/1001), footage=PROGRESSIVE, pulldown_type=PROGRESSIVE
50 0 0
51 0 7
52 0 7
53 0 0
...

# (24000/1001), footage=PROGRESSIVE, pulldown_type=PROGRESSIVE
70 0 7
71 0 0
72 0 0
73 0 0
74 0 7
...
```

## References
- ITU-T Rec H.264 (Table D-1 notably)
- ITU-T Rec H.265 (Table D-2)
- x264 and x265 source code.