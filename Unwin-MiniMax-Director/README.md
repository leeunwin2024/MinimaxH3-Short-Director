# Unwin MiniMax Director v0.3 — local prototype

A standalone ComfyUI extension based on the locally supplied ALLinONE MiniMax H3 T2V/I2V workflow templates. No external API calls. Does not require MiniMaxH3MotionContextSaveLatent, MiniMaxH3MotionContext or MiniMaxH3MotionContextTrim.

## Installation
Copy the `Unwin-MiniMax-Director` directory to your ComfyUI Desktop installation's `ComfyUI/custom_nodes` folder, restart ComfyUI Desktop, hard-refresh the browser. Add `Unwin Director Timeline` to a workflow, then click `OPEN UNWIN DIRECTOR`.

## Features implemented
- Scene timeline: add, duplicate, reorder, delete, edit direction, duration and seed; save project in node properties; import/export JSON.
- Local model scanner and selector; video/audio VAE and text encoder selection.
- Sequential rendering through the local ComfyUI `/prompt` endpoint using included T2V and I2V API templates; per-scene output tracking and rerender.
- Continuity: extract previous MP4's last frame with local FFmpeg, stage in ComfyUI input, and inject into next I2V graph when the installed I2V conditioning node advertises a compatible image input.
- Stitch locally using FFmpeg into output/unwin_director_*.mp4; trims no overlaps, discards clip audio in this first stitching backend.
- Detailed queue errors and a diagnostics log.
- Existing `Unwin Last Frame`, `Unwin Extract Video Frame` and `Unwin Local Video Stitch` standalone nodes.

## Limitations / preflight notes
This is a prototype, **not verified against your running ComfyUI**. It relies on installed ComfyUI MiniMaxH3ImageToVideo, MiniMaxH3ReferenceToVideo, MiniMaxH3SigmaShift, video/audio VAE and other template classes. The source package's I2V template does not include a first-frame connection by default. The director checks the installed conditioning node's input schema; if none of `start_image`, `image`, `first_frame`, `reference_image` exists, it stops with an explicit error rather than silently render without continuity. Some MiniMax H3 versions use keyframe conditioning instead; this needs adapting to your installed schema.

Model compatibility is **not automatically guaranteed**: choose the matching video model, CLIP, video VAE, and audio VAE. Fast/Turbo checkpoint defaults are not auto-calibrated. The prototype does not yet include LoRA application, latent upscale, audio-preserving stitching, scene thumbnail strip or a resumable background server worker. It supports 1–15 second scene controls but actual model frame limits may be lower. The browser must stay open during a multi-scene queue. FFmpeg must be on PATH. The UI is a modal launched from a node, not an independently docked editor.

## Testing
Start with one 3-second T2V scene and a valid local model quartet. Confirm a saved video. Then add a second scene and enable carry to test your installed I2V conditioning. If you get a schema error, send the text and `/object_info/MiniMaxH3ImageToVideo` schema to adjust the adapter.

## Safety
Original ALLinONE installation is not modified. All video paths are resolved inside ComfyUI's output folder. The director uses ComfyUI's local HTTP server only; no internet calls are made by this extension.

## v0.4 additions
- Optional model-only LoRA injection using local `LoraLoaderModelOnly`. LoRA must match the selected MiniMax checkpoint; file visibility does not establish compatibility.
- Experimental 2x latent scaling through `LatentUpscaleBy` before video VAE decode. **H3 video/audio latents may be incompatible with generic latent upscaling. Keep OFF until tested.** It does not upscale audio.
- Audio-preserving local FFmpeg stitching: each source is re-encoded to 48 kHz stereo AAC and H.264 at the selected frame rate; silent audio is generated for clips without an audio stream. This avoids dropping all audio during stitching. Source audio timing may need further validation.
- Optional final 2x FFmpeg Lanczos video enlargement (not neural super-resolution). This is the safer upscale choice for initial testing.
- No external inference services; the director uses only the local ComfyUI server.

**Testing status:** Python syntax checked. No access to the user's ComfyUI models or live H3 sampler; full rendering, LoRA compatibility, latent upscale and audio sync are not verified end-to-end. Do a one-scene test with latent upscale disabled first.

## v0.5 diagnostic fix
Execution errors now show the failing node ID, class and first error line instead of thousands of tensor values. This does not fix the underlying model/runtime error.


