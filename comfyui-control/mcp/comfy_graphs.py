"""Graph builders + PNG workflow extraction for the comfyui MCP server.

Pure stdlib. Every builder returns an API-format graph: {node_id: {class_type,
inputs}}. Node input names were verified against the live 0.26.0 object_info.
"""

import json
import struct
import zlib


# --------------------------------------------------------------- shared pieces

def _clip_and_model(graph: dict, checkpoint: str, lora_spec: str) -> tuple:
    """Wire checkpoint (+optional TripleCLIP for SD3, +LoRA chain).
    Returns (model_ref, clip_ref, vae_ref). Uses node ids 1, 8, 9x."""
    graph["1"] = {"class_type": "CheckpointLoaderSimple",
                  "inputs": {"ckpt_name": checkpoint}}
    model, vae = ["1", 0], ["1", 2]
    if "sd3" in checkpoint.lower():
        # SD3.5 official checkpoints ship without embedded text encoders.
        graph["8"] = {"class_type": "TripleCLIPLoader",
                      "inputs": {"clip_name1": "clip_g.safetensors",
                                 "clip_name2": "clip_l.safetensors",
                                 "clip_name3": "t5xxl_fp8_e4m3fn.safetensors"}}
        clip = ["8", 0]
    else:
        clip = ["1", 1]
    # LoRA chain: "name:strength,name2:strength2" (strength optional, def 0.8)
    if lora_spec:
        for i, part in enumerate(p.strip() for p in lora_spec.split(",") if p.strip()):
            name, _, s = part.partition(":")
            nid = f"9{i}"
            graph[nid] = {"class_type": "LoraLoader",
                          "inputs": {"model": model, "clip": clip,
                                     "lora_name": name.strip(),
                                     "strength_model": float(s or 0.8),
                                     "strength_clip": float(s or 0.8)}}
            model, clip = [nid, 0], [nid, 1]
    return model, clip, vae


def _encode_and_save(graph: dict, model, clip, vae, prompt: str, negative: str,
                     latent, seed: int, steps: int, cfg: float, sampler: str,
                     scheduler: str, denoise: float, tiled_vae: bool) -> None:
    graph["2"] = {"class_type": "CLIPTextEncode",
                  "inputs": {"text": prompt, "clip": clip}}
    graph["3"] = {"class_type": "CLIPTextEncode",
                  "inputs": {"text": negative, "clip": clip}}
    graph["5"] = {"class_type": "KSampler",
                  "inputs": {"model": model, "positive": ["2", 0],
                             "negative": ["3", 0], "latent_image": latent,
                             "seed": seed, "steps": steps, "cfg": cfg,
                             "sampler_name": sampler, "scheduler": scheduler,
                             "denoise": denoise}}
    if tiled_vae:
        graph["6"] = {"class_type": "VAEDecodeTiled",
                      "inputs": {"samples": ["5", 0], "vae": vae,
                                 "tile_size": 512, "overlap": 64,
                                 "temporal_size": 64, "temporal_overlap": 8}}
    else:
        graph["6"] = {"class_type": "VAEDecode",
                      "inputs": {"samples": ["5", 0], "vae": vae}}
    graph["7"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["6", 0], "filename_prefix": "mcp"}}


# --------------------------------------------------------------- image graphs

def txt2img(checkpoint, prompt, negative, width, height, seed, steps, cfg,
            sampler, scheduler, lora_spec="", tiled_vae=False,
            hires_scale=0.0) -> dict:
    """hires_scale (1.5-2.0): latent-space hires-fix — LatentUpscaleBy ->
    second low-denoise KSampler (same seed/prompts) -> tiled decode (forced,
    regardless of tiled_vae). The projection mastering path."""
    graph: dict = {}
    model, clip, vae = _clip_and_model(graph, checkpoint, lora_spec)
    latent_class = "EmptySD3LatentImage" if "sd3" in checkpoint.lower() \
        else "EmptyLatentImage"
    graph["4"] = {"class_type": latent_class,
                  "inputs": {"width": width, "height": height, "batch_size": 1}}
    _encode_and_save(graph, model, clip, vae, prompt, negative, ["4", 0],
                     seed, steps, cfg, sampler, scheduler, 1.0,
                     tiled_vae or hires_scale > 0)
    if hires_scale:
        graph["12"] = {"class_type": "LatentUpscaleBy",
                       "inputs": {"samples": ["5", 0],
                                  "upscale_method": "bicubic",
                                  "scale_by": hires_scale}}
        graph["13"] = {"class_type": "KSampler",
                       "inputs": {"model": model, "positive": ["2", 0],
                                  "negative": ["3", 0],
                                  "latent_image": ["12", 0],
                                  "seed": seed, "steps": steps, "cfg": cfg,
                                  "sampler_name": sampler,
                                  "scheduler": scheduler, "denoise": 0.25}}
        graph["6"]["inputs"]["samples"] = ["13", 0]
    return graph


