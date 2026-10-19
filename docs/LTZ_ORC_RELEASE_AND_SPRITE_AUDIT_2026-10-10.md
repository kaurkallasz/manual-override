**Previous game orc releases and sprite audit**

Read-only audit prepared 10 October 2026. The 70 saved Photon Progress attempts are all practice attempts. Saved results contain total release counters and raw kill counts, but no per-type release counts; the 23,778-line Game event log also contains no `enemy_type` fields or per-enemy spawn events. Historical class totals therefore cannot be directly verified from logs.

For 51 non-interrupted attempts starting after the 13 September checkpoint, a reconstruction using the saved scaled wave counts and documented spawn sequence gives:

| Type | Reconstructed releases | Share |
| --- | ---: | ---: |
| Grunt / regular | 4,123 | 45.3% |
| Runner | 2,307 | 25.4% |
| Breaker | 2,595 | 28.5% |
| Large brute | 71 | 0.8% |
| Total | 9,096 | 100% |

These are **conditional reconstructed counts**, not directly measured class totals. They assume the recorded release counter corresponds to successful spawns, the checked-in wave roles remained in use, and enemies were released in their scheduled order. Saved settings and the recent wave-start events support that interpretation, but the database does not freeze the engine build or group enemy types, nor record per-type pressure-queue releases. A logged total alone cannot prove the ordering of delayed spawns. Do not backfill these inferred values into player records or treat them as definitive input for repricing old matches.

The sample excludes 13 interrupted attempts: their recovery receipts store `released_orcs=0` and zero duration, sometimes alongside hundreds of checkpointed kills. Those zeroes are placeholders, not evidence that no orcs spawned. It also excludes six earlier attempts on 5–8 September, around the documented change from all-brute authored groups to rare brutes; their exact runtime build is not recorded. The raw release counters across all 70 sum to 18,263, but this is not a reliable all-history total because of the interruption placeholders.

**Recent match reconstruction**

Times below are match starts in Europe/Tallinn. Counts mean released enemies, not kills.

| Start | Result | Grunts | Runners | Breakers | Brutes | Recorded releases |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 10 Oct 21:44 | Overrun | 224 | 141 | 167 | 7 | 539 |
| 10 Oct 20:52 | Center-stack win | 185 | 45 | 58 | 3 | 291 |
| 8 Oct 15:55 | Center-stack win | 252 | 115 | 134 | 7 | 508 |
| 6 Oct 14:53 | All-wave win | 495 | 234 | 263 | 17 | 1,009 |

For the 291-release match, saved wave counts are 32 + 45 + 58 + 71 + 85. The logged wave starts confirm waves 1–5 before the stack, so the reconstruction is 185 grunts, 45 runners, 58 breakers and 3 brutes. For the 539-release match, waves 1–7 account for 500 and the first 39 positions of wave 8 account for the rest. These two runs report 291 and 427 kills respectively; released enemies must not be confused with killed enemies or earned credits.

**Spawn rules**

The wave roles repeat grunt, runner, breaker, authored brute. The current engine replaces the authored brute group's ordinary slots with grunts. Starting at the configured first brute wave (4 in all 70 saved attempts), every 41st scheduled enemy becomes a brute: forty regular-sized enemies then one brute, resetting each wave. Breakers retain their authored role and appear primarily in waves 3, 7 and 11, with brute substitutions in the later waves. A breaker is one of the regular-sized roles; a brute is the enlarged enemy.

The wave file's September commit changes lane weights, not these authored roles/counts. The September 5 journal documents the rare-brute rule. Partial matches frequently end before later waves, which explains why brutes are less than 1% of this reconstructed sample even though eligible full waves insert one per 41 positions.

**Different sprites, different toughness**

| Type | Appearance in inspected first frame | Walk animation | Render size | Base health |
| --- | --- | --- | --- | ---: |
| Grunt | Armored orc with sword | Four distinct grunt files | Normal | 70 |
| Breaker | Orc with a large hammer | Four distinct breaker files | Same render size as grunt | 130 |
| Brute | Larger armored axe-bearing orc | Four distinct brute files | 2× linear render size in the saved settings | 960 |