## v0.6 output discovery fix
The director now checks nested ComfyUI history output metadata and, if SaveVideo does not publish a video entry, searches the local ComfyUI output directory for the uniquely named render. This allows completed renders to populate the timeline. Restart ComfyUI after installing. This does not change the model workflow.


## v0.7 additions
- Minimise button collapses the director to a small floating bar, exposing the ComfyUI canvas; click again to restore.
- Rendered-scene filmstrip with independent playback before stitching.
- Local VRAM detection and an **installed-model-only** auto-selection heuristic for 8GB/16GB/higher GPUs. This is NOT an assertion that any given checkpoint/encoder combination is compatible; verify with a short test.
- Verify models/FFmpeg reports local files and whether paths resolve. Model downloads are **not** automated: arbitrary model URLs, licences, and compatibility must be verified before installing.
- Exact last-frame extraction from the final ~2 seconds (reverse filter), replacing approximate -0.5s extraction.
- Optional seam trim of one frame from each subsequent clip during stitching; this can reduce duplicated carried frames. It does not guarantee motion-perfect continuity.
- FFmpeg search checks PATH, imageio_ffmpeg if available, and common adjacent folders.

### Known limits
- Auto-selection cannot know exact model architecture from filenames and does not automatically download models.
- GPU memory recommendations are heuristics, not guaranteed render capacity.
- Seam trim removes a repeated frame, but different generated motion may still require blending/optical-flow processing.
- No actual ComfyUI GPU render was run in this packaging environment.


## v0.8 resolution and LoRA discovery

