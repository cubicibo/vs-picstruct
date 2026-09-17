# VS-PicStruct
Tool to analyze a clip and produce a list of H.26x "pic struct" instructions to store the said clip in a CFR container exploiting soft pulldown.

## Purpose
This improves compression efficiency as video sequences no longer have to contain hard-coded duplicates. The output of VS-PicStruct is a series of pulldown instructions to feed to the video encoder and use them to tag the frame, and improve the ratecontrol decisions. As the frames are no longer hard-duplicated, the encoder makes better use of the bidirectional frames and waste less bits.

Typical use-cases:
- VFR content, both interlaced and progressive.
- 48 fps ("HFR") movies can be encoded in a 60 fps container.
- Black & White silent films at 16, 18, 20 or 22 fps can be encoded in a 30 or 60 fps container.
- PAL content in a NTSC environment.

## Encoders
Use with this [x264 mod](https://github.com/cubicibo/x264), and more specifically the `--psfile` parameter.
x265 support is pending approval.

## Usage

### CLI
`python3 client.py [PARAMETERS] outputfile`

```
 -i, --zonesfile     Input zones file [mandatory]
 -f, --fps           Container framerate. Must be given as a fraction N/D. E.g. 30000/1001
 -o, --order         Default field order of the container (0: Progressive, 1: BFF, 2: TFF)
 -c, --codec         Target video codec ('AVC' or 'HEVC')
 -m, --mixed         Flag to allow mixing progressive and interlaced markings
                       ! Do not set this flag you do not understand this !
```

The zonesfile contains a pulldown zone per line. Each zone specify a count of frames, a framerate and a field order (if it should be encoded as a progressive or interlaced picture). The format is the following:<br/>
`number_of_frames fps_num/fps_den field_order`<br/>
E.g.:
```
210 24000/1001 0
115 30000/1001 2
89 30000/1001 0
```

### VapourSynth / Scripting

```python
from vspicstruct import PicStructFileV1, CodecConfig, VideoCodec

psfile_out = 'some/path/psfile.txt'

#Pulldown in an 29.97 fps interlaced container, TFF (2), H.264 AVC
container_fps = Fraction(30000, 1001)
codec = CodecConfig(container_fps, 2, VideoCodec.AVC)

psf = PicStructFileV1(psfile_out)

# E.g. final 29.97 clip is made of five different parts:
#23.976p
clip1 = core.std.BlankClip(..., fpsnum=24000, fpsden=1001)
clip1 = core.std.SetFieldBased(clip1, 0) # tag section as progressive (default)

#59.94i TFF
clip2 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)
clip2 = core.std.SetFieldBased(clip2, 2) # 2 = TFF, 1 = BFF

#29.97p
clip3 = core.std.BlankClip(..., fpsnum=30000, fpsden=1001)

clip = clip1 + clip2 + clip3

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
- By default, with an interlaced container, VS-PicStruct only uses interlaced structures to combine the interlaced & progressive sequences. E.g. 23.976p in 29.97 would produce the sequence "TB, TBT, BT, BTB" (T=Top, B=Bottom).
- VS-PicStruct only uses progressive picture structures if the field order in  `CodecConfig` is set to progressive.
- VS-PicStruct can mix interlaced and progressive picture structures with `only_interlaced_patterns=False` in `CodecConfig`. The pulldown generation may be intractable in that configuration: an exception will be raised.

## Constraints
- With interlaced pulldown, the maximum pulldown ratio is 1.5 (e.g 20 fps in 30 fps container)
- With progressive pulldown, or mixed, the maximum pulldown ratio is 3 (10 fps in 30 fps container)
- Any pulldown is supported, both 25000/1001 and 25/1 have a valid solutions in a 29.97p container.
- The maximum error from the original presentation timeline never exceed a field of the container timebase: half the duration of a container frame.

For NTSC, it's generally better to convert first the film content rate (18, 24, 48 fps...) to the closest NTSC framerate. E.g., `18 fps` in a `29.97` progressive container is not ideal, while `18000/1001 fps` only requires a cycle of three structures:
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
210 2 3
211 2 3
...

# (30000/1001), footage=PROGRESSIVE, pulldown_type=INTERLACED
315 0 3
...
```

## References
- ITU-T Rec H.264 (Table D-1 notably)
- ITU-T Rec H.265 (Table D-2)
- x264 and x265 source code.