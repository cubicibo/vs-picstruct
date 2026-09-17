#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIT License

Copyright (c) 2025-2026 cubicibo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from typing import TextIO
from dataclasses import dataclass
from enum import IntEnum, IntFlag
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

#%%
class VideoCodec(IntEnum):
    AVC = 0
    HEVC = 1

class PulldownType(IntFlag):
    PROGRESSIVE = 1
    INTERLACED  = 2

class PicStruct(IntEnum):
    PROGRESSIVE_FRAME = 0
    TOP               = 1 # PAFF-only, not supported
    BOTTOM            = 2 # PAFF-only, not supported
    TOP_BOTTOM        = 3
    BOTTOM_TOP        = 4
    TOP_BOTTOM_TOP    = 5
    BOTTOM_TOP_BOTTOM = 6
    FRAME_DOUBLING    = 7
    FRAME_TRIPLING    = 8
    TOP_PREVBOTTOM    = 9  #HEVC
    BOTTOM_PREVTOP    = 10 #HEVC
    TOP_NEXTBOTTOM    = 11 #HEVC
    BOTTOM_NEXTTOP    = 12 #HEVC

    def is_progressive(self) -> bool:
        return self in (0, 7, 8)

    def get_delta_divisor(self) -> int:
        if self.is_progressive():
            delta = max(1, 2 + self - 7)
        elif self in (3, 4):
            delta = 2
        elif self in (5, 6):
            delta = 3
        else:
            assert self in (1, 2, 9, 10, 11, 12)
            delta = 1
        return delta

    def get_paired_field(self) -> 'PicStruct':
        cls = __class__
        if self in range(cls.TOP, cls.BOTTOM_TOP_BOTTOM+1) or\
           self in range(cls.TOP_PREVBOTTOM, cls.BOTTOM_NEXTTOP+1):
            return cls(1 + (self % 2))
        else:
            return self.get_last_field()

    def get_first_field(self) -> 'PicStruct':
        """
        The HEVC prev/next pairing is merely indicative, the picture is still
        conveyed as a field pic, so we return self
        """
        cls = __class__
        if self.is_progressive():
            return cls.PROGRESSIVE_FRAME # irrelevant
        delta_divisor = self.get_delta_divisor()
        if delta_divisor == 1:
            return cls(cls.BOTTOM - (self % 2))
        elif delta_divisor == 3:
            return cls(cls.TOP + ((1 + self) % 2))
        # delta_divisor == 2
        return cls(cls.BOTTOM - (self.get_last_field() >> 1))

    def get_last_field(self) -> 'PicStruct':
        cls = __class__
        if self.is_progressive():
            return cls.PROGRESSIVE_FRAME # irrelevant
        elif self in (cls.BOTTOM, cls.TOP_BOTTOM, cls.BOTTOM_TOP_BOTTOM, cls.BOTTOM_PREVTOP, cls.BOTTOM_NEXTTOP):
            return cls.BOTTOM
        # (cls.TOP, cls.BOTTOM_TOP, cls.TOP_BOTTOM_TOP, cls.TOP_PREVBOTTOM, cls.TOP_NEXTBOTTOM)
        return cls.TOP

    def get_next_structure(self, delta_divisor: int, count_in_fields: bool = True) -> 'PicStruct':
        """
        Returns the next structure given its duration and the last field in display.

        Note: HEVC field picture pairing is the responsibility of the caller.
        """
        assert delta_divisor > 0
        cls = __class__
        candidates = ()
        match self.get_last_field():
            case cls.PROGRESSIVE_FRAME:
                delta_divisor >>= (count_in_fields & 1)
                candidates = (cls.PROGRESSIVE_FRAME, cls.FRAME_DOUBLING, cls.FRAME_TRIPLING)
            case cls.TOP:
                candidates = (cls.BOTTOM, cls.BOTTOM_TOP, cls.BOTTOM_TOP_BOTTOM) #PREV/NEXT pairing is up to the caller.
            case cls.BOTTOM:
                candidates = (cls.TOP, cls.TOP_BOTTOM, cls.TOP_BOTTOM_TOP)
        return cls(candidates[delta_divisor-1])

    def is_paff(self) -> bool:
        return self in (1, 2)

