---
name: roblox-skill
description: Roblox Luau scripting: complete scripts with their Explorer location, server authority, RemoteEvents, DataStore with retries, leaderstats, GUI and tweens, with code.
---
# Roblox skill (Luau)

Deliver COMPLETE scripts, one file each. Start every file with a header comment: name, where it goes in Explorer (ServerScriptService, StarterPlayer > StarterPlayerScripts, StarterGui, ReplicatedStorage, Workspace) and its type (Script, LocalScript, ModuleScript). Also save each to the workspace (one folder per game) and finish with a list: where each script goes, which RemoteEvents must exist, how to test in Studio.

## Quick rules (read first)
1. The server decides. Never trust a number, a name or a position that a client sends through a RemoteEvent; check it on the server.
2. Give complete scripts, one per file, and start each with a comment that names the file, where it goes and its type (Script, LocalScript or ModuleScript).
3. Use `task.wait()` and `task.spawn()`, not the old `wait()` and `spawn()`. Every loop that can run forever has a `task.wait()` inside.
4. DataStore calls go inside `pcall` with a retry, and the data is saved on `PlayerRemoving` and in `game:BindToClose`.
5. Disconnect events you no longer need, and clean up parts you create.

## Safety in this skill
- Do not write exploit, cheat or "executor" scripts, tools that steal accounts or `.ROBLOSECURITY` cookies, or backdoors (`require` of an unknown asset id, `loadstring` on remote text, hidden remotes).
- Do not design gambling-style or deceptive purchase mechanics aimed at children. Keep purchases clear and opt-in. Use only your own modules and trusted, inspected assets.

## Rules
- Modern APIs: `task.wait`, `task.spawn`, `task.delay` (not `wait/spawn`); `game:GetService("Players")`; `:WaitForChild`; set `Parent` last.
- **Server authority:** the client may only ask. The server validates everything (distance, cooldown, ownership, types) and applies the result. Never trust a number sent by a client.
- Put shared constants and pure logic in a ModuleScript in ReplicatedStorage.

## leaderstats (ServerScriptService/Leaderstats)
```lua
local Players = game:GetService("Players")
Players.PlayerAdded:Connect(function(player)
	local stats = Instance.new("Folder"); stats.Name = "leaderstats"; stats.Parent = player
	local coins = Instance.new("IntValue"); coins.Name = "Coins"; coins.Value = 0; coins.Parent = stats
end)
```

## DataStore with retries (ServerScriptService/SaveData)
```lua
local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local store = DataStoreService:GetDataStore("PlayerData_v1")

local function retry(fn, tries)
	for i = 1, tries do
		local ok, result = pcall(fn)
		if ok then return true, result end
		warn("DataStore attempt " .. i .. " failed: " .. tostring(result)); task.wait(2 ^ i)
	end
	return false
end

Players.PlayerAdded:Connect(function(player)
	local ok, data = retry(function() return store:GetAsync(tostring(player.UserId)) end, 3)
	local coins = player:WaitForChild("leaderstats"):WaitForChild("Coins")
	if ok and type(data) == "table" then coins.Value = tonumber(data.Coins) or 0 end
end)

local function save(player)
	local coins = player:FindFirstChild("leaderstats") and player.leaderstats:FindFirstChild("Coins")
	if coins then retry(function() store:SetAsync(tostring(player.UserId), { Coins = coins.Value }) end, 3) end
end
Players.PlayerRemoving:Connect(save)
game:BindToClose(function() for _, p in ipairs(Players:GetPlayers()) do save(p) end end)
```

## Validated RemoteEvent (server side)
```lua
-- ReplicatedStorage/BuyItem (RemoteEvent) must exist
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local remote = ReplicatedStorage:WaitForChild("BuyItem")
local PRICES = { Sword = 50, Shield = 30 }
local lastBuy = {}

remote.OnServerEvent:Connect(function(player, itemName)
	if typeof(itemName) ~= "string" or not PRICES[itemName] then return end         -- type + whitelist
	if (lastBuy[player] or 0) + 0.5 > os.clock() then return end                    -- cooldown
	lastBuy[player] = os.clock()
	local coins = player.leaderstats.Coins
	if coins.Value < PRICES[itemName] then return end                               -- server checks money
	coins.Value -= PRICES[itemName]
end)
```

