# Video Generation Commands

## Usage

```bash
python main.py --topic "<TOPIC>" [--category <CATEGORY>] [--engine semantic|legacy]
```

- `--topic` — The video topic (required)
- `--category` — Specialty prompt category (default: `auto`)
- `--engine` — Rendering engine (default: `semantic`)

## Available Categories

| Category | Best for |
|---|---|
| `networking` | TCP, DNS, BGP, routing, protocols |
| `data-structures` | Arrays, trees, linked lists, hash maps, binary search |
| `programming` | Recursion, Big-O, design patterns, language concepts |
| `cloud-architecture` | AWS VPC, serverless, multi-region, CDN |
| `system-design` | URL shortener, chat system, load balancer design |
| `business-analysis` | SWOT, requirements gathering, use case modeling |
| `databases` | Normalization, B-tree indexes, ACID, SQL queries |
| `security` | TLS handshake, OAuth2, firewall rules, encryption |
| `auto` | LLM auto-detects the best category (default) |

## Examples — Explicit Category

```bash
python main.py --topic "TCP Three-Way Handshake" --category networking
python main.py --topic "Binary Search" --category data-structures
python main.py --topic "AWS VPC Design" --category cloud-architecture
python main.py --topic "SWOT Analysis" --category business-analysis
python main.py --topic "Recursion in Python" --category programming
python main.py --topic "B-Tree Indexes" --category databases
python main.py --topic "TLS Handshake" --category security
python main.py --topic "URL Shortener Design" --category system-design
```

## Examples — Auto-Detect Category

```bash
python main.py --topic "How DNS Resolution Works"
python main.py --topic "Merge Sort Algorithm"
python main.py --topic "Kubernetes Pod Networking"
python main.py --topic "Database Normalization"
```

## Output

Each run creates a timestamped folder under `output/` containing:

- `script.json` — The generated semantic script
- `audio/` — Per-scene TTS narration files
- `video/` — Rendered video files
- `full_narration.mp3` — Combined audio track
- `final_video.mp4` — The finished video with audio
