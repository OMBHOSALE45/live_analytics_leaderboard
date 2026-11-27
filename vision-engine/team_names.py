"""Manual lobby team-name mapping keyed by Free Fire scoreboard slot color."""

import json
import os
import urllib.request
from typing import Dict, Tuple

SLOT_COLORS_12 = [
  "RED",
  "ORANGE",
  "YELLOW",
  "GREEN",
  "MINT GREEN",
  "CYAN",
  "BLUE",
  "PURPLE",
  "PINK",
  "BROWN",
  "GRAY",
  "WHITE",
]


def default_team_names_path(project_root: str) -> str:
  return os.path.join(project_root, 'config', 'team_names.json')


def _derive_tag(name: str) -> str:
  cleaned = name.strip().upper()
  if cleaned.startswith("TEAM "):
    cleaned = cleaned[5:].strip()
  words = [w for w in cleaned.replace('-', ' ').split() if w]
  if not words:
    return "TAG"
  if len(words) == 1:
    return words[0][:5]
  if len(words) >= 3:
    return "".join(w[0] for w in words[:4])
  return words[0][:4]


def load_team_names(config_path: str) -> Dict[str, Dict[str, str]]:
  if not config_path or not os.path.exists(config_path):
    return {}
  try:
    with open(config_path, 'r', encoding='utf-8') as f:
      raw = json.load(f)
    if not isinstance(raw, dict):
      return {}
    normalized: Dict[str, Dict[str, str]] = {}
    for k, v in raw.items():
      key = str(k).strip().upper()
      if isinstance(v, dict):
        name = str(v.get('name', '')).strip()
        if not name:
          continue
        tag = str(v.get('tag', '') or _derive_tag(name)).strip().upper()
        normalized[key] = {'name': name, 'tag': tag}
      elif isinstance(v, str) and v.strip():
        name = v.strip()
        normalized[key] = {'name': name, 'tag': _derive_tag(name)}
    return normalized
  except Exception:
    return {}


def save_team_names(mapping: Dict[str, Dict[str, str]], config_path: str):
  os.makedirs(os.path.dirname(config_path), exist_ok=True)
  with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(mapping, f, indent=2, ensure_ascii=False)


def resolve_team_identity(
  team_map: Dict[str, Dict[str, str]],
  color_name: str,
  stream_id: str = "default"
) -> Tuple[str, str]:
  """Returns (full_name, clan_tag) for a detected slot color."""
  col_key = (color_name or "GRAY").strip().upper()
  if stream_id and stream_id != "default":
    scoped = f"{stream_id.upper()}:{col_key}"
    if scoped in team_map:
      entry = team_map[scoped]
      return entry['name'], entry.get('tag') or _derive_tag(entry['name'])
  if col_key in team_map:
    entry = team_map[col_key]
    return entry['name'], entry.get('tag') or _derive_tag(entry['name'])
  return f"TEAM {col_key}", col_key[:5]


def push_team_names_to_server(mapping: Dict[str, Dict[str, str]], server_url: str):
  try:
    url = server_url.rstrip('/').replace('localhost', '127.0.0.1') + '/api/roster/colors'
    data = json.dumps({'teamNames': mapping}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=1.0):
      pass
  except Exception:
    pass


def prompt_lobby_team_names(config_path: str, server_url: str = "http://localhost:3001") -> Dict[str, Dict[str, str]]:
  """
  Interactive lobby prompt before starting Vision Engines:
  Lets the operator enter all 12 team names mapped by their slot color.
  Format: 'TEAM NAME' or 'TEAM NAME | TAG'. Press ENTER to keep existing/default.
  """
  existing = load_team_names(config_path)
  print("\n" + "=" * 72)
  print(" LOBBY SETUP: ENTER 12 TEAM NAMES BY SLOT COLOR")
  print(" Tip: Type 'TEAM NAME | TAG' (or just 'TEAM NAME'). Press ENTER to keep.")
  print("=" * 72)

  updated: Dict[str, Dict[str, str]] = dict(existing)
  for idx, color in enumerate(SLOT_COLORS_12, start=1):
    cur = existing.get(color)
    cur_label = f"{cur['name']} [{cur['tag']}]" if cur else f"TEAM {color}"
    try:
      raw = input(f"  {idx:2d}. [{color:10s}] (current: {cur_label}): ").strip()
    except EOFError:
      raw = ""
    if not raw:
      if cur:
        updated[color] = cur
      else:
        updated[color] = {'name': f"TEAM {color}", 'tag': color[:5]}
      continue
    if '|' in raw:
      name_part, tag_part = raw.split('|', 1)
      name = name_part.strip() or f"TEAM {color}"
      tag = tag_part.strip().upper()[:6] or _derive_tag(name)
    else:
      name = raw
      tag = _derive_tag(name)
    updated[color] = {'name': name, 'tag': tag}

  save_team_names(updated, config_path)
  push_team_names_to_server(updated, server_url)
  print(f"\n[Lobby Setup] Saved 12 team color mappings -> {config_path}\n", flush=True)
  return updated

