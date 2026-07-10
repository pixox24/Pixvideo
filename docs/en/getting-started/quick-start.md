# Quick Start

Already installed and configured? Let's create your first video!

---

## Start the React Workbench

### Windows All-in-One Package Users

If you're using the Windows All-in-One Package, simply:
1. Double-click `start.bat`
2. Open `http://localhost:8000` in your browser

### Install from Source Users

```bash
# Build the workbench, then start FastAPI
cd frontend && npm ci && npm run build && cd ..
uv run python api/app.py --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000` to load the workbench.

---

## Create Your First Video

### Step 1: Check Configuration

On first use, open the **System Settings** tab and confirm:

- **LLM Configuration**: Select an AI model (e.g., Qianwen, GPT) and enter API Key
- **Image Configuration**: Configure ComfyUI address or RunningHub API Key

If not yet configured, see the [Configuration Guide](configuration.md).

Click **Save System Settings** when done.

---

### Step 2: Enter a Topic

In the **Quick Create** tab:

1. Select「**AI Generate Content**」mode
2. Enter a topic in the text box, for example:
   ```
   Why develop a reading habit
   ```
3. (Optional) Set number of scenes, default is 5 frames

!!! tip "Topic Examples"
    - Why develop a reading habit
    - How to improve work efficiency
    - The importance of healthy eating
    - The meaning of travel

---

### Step 3: Configure Voice and Visuals

Continue in the **Quick Create** tab:

**Voice Settings**
- Select TTS workflow (default Edge-TTS works well)
- For voice cloning, upload a reference audio file

**Visual Settings**
- Select image generation workflow (default works well)
- Set image dimensions (default 1024x1024)
- Choose video template (recommend portrait 1080x1920)

---

### Step 4: Generate Video

Click **Generate Video** at the bottom of the **Quick Create** tab.

The system will show real-time progress:
- Generate script
- Generate images (for each scene)
- Synthesize voice
- Compose video

!!! info "Generation Time"
    Generating a 5-scene video takes about 2-5 minutes, depending on: LLM API response speed, image generation speed, TTS workflow type, and network conditions

---

### Step 5: Preview Video

Once complete, inspect the task status and preview from the workbench; use the **History** tab to manage, download, or resume generated videos.

You'll see:
- 📹 Video preview player
- ⏱️ Video duration
- 📦 File size
- 🎬 Number of scenes
- 📐 Video dimensions

The video file is saved in the `output/` folder.

---

## Next Steps

Congratulations! You've successfully created your first video 🎉

Next, you can:

- **Adjust Styles** - See the [Custom Visual Style](../tutorials/custom-style.md) tutorial
- **Clone Voices** - See the [Voice Cloning with Reference Audio](../tutorials/voice-cloning.md) tutorial
- **Use API** - See the [API Usage Guide](../user-guide/api.md)
- **Develop Templates** - See the [Template Development Guide](../user-guide/templates.md)
