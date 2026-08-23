# The skin management flow (skin_playbook.md)

**Protection level**: core-playbook

> Placement: `50_playbook/`. It governs creating, switching, and validating T2AG skins.
> A skin is an appearance component, not a new layer — it has no acceptance logic of its own; it is configuration plus assets.
>
> **Triggers**: the user asks to change a skin / create a new skin / a skin-related doctor error.

---

## 1. Architecture overview

```
main/80_interface/
  skin.yaml              ← the global configuration (the active pointer + the registry)
  SK001_default/         ← a skin folder
    skin.yaml            ← the skin's metadata
    01_welcome.txt       ← the art asset
```

**Configuration format**: a flat YAML subset (`key: value`), parsed by doctor with a regex, zero
dependencies.
PyYAML is not used — a skin configuration tops out at a dozen or so keys, and bringing in a third-party
dependency is not worth it.

### Keys in the global skin.yaml

| Key | Meaning | Example |
|---|---|---|
| `active` | the currently active skin ID | `SK001` |
| `registry.SKxxx` | skin ID → folder name | `registry.SK001: SK001_default` |

### Keys in a skin's skin.yaml

| Key | Meaning | Example |
|---|---|---|
| `id` | the skin ID (matching the folder prefix) | `SK001` |
| `name` | the display name | `Default skin` |
| `version` | the version number | `1` |
| `welcome_msg` | the startup welcome line | `Welcome to ...` |
| `art_file` | the art filename | `01_welcome.txt` |
| `style` | a style description | `plain` |

---

## 2. Creating a new skin

### Step 1: ask about preferences

Ask the user in turn (wait for each answer before the next question):

1. **What is the skin called?** (for example "minimal", "anime", "academic")
2. **What style of welcome line do you want?** (one sentence, such as "formal", "relaxed", "high-energy")
3. **Do you have ASCII art already?** (if so, supply the file; if not, use the default or generate one)

### Step 2: generate the skin's content

- Generate the welcome line (`welcome_msg`) from the user's preferences
- If the user supplied ASCII art, save it as the art file; otherwise copy the default `01_welcome.txt` and modify it
- Settle the style description (`style`)

### Step 3: create the skin folder

1. Allocate a skin ID: look at the registry and take the largest number + 1 (for example `SK002`)
2. Create the folder: `main/80_interface/SKxxx_<name>/`
3. Write `main/80_interface/SKxxx_<name>/skin.yaml`:
   ```yaml
   id: SKxxx
   name: <the name the user chose>
   version: 1
   welcome_msg: <the generated welcome line>
   art_file: 01_welcome.txt
   style: <the style description>
   ```
4. Put the art file in place

### Step 4: register it

Append one line in `main/80_interface/skin.yaml`:
```yaml
registry.SKxxx: SKxxx_<name>
```

### Step 5: verify

Run `python -B main/70_tools/t2ag_doctor.py --profile runtime` and confirm the local skin is 0 FAIL;
cross-release skin consistency is left to `--profile release`.

---

## 3. Switching skins

1. Read `main/80_interface/skin.yaml` and confirm the target skin is in the registry
2. Change the `active:` line to the target skin ID
3. Run doctor to verify
4. Show the user the new skin's welcome line and art

---

## 4. Doctor validation rules

| Check | Level | Rule |
|---|---|---|
| the global configuration | FAIL | `main/80_interface/skin.yaml` exists and has `active` |
| active registration | FAIL | the skin ID `active` points at exists in the registry |
| the skin carrier | FAIL | the registry's target folder and its `skin.yaml` exist, with an ID matching the registry entry |
| the art file | FAIL | `art_file` is a filename inside the skin directory and the target really exists |
| an unregistered skin | WARN | a folder starting with `SK` exists under `main/80_interface/` but is not in the registry |
| the welcome-line boundary | WARN | `welcome_msg` contains a teaching-instruction word such as "must" / "rule" / "forbidden" |
| the default fork | FAIL | under SK001, Main/Lite use the Inori welcome art; the Skeleton uses the default t2AG ASCII art |

The approved fork affects only `art_file` in `SK001_default/skin.yaml`: Main and its Lite projection use
`03_inori_2.txt`, and the empty Skeleton template uses `01_welcome.txt`. `01_welcome.txt` must display
`t2AG` clearly and must no longer carry the old `t2ac` spelling; whichever art is chosen, the
`welcome_msg` from the same skin's metadata is displayed first. Main's personal choice must never be
overwritten in reverse by the Skeleton's default art.

---

## 5. Discipline

- **A skin must never carry teaching semantics**: a welcome line may have character, but it must not
  contain an instruction that affects teaching behaviour.
  This keeps an appearance file from becoming a second overlay backdoor.
- **The zero-dependency principle**: skin.yaml uses a flat `key: value` format and does not bring in
  PyYAML.
  Doctor parses it with a regex, preserving the "it still runs even if the venv is deleted" portability.
- **The art file has no enforced format**: ASCII art uses .txt, not an image. It stays plain text and
  readable in any editor.

---

## 6. Related files

- `main/80_interface/` — the skin directory
- `main/80_interface/skin.yaml` — the global configuration
- `main/80_interface/README.md` — notes on the skin directory
- `main/t2ag.md` — "3.0 the startup welcome message" owns the display timing and the authority chain for every startup
- `main/70_tools/t2ag_doctor.py` — the skin validation checks
- `main/50_playbook/first_run.md` — step 1 displays the welcome message
- `main/bin/t2ag` — the optional terminal projection; it reads the metadata dynamically and does not own a second copy of the text
