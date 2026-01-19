# ReactionSync

ReactionSync is a Python-based desktop application designed for syncing two video files, typically a "Reaction" video and a "Source" (e.g., Anime) video. It provides a synchronized playback experience with offsets, dual volume controls, and an overlay (Picture-in-Picture) mode.

## Features

- **Dual Video Playback**: syncs a master "Reaction" video with a secondary "Source" video.
- **Synchronization Control**: Adjust the offset between the two videos to perfectly align the reaction.
- **Overlay Mode**: Toggle a draggable and resizable overlay of the secondary video on top of the main player.
- **Playback Controls**: Play, pause, and seek both videos simultaneously.
- **Volume Control**: Independent volume sliders for each video source.
- **Fullscreen Support**: Double-click to toggle fullscreen (supports standard and overlay modes).

## Prerequisites

- **Windows OS** (Tested on Windows).
- **Python 3.x** installed.
- **libmpv**: The application requires `mpv-2.dll` (or `mpv-1.dll`) to be present in the project folder.

## Installation & Setup

1.  **Clone the Repository**
    ```bash
    git clone <repository_url>
    cd ReactionSync
    ```

2.  **Install Python Dependencies**
    It is recommended to use a virtual environment.
    ```bash
    pip install -r requirements.txt
    ```

3.  **Download libmpv**
    - Go to [SourceForge - mpv-player-windows/libmpv](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/).
    - Download the latest `mpv-dev-x86_64-...` archive.
    - Extract the main DLL file (often named `libmpv-2.dll` or similar).
    - **Rename it** to `mpv-2.dll` (if it's not already).
    - Place the `mpv-2.dll` file into the `libs/` folder inside the `ReactionSync` root directory.

## Usage

1.  **Run the Application**
    ```bash
    python reaction_sync.py
    ```

2.  **Load Videos**
    - Click **"Load Reaction"** to open the main video (Controls/Timeline Master).
    - Click **"Load Anime"** to open the secondary video.

3.  **Sync**
    - Use the **"Anime Offset"** spinner to delay or advance the secondary video relative to the main one.
    - Use **"Play/Pause"** to check sync.

4.  **Overlay / PiP**
    - Click **"Toggle Overlay"** to switch the secondary video into a floating window on top of the main video.
    - Drag the overlay to move it.
    - Drag the edges/corners of the overlay to resize it.

5.  **Swap Views**
    - Click **"Swap View"** to switch which video is in the main container and which is in the secondary window/overlay.

## Troubleshooting

- **"Could not load libmpv"**: Ensure `mpv-2.dll` is in the same folder as the script.
- **Video not playing**: Ensure the file format is supported by mpv (most formats are).

## Disclaimer

> [!NOTE]
> This project was "vibe-coded" and written with the assistance of AI. While it is fully functional, the code structure and implementation details may reflect the iterative and assisted nature of its development. Use with this context in mind!
