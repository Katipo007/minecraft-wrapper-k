Build #97:
- Split plugin, command, and event code into separate respectively-named files/classes for cleaner code
- Fixed nobody being able to connect via proxy with oddly-formatted whitelist.json
- `/permissions groups [group] info` now shows usernames alongside UUID [surresttexas00/#145]
- `/permissions users [username] remove` sub-command added [surresttexas00/#148]
- Fixed `player.hasGroup` always returning None [issue #144]
- Fixed `/help` command showing two pages when only four items are listed [issue #141]
- Passing a list or tuple as the command name to api.registerCommand for easily registering multiple aliases for a command [issue #135]
- Commands are no longer case-sensitive [issue #135]
- Removed bolding on `/help` command groups [issue #121]
- Proxy config option `convert-player-files` is now False by default until fixed