class VideoFieldOrder(IntEnum):
    PROGRESSIVE        = 0
    BOTTOM_FIELD_FIRST = 1
    TOP_FIELD_FIRST    = 2

    def get_last_field(self) -> PicStruct:
        if self == self.PROGRESSIVE:
            return PicStruct.PROGRESSIVE_FRAME
        if self == self.BOTTOM_FIELD_FIRST:
            return PicStruct.TOP
        if self == self.TOP_FIELD_FIRST:
            return PicStruct.BOTTOM
        assert 0, self

class PureInterlacedRateException(Exception):
    pass
class IllegalPulldownException(Exception):
    pass
class OrphanedFieldException(Exception):
    pass
class FieldOrderMismatchException(Exception):
    pass

def _sanitize_fps(fps: Fraction | float | str) -> Fraction:
    if isinstance(fps, Fraction):
        return fps
    if isinstance(fps, str):
            fps = float(fps)
    if not isinstance(fps, int):
        ntsc_fps = Fraction(round((fps * 1001) / 1000) * 1000, 1001)
        if abs(fps - ntsc_fps) < 4e-3:
            return ntsc_fps
    return Fraction(fps)

@dataclass(frozen=True)
class CodecConfig:
    fps: Fraction | str | float
    default_field_order: VideoFieldOrder
    codec: VideoCodec
    only_interlaced_patterns: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.fps, Fraction):
            object.__setattr__(self, 'fps', _sanitize_fps(self.fps))
        if not isinstance(self.default_field_order, (VideoFieldOrder, int)):
            raise TypeError("default_field_order shall be int or VideoFieldOrder")
        if self.default_field_order not in VideoFieldOrder:
            raise ValueError("Unknown default_field_order.")
        if self.codec not in VideoCodec:
            raise ValueError("Unknown codec, not enumerated in VideoCodec.")
        if self.codec == VideoCodec.HEVC and self.default_field_order != VideoFieldOrder.PROGRESSIVE:
            raise NotImplementedError("HEVC + interlaced is not implemented.")
        if self.default_field_order == VideoFieldOrder.PROGRESSIVE and self.only_interlaced_patterns:
            object.__setattr__(self, 'only_interlaced_patterns', False)

@dataclass(frozen=True)
class VideoSequence:
    fps: Fraction | str | float
    field_order: VideoFieldOrder

    def __post_init__(self) -> None:
        object.__setattr__(self, 'fps', _sanitize_fps(self.fps))
        object.__setattr__(self, 'field_order', VideoFieldOrder(self.field_order))

@dataclass
class PulldownZone:
    sequence: VideoSequence
    pulldown_type: PulldownType
    frames: int = 1

