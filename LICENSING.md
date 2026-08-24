# Licensing map / 许可证边界

T2AG ships under two licences plus one grant. This file says which is which.
若中英文有出入，以本文件的中文段为准。

| Layer | Licence | File |
|---|---|---|
| Code | Apache License 2.0 | [`LICENSE`](LICENSE) |
| Prose | CC BY-SA 4.0 | [`LICENSE-DOCS.md`](LICENSE-DOCS.md) |
| Invited trial distribution | Invited Use Grant | [`INVITED_USE_GRANT.md`](INVITED_USE_GRANT.md) |

## Which paths are code (Apache-2.0)

Both editions, `zh/` and `en/`:

- `main/70_tools/**` — every `.py`, `.json`, test and schema
- `main/*/bin/**` and any executable script anywhere in the tree
- `tools/**` and `.github/**` — public-release verification code and CI configuration
- `*.json` configuration and contract files wherever they sit

## Which paths are prose (CC BY-SA 4.0)

Both editions:

- `main/00_core/**` — the constitution, changelog, problemlog, patterns
- `main/50_playbook/**` — every playbook and protocol
- `main/10_student/`, `20_teacher/`, `30_group/`, `40_course/`, `80_interface/`
  — contracts, templates and guidance text
- `README.md`, `INSTALL.md`, `AGENTS.md`, `docs/**`, `t2ag_directory_guide.html`
- `*.template` files: prose, even when a tool consumes them — a template is
  text a person reads and edits, not a program

Where a single file mixes both (a `.py` carrying a long prose rationale in
comments, a `.md` carrying a runnable snippet), the licence of the **file's
primary form** governs the whole file. Extracting the minority part does not
change which licence came with it.

## Where the Invited Use Grant fits

`INVITED_USE_GRANT.md` governs the **release zips handed directly to invited
individuals** while this repository is private. It is a per-version grant with
a feedback obligation as consideration; it reserves all rights and does not
extend by forwarding.

The two open-source licences and the grant do not conflict, because they
attach to different copies:

- a copy someone received **as an invited zip** carries the grant;
- a copy someone obtained **from this repository once it is public** carries
  Apache-2.0 / CC BY-SA 4.0.

A grantee who later clones the public repository may rely on the open
licences for that clone. The grant is not thereby revoked; it simply stops
being the only thing on offer.

## 一个不可逆的事实（施工前请读）

**开源许可证一旦随公开仓发布，即对所有取得副本的人生效，且不可撤回。** 此后
改变主意只能影响*将来*的版本——已发布版本永远处于已授权状态，任何人可继续使用、
分发、修改那一份。

因此这两件事是分开的动作，且顺序不可颠倒地重要：

1. 把许可证文件**放进仓**——仓仍 private 时无第三方取得副本，尚无人被授权，可随时改；
2. 把仓**转为 public**——此刻起授权生效，不可逆。

本仓已进入第 2 步。原门0 裁决（2026-08-18）将转 public 时点定为门1 收（≤11-30）之后、
门2 之前；2026-08-22 授权人改判，提前转 public。前置 `skeleton_privacy` 已实测归零
（zh / en 两版 doctor 均 0 FAIL / 0 WARN）。自本仓转 public 之时起，上述两份开源许可证
对所有取得副本者生效；此前已交付的受邀 zip 仍按各自版本的授权书执行。

---

*Questions about licensing: t2ac@tutamail.com*
