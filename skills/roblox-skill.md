---
name: roblox-skill
description: Roblox Luau scripting: complete scripts with their Explorer location, server authority, RemoteEvents, DataStore with retries, leaderstats, GUI and tweens, with code.
---
# Roblox skill (Luau)

Deliver COMPLETE scripts, one file each. Start every file with a header comment: name, where it goes in Explorer (ServerScriptService, StarterPlayer > StarterPlayerScripts, StarterGui, ReplicatedStorage, Workspace) and its type (Script, LocalScript, ModuleScript). Also save each to the workspace (one folder per game) and finish with a list: where each script goes, which RemoteEvents must exist, how to test in Studio.

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
