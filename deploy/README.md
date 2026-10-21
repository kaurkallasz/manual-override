# MechArena private scoreboard

Deploy the contents of `score/` to `/home/kaurzz/mecharena.eu/score/` on DreamHost. The existing site remains unchanged. Requires PHP 8.1+ with PDO SQLite, Apache `.htaccess`, HTTPS, and outbound PHP mail. No external packages or build step.

`score/config.php` sets the canonical origin, administrator mailbox (`kaur@mecharena.eu`), sender, and session lifetime. It contains no passwords. The database is created at `/home/kaurzz/.mecharena-score/score.sqlite3`, outside the website. Back up that private directory separately. Do not upload a local test configuration or database.

## Install and pair a game

1. Restart the game hub after installing the Python changes, when the arena is idle. Existing paired installations keep their keys and need no new request.
2. In **Gamemaster → Photon Progress → Online scoreboard**, enter the installation name and operator contact email, then choose **Request pairing**.
3. The scoreboard automatically emails **kaur@mecharena.eu** a review link. The operator does not need to send a separate email. Contact details are self-reported, so confirm unfamiliar installations with their operator.
4. Kaur opens the review link, signs in with the administrator email using the normal one-time sign-in email, and chooses **Approve upload access** or **Reject request** in **Installation administration → Pairing requests**. Opening the notification itself grants no access. Sign-in links expire after 15 minutes; confirmed sessions last seven days.
5. Keep the game online. It checks approval every 30 seconds, saves its installation ID, and automatically uploads its queued profiles/results. Requests survive restarts and expire after seven days. Offline requests retry; failed administrator mail submission retries after five minutes. Email acceptance does not prove inbox delivery.
6. Each game has its own random upload-only key, saved before requesting approval in `photon-progress/data/scoreboard/installation.json` with owner-only permissions. Only its hash is stored online. No DreamHost credentials or player sign-in tokens are kept on the game.

**Cancel request** withdraws an outstanding request. If cancellation races with approval, cancellation revokes that newly approved key. A rejected/expired request can be replaced with a new request. The existing ten-minute one-time-code flow remains available under the operator panel’s manual pairing details; cancel any pending request before using it.

The administrator can revoke an installation on the website. Local **Disconnect** removes this computer’s key but does not revoke a copied key; use website revocation when retiring or replacing a computer. Back up the private installation file with the local database if moving an installation. Do not copy one installation’s key to multiple active games.

## Player behavior

Email is optional. A player or team can enter up to ten addresses separated by commas. Whitespace and duplicate addresses are normalized. Each recipient gets a separate private sign-in link and can view the same profile’s history. To add teammates to an existing profile, submit all previously registered addresses plus the new ones. Existing addresses cannot be replaced or removed in the game. Adding the first email also queues previously completed results; later teammates receive access to those existing results without duplicating them. The first registration for each mailbox sends a welcome sign-in link; the website issues a fresh one-time link whenever a registered player enters their email. Players with the same verified mailbox can see their own profiles across paired installations. Local end screens and visualizations work without internet access.

Every saved final level (win, overrun, operator-ended, or aborted) is uploaded when at least one participant has added email. Provisional interruption checkpoints stay local. The online result includes the combined kill heatmap and available robot movement replay. Replay starts at 50× and also supports 20× and 100×. Legacy results without recordings show their available statistics.

## Security and operations

- Per-installation bearer keys are random, hashed on the server, scoped to append-only profile/result uploads, and revocable. They cannot read player results or administer installations.
- Recipient delivery is tracked individually, so a failed email retries without resending successful welcomes. Legacy single-email profiles migrate automatically and retain their existing delivery flags.
- Result IDs are immutable and scoped by installation. Retries are idempotent. A lost pairing response can be retried with the same locally saved proof until the code expires.
- Browser access requires email ownership. Tokens and session IDs are stored hashed; cookies are Secure, HttpOnly, and SameSite. Admin mutations require a CSRF token and the correct Origin. Email links use fragments to keep tokens out of HTTP request logs.
- Email addresses stay out of public game snapshots, rosters, logs, and portable gameplay exports. They remain in the private local contacts/outbox tables and the private hosted database. Portable gameplay export is not a backup of email registrations or installation keys.
- Uploads are capped at 2 MB, 120 requests/hour and 1,000/day per installation. Login, pairing and email sends are rate limited. Hosted storage stops accepting uploads at 2 GB. Watch the queue in Photon Progress and back up the private database regularly.
- The sender uses DreamHost PHP mail with the existing hosted `kaur@mecharena.eu` mailbox. Server acceptance does not prove inbox delivery; test real delivery and check spam before the first event.
- A compromised paired game can fabricate results for its own installation. Pairing authenticates the source; it is not anti-cheat attestation. Revoke suspect installations.

## Checks

From the repository, run `PYTHONPATH=tests .venv/bin/python -m unittest test_scoreboard_upload test_level_results test_results_replay_heatmap test_player_continue` plus `test_scoreboard_pairing`, and `php tests/scoreboard_security.php` and `php tests/scoreboard_pairing_requests.php`. The website was also checked with HTTP integration tests for authentication, CSRF, upload-only restrictions, revocation, and single-use login, plus a phone browser preview using synthetic results.

## First-installation recovery through hosting access

If administrator email access blocks initial setup, the hosting owner can place `initial-pairing.json` inside the private data directory (not `/score`). It contains `code_hash` (SHA-256 of a newly generated uppercase 32-hex-character code without hyphens) and `expires` (a Unix timestamp no more than ten minutes ahead). Only a server with zero installations imports it; the normal single-use pairing rules still apply. The file cannot create a browser/admin session, replace an installation, or provision another key after pairing. Remove the setup file after use. Subsequent installations use the administrator-approved request flow or a one-time code.

Player status now distinguishes setup required, queued, retrying, and profile submitted for email delivery. Hosted mail acceptance, rejection and rate limiting are recorded in the private audit table using hashed recipient addresses. Acceptance is not proof of inbox delivery.
