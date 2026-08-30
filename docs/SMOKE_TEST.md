# Hill175 server smoke test

Run against Minecraft Java Edition 26.2.

## Authentication

1. Join `135.181.78.188:25566` with a new offline nickname.
2. Confirm spawn in the glass authentication lobby.
3. Confirm the title and chat instructions say to sign in.
4. Run `/register <currentNickname> TestPassword123! TestPassword123!`.
5. Confirm a temporary browser link appears.
6. Confirm the development identity adapter approves after approximately one second.
7. Confirm teleport to the exhibition hub and receipt of the Competition Compass and Rules book.
8. Disconnect and reconnect with the same nickname.
9. Confirm building/chat are blocked until authentication.
10. Confirm `/login WrongPassword` fails.
11. Confirm `/login TestPassword123!` succeeds.
12. Check `plugins/Hill175/competition-data.yml`; confirm only salt/hash fields exist and the plaintext password is absent.
13. Check `logs/latest.log` and `journalctl -u hill175`; confirm the password arguments are absent because `spigot.yml -> commands.log` is false.

## Entries and GUI

1. Right-click the Compass.
2. Create Journey; confirm the creation screen before allocation.
3. Confirm teleport to a 64x64 grass plot in Creative Mode.
4. Leave the plot boundary; confirm automatic Spectator Mode.
5. Re-enter the owned plot; confirm Creative Mode returns.
6. Return to the hub and create Place; confirm the two-entry limit.
7. Try to create People as a third entry; confirm rejection.
8. Delete or switch one entry, then create People; confirm a private `hill_people_<entry>` world.
9. Open Visit Builds; confirm player-head entry cards and read-only visitor teleport.
10. Confirm all three category guides are Player entities (not armor stands), use distinct role-appropriate skins, have a floating category title plus `CLICK TO OPEN`, and do not remain listed in the player list.
11. Left-click and right-click each category guide; confirm each action opens exactly one category entry/creation GUI.
12. In an owned entry, confirm the hotbar contains Return to Hub, Camera, Rules, and Entry Controls, but no standalone Reset or Lock item.
13. Open Entry Controls; confirm Build Options contains submission lock/unlock, reset, delete, and category change, with confirmations for destructive actions.
14. Reset an entry, leave its region, and re-enter it; confirm the owner returns to Creative Mode and may build. Repeat once while another reset request is attempted and confirm the second request is rejected until the first completes.

## Teams

1. Join and authenticate a second nickname.
2. As the first nickname, stand in an owned entry and run `/team invite <secondNickname>`.
3. As the second nickname, run `/team accept <firstNickname>`.
4. Confirm both players may build in the entry.
5. Confirm a third member cannot join.
6. Confirm a participant cannot join more than two entries or two entries in the same category.

## Protection

1. As an owner, place and break normal blocks inside the plot.
2. As a visitor, attempt break/place/bucket/entity interaction; confirm cancellation.
3. Place water and lava inside the plot; confirm flow stops at the region boundary.
4. Place fire with flint and steel; confirm the fire stays but does not spread or burn blocks.
5. Place TNT; attempt flint, redstone, fire, projectile, and explosion ignition; confirm no detonation.
6. Place an end crystal; strike it normally; confirm no explosion. Sneak-punch it; confirm safe removal.
7. Try living-mob spawn eggs and dispensers; confirm living mobs are removed/blocked.
8. Place armor stands, paintings, item frames, boats, and minecarts; confirm they work inside the plot.
9. Move a boat/minecart toward the plot boundary; confirm it cannot leave.
10. Try a nether/end portal; confirm portal creation/use is canceled.
11. Try `/kill`, `/setblock`, `/summon`, `/give`, and `/minecraft:kill`; confirm player command execution is blocked.
12. Test pistons, saplings, mushrooms, vines, bamboo, fluids, and dispensers on the border; confirm no cross-plot changes.

## Camera and submission

1. Hold the Camera and right-click empty air at three positions inside the owned entry; confirm no ground click is required.
2. Confirm the fourth right-click replaces camera 1 and continues rotating through the three saved slots.
3. Run `/camera list`, then `/camera remove 2` and save a replacement.
4. Sneak, swim, or glide, then left-click the Camera; confirm preview canonicalizes the player to standing and begins at the exact saved eye viewpoint, yaw, and pitch without shifting vertically into a block. Confirm it displays `Previewing camera #…` as a title plus a persistent status bar.
5. While previewing, try walking, flying, sneaking, swimming, gliding, and rotating the view; confirm all position and camera changes are corrected immediately and camera markers are hidden.
6. Use the Exit Camera Preview item with a right-click, preview again, then use it with a left-click; confirm both return to the pre-preview position and restore the owner hotbar.
7. Left-click and right-click each visible camera marker; confirm both enter that marker's exact locked preview and show its camera number.
8. Run `/entry title <title>`.
9. Run `/entry description <description>`.
10. Open Entry Controls, choose Lock Submission, confirm the checklist appears, then choose Confirm Lock.
11. Confirm the entry changes to read-only Spectator Mode for both team members.
12. Confirm reset/delete/switch/title/description/camera/team changes are rejected while submitted.
13. Run `/entry unlock`; confirm Creative Mode/building returns.

## Persistence and restart

1. Stop the server normally.
2. Start it again.
3. Login with the same nickname/password.
4. Confirm both entries, team members, title, description, camera poses, submission state, plots, and private People worlds persist.
5. Confirm the checksum-pinned Hill exhibition hub and three Player category guides load without duplicates.
6. Confirm `/hub` arrives safely at `70.5, 66.1, 42.5`, facing south toward the category personnel.
7. Confirm Journey, Place, and People personnel stand at the block-centred anchors `70.5,67,70.5`, `70.5,75,70.5`, and `70.5,61,70.5`, respectively, and face the arrival point.