def img2img(checkpoint, image_name, prompt, negative, denoise, seed, steps,
            cfg, sampler, scheduler, lora_spec="", tiled_vae=False) -> dict:
    graph: dict = {}
    model, clip, vae = _clip_and_model(graph, checkpoint, lora_spec)
    graph["10"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    graph["4"] = {"class_type": "VAEEncode",
                  "inputs": {"pixels": ["10", 0], "vae": vae}}
    _encode_and_save(graph, model, clip, vae, prompt, negative, ["4", 0],
                     seed, steps, cfg, sampler, scheduler, denoise, tiled_vae)
    return graph


def inpaint(checkpoint, image_name, mask_name, prompt, negative, seed, steps,
            cfg, sampler, scheduler, grow_mask_by=16, lora_spec="") -> dict:
    """Mask = a separate uploaded image; white (red channel) areas regenerate."""
    graph: dict = {}
    model, clip, vae = _clip_and_model(graph, checkpoint, lora_spec)
    graph["10"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    graph["11"] = {"class_type": "LoadImageMask",
                   "inputs": {"image": mask_name, "channel": "red"}}
    graph["4"] = {"class_type": "VAEEncodeForInpaint",
                  "inputs": {"pixels": ["10", 0], "vae": vae,
                             "mask": ["11", 0], "grow_mask_by": grow_mask_by}}
    _encode_and_save(graph, model, clip, vae, prompt, negative, ["4", 0],
                     seed, steps, cfg, sampler, scheduler, 1.0, False)
    return graph


def upscale(image_name, model_name) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "UpscaleModelLoader",
              "inputs": {"model_name": model_name}},
        "3": {"class_type": "ImageUpscaleWithModel",
              "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
        "4": {"class_type": "SaveImage",
              "inputs": {"images": ["3", 0], "filename_prefix": "mcp_upscaled"}},
    }


# --------------------------------------------------------------- video graph

def ltxv_txt2video(checkpoint, t5_name, prompt, negative, width, height,
                   frames, fps, seed, steps, cfg) -> dict:
    """Official LTX-Video t2v shape: CheckpointLoaderSimple carries the video
    VAE; CLIPLoader(type=ltxv) drives T5; LTXVScheduler sigmas into
    SamplerCustom; CreateVideo+SaveVideo produce an mp4 in output/video."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": t5_name, "type": "ltxv"}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["2", 0]}},
        "5": {"class_type": "EmptyLTXVLatentVideo",
              "inputs": {"width": width, "height": height,
                         "length": frames, "batch_size": 1}},
        "6": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["3", 0], "negative": ["4", 0],
                         "frame_rate": float(fps)}},
        "7": {"class_type": "LTXVScheduler",
              "inputs": {"steps": steps, "max_shift": 2.05, "base_shift": 0.95,
                         "stretch": True, "terminal": 0.1, "latent": ["5", 0]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "SamplerCustom",
              "inputs": {"model": ["1", 0], "add_noise": True,
                         "noise_seed": seed, "cfg": cfg,
                         "positive": ["6", 0], "negative": ["6", 1],
                         "sampler": ["8", 0], "sigmas": ["7", 0],
                         "latent_image": ["5", 0]}},
        "10": {"class_type": "VAEDecode",
               "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "CreateVideo",
               "inputs": {"images": ["10", 0], "fps": float(fps)}},
        "12": {"class_type": "SaveVideo",
               "inputs": {"video": ["11", 0], "filename_prefix": "video/mcp",
                          "format": "mp4", "codec": "h264"}},
    }


def ltxv_img2video(checkpoint, t5_name, image_name, prompt, negative, width,
                   height, frames, fps, seed, steps, cfg, strength=0.9,
                   loop=True, img_compression=35) -> dict:
    """LTX-Video image-to-video with keyframe guides (verified against 0.26.0
    nodes_lt.py). The input still is pinned at frame 0 via LTXVAddGuide; with
    loop=True a second guide pins the SAME image at frame_idx=-1 (negative
    indices count from the end) -> the clip is a true seamless cycle, no
    crossfade ghosting. Pair with a steady-state motion prompt (motion must be
    mid-cycle at start/end, never "begins to..."). LTXVCropGuides strips the
    appended guide latents after sampling — mandatory. LTXVPreprocess
    jpeg-degrades the still to match LTXV's training distribution."""
    guide_common = {"vae": ["1", 2], "image": ["21", 0], "strength": strength}
    graph = {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": t5_name, "type": "ltxv"}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["2", 0]}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["2", 0]}},
        "5": {"class_type": "EmptyLTXVLatentVideo",
              "inputs": {"width": width, "height": height,
                         "length": frames, "batch_size": 1}},
        "6": {"class_type": "LTXVConditioning",
              "inputs": {"positive": ["3", 0], "negative": ["4", 0],
                         "frame_rate": float(fps)}},
        "20": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "21": {"class_type": "LTXVPreprocess",
               "inputs": {"image": ["20", 0],
                          "img_compression": img_compression}},
        "22": {"class_type": "LTXVAddGuide",
               "inputs": {"positive": ["6", 0], "negative": ["6", 1],
                          "latent": ["5", 0], "frame_idx": 0, **guide_common}},
    }
    last = "22"
    if loop:
        graph["23"] = {"class_type": "LTXVAddGuide",
                       "inputs": {"positive": ["22", 0], "negative": ["22", 1],
                                  "latent": ["22", 2], "frame_idx": -1,
                                  **guide_common}}
        last = "23"
    graph.update({
        "7": {"class_type": "LTXVScheduler",
              "inputs": {"steps": steps, "max_shift": 2.05, "base_shift": 0.95,
                         "stretch": True, "terminal": 0.1,
                         "latent": [last, 2]}},
        "8": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "9": {"class_type": "SamplerCustom",
              "inputs": {"model": ["1", 0], "add_noise": True,
                         "noise_seed": seed, "cfg": cfg,
                         "positive": [last, 0], "negative": [last, 1],
                         "sampler": ["8", 0], "sigmas": ["7", 0],
                         "latent_image": [last, 2]}},
        "24": {"class_type": "LTXVCropGuides",
               "inputs": {"positive": [last, 0], "negative": [last, 1],
                          "latent": ["9", 0]}},
        "10": {"class_type": "VAEDecode",
               "inputs": {"samples": ["24", 2], "vae": ["1", 2]}},
        "11": {"class_type": "CreateVideo",
               "inputs": {"images": ["10", 0], "fps": float(fps)}},
        "12": {"class_type": "SaveVideo",
               "inputs": {"video": ["11", 0], "filename_prefix": "video/mcp_i2v",
                          "format": "mp4", "codec": "h264"}},
    })
    return graph


# ------------------------------------------------------- PNG workflow extract

def png_workflow(png_path: str) -> dict:
    """Extract the API-format graph ComfyUI embeds in every PNG it saves
    (tEXt/zTXt/iTXt chunk keyed 'prompt')."""
    data = open(png_path, "rb").read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    while pos < len(data) - 12:
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        if typ in (b"tEXt", b"zTXt", b"iTXt"):
            key, _, rest = chunk.partition(b"\x00")
            if key == b"prompt":
                if typ == b"zTXt":
                    rest = zlib.decompress(rest[1:])
                elif typ == b"iTXt":
                    comp = rest[0:1]
                    rest = rest.split(b"\x00", 2)[-1]
                    if comp == b"\x01":
                        rest = zlib.decompress(rest)
                return json.loads(rest.decode("utf-8", "replace"))
        pos += 12 + ln
    raise ValueError("no embedded 'prompt' workflow found (not a ComfyUI PNG?)")