class VideoContext:
    def __init__(self, config: CodecConfig) -> None:
        self.config = config

    def _determine_all_sequences(self, video_sequence: VideoSequence) -> list[PulldownType]:
        fps_ratio = self.config.fps / video_sequence.fps

        sequences = []
        # only allow progressive pulldown with progressive sequences
        # the highest ratio is 3/1 (every frame is tripled)
        if video_sequence.field_order == VideoFieldOrder.PROGRESSIVE and fps_ratio <= Fraction(3, 1):
            sequences.append(PulldownType.PROGRESSIVE)

        # can only repeat a single field per frame. so the highest ratio is 1.5
        # also exclude progressive-only codec configs
        if fps_ratio <= Fraction(3, 2) and self.config.default_field_order != VideoFieldOrder.PROGRESSIVE:
            sequences.append(PulldownType.INTERLACED)

        if len(sequences) == 0:
            raise RuntimeError(f"Impossible pulldown (fps ratio={fps_ratio}) too large (<= 3 for progressive, <= 1.5 for interlaced)")
        return sequences

    def _select_pulldown(self, video_sequence: VideoSequence, prefer_progressive: bool = False) -> PulldownType:
        possible_pulldown_types = self._determine_all_sequences(video_sequence)

        if len(possible_pulldown_types) == 1:
            chosen_pulldown = possible_pulldown_types[0]
        else:
            chosen_pulldown = PulldownType.INTERLACED if not prefer_progressive else PulldownType.PROGRESSIVE
        if self.config.only_interlaced_patterns and chosen_pulldown == PulldownType.PROGRESSIVE:
            raise IllegalPulldownException(f"Progressive sequence in an interlaced-only configuration: {video_sequence} (forced=prefer_progressive)")
        return chosen_pulldown

    @staticmethod
    def _extract_props(frame: 'vs.VideoFrame') -> tuple[VideoSequence, bool]:
        props = frame.props
        fb = VideoFieldOrder(props.get('_FieldBased', 0)) #if unset, then it is progressive
        tbd = props.get('_DurationNum')
        tbn = props.get('_DurationDen')
        vidseq_config = VideoSequence(Fraction(tbn, tbd), fb)
        return vidseq_config, props.get('FavorProgressive', False)

    def find_structures(self, zones: list[PulldownZone]) -> list[list[PicStruct]]:
        # Hard requirement: real interlaced zones enforces specific structures
        filled_zones = [False] * len(zones)

        structures_zones = []
        for zk, zone in enumerate(zones):
            assert zone.frames > 0
            structures = []
            if zone.sequence.field_order != VideoFieldOrder.PROGRESSIVE:
                if zone.sequence.field_order == VideoFieldOrder.TOP_FIELD_FIRST:
                    pic_struct = PicStruct.TOP_BOTTOM
                else:
                    pic_struct = PicStruct.BOTTOM_TOP
                structures += [pic_struct] * zone.frames
                filled_zones[zk] = True
            structures_zones.append(structures)

        # Check for contiguous field order swaps
        frame_cnt = 0
        for (zone1, structs1), (_, structs2) in pairwise(zip(zones, structures)):
            frame_cnt += zone1.frames
            if len(structs1) and len(structs2):
                if structs2[0].get_first_field() != structs1[-1].get_last_field():
                    print(f"Warning: switching field order at frame {frame_cnt} (from zero), this frame must be an IDR.")

        global_error_at_edges = [Fraction(0, 1)] * len(zones)
        global_error = Fraction(0, 1)
        last_structure = PicStruct.PROGRESSIVE_FRAME
        orphan_state = [False] * len(zones)
        orphan_field = False

        recover_from = -1
        zk = frames = 0
        paired_field = None
        while zk < len(zones):
            zone = zones[zk]
            if orphan_field and (zone.pulldown_type == PulldownType.PROGRESSIVE):
                raise OrphanedFieldException(f"Orphaned field from a preceding sequence leaking in another that cannot handle one. {zone}")

            if filled_zones[zk]:
                global_error_at_edges[zk] = global_error
                orphan_state[zk] = orphan_field
                last_structure = structures_zones[zk][-1].get_last_field()
                if zk == 0 or structures_zones[zk-1][-1].is_progressive() or structures_zones[zk][0].is_progressive() or\
                   structures_zones[zk][0].get_last_field() == structures_zones[zk-1][-1].get_last_field():
                    if recover_from == zk:
                        recover_from = -1
                    zk += 1
                    frames += zone.frames
                    continue
                edge_field = structures_zones[zk][0].get_first_field()
                if recover_from < 0:
                    bzk = zk - 1
                    while bzk >= 0 and zones[bzk].pulldown_type == PulldownType.INTERLACED and zones[bzk].sequence.field_order == VideoFieldOrder.PROGRESSIVE:
                        filled_zones[bzk] = False
                        bzk -= 1
                    if bzk == zk-1:
                        raise FieldOrderMismatchException(f"Intractable field pairing, cannot place a {edge_field.get_paired_field().name} field for a mandatory {edge_field.name}.")
                    paired_field = self.config.default_field_order.get_last_field().get_paired_field()
                else:
                    raise FieldOrderMismatchException(f"Intractable field pairing, cannot place a {edge_field.get_paired_field().name} field for a mandatory {edge_field.name}.")
                recover_from = zk
                zk = max(bzk, 0)

                # start off at a valid point to reinitialize global_error
                global_error = global_error_at_edges[zk]
                orphan_field = orphan_state[zk]
                prev_frame = frames
                frames = sum(x.frames for x in zones[:zk])
                last_structure = PicStruct.PROGRESSIVE_FRAME # erased in filled_zones[zk]
                print(f"Failed to converge: swapping fields and starting from last safe anchor (reverting from frame {prev_frame} to {frames}).")
                continue

            structures_zones[zk].clear()
            # reset at boundary zone (no orphaned field: POC of top and bottom fields are equal)
            if zone.pulldown_type == PulldownType.INTERLACED and last_structure.is_progressive():
                last_structure = paired_field or self.config.default_field_order.get_last_field()
            elif zone.pulldown_type == PulldownType.PROGRESSIVE and not last_structure.is_progressive():
                last_structure = PicStruct.PROGRESSIVE_FRAME
            paired_field = None

            count_in_fields = self.config.codec == VideoCodec.AVC and zone.pulldown_type == PulldownType.INTERLACED
            fps_ratio = int(1 + count_in_fields)*self.config.fps/zone.sequence.fps

            for fnum in range(zone.frames):
                duration = round(fps_ratio + global_error)
                duration = max(1, min(3, duration))

                if fnum+1 == zone.frames and zone.pulldown_type == PulldownType.INTERLACED:
                    # Pure interlaced sequence can live with a delta poc, but then we could have
                    # a progressive sequence and no mean to address the orphan, just forbid it.
                    last_zone = zk + 1 == len(zones)
                    orphan_disallowed = last_zone or zones[zk+1].pulldown_type == PulldownType.PROGRESSIVE
                    force_orphan = not last_zone and zones[zk+1].sequence.field_order != VideoFieldOrder.PROGRESSIVE

                    new_duration = duration
                    if force_orphan:
                        last_field = last_structure.get_next_structure(duration, count_in_fields).get_last_field()
                        next_first = structures_zones[zk+1][0].get_first_field()
                        if last_field == next_first:
                            duration = 2 if duration == 3 else 3
                    elif orphan_disallowed:
                        if orphan_field and duration % 2 == 0:
                            new_duration = 3
                        elif not orphan_field and duration % 2 == 1:
                            new_duration = 2
                    if new_duration != duration:
                        print(f"Forcing a structure to have paired fields at a pulldown change: {duration}->{new_duration} at frame: {frames + fnum}.")
                        duration = new_duration
                global_error += fps_ratio - duration
                last_structure = last_structure.get_next_structure(duration, count_in_fields)
                structures_zones[zk].append(last_structure)

                if zone.pulldown_type == PulldownType.INTERLACED and last_structure.get_delta_divisor() % 2 == 1:
                    orphan_field = not orphan_field
            orphan_state[zk] = orphan_field
            filled_zones[zk] = True
            global_error_at_edges[zk] = global_error
            zk += 1
            frames += zone.frames

        assert all(filled_zones)
        assert sum(len(s) for s in structures_zones) == sum(z.frames for z in zones)
        return structures_zones

    def find_zones_from_clip(self, clip: 'vs.VideoNode') -> list[PulldownZone]:
        zones: list[PulldownZone] = []
        current_ctx = PulldownZone(None, None)

        for k in range(len(clip)):
            new_sequence, prefer_progressive = self.__class__._extract_props(clip.get_frame(k))
            if current_ctx.sequence != new_sequence or (prefer_progressive is True and current_ctx.pulldown_type == PulldownType.INTERLACED):
                if new_sequence.fps != self.config.fps and new_sequence.field_order != 0:
                    raise PureInterlacedRateException(f"FPS of TFF/BFF section cannot differ from its container, got fps={new_sequence.video_sequence.fps}.")
                seq_type = self._select_pulldown(new_sequence, prefer_progressive)

                current_ctx = PulldownZone(new_sequence, seq_type)
                zones.append(current_ctx)
            else:
                current_ctx.frames += 1
        return zones
