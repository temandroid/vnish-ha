# vnish-ha

Home Assistant integration for ASIC miners running [Vnish firmware](https://anthill.farm).

## Features

- **Sensors:** hashrate (realtime / average / nominal), power consumption, power efficiency, PCB & chip temperatures (min/max), fan duty, HW errors %, miner state, restart count, active pool
- **Binary sensor:** mining (running/stopped)
- **Switch:** mining on/off
- **Buttons:** reboot, restart mining, pause mining, resume mining

## Requirements

- ASIC miner with Vnish (AnthillOS) firmware
- Home Assistant 2024.1+

## Installation

### HACS

1. HACS → Settings → Custom repositories
2. Add `temandroid/vnish-ha`, category `Integration`
3. Install and restart HA

### Manual

Copy `custom_components/vnish/` to `<HA config>/custom_components/`.

## Setup

1. Settings → Devices & Services → Add Integration → **Vnish Miner**
2. Enter the miner's local IP address
3. Optionally enter an API key (create one in the miner's web UI → API Keys)

## API

Uses the local REST API (`/api/v1`) provided by Vnish firmware. Auth via `x-api-key` header or anonymous (if the miner allows it).
