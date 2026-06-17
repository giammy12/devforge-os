```
  ██████╗ ███████╗██╗   ██╗███████╗ ██████╗ ██████╗  ██████╗ ███████╗
  ██╔══██╗██╔════╝██║   ██║██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
  ██║  ██║█████╗  ██║   ██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗
  ██║  ██║██╔══╝  ╚██╗ ██╔╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
  ██████╔╝███████╗ ╚████╔╝ ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
  ╚═════╝ ╚══════╝  ╚═══╝  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
                         ██████╗ ███████╗
                        ██╔═══██╗██╔════╝
                        ██║   ██║███████╗
                        ██║   ██║╚════██║
                        ╚██████╔╝███████║
                         ╚═════╝ ╚══════╝
```

<div align="center">

**The operating system built for developers, by developers.**

[![Build Status](https://github.com/devforge-os/devforge-os/actions/workflows/build-iso.yml/badge.svg)](https://github.com/devforge-os/devforge-os/actions)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Version](https://img.shields.io/badge/version-0.1.0--alpha-orange)](https://github.com/devforge-os/devforge-os/releases)
[![Debian](https://img.shields.io/badge/base-Debian%2012%20Bookworm-red)](https://www.debian.org/)
[![Wayland](https://img.shields.io/badge/display-Wayland-yellow)](https://wayland.freedesktop.org/)

[Features](#features) • [Install](#install) • [Profiles](#developer-profiles) • [Contributing](#contributing) • [Roadmap](#roadmap)

</div>

---

## What is DevForge OS?

DevForge OS is a Linux operating system based on **Debian 12 Bookworm**, designed from the ground up for software developers. It's not just another distro with some extra tools — it's a complete ecosystem where every component has been purpose-built for people who write code every day.

### What makes it unique

- **Smart Setup**: at installation, it asks who you are as a developer and configures everything automatically
- **Offline-first AI**: every AI feature runs on your hardware, in pure Python, with zero data sent outside
- **Proprietary IDE (ForgeIDE)**: not a modified VS Code — an editor built from scratch, deeply integrated with the OS
- **Coherent Ecosystem**: all apps communicate with each other, share data, and speak the same visual language
- **Absolute Privacy**: no telemetry, no mandatory cloud, everything local

---

## Features

| Feature | Description |
|---------|-------------|
| **ForgeIDE** | Electron-based IDE with Monaco Editor, integrated git, terminal, and AI |
| **ForgeAI** | Offline AI assistant (Mistral-7B + CodeLlama-7B) with ROCm acceleration |
| **ForgeNavigator** | Chromium browser with built-in ad blocker and AI summarizer |
| **ForgeSecurity** | Visual firewall, WireGuard VPN, KeePass-based password manager |
| **ForgeConnect** | Unified messaging hub (Telegram, Discord, WhatsApp, Email) |
| **ForgeMedia** | Music/video player with AI subtitles via whisper.cpp |
| **ForgeStore** | Marketplace for IDE plugins, themes, project templates |
| **ForgeCommunity** | Integrated developer community with forum and gamification |
| **14 Dev Profiles** | Pre-configured environments for every developer type |
| **Custom Desktop** | Wayland compositor with glassmorphism effects and profile themes |

---

## Developer Profiles

DevForge OS configures itself based on who you are:

| Profile | Tools |
|---------|-------|
| 🌐 Web Frontend | React, Vue, Angular, TypeScript, Vite, ESLint, Prettier |
| 🖥️ Web Backend | Node.js, Django, FastAPI, Spring, Go, PostgreSQL, Redis |
| 🔄 Web Fullstack | Everything above + Nginx, PM2, deploy tools |
| 🎮 Game Dev (Unity) | Unity Hub, .NET SDK, Blender, GIMP, Audacity |
| 🎮 Game Dev (Unreal) | Unreal Engine 5, C++, Clang, Blender |
| 🎮 Game Dev (Godot) | Godot 4, GDScript, Blender, Aseprite |
| 🤖 AI / ML | Python, PyTorch, TensorFlow, Jupyter, ROCm/CUDA |
| 📊 AI / Data Science | Python, R, pandas, Jupyter, dbt, SQL |
| 🔧 Embedded (Arduino) | Arduino IDE, PlatformIO, C/C++, minicom |
| 🔧 Embedded (Linux) | Cross-compiler, Buildroot, Yocto, QEMU |
| 🔒 Pentesting | Metasploit, Nmap, Wireshark, Burp Suite, Hashcat |
| 🔍 Malware Analysis | Ghidra, radare2, YARA, Volatility |
| ☁️ DevOps (Docker) | Docker, Kubernetes, Helm, Terraform, Ansible |
| ☁️ DevOps (Cloud) | AWS CLI, GCP SDK, Azure CLI, Pulumi, Prometheus |

---

## Install

### Test in a Virtual Machine (recommended first step)

**Requirements**: VirtualBox or QEMU, 8GB+ RAM, 40GB+ disk

```bash
# 1. Download the ISO (when available)
wget https://github.com/devforge-os/devforge-os/releases/download/v0.1.0-beta/devforge-os-0.1.0-amd64.iso

# 2. Verify checksum
sha256sum devforge-os-0.1.0-amd64.iso
# Compare with the SHA256 in the release page

# 3. In VirtualBox: New VM → Linux → Debian 64-bit
#    RAM: 4096MB minimum, 8192MB recommended
#    Disk: 40GB minimum
#    Boot from ISO, follow the graphical installer
```

### Build from source

```bash
# On Debian/Ubuntu — requires live-build
git clone https://github.com/devforge-os/devforge-os.git
cd devforge-os
sudo apt install live-build
sudo bash build/scripts/build-iso.sh
# The ISO will be in output/devforge-os-VERSION-amd64.iso
```

---

## Project Structure

```
devforge-os/
├── build/          # ISO build system (live-build config)
├── installer/      # GTK4 graphical installer
├── desktop/        # Wayland compositor + dock + topbar
├── forge-ide/      # Electron IDE (React + Monaco)
├── forge-ai/       # FastAPI AI server (Python)
├── forge-navigator/# Chromium-based browser
├── forge-security/ # Firewall + VPN + Vault
├── forge-connect/  # Unified messaging
├── forge-media/    # Media player suite
├── forge-store/    # Plugin marketplace
├── forge-community/# Community platform
└── assets/         # Fonts, icons, wallpapers, sounds
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

```bash
# Fork the repo, then:
git clone https://github.com/YOUR_USERNAME/devforge-os.git
cd devforge-os
# Set up dev environment
bash scripts/setup-dev-environment.sh
```

---

## Roadmap

```
[████████░░░░░░░░░░░░] Phase 1 — Base OS & Installer      ████ In Progress
[░░░░░░░░░░░░░░░░░░░░] Phase 2 — Desktop Environment      ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 3 — ForgeIDE Base            ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 4 — Native AI                ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 5 — ForgeNavigator           ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 6 — ForgeSecurity            ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 7 — Connect + Media          ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 8 — Store + Community        ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 9 — Public Beta              ░░░░ Planned
[░░░░░░░░░░░░░░░░░░░░] Phase 10 — Monetization            ░░░░ Planned
```

---

## License

DevForge OS is released under the **GNU General Public License v3.0**.
See [LICENSE](LICENSE) for full text.

---

<div align="center">
Built with passion for developers who love their tools.
</div>
