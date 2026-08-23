# skin — the startup welcome-screen skin system

> Location: `main/80_interface/`. It holds the ASCII art and the skin configuration shown at startup.
> A skin is an **appearance component**, not a new layer — it has no acceptance logic of its own; it is
> configuration plus assets.

## Directory structure

```
main/80_interface/
  skin.yaml              ← the global configuration (the active pointer + the registry)
  README.md              ← this file
  SK001_default/         ← the default skin
    skin.yaml            ← the skin metadata (id / name / welcome line / art file / style)
    01_welcome.txt       ← the t2AG lettering the Skeleton install template uses by default
    02_inori.txt         ← an alternative character artwork
    03_inori_2.txt       ← the Inori character artwork currently selected by Main/Lite
    04_inori_3.txt       ← an alternative character artwork
```

## Configuration format

It uses a **flat YAML subset** (`key: value`), parsed by doctor with a regex, with zero dependencies (no
PyYAML needed).

### The global `main/80_interface/skin.yaml`

| Key | Meaning |
|---|---|
| `active` | the currently active skin ID |
| `registry.SKxxx` | the skin ID → folder name mapping |

### A skin's `SKxxx/skin.yaml`

| Key | Meaning |
|---|---|
| `id` | the skin ID (matching the folder-name prefix) |
| `name` | the skin's display name |
| `version` | the skin's version number |
| `welcome_msg` | the startup welcome line |
| `art_file` | the welcome-screen art filename (relative to this skin's directory) |
| `style` | a style description |

## Startup logic

`main/t2ag.md` "3.0 the startup welcome message" requires this to run once at first initialization and
once at every ordinary takeover:

1. Read `main/80_interface/skin.yaml` → get the `active` value
2. Look it up in the registry → get the active skin's folder name
3. Read `SKxxx/skin.yaml` → get `welcome_msg` and `art_file`
4. Print the welcome line + display the art file's content verbatim + the version number

Main/Lite currently display `03_inori_2.txt`; a first Skeleton install displays `01_welcome.txt`. This is
the approved release-role fork, and Main's chosen character artwork must never be overwritten by the
Skeleton's default identity artwork.

## Skin management

The creation, switching and validation flows are in `50_playbook/skin_playbook.md` (a core-playbook).
