#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import e2s_sample_all as e2s
import RIFF
import os
import math
import argh
import glob
import re
from Oe2sSLE_GUI import SampleAllEditor


def make_korg_sample(filename, import_num, category="User", name=None):
    import_num = int(import_num)
    with open(filename, 'rb') as f:
        sample = e2s.e2s_sample(f)

    if not sample.RIFF.chunkList.get_chunk(b'korg'):
        korg_data = e2s.RIFF_korg()
        korg_chunk = RIFF.Chunk(header=RIFF.ChunkHeader(id=b'korg'), data=korg_data)
        sample.RIFF.chunkList.chunks.append(korg_chunk)
        sample.header.size += len(korg_chunk)
    fmt = sample.get_fmt()
    if fmt.formatTag != fmt.WAVE_FORMAT_PCM:
        return False
    if fmt.bitPerSample != 16:
        return False
    korg_chunk = sample.RIFF.chunkList.get_chunk(b'korg')
    esli_chunk = korg_chunk.data.chunkList.get_chunk(b'esli')
    if not esli_chunk:
        esli = e2s.RIFF_korg_esli()
        esli_chunk = RIFF.Chunk(header=RIFF.ChunkHeader(id=b'esli'), data=esli)
        korg_chunk.data.chunkList.chunks.append(esli_chunk)
        data = sample.get_data()
        esli.samplingFreq = fmt.samplesPerSec
        esli.OSC_EndPoint_offset = esli.OSC_LoopStartPoint_offset = len(data) - fmt.blockAlign
        esli.WAV_dataSize = len(data)
        if fmt.blockAlign == 4:
            # stereo
            esli.useChan1 = True
        # by default use maximum volume (not like electribe that computes a good value)
        esli.playVolume = 65535

        # by default play speed is same as indicated by Frequency
        esli.playLogPeriod = 65535 if fmt.samplesPerSec == 0 else max(0, int(
            round(63132 - math.log2(fmt.samplesPerSec) * 3072)))
        esli_chunk.header.size += len(esli_chunk)
        sample.header.size += len(esli_chunk)

        # check if smpl chunk is used
        smpl_chunk = sample.RIFF.chunkList.get_chunk(b'smpl')
        if smpl_chunk:
            # use it to initialize loop point
            if smpl_chunk.data.numSampleLoops > 0:
                # todo: if several LoopData, propose to generate several wavs ?
                smpl_loop = smpl_chunk.data.loops[0]
                if smpl_loop.playCount != 1:
                    # looping sample
                    start = smpl_loop.start * fmt.blockAlign
                    end = smpl_loop.end * fmt.blockAlign
                    if start < end and end <= len(data) - fmt.blockAlign:
                        esli.OSC_LoopStartPoint_offset = start - esli.OSC_StartPoint_address
                        esli.OSC_OneShot = 0
                        esli.OSC_EndPoint_offset = end - esli.OSC_StartPoint_address
        # check if cue chunk is used
        cue_chunk = sample.RIFF.chunkList.get_chunk(b'cue ')
        if cue_chunk:
            num_cue_points = cue_chunk.data.numCuePoints
            num_slices = 0
            num_samples = len(data) // fmt.blockAlign
            for cue_point_num in range(num_cue_points):
                cue_point = cue_chunk.data.cuePoints[cue_point_num]
                if cue_point.fccChunk != b'data' or cue_point.sampleOffset >= num_samples:
                    # unhandled cue_point
                    continue
                else:
                    esli.slices[num_slices].start = cue_point.sampleOffset
                    esli.slices[num_slices].length = num_samples - cue_point.sampleOffset
                    if num_slices > 0:
                        esli.slices[num_slices - 1].length = esli.slices[num_slices].start - esli.slices[
                            num_slices - 1].start
                    num_slices += 1
                    if num_slices >= 64:
                        break
    else:
        esli = esli_chunk.data
    if name:
        esli.OSC_name = bytes(name, 'ascii', 'ignore')
    else:
        esli.OSC_name = bytes(os.path.splitext(os.path.basename(filename))[0], 'ascii', 'ignore')
    if category in e2s.esli_str_to_OSC_cat:
        esli.OSC_category = e2s.esli_str_to_OSC_cat[category]
    esli.OSC_0index = import_num -1

    return sample.get_clean_copy()


def from_e2s(input_e2s_file, output_dir):
    """
    Export all samples in an electribe file
    """
    all_samples = e2s.e2s_sample_all(filename=input_e2s_file)
    for sample in all_samples.samples:
        esli = sample.RIFF.chunkList.get_chunk(b'korg').data.chunkList.get_chunk(b'esli').data
        filename = "{}/{:0>3}-{}-{}.wav".format(os.path.abspath(output_dir), esli.OSC_0index + 1,
                                                e2s.esli_OSC_cat_to_str[esli.OSC_category],
                                                esli.OSC_name.decode('ascii', 'ignore').split('\x00')[0])
        with open(filename, 'wb') as f:
            sample.write(f, export_smpl=True, export_cue=True)


def to_e2s(input_dir, output_e2s_file):
    """
    Import all samples to an electribe file
    """
    all_samples = e2s.e2s_sample_all()
    for path in glob.glob(input_dir + "/*.wav"):
        found = re.findall(r'''([0-9]+)-(.+)-(.+)\.wav''', os.path.basename(path))
        if found:
            korg_sample = make_korg_sample(filename=path, import_num=found[0][0], category=found[0][1],
                                           name=found[0][2])
            if not korg_sample:
                print("Error. Could not import {}. Import aborted.".format(path))
                return
            all_samples.samples.append(korg_sample)
    all_samples.save(output_e2s_file)


parser = argh.ArghParser()
parser.add_commands([from_e2s, to_e2s])
parser.dispatch()
