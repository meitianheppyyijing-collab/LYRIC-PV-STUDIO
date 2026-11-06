# User guide

## Preparing lyrics

Prepare an `.lrc` file containing timestamped lyric lines. Keep a backup of the source file before experimenting with a new project.

## Generating a lyric PV

1. Open a Blender project and install/enable LYRIC PV STUDIO.
2. Open the 3D View sidebar and locate the **Lyric PV** panel.
3. Use the panel's lyric import workflow to select the LRC file.
4. Review the generated lyric objects and animation in the scene and timeline.
5. Save a separate `.blend` project before making substantial adjustments.

## LRC spacing fix in v0.5.15

This version corrects the LRC EMPHASIS layout behavior where enlarging the first character could compress the following characters. The spacing calculation accounts for the enlarged character's actual width. Per-character objects and animation are retained. YRC per-character timing is not changed by this fix.

## Scope of this guide

Control names and available options may evolve between releases. Use the controls exposed by the installed add-on as the definitive reference for that source version. This guide intentionally does not describe unverified features or promise automatic camera/character handling beyond what the installed build exposes.
