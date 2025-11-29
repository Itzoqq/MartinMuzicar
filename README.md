Here is a comprehensive, professionally formatted `README.md` file tailored specifically to the code you provided. It includes detailed instructions on setting up FFmpeg (which your code handles specifically) and a full command reference.

-----

# 🎵 MartinMuzicar Discord Bot

**MartinMuzicar** is a feature-rich, open-source Discord music bot built with [discord.py](https://discordpy.readthedocs.io/en/stable/) and [yt-dlp](https://github.com/yt-dlp/yt-dlp). It allows you to play high-quality audio from YouTube directly in your voice channels with a robust queuing system.

## ✨ Features

  * **Music Playback:** Stream music via YouTube links or direct search queries.
  * **Queue Management:** Add songs, view the queue, remove specific tracks, or clear everything.
  * **Looping:** Support for looping the entire queue or just the current song.
  * **Playback Control:** Pause, resume, skip, and stop commands.
  * **Shuffle:** Randomize your current music queue.
  * **Volume Control:** (Bot Owner Only) Adjust playback volume dynamically.
  * **Smart Error Handling:** Auto-reconnects to voice channels and handles playlist logic.

-----

## 🛠️ Prerequisites

Before you begin, ensure you have the following installed:

1.  **Python 3.8+**: [Download Python](https://www.python.org/downloads/)
2.  **Git**: [Download Git](https://git-scm.com/)
3.  **FFmpeg**: Essential for audio processing (See setup guide below).

-----

## 📥 Installation & Setup

### 1\. Clone the Repository

Open your terminal/command prompt and run:

```bash
git clone https://github.com/yourusername/MartinMuzicar.git
cd MartinMuzicar
```

### 2\. Set Up a Virtual Environment (Recommended)

It is best practice to run Python projects in a virtual environment.

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3\. Install Dependencies

Install the required Python packages listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 4\. FFmpeg Setup (Crucial)

This bot requires FFmpeg to process audio. You have two options:

#### **Option A: Project-Level Installation (Recommended)**

The bot is programmed to automatically look for a folder named `ffmpeg` inside the project directory.

1.  Go to the [FFmpeg Downloads Page](https://ffmpeg.org/download.html).
      * **Windows:** Go to [Gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and download the "release-essentials" `.zip` file.
2.  Extract the ZIP file.
3.  Create a folder named `ffmpeg` in your project root.
4.  Copy the contents of the extracted folder into your new `ffmpeg` folder.
      * *Ensure the `bin` folder containing `ffmpeg.exe` is inside.*
      * Structure should look like: `MartinMuzicar/ffmpeg/bin/ffmpeg.exe`

#### **Option B: System Path**

If you already have FFmpeg installed globally on your computer (added to your System PATH variables), the bot will automatically detect it.

### 5\. Environment Configuration

1.  Create a file named `.env` in the root directory.
2.  Add your Discord Bot Token inside the file:

<!-- end list -->

```env
DISCORD_BOT_TOKEN=your_token_here
```

> **Note:** You can get your token from the [Discord Developer Portal](https://www.google.com/search?q=https://discord.com/developers/applications).

-----

## 🚀 Running the Bot

Once everything is set up, run the bot using:

```bash
python bot.py
```

If successful, you will see logs in the console indicating the bot has logged in and cogs have loaded.

-----

## 🎮 Command Reference

The default prefix is **`.`** (dot).

### 🎶 Music Commands

| Command | Alias | Arguments | Description |
| :--- | :--- | :--- | :--- |
| **`.play`** | `.p` | `<url>` or `<search>` | Plays a song from a URL or searches YouTube. |
| **`.pause`** | | None | Pauses the current track. |
| **`.resume`** | `.unpause` | None | Resumes a paused track. |
| **`.skip`** | `.s` | None | Skips the current song. |
| **`.stop`** | | None | Stops playback and clears the queue. |
| **`.join`** | `.connect` | None | Summons the bot to your voice channel. |
| **`.leave`** | `.dc` | None | Disconnects the bot from the voice channel. |

### 📂 Queue & Management

| Command | Alias | Arguments | Description |
| :--- | :--- | :--- | :--- |
| **`.queue`** | `.q` | None | Displays the current list of songs. |
| **`.remove`** | `.rm` | `<index>` or `<name>` | Removes a specific song from the queue. |
| **`.shuffle`** | `.mix` | None | Randomizes the order of songs in the queue. |
| **`.loop`** | | None | Toggles looping for the **entire queue**. |
| **`.loopsong`**| | None | Toggles looping for the **current song**. |

### ⚙️ Utility & Admin

| Command | Alias | Arguments | Description |
| :--- | :--- | :--- | :--- |
| **`.help`** | `.h` | `[command]` | Shows the help menu or details for a command. |
| **`.volume`** | `.vol` | `<0-100>` | **Owner Only:** Sets the playback volume. |

-----

## 📁 Project Structure

```text
MartinMuzicar/
├── bot.py               # Main bot entry point
├── requirements.txt     # Python dependencies
├── .env                 # Token storage (Do not commit this!)
├── .gitignore           # Files to ignore (logs, venv, etc.)
├── cogs/                # Bot extensions (plugins)
│   ├── help.py          # Custom help command
│   └── music.py         # Main music logic
├── utils/
│   └── ytdl.py          # YouTube-DL and FFmpeg helper functions
└── ffmpeg/              # (Optional) Local FFmpeg binaries
```

## 🤝 Troubleshooting

  * **"FFmpeg not found":** Ensure you followed the FFmpeg setup step correctly. If you are using the local folder method, ensure `ffmpeg.exe` is located at `ffmpeg/bin/ffmpeg.exe` or `ffmpeg/ffmpeg.exe` relative to `bot.py`.
  * **"Opus not loaded":** On some Linux systems, you may need to install `libopus` (e.g., `sudo apt install libopus0`). `discord.py[voice]` usually handles this, but keep it in mind.
  * **"Download Error":** YouTube frequently changes their API. If music stops playing, try running `pip install --upgrade yt-dlp`.

-----

## 📜 License

This project is open-source. Feel free to modify and distribute it as needed.