## GUI built in code (StarterPlayerScripts, LocalScript)
```lua
local player = game:GetService("Players").LocalPlayer
local gui = Instance.new("ScreenGui"); gui.Name = "Hud"; gui.ResetOnSpawn = false; gui.Parent = player:WaitForChild("PlayerGui")
local label = Instance.new("TextLabel"); label.Size = UDim2.fromScale(0.3, 0.07); label.Position = UDim2.fromScale(0.35, 0.02)
label.BackgroundTransparency = 0.3; label.TextScaled = true; label.Text = "Coins: 0"; label.Parent = gui       -- Scale, not Offset: works on phones
local coins = player:WaitForChild("leaderstats"):WaitForChild("Coins")
coins:GetPropertyChangedSignal("Value"):Connect(function() label.Text = "Coins: " .. coins.Value end)
```

## Tween
```lua
local TweenService = game:GetService("TweenService")
local tween = TweenService:Create(part, TweenInfo.new(0.6, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), { Position = part.Position + Vector3.new(0, 5, 0) })
tween:Play()
```

## Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| `attempt to index nil` | Object not loaded yet | `WaitForChild` or `FindFirstChild` plus a nil check |
| Script does nothing | Wrong script type or location | LocalScripts only run under the player (StarterPlayerScripts, StarterGui) |
| Remote not firing | Event missing or fired from the wrong side | Create it in ReplicatedStorage; `FireServer` on the client, `OnServerEvent` on the server |
| DataStore error 403/ API disabled | Studio API access off | Game Settings > Security > Enable Studio Access to API Services |
| GUI gone after respawn | `ResetOnSpawn` true | Set it to false |

## Good and bad examples

### 1. Trusting the client
Bad: the client says how many coins it earned.
```lua
-- File: GiveCoins | Location: ServerScriptService | Type: Script
remote.OnServerEvent:Connect(function(player, amount)
	player.leaderstats.Coins.Value += amount   -- an exploiter sends 1e9
end)
```
Good: the server checks what is allowed.
```lua
-- File: CoinHandler | Location: ServerScriptService | Type: Script
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local remote = ReplicatedStorage:WaitForChild("CollectCoin")
local REACH = 15

remote.OnServerEvent:Connect(function(player, coin)
	if typeof(coin) ~= "Instance" or not coin:IsDescendantOf(workspace.Coins) then return end
	local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
	if not root or (root.Position - coin.Position).Magnitude > REACH then return end
	coin:Destroy()
	player.leaderstats.Coins.Value += 1
end)
```

### 2. Saving data
Bad: one `SetAsync` call with no error handling; a failed save loses progress.
Good:
```lua
-- File: SaveHelper | Location: ServerScriptService | Type: ModuleScript
local DataStoreService = game:GetService("DataStoreService")
local store = DataStoreService:GetDataStore("PlayerData")
local SaveHelper = {}

function SaveHelper.save(key, value)
	for attempt = 1, 3 do
		local ok, err = pcall(function() store:SetAsync(key, value) end)
		if ok then return true end
		warn("Save failed (attempt " .. attempt .. "): " .. tostring(err))
		task.wait(2 ^ attempt)
	end
	return false
end

return SaveHelper
```

### 3. Loops
Bad: `while true do spawnEnemy() end` freezes the game (no yield).
Good:
```lua
-- File: Spawner | Location: ServerScriptService | Type: Script
while true do
	task.wait(5)
	-- spawn one enemy here
end
```

### 4. Unknown code
Bad: `require(1234567890)` pulls code you have not read; this is a common backdoor.
Good: `require(script.Parent.MyModule)`, a module you wrote or inspected.

### 5. Client UI
Bad: a Script that tries to change a player's GUI directly.
Good: a LocalScript in `StarterPlayerScripts` (or `StarterGui`) builds and updates the GUI; it asks the server through a RemoteEvent when it needs something saved or paid for.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| `Infinite yield possible` warning | Use `WaitForChild` with a timeout, or check the exact name and parent |
| Script does not run | Check its type and location: a LocalScript in `ServerScriptService` never runs |
| Changes visible only to one player | The change was made in a LocalScript; make it on the server |
| `attempt to index nil` | Check that the character, humanoid or child exists before using it |
| Memory grows | Call `:Destroy()` on parts and `:Disconnect()` on connections |
| Players share one value by accident | Store values per player, in `leaderstats` or a table keyed by `UserId` |

## Checklist before you finish
- [ ] Every script is a complete file with a header comment: name, location, type.
- [ ] RemoteEvents validate everything on the server.
- [ ] DataStore calls use `pcall`, retry and save on exit.
- [ ] No `wait()`, no loop without a yield, no unknown `require`.
- [ ] Nothing is meant to cheat, steal or deceive.