Health values precede match multipliers. The grunt and breaker assets are both under `enemies-light-orcs-v2`, but have different image contents and filenames. The brute comes from `enemies-heavy-orcs-v2`. The renderer selects four-frame animations by `enemy_type`; it scales only brutes. If sprite loading fails, a fallback is used, so this verifies the asset mapping and pixels, not successful loading on every historical device.

The earlier approval plan's “Heavy breaker” label meant a tougher enemy, not a visually enlarged one. Use **Breaker** in the plan/UI to avoid confusing it with the large brute. The proposed 1/1/2/10 values remain candidates; no existing rewards or sprites have changed.

**Attempt ledger**

“Reconstructed” rows use the conditional method above. A dash means unknown or intentionally excluded; it never means zero. Full run IDs are included to make the audit reproducible against the local database.

| Start (Tallinn) | Run | Outcome | Saved release counter | Grunt | Runner | Breaker | Brute | Basis |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-09-05 18:00 | `7f7ee8d2b80d4b78bcb24a56feb6852d` | overrun | 2757 | — | — | — | — | Not reconstructed: early runtime transition |
| 2026-09-05 18:48 | `d34afd297b0649ceb1b7a8c89b550fc6` | overrun | 154 | — | — | — | — | Not reconstructed: early runtime transition |
| 2026-09-05 18:49 | `4aa2592ec18f43fcba8309e92129752d` | overrun | 259 | — | — | — | — | Not reconstructed: early runtime transition |
| 2026-09-05 19:22 | `fc819c794672410eb0e86ebf200ce5ba` | overrun | 166 | — | — | — | — | Not reconstructed: early runtime transition |
| 2026-09-05 22:41 | `d3c97c6800524921982538ecf15199ba` | won | 1410 | — | — | — | — | Not reconstructed: early runtime transition |
| 2026-09-08 10:38 | `79f61a884f654b3db38fb9bf2a88fce3` | overrun | 4421 | — | — | — | — | Not reconstructed: early runtime transition |
| 2026-09-15 20:08 | `7656f0f532024d0381d88c4fb781af29` | overrun | 141 | 118 | 23 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 20:09 | `95554ce227e3487e91b13e1dfb43f4aa` | overrun | 141 | 118 | 23 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 20:12 | `14597769736e4ae8b19c8ee0a3a94aa5` | overrun | 141 | 118 | 23 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 20:13 | `ad1805f18174422f961fc2d6ba7dd304` | aborted | 106 | 106 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 20:38 | `fa2016cc456d4e4b9b653ad415589513` | overrun | 141 | 118 | 23 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 20:41 | `9db83b10ed374791844c959fe0c6c36e` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-09-15 20:49 | `8d59147bec0e45f2b0fd05a394cb67c7` | aborted | 2 | 2 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 21:02 | `ef86637e298f4ecfa3f1f690f98b9d74` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-09-15 21:32 | `c2f70b72a77b4092afa5c8397808cfa8` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-09-15 21:56 | `a2ba261130d84bdaa27909cc61064366` | overrun | 140 | 118 | 22 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 22:25 | `8213733377ad4bdba69248d36f76a7f9` | aborted | 9 | 9 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 22:25 | `645342e565fc4857beb7ec0301cc9f67` | aborted | 32 | 32 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-09-15 22:58 | `d15a5e154a86420e8570f0fe5bc46dee` | overrun | 140 | 118 | 22 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-01 17:44 | `aa5634648a264a88af5017a2f3f0cf69` | overrun | 118 | 28 | 39 | 51 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-01 19:01 | `32a4b3a5401c40c295daeeb00da7d373` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-02 12:18 | `3508f5c98d7a4f9682741a7a347a095e` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 12:10 | `d883e19cce744aa19cabfc87a2797ac9` | aborted | 0 | 0 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 12:36 | `9a01aec0b587400a91fd26903ae83632` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 13:05 | `83a883cc08a44cab9102690d9f96f578` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 14:03 | `44fe205733034864932562c25465abd5` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 14:53 | `569a3cb12d524021a343596da32e49fa` | won | 1009 | 495 | 234 | 263 | 17 | Reconstructed prefix; not directly logged |
| 2026-10-06 15:34 | `6f05c2d8c98f4b3fbdc43b9c33b6f681` | won | 0 | 0 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 16:58 | `622588b9805649168839457b9184a6cc` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 17:14 | `e2916c26fb564d4e976c9b9339b9515b` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 19:34 | `755cf265a39e442a929c9b4333129437` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 19:53 | `a4dc3ef3816c48eba7c065afadcbffb7` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 20:05 | `153f6cacfd6a43bc9037dc76879fe64b` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 21:47 | `781ea46594a14c608a68f0c0be22dc5c` | aborted | 0 | 0 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 21:50 | `ed998516905f4323857f46e0d8d0e5ab` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-06 21:53 | `618c58b449934f92b6a2fd12ea624c2a` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-06 22:11 | `286d434ee47c4b29bfa08dda14e03b68` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-06 22:12 | `ffd65e9caf78402f8c9aac3e50c3fa76` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 22:22 | `539ec5313233407680724b57fd22c163` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-06 22:42 | `0af684cb47d74bc0b2409fb01c87cb3c` | overrun | 504 | 248 | 115 | 134 | 7 | Reconstructed prefix; not directly logged |
| 2026-10-06 23:04 | `59e39b6607554ea6ba38f45ec2e902e7` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-06 23:05 | `317788fac844481fa88994fa1f6bd6e0` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-06 23:35 | `28650e319cec47518bbbaa76bc9e837c` | overrun | 406 | 152 | 115 | 134 | 5 | Reconstructed prefix; not directly logged |
| 2026-10-07 00:00 | `a0fb6171bc0545ea93b6a0fc7c064059` | aborted | 0 | 0 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-07 00:00 | `4885f4879ec94477aa5f8338eeb6ac48` | aborted | 0 | 0 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-07 00:00 | `fd28c6d1077841f69162f0e5d30fddc1` | aborted | 0 | 0 | 0 | 0 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-07 00:04 | `a54c37596bc0474087af6d11f2ec6911` | overrun | 224 | 138 | 37 | 47 | 2 | Reconstructed prefix; not directly logged |
| 2026-10-07 00:17 | `09f16dddb8114f4ea65cde3fcf4980b8` | overrun | 404 | 150 | 115 | 134 | 5 | Reconstructed prefix; not directly logged |
| 2026-10-08 12:00 | `34ccd712b8234921b7d94adb33195d17` | overrun | 168 | 83 | 37 | 47 | 1 | Reconstructed prefix; not directly logged |
| 2026-10-08 12:12 | `9ca5de8461784ec3a3963887d86e463f` | overrun | 156 | 53 | 45 | 58 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-08 12:21 | `719b51045d3f41e0ba9bbf19c87754b6` | overrun | 500 | 185 | 141 | 167 | 7 | Reconstructed prefix; not directly logged |
| 2026-10-08 12:39 | `5a3ca596da7742e88250a81e27c11970` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-08 12:55 | `d4df5fad51a94baa815c7eba5dfa711a` | overrun | 263 | 150 | 64 | 47 | 2 | Reconstructed prefix; not directly logged |
| 2026-10-08 13:19 | `db84317eac70419abdeef9bfb455a420` | overrun | 404 | 150 | 115 | 134 | 5 | Reconstructed prefix; not directly logged |
| 2026-10-08 13:52 | `24749a467e2b4803ae0b3c5195257489` | overrun | 140 | 37 | 45 | 58 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-08 14:22 | `fc413f4b8e6c49aeae9c2a985d59ed4e` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-08 15:08 | `f708b53fe8a8442eb7ab21f49b57c175` | overrun | 248 | 150 | 49 | 47 | 2 | Reconstructed prefix; not directly logged |
| 2026-10-08 15:35 | `beca6b00f18d4f50ac761f91850e6ece` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-08 15:55 | `cb387ce9d09d456992227db2974e1957` | won | 508 | 252 | 115 | 134 | 7 | Reconstructed prefix; not directly logged |
| 2026-10-08 16:18 | `de7ab3de941d418e96018b75a86351bb` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-08 16:46 | `70ee160a6510428b9b328fd6c8a48c9e` | overrun | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-08 18:33 | `1913d31a3f544cbbb4199ed2dbd11dd6` | overrun | 141 | 57 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-08 18:59 | `8b1b39ae55894af9ad967cb7b33b3374` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-08 20:58 | `2c0e4eeb021548bc850b31e9bd5fd120` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-08 22:13 | `0efb2c400acd48f39c12b4d8abe9ea29` | aborted | 110 | 26 | 37 | 47 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-08 22:58 | `4853a5e9425746848ba9c4150135f46c` | overrun | 185 | 81 | 45 | 58 | 1 | Reconstructed prefix; not directly logged |
| 2026-10-08 23:42 | `7c8b80580dd74a5387f86dff15f152d0` | overrun | 135 | 32 | 45 | 58 | 0 | Reconstructed prefix; not directly logged |
| 2026-10-09 00:17 | `46c3d1f74f9745fdb57ef0a21b8f8ee8` | interrupted | 0 | — | — | — | — | Unknown: recovery placeholder |
| 2026-10-10 20:52 | `311f89b1a2584e2b9138d6de77a97fc9` | won | 291 | 185 | 45 | 58 | 3 | Reconstructed prefix; not directly logged |
| 2026-10-10 21:44 | `497554d8419d4039bdc5db2d15a5cd07` | overrun | 539 | 224 | 141 | 167 | 7 | Reconstructed prefix; not directly logged |