- Resolution presets: 640×352, 768×432, 960×544, 1280×720, and portrait equivalents; custom width/height supported. Dimensions validated as multiples of 16 before queueing. Higher presets may exhaust VRAM.
- LoRA dropdown lists locally installed LoRAs. A compatibility advisory flags filenames not clearly identified as MiniMax H3; filenames alone **cannot prove** compatibility.
- **Find H3 LoRAs / downloads** opens Hugging Face model search (https://huggingface.co/models?search=MiniMax%20H3%20LoRA). These are discovery links, not a curated or verified compatibility list, and do not install anything. Verify each model card, architecture, checkpoint, licence, and required trigger words.
- Install approved safetensors LoRAs under ComfyUI/models/loras and press Refresh models.
- Model downloads, automatic compatibility verification, and live GPU render testing are not included.

## v0.9: Save and Load Project

Use **Save Project** in the director header to name your project and download a `.unwin.json` file. The file contains the ordered scenes, prompts, durations, seeds, model/LoRA choices, settings, render statuses, and relative output references. **Load Project** opens a local `.json` file and restores the timeline. Existing projects are still stored in the ComfyUI node's workflow properties when you save the ComfyUI workflow.

**Important:** A project JSON is not a media archive. Rendered video previews will only work while their original MP4 files remain in the ComfyUI output directory at the same relative paths. Export the videos separately when moving projects between machines. Loading a project replaces the current timeline; save the current project first.

## v1.0 Model Manager
The director toolbar now includes **Model Manager**. The catalogue uses fixed, reviewed
Hugging Face repository/file URLs, rather than filename guessing. Downloads are opt-in,
use HTTPS, stream to a temporary file in the correct ComfyUI models folder, validate the
safetensors header, and atomically rename only after successful completion. One listed
LoRA has a published SHA-256 in the registry, and its hash is checked on installation;
other files use structural checks only and are explicitly NOT described as hash-verified.
Click Verify to run the available checks. The manager polls for progress every 2.5 seconds.
Download jobs live in ComfyUI's Python process; restarting ComfyUI interrupts a download.
The manager does not promise that a model fits 8GB or 16GB VRAM. It does not automatically
accept model licenses, authenticate to gated repos, or support pause/resume.


## v1.0.1 timeout hotfix
- Increased frontend history wait from 24 to 90 minutes for slower MiniMax H3 renders.
- Records queued prompt ID in project state and logs waiting status every minute.
- A timeout does not cancel a ComfyUI render. Check ComfyUI queue and console before retrying.
- Does not change model inference speed or solve a stalled sampler/OOM.


## v1.0.3: Offline AI Video Upscale

The **AI Video Upscale** toolbar button processes any rendered scene or the latest stitched project using the **optional external Real-ESRGAN NCNN Vulkan** executable. It runs fully locally; no cloud API. The engine is **not bundled** and must be installed separately from the official releases: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases . Download the Windows package including the `models` folder. Either put `realesrgan-ncnn-vulkan.exe` on PATH, place it at `Unwin-MiniMax-Director/tools/realesrgan-ncnn-vulkan.exe` (with the `models` folder beside it), or set `UNWIN_REALESRGAN_EXE` to the full executable path before starting ComfyUI.

Choose **realesrgan-x4plus** for photorealistic scenes; 2× output is recommended as a starting point. The manager extracts all frames to a temporary directory, runs Real-ESRGAN on the GPU, then re-encodes H.264 and copies the original audio. The temporary directory is deleted after the job. Requires significant temporary disk space, and long clips can take time. The model must exist in the Real-ESRGAN package's `models` directory. Status and per-frame progress are displayed in the upscale dialog. The resulting MP4 is saved to ComfyUI output.

For photorealistic character consistency, use a locked character description (age, hair, eye colour, wardrobe, distinctive features) repeated verbatim in every scene, image-to-video with a reference frame, consistent lighting and camera settings, and minimal changes between shots. Frame carryover alone cannot guarantee facial identity. AI upscaling sharpens frames but does not repair inconsistent faces, poor hands, or temporal flicker.

## v1.0.4 Character / Location Studio

Click **Character / Location Studio** in the director toolbar. Upload a PNG/JPG/WebP reference (18MB max), enter a name and a fixed character/location description, then click **Create reference sheet**. This creates a labelled contact sheet with the source reference and marked placeholders for angles that are not available. It **does not fabricate new viewpoints**; those require an image-edit workflow. Click **Save to project** to retain metadata in exported `.unwin.json`. The actual images are saved to `studio_assets/` inside this custom node folder. Back up this directory when updating; JSON alone does not embed image bytes.

**Add description to selected scene** inserts the identity/location description into the current video scene prompt. This is a prompt aid, not a trained identity lock or true H3 image reference conditioning. Use the existing I2V start frame to reinforce consistency. The **Validate local image model installation** control checks six exact ComfyUI model filenames. It does not test model compatibility at inference time. Download/documentation links for Qwen Image Edit and Z-Image are provided in the Studio window; automated image generation and automated downloads for those models are NOT yet implemented.

**AI upscale selected reference (2x)** sends the saved source image through the portable Real-ESRGAN Vulkan executable, using tile size 128 to reduce peak GPU usage. The original is preserved. If GPU memory remains insufficient, use the executable manually with `-t 64`. AI enhancement may invent texture or subtly alter facial details, so keep the original reference as the source of identity.

### Install Real-ESRGAN on Windows 11 (portable, no Python install)

1. Download the official portable Windows ZIP: https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip
2. Extract it (do not run it from inside the ZIP). Keep the `models` folder beside `realesrgan-ncnn-vulkan.exe`.
3. Copy **both** `realesrgan-ncnn-vulkan.exe` and its entire `models` directory to `ComfyUI/custom_nodes/Unwin-MiniMax-Director/tools/` (create `tools` if necessary).
4. Restart ComfyUI Desktop. The director's AI Video Upscale button should detect the engine, and Character / Location Studio image upscaling uses the same executable.
5. To test manually in PowerShell, change to the folder containing the executable and run:

   `./realesrgan-ncnn-vulkan.exe -i "C:\\path\\to\\photo.png" -o "C:\\path\\to\\enhanced.png" -n realesrgan-x4plus -s 2 -t 128`

   For memory problems use `-t 64`. This is image enhancement, not guaranteed identity preservation.

Official README: https://github.com/xinntao/Real-ESRGAN/blob/master/README.md

**Compatibility:** image-edit models need their own separate ComfyUI graph. This release validates installation and manages reference images, but does not automatically render six newly imagined character angles or generate new locations using Qwen/Z-Image. It avoids silently substituting resized/cropped copies as synthetic viewpoints.


## v1.0.5 native ComfyUI image workflow bridge

Character/Location Studio now imports **API-format** ComfyUI workflow JSON files (enable Dev Mode > Save API Format, or use workflow export as API JSON). It runs the graph locally using ComfyUI's `/prompt` and `/history` endpoints. You must select the appropriate prompt node and, for Qwen reference edits, a `LoadImage` node in the graph. For Z-Image, choose the Z-Image engine and import a compatible text-to-image workflow. For Qwen, import a compatible Qwen Image Edit workflow and select the LoadImage that feeds the reference image. The **Generate 4-view character sheet** action runs four Qwen image edits and assembles a real generated sheet. It is not guaranteed to preserve exact facial identity. Image-model downloads and validation remain on the Studio and Model Manager pages; workflow import is needed because the available model variants use different ComfyUI node graphs. Images are generated to the ComfyUI output folder; sheets go into `studio_assets`. Back up `studio_assets` on upgrade.


## v1.0.6 automatic image workflows

Character Studio now builds ComfyUI API graphs locally for Qwen Image Edit and Z-Image Turbo without importing JSON. It detects model filenames from ComfyUI folders and checks node input names using `/object_info`. This is an initial built-in graph template; actual model inference compatibility varies by ComfyUI version, especially Qwen Image Edit conditioning/latent interfaces. Use **Detect models & validate workflow** before rendering. The generator does not download models automatically; use Model Manager.


## v1.0.7 scene references
Character/Location Studio has been removed from the Director toolbar. Each scene now has optional character and location/scene reference image uploads, saved in the existing `studio_assets` folder and referenced in project JSON. Uploaded images use the existing local reference and input-preparation endpoints.

**MiniMax H3 limitation:** Its I2V graph currently accepts one starting image. The scene/location reference takes precedence over the character reference, which takes precedence over last-frame carryover. When both are provided, the character image is retained for visual reference but **not** sent as a second image conditioning input. T2V automatically switches to I2V when an image is present. To continue from the preceding clip instead, remove the explicit scene references. Keep the `studio_assets` folder when upgrading or moving projects.


## v1.0.8 — Character continuity per scene

For Scene 2+, upload a **character reference**, enable **Use character continuity**, then click **Prepare / regenerate continuity frame**. The director extracts the previous rendered scene's last frame and uses Qwen Image Edit's two-image conditioning (image1=last frame, image2=portrait) to produce an identity-corrected starting frame. Preview it and render the scene. A separate **Discard prepared frame** action restores the original handoff workflow.

Requires Qwen Image Edit checkpoint, compatible encoder/VAE and ComfyUI's two-image Qwen editing node (`image2` input). Identity strength is prompt guidance, **not a numerical conditioning weight**. Qwen may change pixels beyond the face, so review joins carefully. The approved image is stored in `studio_assets`; back up that folder. No automatic character edits happen during video rendering.


## v1.0.9 hotfix — FFmpeg and I2V preflight
- AI upscale uses `-fps_mode passthrough` rather than legacy `-vsync 0`, with fallback for FFmpeg builds lacking that option.
- Image-to-video now normalises uploaded references and extracted last frames to the selected video size using ComfyUI `ImageScale` (Lanczos, centre crop).
- I2V preflight rejects width/height not divisible by 64 before GPU sampling. Recommended working test sizes: 960×512, 1024×576, 1280×704. Export exact 1280×720 after rendering/stitching if needed.
- The preflight reduces a known source of MiniMax `patchify_video` reshape errors; checkpoint-specific conditioning bugs may still require a further fix.
- Scene videos and projects are not modified by installing this patch. Back up the existing extension folder and project JSON first.


## v1.1.1 — 1024 × 576 and Real-ESRGAN Install & Verify

New projects start at 1024 × 576. Auto-select on 16 GB VRAM also uses 1024 × 576. Existing saved projects retain their resolution; select the 1024 × 576 preset to change them.

Open **AI Video Upscale** → **Verify Real-ESRGAN** or **Install / Repair Real-ESRGAN**. The installer downloads the official portable Windows ZIP from the Real-ESRGAN GitHub release, installs the executable and photorealistic/anime `.param` and `.bin` model pairs into `tools/`, and validates presence and nonzero file size. Download progress is displayed. The installation requires internet access; inference remains fully local.

Verification checks file existence and size, **not** SHA-256 authenticity or GPU execution. The installer does not install FFmpeg.


### v1.1.2 AI upscale reliability hotfix
- Real-ESRGAN runs in batches of eight frames, forced to NVIDIA Vulkan GPU 0 (`-g 0`).
- Each batch has a 180-second watchdog; retries at tile sizes 128, 64 and 32.
- Stdout/stderr are continuously drained to prevent subprocess pipe deadlocks.
- Upscale cache is stored under `output/unwin_ai_cache/<hash>` next to the source video, so a retry resumes completed frames.
- The AI upscale dialog has a Cancel Upscale button and an ETA based on completed batches.
- A job that was already running under an older version cannot be resumed in place; restart ComfyUI and start a new upscale.
- GPU index 0 must be the NVIDIA GPU; check Real-ESRGAN's device list if your device order differs.
- Cache may use substantial disk space; delete `unwin_ai_cache` folders when finished.