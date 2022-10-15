#!/bin/python3

########################
##|   ggmpeg  v0.1   |##
########################
##|       xram       |##
########################

# [References]
# - https://github.com/kkroening/ffmpeg-python
# - https://kkroening.github.io/ffmpeg-python
# - https://ffmpeg.org/ffmpeg-formats.html#concat-1
# - https://ffmpeg.org/ffmpeg-filters.html#drawtext-1
# - https://ffmpeg.org/ffmpeg-filters.html#subtitles
# - https://ffmpeg.org/ffmpeg-utils.html#Expression-Evaluation
# - http://ffmpeg.org/pipermail/ffmpeg-user/2021-January/051566.html

from os import path
from ctypes.wintypes import MAX_PATH
from tkinter.tix import MAX
from typing import Dict, List, Tuple
from enum import Enum
from glob import glob
import ffmpeg
from ffmpeg._run import Error

# General options
class GeneralOpt(Enum):
    input_fps = 'input_fps'
    
# Interpolation filter options
class IntrpOpt(Enum):
    fps = 'fps'
    mi_mode = 'mi_mode'
    mc_mode = 'mc_mode'
    vsbmc = 'vsbmc'
    me = 'me'
    mb_size = 'mb_size'
    
    MODE_OPTS_BLEND = [fps, mi_mode]
    MODE_OPTS_MCI = [fps, mi_mode, mc_mode, vsbmc, me, mb_size]

# Text overlay filter options
class TextOpt(Enum):
    text = 'text'                       # text to render
    expansion = 'expansion'             # text mode: 'normal' (default), 'none' (plaintext)
    pos_x = 'x'                         # x position of top-left corner for text box
    pos_y = 'y'                         # y position of top-left corner for text box
    
    font = 'font'                       # valid options: 'Sans'
    font_file = 'fontfile'              # path to a font file
    font_size = 'fontsize'              # default 16
    font_color = 'fontcolor'            # includes opacity (e.g. 'white@0.8' or '#ffffff@0.8')

    box_enabled = 'box'                 # 1=enable, 0=disable
    box_color = 'boxcolor'              # includes opacity
    box_border_width = 'boxborderw'     # padding for box around text, in pixels

    shadow_color = 'shadowcolor'        # includes opacity
    shadow_x = 'shadowx'                # offset for text shadow (default 0)
    shadow_y = 'shadowy'                # offset for text shadow (default 0)


def get_files(input_dir, input_pattern):
    prefix = '*' if input_pattern != "" else ''
    ext = '*.png' if ".png" not in input_pattern else '*'
    
    input_path_root = path.abspath(input_dir)
    input_path_glob = path.join(input_path_root, f'{prefix}{input_pattern}{ext}').replace("\\", "/")
    input_fullpaths = glob(input_path_glob)
    
    return (input_path_glob, input_fullpaths)