**Evidence**

- [Spawn implementation](../sandboxes/gamemaster/prototypes/photon-game/photon_game_runtime/engine.py): `REGULAR_ORCS_PER_BRUTE`, `_launch_wave`, `_wave_enemy_type`, `_spawn_due`, `_spawn_enemy`; base enemy stats are near the top of the file.
- [Authored wave roles](../sandboxes/gamemaster/prototypes/photon-level/assets/tiled/levels/z-pixel-first-map.waves.json).
- [Level-owned sprite mapping](../sandboxes/gamemaster/prototypes/photon-level/level_assets.py), [Y sprite selection and size](../sandboxes/gamemaster/prototypes/laser-tag-y/tower-defence-view.js).
- [Regular sprite](../sandboxes/gamemaster/prototypes/photon-level/assets/game-art/sprites/enemies-light-orcs-v2/grunt-walk-01.png), [breaker sprite](../sandboxes/gamemaster/prototypes/photon-level/assets/game-art/sprites/enemies-light-orcs-v2/breaker-walk-01.png), [brute sprite](../sandboxes/gamemaster/prototypes/photon-level/assets/game-art/sprites/enemies-heavy-orcs-v2/brute-walk-01.png).
- [Saved result delivery](../sandboxes/gamemaster/prototypes/photon-game/progress_link.py), [interruption recovery](../sandboxes/gamemaster/prototypes/photon-progress/store.py), [development journal](../DEVELOPMENT_JOURNAL.md).
- Sources read without importing application runtime: `photon-progress/data/progress.sqlite3` in a read-only transaction, `photon-game/data/runs.jsonl`, and Git history for the wave file. No gameplay, player data, live settings or hardware changes.

Future telemetry should persist per-type **scheduled, released and killed** counts, separate combat/purge deaths, and freeze the source/build/reward revisions. This removes the need to infer class mix for the planned weighted rewards.
