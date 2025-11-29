Based on the CommonMark standards, here is the properly formatted raw Markdown source code.

**Instructions:**

1.  Hover over the top-right corner of the black box below.
2.  Click the **"Copy"** icon (📋).
3.  Paste it directly into your `README.md` file in VS Code.

<!-- end list -->

````markdown
# 🎵 MartinMuzicar - Discord Music Bot

A feature-rich, open-source Discord Music Bot built with **Python (discord.py)** and **yt-dlp**. It supports playing high-quality audio from YouTube, queue management, volume control, and looping.

## ✨ Features

- **Music Playback:** Play songs via URL or search terms.
- **Queue System:** Add multiple songs, shuffle, and view the queue.
- **Playback Control:** Pause, Resume, Skip, Stop, and seek functionality.
- **Looping:** Loop a single song or the entire queue.
- **Volume Control:** Owner-only volume adjustment.
- **Smart Help:** Interactive help menu (`.help`).
- **Clean Code:** Modular design using Cogs.

---

## 🚀 Prerequisites

Before running the bot, ensure you have the following installed:

1. **Python 3.8+**: [Download Python](https://www.python.org/downloads/)
   * *Note during installation: Check "Add Python to PATH"*
2. **FFmpeg**: Essential for audio processing. (See setup instructions below)
3. **Git**: [Download Git](https://git-scm.com/downloads) (Optional, for cloning)

---

## 🛠️ Installation Guide

### 1. Clone the Repository
Open your terminal (Command Prompt, PowerShell, or Terminal) and run:
```bash
git clone [https://github.com/Itzoqq/MartinMuzicar.git](https://github.com/Itzoqq/MartinMuzicar.git)
cd MartinMuzicar
````

*Alternatively, download the code as a ZIP file and extract it.*

### 2\. Set Up Virtual Environment (Recommended)

This keeps your project dependencies isolated.

  * **Windows:**
    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```
  * **Mac/Linux:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

### 3\. Install Dependencies

Install the required Python libraries using the provided `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4\. Configure Environment Variables

1.  Create a file named `.env` in the root folder (same folder as `bot.py`).
2.  Open it with a text editor (Notepad, VS Code).
3.  Add your Discord Bot Token inside:
    ```env
    DISCORD_BOT_TOKEN=your_actual_bot_token_here
    ```
    *(Do not use quotes around the token)*

-----

## 📼 FFmpeg Setup (Crucial\!)

The bot needs **FFmpeg** to stream audio. You have two options:

### Option A: System-Wide Installation (Recommended)

1.  Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).
2.  Extract the ZIP file.
3.  Copy the `bin` folder path (e.g., `C:\ffmpeg\bin`).
4.  Add this path to your **System Environment Variables** (Path).
5.  Restart your terminal and type `ffmpeg -version` to verify.

### Option B: Local Project Folder

1.  Create a folder named `ffmpeg` inside the `MartinMuzicar` directory.
2.  Place the `ffmpeg.exe` file directly into this folder (or inside `ffmpeg/bin/`).
      * *Structure: `MartinMuzicar/ffmpeg/bin/ffmpeg.exe` OR `MartinMuzicar/ffmpeg/ffmpeg.exe`*
3.  The bot is coded to automatically look for FFmpeg in these locations.

-----

## ▶️ Running the Bot

Once everything is set up, start the bot:

```bash
python bot.py
```

*(Use `python3 bot.py` on Mac/Linux)*

You should see logs indicating the bot has logged in and loaded the `Music` Cog.

-----

## 🎮 Usage

**Prefix:** `.` (dot)

### 🎵 Music Commands

| Command | Alias | Description |
| :--- | :--- | :--- |
| `.play <query>` | `.p` | Plays a song from YouTube (Link or Search). |
| `.skip` | `.s` | Skips the current song. |
| `.stop` | | Stops playback and clears the queue. |
| `.pause` | | Pauses the current song. |
| `.resume` | `.unpause` | Resumes playback. |
| `.queue` | `.q` | Displays the current queue. |
| `.remove <id/name>`| `.rm` | Removes a specific song from the queue. |
| `.shuffle` | `.mix` | Randomizes the current queue. |
| `.loop` | | Toggles looping for the entire queue. |
| `.loopsong` | | Toggles looping for the current song. |

### ⚙️ Utility Commands

| Command | Alias | Description |
| :--- | :--- | :--- |
| `.join` | `.connect` | Summons the bot to your voice channel. |
| `.leave` | `.dc` | Disconnects the bot. |
| `.help` | `.h` | Shows the help menu. |
| `.volume <0-100>` | `.vol` | **(Owner Only)** Sets the playback volume. |

-----

## 📝 Troubleshooting

  * **"FFmpeg was not found"**: Ensure you followed the FFmpeg setup step correctly. Try Option B if Option A fails.
  * **"Privileged Intent" Error**: Go to the [Discord Developer Portal](https://www.google.com/search?q=https://discord.com/developers/applications) \> Your Bot \> **Bot** Tab \> Enable **"Message Content Intent"**.
  * **"Opus Not Loaded"**: If on Linux, install `libopus` (`sudo apt install libopus0`). On Windows, `discord.py` usually handles this.

-----

## 📜 License

This project is open-source. Feel free to modify and distribute.

```
```