def make_video(input_dir: str,
               input_pattern: str,
               output_filename: str,
               options: Dict[str, str|int|float],
               overlay_text: Dict[str, str] = {},
               final_frame_dur: int = 1,
               debug: bool = False
               ):
    # Other options:
    #  - loop=1 : "loop over input" [.input()]
    #  - search_param=32 : "motion est. search parameter, default=32" [.filter()]

    # TODO: Allow decimal/rational inputs for IntrpOpt.fps (allow input in decimal, then convert to fraction before passing to ffmpeg).
    # TODO: Allow for providing a sequence of numbers to specify the duration of each frame (or other properties)?
    # TODO: Allow for non-interactive command-line arg entry.
    # TODO: Add a keybind to skip all remaining prompts and use defaults.
    # TODO: Delete text file after generation (optionally?).
    # TODO: Fix path for video destination (and other paths?) to work relative to the input folder, and make sure all folders are
    #         correctly read as relative to the terminal directory.

    tmp_concat_file_name = "~ffmpeg_inputs.txt"

    frame_duration = round(1/options[GeneralOpt.input_fps], 8)  # frame_duration = "seconds per frame"
    
    input_path_glob, input_fullpaths = get_files(input_dir, input_pattern)
    
    print(f"Found {len(input_fullpaths)} files matching {input_path_glob}.")

    # Fail if no files were found
    if len(input_fullpaths) < 1:
        print(f"[Error] Found no files matching '{input_path_glob}'")
        return  # TODO: Return error

    with open(tmp_concat_file_name, "wb") as tmp_concat_file:
        tmp_concat_file.write(f"## Input file for ffmpeg 'concat' format. Total frames: {len(input_fullpaths)}. Total duration: {len(input_fullpaths)*frame_duration} s.\n\n".encode())

        for i, fullpath in enumerate(input_fullpaths):
            fullpath = fullpath.replace("'", "\\'")                         # escape any single-quotes for ffmpeg
            tmp_concat_file.write(f"# Frame {i+1}\n".encode())              # add a comment to mark the frame number
            tmp_concat_file.write(f"file '{fullpath}'\n".encode())          # add the file path for this frame
            tmp_concat_file.write(f"duration {frame_duration}\n".encode())  # add the duration for this frame
            
        # Append extra references to the final frame, if enabled
        if final_frame_dur > 1:
            for j in range(int(final_frame_dur)-1):
                tmp_concat_file.write(f"# Frame {len(input_fullpaths)+j+1} - Repeated Final Frame ({j+2}/{int(final_frame_dur)} total)\n".encode())
                tmp_concat_file.write(f"file '{input_fullpaths[-1]}'\n".encode())
                tmp_concat_file.write(f"duration {frame_duration}\n".encode())

    # Set default output path (matching first input image filename), and set absolute path for a provided filename (inside input folder)
    if output_filename == "":
        output_filepath = path.abspath(input_fullpaths[0]).removesuffix('.png') + '.mp4'
        # Catch paths that are too long
        if len(output_filepath) > MAX_PATH:
            path_dir = path.dirname(input_fullpaths[0])
            used_chars = len(path_dir) + len('//') + len('.mp4')
            if used_chars >= MAX_PATH:
                print(f"[Error] Output file destination folder too long.")
                return  # TODO: Return error
            else:
                # If enough space is left after the dir, use truncated filename
                path_base = path.basename(input_fullpaths[0]).removesuffix('.png')
                output_filepath = path.join(path_dir, path_base[:(MAX_PATH - used_chars)] + '.mp4')
    else:
        output_filepath = path.join(path.dirname(input_fullpaths[0]), output_filename)
        # Catch paths that are too long
        if len(output_filepath) > MAX_PATH:
            print(f"[Error] Output filepath too long.")
            return  # TODO: Return error

    #>> Configure input, initialize `stream`
    stream = ffmpeg.input(tmp_concat_file_name,
                          format='concat',
                          safe=0)
    
    #>> Apply interpolation filter
    options_kwargs = {}
        
    if options[IntrpOpt.mi_mode] == 'blend':
        # Prepare keyword args for filter options
        for arg in options.keys():
            if arg.value in IntrpOpt.MODE_OPTS_BLEND.value:
                options_kwargs[arg.value] = options[arg]
                
        stream = ffmpeg.filter(stream, 'minterpolate', **options_kwargs)
        
    elif options[IntrpOpt.mi_mode] == 'mci':
        # Prepare keyword args for filter options
        for arg in options.keys():
            if arg.value in IntrpOpt.MODE_OPTS_MCI.value:
                options_kwargs[arg.value] = options[arg]
                
        stream = ffmpeg.filter(stream, 'minterpolate', **options_kwargs)

    #>> Apply text overlay filter
    if overlay_text.get(TextOpt.text) is not None:
        overlay_text_kwargs = {}
        # Prepare keyword args for text overlay
        for param in overlay_text.keys():
            overlay_text_kwargs[param.value] = overlay_text[param]
        
        stream = ffmpeg.drawtext(stream, escape_text=False, **overlay_text_kwargs)

    #>> Configure output
    stream = ffmpeg.output(stream, output_filepath, format='mp4', vcodec='libx264', crf=15)

    #>> Run ffmpeg
    try:
        out, err = ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
    except Error as e:
        print("-------- Error thrown by `ffmpeg._run` --------")
        print(f"\n[stdout]\n{e.stdout}")
        print(f"\n[stderr]\n{e.stderr}")
    
    if debug:
        print(f"\n[Output]\n{out}")
        print(f"\n[Error]\n{err}")


