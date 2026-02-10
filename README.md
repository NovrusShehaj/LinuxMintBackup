# LinuxMintBackup 🗄️🐧

A Python-based automation tool for creating **incremental, timestamped
backups** on Linux Mint using `rsync`.\
Designed to be **safe, configurable, and production-ready**, with
support for logging and optional systemd automation.

------------------------------------------------------------------------

## 📌 Features

-   ✅ Incremental backups using `rsync`
-   📁 Timestamped snapshot directories
-   🔗 `latest` symlink for easy restores
-   🧾 Configurable sources, exclusions, and destination
-   📝 Detailed logging
-   ⏱️ Optional automation via `systemd` timer
-   🛡️ Safe-by-design testing workflow (supports dry runs)

------------------------------------------------------------------------

## 📂 Project Structure

    LinuxMintBackup/
    ├── backup.py
    ├── config.json
    ├── logs/
    ├── .gitignore
    └── README.md

------------------------------------------------------------------------

## ⚙️ Requirements

-   Linux Mint (or any modern Linux distribution)
-   Python 3.8+
-   rsync

Install rsync if needed:

``` bash
sudo apt install rsync
```

------------------------------------------------------------------------

## 🔧 Configuration

Edit `config.json` to define what gets backed up:

``` json
{
  "sources": ["/home/youruser", "/etc"],
  "exclude": ["/home/youruser/.cache", "/home/youruser/.local/share/Trash"],
  "destination": "/mnt/backup/linux-mint",
  "log_file": "/home/youruser/LinuxMintBackup/logs/backup.log"
}
```

------------------------------------------------------------------------

## ▶️ Usage

``` bash
python3 backup.py
```

------------------------------------------------------------------------

## 🔐 Security Notes

-   Do **NOT** commit backup data to Git
-   Ensure `.gitignore` excludes backup destinations and logs

------------------------------------------------------------------------

## 🧑‍💻 Author

Novrus Shehaj\
GitHub: https://github.com/NovrusShehaj

------------------------------------------------------------------------

## 📜 License

MIT License