#%%

class PicStructFileV1:
    def __init__(self,
        file: Path | str,
    ) -> None:
        self._fp = Path(file).expanduser().resolve()
        assert self._fp.parent.exists()

    def _write_header(self, f: TextIO) -> None:
        f.write("# picstruct format v1\n\n")
        f.write("# format: frame_num frame_field_order pic_struct\n")

    def write(self, structures_zones: list[list[PicStruct]], zones: list[PulldownZone]) -> None:
        with open(self._fp, 'w') as f:
            self._write_header(f)
            frame_cnt = 0
            for zone, struct_zone in zip(zones, structures_zones):
                assert zone.frames == len(struct_zone)
                f.write(f"\n# ({zone.sequence.fps}), footage={zone.sequence.field_order.name}, pulldown_type={zone.pulldown_type.name}")
                for ps in struct_zone:
                    assert not ps.is_paff(), "PAFF structure cannot be used in a pulldown."
                    f.write(f"\n{frame_cnt} {int(zone.sequence.field_order)} {int(ps)}")
                    frame_cnt += 1
            f.write("\n")
            
    def write_from_clip(self, codec: CodecConfig, clip: 'vs.VideoNode') -> None:
        vctx = VideoContext(codec)
        
        zones = vctx.find_zones_from_clip(clip)
        structures = vctx.find_structures(zones)
        
        self.write(structures, zones)