def parse_choice(choice: str, options: List[str]|Tuple[int,int]|Tuple[float,float], default: str):
    # Default on empty choice
    if choice == "" or choice == None: return default

    # Parse Tuple[int,int] (numerical range) options
    if isinstance(options, tuple) and isinstance(options[0], int):
        try:
            choice = int(choice)
        except:
            print(f'Cannot parse "{choice}" as an integer. Using default value: {default}.')
            return default

        if not options[0] <= choice <= options[1]:
            print(f'Invalid value: {choice} (must be within {options[0]}-{options[1]}). Using default value: {default}.')
            return default

        return choice

    # Parse Tuple[float,float] (numerical range) options
    elif isinstance(options, tuple) and isinstance(options[0], float):
        try:
            choice = float(choice)
        except:
            print(f'Cannot parse "{choice}" as a float. Using default value: {default}.')
            return default

        if not options[0] <= choice <= options[1]:
            print(f'Invalid value: {choice} (must be within {options[0]}-{options[1]}). Using default value: {default}.')
            return default

        return choice

    # Parse List[str] options
    elif isinstance(options, list):
        for opt in options:
            if choice.strip().lower() == opt:
                return opt
        else:
            print(f'Unrecognized value "{choice}". Using default value: {default}.')
            return default

    else:
        print(f'Something went wrong... Using default value: {default}.')
        return default


if __name__ == '__main__':
    filter_options = {
        IntrpOpt.mc_mode: ['aobmc', 'obmc'],
        IntrpOpt.vsbmc: ['0', '1'],
        IntrpOpt.me: ['ds', 'epzs', 'esa', 'fss', 'hexbs', 'ntss', 'tdls', 'tss', 'umh'],
        IntrpOpt.mb_size: (1,512),
    }
    filter_defaults = {
        IntrpOpt.mc_mode: 'aobmc',
        IntrpOpt.vsbmc: '1',
        IntrpOpt.me: 'epzs',
        IntrpOpt.mb_size: 16,
    }
    docs = {
        'Notes': ['`*` indicates defaults.', '`mc_mode`, `vsbmc`, `me`, and `mb_size` only apply to `mi_mode=mci`.']
    }

    print('|==| better_ffmpeg |==|')
    print('| - Defaults indicated by ^')
    print()


    #### CLI ####
    retry_loop = True
    while retry_loop:
        choices = {}
        retry_loop = False

        # Collect general options
        c_in = input('Path to folder containing image files (can be relative) [^"."]: ')
        c_in = c_in.strip().replace('\\', '/')  # BUG: Handle '[', ']', and other chars in filepath. glob fails if these are included.
        input_dir = c_in if (c_in != "") else "."

        c_in = input('Pattern to match files in folder [^""]: ')
        input_pattern = c_in.strip() if (c_in.strip() != "") else ""

        c_in = input('File name for output video [^"<name-of-first-input-image>.mp4"]: ')
        output_filename = c_in.strip() if (c_in.strip() != "") else ""
        if (output_filename != "") and (".mp4" not in output_filename.lower()):
            output_filename += ".mp4"

        c_in = input('Input FPS [^15]: ')
        choices[GeneralOpt.input_fps] = parse_choice(c_in, (0.1, 144.0), 15.0)

        c_in = input('Interpolation FPS [^60]: ')
        choices[IntrpOpt.fps] = parse_choice(c_in, (1, 144), 60)

        c_in = input(f'{IntrpOpt.mi_mode.value} [^mci/blend]: ')
        choices[IntrpOpt.mi_mode] = parse_choice(c_in, ['blend', 'mci'], 'mci')

        # Continue collecting 'mci' filter options, if selected
        if choices[IntrpOpt.mi_mode] == 'mci':
            for option in filter_options.keys():
                # Make prompt string
                pmt_start = f'{option.value} ['
                pmt_opt = ''
                pmt_end = ']: '
                for o in filter_options[option]:
                    pmt_opt += f'^{o}/' if (o == filter_defaults[option]) else f'{o}/'
                pmt = pmt_start + pmt_opt[:-1] + pmt_end  # removing extra '/' from the end of pmt_opt

                # Read choice
                c_in = input(pmt)
                choices[option] = parse_choice(c_in, filter_options[option], filter_defaults[option])

        result = make_video(input_dir, input_pattern, output_filename, choices)

        ## TODO ##
        # if {FAIL}:
        #     print(result)
        #     retry_loop = True

        # elif {SUCCESS}:
        #     print(result)